# wow-hd-icons

Extracts every icon from a local WoW install, upscales it 4× on the GPU, and writes game-ready BLP files that the
client loads as loose files from `Interface\Icons`.

## Pipeline

| Step | Script | What it does |
|---|---|---|
| 1 | `tools/extract.py` | Reads the game's local CASC storage directly (`tools/casc.py`), names files with the community listfile, writes `work/src/*.png` and `work/manifest.json`. |
| 2 | `tools/upscale.py` | 1× BCGone removes DXT block artifacts; 4x-UltraSharp and 4x NMKD-Siax both upscale; each result is shrunk back in linear light and scored against the original with alpha-weighted SSIM, the better one wins, and anything under `--min-ssim` falls back to bicubic. Alpha is upscaled separately with bicubic. Writes `work/up/*.png` and `work/scores.csv`. Resumable. |
| 3 | `tools/encode.py` | Lanczos mipmaps in linear light with premultiplied alpha, DXT1 for opaque icons and DXT5 only where there's real alpha (texconv), packed as BLP2. Writes `out/Interface/Icons/*.blp`. |
| 4 | `tools/install.py` | Copies into the game folder and records what it added; `--uninstall` removes exactly those. |
| 5 | `tools/pack.py` | Zips `out/Interface` with `INSTALL.md` into `dist/`. |

`tools/preview.py NAME ...` renders a side-by-side sheet (original, bicubic, both models, final).

Icons already 256 px or larger are left alone. Encrypted files (unreleased content) are skipped.

## Setup

```
python -m venv .venv
.venv\Scripts\python -m pip install spandrel numpy pillow safetensors
.venv\Scripts\python -m pip install --force-reinstall --no-deps torch torchvision --index-url https://download.pytorch.org/whl/cu128
```

Downloads (not in git): `work/community-listfile.csv` from
[wowdev/wow-listfile](https://github.com/wowdev/wow-listfile/releases), `bin/texconv.exe` from
[microsoft/DirectXTex](https://github.com/microsoft/DirectXTex/releases), and the models in `models/`
(`4x-UltraSharp`, `4x_NMKD-Siax_200k`, `1x_BCGone_Smooth`, see [OpenModelDB](https://openmodeldb.info)), converted to
`.safetensors` with `torch.load(..., weights_only=True)`.

## Run

```
python -I tools/extract.py --wow "G:\World of Warcraft" --product wow_classic_beta
.venv\Scripts\python -I tools/upscale.py --min-ssim 0.80
.venv\Scripts\python -I tools/encode.py
python -I tools/install.py --game "G:\World of Warcraft\_classic_beta_"
python -I tools/pack.py
```

The whole run takes about 10 minutes on an RTX 5090. Expect about 2 GB of BLPs.
