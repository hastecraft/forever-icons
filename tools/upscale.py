"""Step 2: upscale the extracted icons on the GPU.

Per icon:
  1. 1x BCGone removes the DXT block artifacts from the color.
  2. Both 4x models upscale the cleaned color.
  3. Each result is shrunk back to the source size (in linear light) and scored against the
     original with alpha-weighted SSIM; the higher score wins. Below --min-ssim, the icon falls
     back to a plain bicubic upscale and is flagged in the report.
  4. Alpha is upscaled separately with bicubic so edges stay clean.
  5. Optionally (--rim) the outer rim is blended toward the bicubic upscale, since the painted
     dark border is where upscalers smear.
Writes work/up/<name>.png (RGBA) and work/scores.csv.
"""
import argparse
import csv
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from spandrel import ModelLoader

ROOT = Path(__file__).resolve().parent.parent
MAX_SIDE = 256
PAD = 8  # source pixels of reflection padding around each icon while it runs through a model


def to_linear(x):
    return torch.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def to_srgb(x):
    x = x.clamp(0, 1)
    return torch.where(x <= 0.0031308, x * 12.92, 1.055 * x.pow(1 / 2.4) - 0.055)


def shrink(x, size):
    """Resize down in linear light (area filter, exact for integer factors)."""
    return to_srgb(F.interpolate(to_linear(x), size=size, mode='area'))


def _gauss(device):
    g = torch.exp(-((torch.arange(11, device=device) - 5.0) ** 2) / (2 * 1.5 ** 2))
    g = g / g.sum()
    return (g[:, None] * g[None, :]).expand(3, 1, 11, 11).contiguous()


def ssim(a, b, weight, kernel):
    """Alpha-weighted mean SSIM per image; a, b: (B,3,H,W) in [0,1], weight: (B,1,H,W)."""
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    blur = lambda t: F.conv2d(F.pad(t, (5, 5, 5, 5), mode='reflect'), kernel, groups=3)  # noqa: E731
    mu_a, mu_b = blur(a), blur(b)
    var_a = blur(a * a) - mu_a ** 2
    var_b = blur(b * b) - mu_b ** 2
    cov = blur(a * b) - mu_a * mu_b
    s = ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / ((mu_a ** 2 + mu_b ** 2 + c1) * (var_a + var_b + c2))
    s = s.mean(1, keepdim=True)
    w = weight + 1e-6
    return (s * w).sum((1, 2, 3)) / w.sum((1, 2, 3))


def run_model(model, x, half):
    """x: (B,3,H,W) sRGB; reflection-padded so the icon's edges get real context."""
    xp = F.pad(x, (PAD, PAD, PAD, PAD), mode='reflect')
    with torch.inference_mode():
        y = model(xp.half() if half else xp).float()
    s = model.scale
    return y[:, :, PAD * s:y.shape[2] - PAD * s, PAD * s:y.shape[3] - PAD * s].clamp(0, 1)


