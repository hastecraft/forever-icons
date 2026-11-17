"""Upscale icons that the game draws from a UI atlas instead of a file in Interface/Icons.

The key ring on the bag bar is the atlas UI-HUD-ActionBar-Keyring-Small: a cell of the action bar
atlas, which comes as a 1x file (512 px) and a 2x file (1024 px) for high UI scales. Both are
written out at 2048 px. Everything else on them (gryphons, slot frames) is resized in linear light
and looks as before; only the cells in CELLS go through the upscale models, so they match the icons
at 4x their 1x size. The game finds atlas cells by fraction of the texture, so a larger file lines
up without other changes.

Cells come from the UiTextureAtlasMember table (CommittedLeft, Right, Top, Bottom) of build
1.60.1.70959. After a patch, check them against the new build.

  atlas.py                     writes out/ and out-frame8/ (the same files for both packs)
  atlas.py --out out-custom    other pack folders
"""
import argparse
import struct
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from spandrel import ModelLoader

sys.path.insert(0, str(Path(__file__).parent))
import casc  # noqa: E402
from encode import _resize, linear_to_srgb, mip_chain, srgb_to_linear  # noqa: E402
from extract import decode  # noqa: E402
from upscale import _gauss, run_model, shrink, ssim  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SIZE = 2048

ATLASES = [
    # (game path, FileDataID, scale of the art in it, {cell name: (left, right, top, bottom)})
    ('Interface/HUD/UIActionBar2xC60.blp', 7948326, 2, {'keyring-small': (965, 1019, 83, 163)}),
    ('Interface/HUD/UIActionBarC60.blp', 7948328, 1, {'keyring-small': (67, 94, 374, 414)}),
]
SOURCE = 0  # cells are upscaled from the 2x atlas, which has the most detail


def resize_rgba(rgba, size):
    """Lanczos in linear light with premultiplied alpha, like encode.mip_chain."""
    a = rgba[..., 3].astype(np.float32) / 255
    lin = srgb_to_linear(rgba[..., :3].astype(np.float32) / 255) * a[..., None]
    la = np.clip(_resize(a, size), 0, 1)
    lc = np.stack([_resize(lin[..., c], size) for c in range(3)], -1) / np.maximum(la[..., None], 1e-4)
    return np.dstack([linear_to_srgb(lc) * 255 + 0.5, la * 255 + 0.5]).clip(0, 255).astype(np.uint8)


def load_models(dev):
    loader = ModelLoader(device=dev)
    models = {}
    for key, file in (('clean', '1x_BCGone_Smooth'), ('ultrasharp', '4x-UltraSharp'), ('siax', '4x_NMKD-Siax_200k')):
        m = loader.load_from_file(ROOT / 'models' / f'{file}.safetensors')
        m.eval()
        models[key] = m
    return models


def upscale_cell(rgba, models, dev):
    """Same steps as upscale.py for one image: clean, both 4x models, keep the closer one."""
    x = torch.from_numpy(rgba.copy()).to(dev).permute(2, 0, 1)[None].float() / 255
    rgb, alpha = x[:, :3], x[:, 3:]
    h, w = rgb.shape[-2:]
    clean = run_model(models['clean'], rgb, False)
    cands = {k: run_model(models[k], clean, False) for k in ('ultrasharp', 'siax')}
    kernel = _gauss(dev)
    scores = {k: ssim(shrink(v, (h, w)), rgb, alpha, kernel).item() for k, v in cands.items()}
    pick = max(scores, key=scores.get)
    up_alpha = F.interpolate(alpha, size=(h * 4, w * 4), mode='bicubic', align_corners=False).clamp(0, 1)
    img = torch.cat([cands[pick], up_alpha], 1)[0].permute(1, 2, 0)
    return (img * 255 + 0.5).clamp(0, 255).byte().cpu().numpy(), pick, scores


def write_blp_bgra(path, rgba):
    """Uncompressed BGRA like the game's own atlas files, plus mipmaps: the originals are drawn
    about 1:1 and need none, but a 4x file drawn at the same size would shimmer without them."""
    levels = [np.ascontiguousarray(l[..., [2, 1, 0, 3]]).tobytes() for l in mip_chain(rgba)][:16]
    h, w = rgba.shape[:2]
    offsets, sizes, pos = [], [], 148 + 1024
    for lv in levels:
        offsets.append(pos)
        sizes.append(len(lv))
        pos += len(lv)
    offsets += [0] * (16 - len(levels))
    sizes += [0] * (16 - len(levels))
    head = struct.pack('<4sIBBBBII16I16I', b'BLP2', 1, 3, 8, 8, 1, w, h, *offsets, *sizes)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(head + bytes(1024) + b''.join(levels))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wow', default=r'G:\World of Warcraft')
    ap.add_argument('--product', default='wowf')
    ap.add_argument('--out', nargs='*', default=[str(ROOT / 'out'), str(ROOT / 'out-frame8')])
    args = ap.parse_args()

    storage = casc.Casc(args.wow, args.product)
    print(storage.build_name)
    images = []
    for path, fdid, scale, cells in ATLASES:
        d = storage.read_fdid(fdid)
        enc = d[8]
        w, h = struct.unpack_from('<II', d, 12)
        images.append(np.array(decode(d, enc, w, h)))

    dev = torch.device('cuda')
    models = load_models(dev)
    src_path, _, src_scale, src_cells = ATLASES[SOURCE]
    hd = {}
    for name, (l, r, t, b) in src_cells.items():
        hd[name], pick, scores = upscale_cell(images[SOURCE][t:b, l:r], models, dev)
        print(f'{name}: {pick} {scores}')

    for (path, fdid, scale, cells), img in zip(ATLASES, images):
        f = SIZE // img.shape[1]
        out = resize_rgba(img, (SIZE, SIZE))
        for name, (l, r, t, b) in cells.items():
            out[t * f:b * f, l * f:r * f] = resize_rgba(hd[name], ((r - l) * f, (b - t) * f))
        for o in args.out:
            write_blp_bgra(Path(o) / path, out)
        print(f'{path}: {img.shape[1]} -> {SIZE} px, cells {list(cells)} at {4 // scale}x')


if __name__ == '__main__':
    main()
