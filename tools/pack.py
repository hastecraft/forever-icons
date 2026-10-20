"""Zip out/Interface plus the player install instructions into dist/."""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    build = json.loads((ROOT / 'work' / 'manifest.json').read_text())['build']
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    zpath = dist / f'wow-hd-icons-{build}.zip'
    files = sorted((ROOT / 'out' / 'Interface' / 'Icons').glob('*.blp'))
    # BLPs are already DXT-compressed, so storing them is nearly as small as deflating and much faster
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        z.write(ROOT / 'INSTALL.md', 'INSTALL.md')
        for p in files:
            z.write(p, f'Interface/Icons/{p.name}')
    print(f'{zpath} ({zpath.stat().st_size / 2**30:.2f} GB, {len(files)} icons)')


if __name__ == '__main__':
    main()
