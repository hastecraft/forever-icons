"""Zip an encoded pack plus the player install instructions into dist/.

  pack.py                                        out/ -> forever-icons-<build>.zip
  pack.py --src out-frame8 --name black-frame    out-frame8/ -> forever-icons-black-frame-<build>.zip
"""
import argparse
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=str(ROOT / 'out'), help='folder holding Interface/Icons')
    ap.add_argument('--name', default='', help='variant name added to the zip name')
    args = ap.parse_args()

    build = json.loads((ROOT / 'work' / 'manifest.json').read_text())['build']
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    zpath = dist / f"forever-icons-{args.name + '-' if args.name else ''}{build}.zip"
    files = sorted((Path(args.src) / 'Interface' / 'Icons').glob('*.blp'))
    # BLPs are already DXT-compressed, so storing them is nearly as small as deflating and much faster
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        z.write(ROOT / 'INSTALL.md', 'INSTALL.md')
        for p in files:
            z.write(p, f'Interface/Icons/{p.name}')
    print(f'{zpath} ({zpath.stat().st_size / 2**30:.2f} GB, {len(files)} icons)')


if __name__ == '__main__':
    main()
