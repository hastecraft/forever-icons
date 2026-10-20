"""Comparison sheet: original (pixel-doubled), bicubic, UltraSharp, Siax, and the pipeline's pick.

Usage: preview.py NAME [NAME ...] [--out file.png] [--up work/up]
"""
import argparse
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw
from spandrel import ModelLoader

import upscale as U

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('names', nargs='+')
    ap.add_argument('--out', default=str(ROOT / 'work' / 'preview.png'))
    ap.add_argument('--up', default=None, help='folder of final upscales to show as the last column')
    args = ap.parse_args()

    dev = torch.device('cuda')
    loader = ModelLoader(device=dev)
    models = {k: loader.load_from_file(ROOT / 'models' / f'{f}.safetensors').eval().half()
              for k, f in (('clean', '1x_BCGone_Smooth'), ('ultrasharp', '4x-UltraSharp'), ('siax', '4x_NMKD-Siax_200k'))}

    cols = ['original', 'bicubic', 'UltraSharp', 'Siax'] + (['final'] if args.up else [])
    tile, label = 256, 18
    sheet = Image.new('RGB', (tile * len(cols), (tile + label) * len(args.names)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for r, name in enumerate(args.names):
        src = Image.open(ROOT / 'work' / 'src' / f'{name}.png').convert('RGBA')
        x = torch.from_numpy(np.asarray(src)).to(dev).permute(2, 0, 1)[None].float() / 255
        rgb = x[:, :3]
        clean = U.run_model(models['clean'], rgb, True)
        size = (src.height * 4, src.width * 4)
        imgs = [
            src.convert('RGB').resize((tile, tile), Image.NEAREST),
            U.to_srgb(F.interpolate(U.to_linear(rgb), size=size, mode='bicubic', align_corners=False)),
            U.run_model(models['ultrasharp'], clean, True),
            U.run_model(models['siax'], clean, True),
        ]
        if args.up:
            imgs.append(Image.open(Path(args.up) / f'{name}.png').convert('RGB'))
        y = r * (tile + label)
        draw.text((4, y + 3), name, fill=(220, 220, 220))
        for c, im in enumerate(imgs):
            if torch.is_tensor(im):
                im = Image.fromarray((im[0].permute(1, 2, 0).clamp(0, 1) * 255 + 0.5).byte().cpu().numpy())
            sheet.paste(im.resize((tile, tile), Image.LANCZOS), (c * tile, y + label))
    for c, col in enumerate(cols):
        draw.text((c * tile + tile - 8 * len(col) - 4, 3), col, fill=(150, 200, 255))
    sheet.save(args.out)
    print(args.out)


if __name__ == '__main__':
    main()