def rim_mask(h, w, band, device):
    """1 at the outer edge fading to 0 over `band` pixels."""
    ys = torch.arange(h, device=device).float()
    xs = torch.arange(w, device=device).float()
    d = torch.minimum(torch.minimum(ys, h - 1 - ys)[:, None], torch.minimum(xs, w - 1 - xs)[None, :])
    return (1 - d / band).clamp(0, 1)[None, None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--batch', type=int, default=24)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--only', nargs='*', help='icon names to process (for previews)')
    ap.add_argument('--min-ssim', type=float, default=0.0)
    ap.add_argument('--rim', type=int, default=0, help='source pixels of rim blended toward bicubic (0 = off)')
    ap.add_argument('--out', default=str(ROOT / 'work' / 'up'))
    args = ap.parse_args()

    dev = torch.device('cuda')
    torch.backends.cudnn.benchmark = False  # benchmarking grabs big workspaces; the game may share the GPU
    loader = ModelLoader(device=dev)
    models = {}
    for key, file in (('clean', '1x_BCGone_Smooth'), ('ultrasharp', '4x-UltraSharp'), ('siax', '4x_NMKD-Siax_200k')):
        m = loader.load_from_file(ROOT / 'models' / f'{file}.safetensors')
        m.eval()
        if m.supports_half:
            m.half()
        models[key] = m
    half = all(m.supports_half for m in models.values())
    kernel = _gauss(dev)

    manifest = json.loads((ROOT / 'work' / 'manifest.json').read_text())['icons']
    todo = [i for i in manifest if max(i['w'], i['h']) < MAX_SIDE]
    if args.only:
        wanted = {n.lower() for n in args.only}
        todo = [i for i in todo if i['name'].lower() in wanted]
    if args.limit:
        todo = todo[:args.limit]
    groups = defaultdict(list)
    for i in todo:
        groups[(i['w'], i['h'])].append(i)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scores_path = ROOT / 'work' / ('scores_preview.csv' if args.only else 'scores.csv')
    done_names = set()
    if not args.only and scores_path.exists():  # resume: keep icons already upscaled and scored
        with open(scores_path, newline='') as f:
            done_names = {r['name'] for r in csv.DictReader(f) if (out / f"{r['name']}.png").exists()}
        groups = {k: [i for i in v if i['name'] not in done_names] for k, v in groups.items()}
    total = sum(len(v) for v in groups.values())
    print(f'{total} to upscale ({len(done_names)} already done)', flush=True)
    new_file = args.only or not done_names
    scores_file = open(scores_path, 'w' if new_file else 'a', newline='')
    writer = csv.writer(scores_file)
    if new_file:
        writer.writerow(('name', 'chosen', 'ssim_ultrasharp', 'ssim_siax'))

    def process(chunk, w, h, tw, th, scale):
        arr = np.stack([np.asarray(Image.open(ROOT / 'work' / 'src' / f"{i['name']}.png").convert('RGBA'))
                        for i in chunk])
        x = torch.from_numpy(arr.copy()).to(dev).permute(0, 3, 1, 2).float() / 255
        rgb, alpha = x[:, :3], x[:, 3:]

        clean = run_model(models['clean'], rgb, half)
        cands = {k: run_model(models[k], clean, half) for k in ('ultrasharp', 'siax')}
        if cands['ultrasharp'].shape[-1] != tw:
            cands = {k: shrink(v, (th, tw)) for k, v in cands.items()}
        scores = {k: ssim(shrink(v, (h, w)), rgb, alpha, kernel) for k, v in cands.items()}

        bicubic = to_srgb(F.interpolate(to_linear(clean), size=(th, tw), mode='bicubic', align_corners=False))
        pick = scores['siax'] > scores['ultrasharp']
        best = torch.where(pick[:, None, None, None], cands['siax'], cands['ultrasharp'])
        fallback = torch.maximum(scores['ultrasharp'], scores['siax']) < args.min_ssim
        best = torch.where(fallback[:, None, None, None], bicubic, best)
        if args.rim:
            m = rim_mask(th, tw, args.rim * scale, dev)
            best = best * (1 - m) + bicubic * m

        up_alpha = F.interpolate(alpha, size=(th, tw), mode='bicubic', align_corners=False).clamp(0, 1)
        img = torch.cat([best, up_alpha], 1)
        img = (img * 255 + 0.5).clamp(0, 255).byte().permute(0, 2, 3, 1).cpu().numpy()
        su, ss = scores['ultrasharp'].tolist(), scores['siax'].tolist()
        pick, fallback = pick.tolist(), fallback.tolist()
        rows = []
        for n, i in enumerate(chunk):
            Image.fromarray(img[n], 'RGBA').save(out / f"{i['name']}.png", compress_level=1)
            rows.append((i['name'], 'bicubic' if fallback[n] else ('siax' if pick[n] else 'ultrasharp'),
                         f'{su[n]:.4f}', f'{ss[n]:.4f}'))
        return rows

    def process_safe(chunk, *dims):
        try:
            return process(chunk, *dims)
        except (torch.OutOfMemoryError, torch.AcceleratorError) as e:
            if "out of memory" not in str(e):
                raise
            torch.cuda.empty_cache()
            if len(chunk) == 1:
                raise
            half_n = len(chunk) // 2
            print(f'  out of GPU memory, splitting a batch of {len(chunk)}', flush=True)
            return process_safe(chunk[:half_n], *dims) + process_safe(chunk[half_n:], *dims)

    picks = defaultdict(int)
    t0 = time.time()
    done = 0
    for (w, h), icons in groups.items():
        scale = min(4, MAX_SIDE // max(w, h))
        dims = (w, h, w * scale, h * scale, scale)
        for b in range(0, len(icons), args.batch):
            rows = process_safe(icons[b:b + args.batch], *dims)
            writer.writerows(rows)
            scores_file.flush()
            for r in rows:
                picks[r[1]] += 1
            done += len(rows)
            if done % (args.batch * 40) < args.batch:
                rate = done / (time.time() - t0)
                print(f'  {done}/{total}  {rate:.0f}/s  eta {(total - done) / rate / 60:.1f} min', flush=True)
    scores_file.close()
    print(f'upscaled {done} in {time.time() - t0:.0f}s: {dict(picks)}')

if __name__ == '__main__':
    main()
