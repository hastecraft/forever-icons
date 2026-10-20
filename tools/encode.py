"""Step 3: turn the upscaled PNGs into game-ready BLP2 files.

Per icon:
  - Mipmaps down to 1x1, each made from the full-size image with Lanczos in linear light, with
    alpha premultiplied so transparent edges don't darken.
  - DXT1 when the icon is opaque (most of them, half the size), DXT1 with 1-bit alpha when the
    original had 1-bit alpha, DXT5 otherwise. Compression is texconv's (DirectXTex).
  - Written as BLP2 in the same layout the game's own icons use.
Output: out/Interface/Icons/<name>.blp
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
TEXCONV = ROOT / 'bin' / 'texconv.exe'
WORK = ROOT / 'work'
OPAQUE = 250


def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055)


def _resize(channel, size):
    return np.asarray(Image.fromarray(channel.astype(np.float32), 'F').resize(size, Image.LANCZOS))


def mip_chain(rgba):
    """All mip levels as uint8 RGBA arrays, each level filtered from the full-size image."""
    h, w = rgba.shape[:2]
    a = rgba[..., 3].astype(np.float32) / 255
    lin = srgb_to_linear(rgba[..., :3].astype(np.float32) / 255) * a[..., None]
    levels = [rgba]
    while w > 1 or h > 1:
        w, h = max(1, w // 2), max(1, h // 2)
        la = np.clip(_resize(a, (w, h)), 0, 1)
        lc = np.stack([_resize(lin[..., c], (w, h)) for c in range(3)], -1)
        lc = lc / np.maximum(la[..., None], 1e-4)
        rgb = linear_to_srgb(lc) * 255 + 0.5
        levels.append(np.dstack([rgb, la * 255 + 0.5]).clip(0, 255).astype(np.uint8))
    return levels


def write_dds(path, levels):
    h, w = levels[0].shape[:2]
    hdr = struct.pack('<4s7I44x', b'DDS ', 124, 0x1 | 0x2 | 0x4 | 0x8 | 0x1000 | 0x20000, h, w, w * 4, 0, len(levels))
    pf = struct.pack('<8I', 32, 0x41, 0, 32, 0xFF, 0xFF00, 0xFF0000, 0xFF000000)
    caps = struct.pack('<5I', 0x401008, 0, 0, 0, 0)
    with open(path, 'wb') as f:
        f.write(hdr + pf + caps + b''.join(np.ascontiguousarray(l).tobytes() for l in levels))


def choose_format(rgba, icon):
    """(texconv format, BLP alpha depth, BLP alpha type)."""
    a = rgba[..., 3]
    if a.min() >= OPAQUE:
        return 'BC1_UNORM', 0, 0
    if icon['alpha_depth'] == 1:
        return 'BC1_UNORM', 1, 0
    return 'BC3_UNORM', 8, 7


def prepare(icon):
    """Worker: mips + format choice, writes the uncompressed DDS. Returns (name, fmt, depth, type)."""
    rgba = np.array(Image.open(WORK / 'up' / f"{icon['name']}.png").convert('RGBA'))
    if icon['alpha_depth'] == 0:  # the game draws these opaque whatever the decoded alpha says
        rgba[..., 3] = 255
    fmt, depth, atype = choose_format(rgba, icon)
    write_dds(WORK / 'dds_in' / fmt / f"{icon['name']}.dds", mip_chain(rgba))
    return icon['name'], fmt, depth, atype


def dds_levels(path):
    d = Path(path).read_bytes()
    h, w, _pitch, _depth, count = struct.unpack_from('<5I', d, 12)
    fourcc = d[84:88]
    block = 8 if fourcc == b'DXT1' else 16
    pos, out = 128, []
    for _ in range(count):
        size = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block
        out.append(d[pos:pos + size])
        pos += size
        w, h = max(1, w // 2), max(1, h // 2)
    return out


def write_blp(path, w, h, levels, alpha_depth, alpha_type, mip_flags):
    offsets, sizes, pos = [], [], 148 + 1024
    for lv in levels:
        offsets.append(pos)
        sizes.append(len(lv))
        pos += len(lv)
    offsets += [0] * (16 - len(levels))
    sizes += [0] * (16 - len(levels))
    head = struct.pack('<4sIBBBBII16I16I', b'BLP2', 1, 2, alpha_depth, alpha_type, mip_flags, w, h, *offsets, *sizes)
    with open(path, 'wb') as f:
        f.write(head + bytes(1024) + b''.join(levels))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument('--out', default=str(ROOT / 'out'))
    args = ap.parse_args()

    manifest = json.loads((WORK / 'manifest.json').read_text())
    icons = [i for i in manifest['icons'] if (WORK / 'up' / f"{i['name']}.png").exists()]
    for d in ('dds_in', 'dds_out'):
        shutil.rmtree(WORK / d, ignore_errors=True)
        for fmt in ('BC1_UNORM', 'BC3_UNORM'):
            (WORK / d / fmt).mkdir(parents=True)

    print(f'mipmaps for {len(icons)} icons on {args.jobs} processes')
    with Pool(args.jobs) as pool:
        chosen = {name: (fmt, depth, atype) for name, fmt, depth, atype in pool.imap_unordered(prepare, icons, chunksize=32)}

    for fmt in ('BC1_UNORM', 'BC3_UNORM'):
        files = sorted((WORK / 'dds_in' / fmt).glob('*.dds'))
        if not files:
            continue
        flist = WORK / 'dds_in' / f'{fmt}.txt'
        flist.write_text('\n'.join(str(p) for p in files))
        print(f'compressing {len(files)} as {fmt}')
        subprocess.run([str(TEXCONV), '-nologo', '-y', '-f', fmt, '-o', str(WORK / 'dds_out' / fmt), '-flist', str(flist)],
                       check=True, stdout=subprocess.DEVNULL)

    dest = Path(args.out) / 'Interface' / 'Icons'
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    counts = {}
    for icon in icons:
        fmt, depth, atype = chosen[icon['name']]
        levels = dds_levels(WORK / 'dds_out' / fmt / f"{icon['name']}.dds")
        w = icon['w'] * min(4, 256 // max(icon['w'], icon['h']))
        h = icon['h'] * min(4, 256 // max(icon['w'], icon['h']))
        write_blp(dest / f"{icon['name']}.blp", w, h, levels, depth, atype, icon['mips'] | 1)
        key = 'DXT5' if fmt == 'BC3_UNORM' else ('DXT1 1-bit alpha' if depth else 'DXT1')
        counts[key] = counts.get(key, 0) + 1
    total = sum(p.stat().st_size for p in dest.glob('*.blp'))
    print(f'wrote {len(icons)} BLPs ({total / 2**30:.2f} GB): {counts}')


if __name__ == '__main__':
    main()
