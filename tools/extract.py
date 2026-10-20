"""Step 1: pull every interface/icons BLP out of the local game data as RGBA PNGs.

Writes work/src/<name>.png and work/manifest.json (FileDataID, game path, size and BLP format per icon).
"""
import argparse
import io
import json
import struct
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import casc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def decode(data, encoding, w, h):
    if encoding == 3:  # uncompressed BGRA, which Pillow doesn't read
        offset = struct.unpack_from('<I', data, 20)[0]
        return Image.frombuffer('RGBA', (w, h), data[offset:offset + w * h * 4], 'raw', 'BGRA', 0, 1).copy()
    return Image.open(io.BytesIO(data)).convert('RGBA')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--wow', default=r'G:\World of Warcraft')
    ap.add_argument('--product', default='wow_classic_beta')
    ap.add_argument('--listfile', default=str(ROOT / 'work' / 'community-listfile.csv'))
    ap.add_argument('--limit', type=int, default=0, help='only the first N icons (for trial runs)')
    args = ap.parse_args()

    storage = casc.Casc(args.wow, args.product)
    print(f'{storage.build_name}: {len(storage.root)} files')

    icons = []
    with open(args.listfile, encoding='utf-8') as f:
        for line in f:
            fdid, path = line.rstrip('\n').split(';', 1)
            low = path.lower()
            if low.startswith('interface/icons/') and low.endswith('.blp') and int(fdid) in storage.root:
                icons.append((int(fdid), path))
    icons.sort()
    if args.limit:
        icons = icons[:args.limit]

    src = ROOT / 'work' / 'src'
    src.mkdir(parents=True, exist_ok=True)
    manifest, skipped = [], {'encrypted': 0, 'missing': 0, 'bad': 0}
    for n, (fdid, path) in enumerate(icons, 1):
        if not storage.has_local(fdid):
            skipped['missing'] += 1
            continue
        try:
            data = storage.read_fdid(fdid)
        except casc.Encrypted:
            skipped['encrypted'] += 1
            continue
        if data[:4] != b'BLP2':
            skipped['bad'] += 1
            continue
        encoding, alpha_depth, alpha_type, mips = data[8:12]
        w, h = struct.unpack_from('<II', data, 12)
        name = Path(path).stem
        try:
            decode(data, encoding, w, h).save(src / f'{name}.png', compress_level=1)
        except Exception as e:  # noqa: BLE001
            print(f'  {path}: {e}')
            skipped['bad'] += 1
            continue
        manifest.append({'fdid': fdid, 'path': path, 'name': name, 'w': w, 'h': h,
                         'encoding': encoding, 'alpha_depth': alpha_depth,
                         'alpha_type': alpha_type, 'mips': mips})
        if n % 2000 == 0:
            print(f'  {n}/{len(icons)}')
    (ROOT / 'work' / 'manifest.json').write_text(json.dumps({'build': storage.build_name, 'icons': manifest}, indent=0))
    print(f'extracted {len(manifest)}, skipped {skipped}')


if __name__ == '__main__':
    main()
