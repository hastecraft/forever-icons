"""Install or remove the HD icons in a game folder.

  install.py                 copy out/Interface/Icons into the game's Interface/Icons
  install.py --uninstall     delete exactly the files a previous install added
  --game <folder>            the game folder holding Interface (default: WoW Forever)
  --src <folder>             the icons to install, e.g. out-frame8/Interface/Icons for the black-frame pack

The list of installed files is kept in <game>/Interface/Icons/.hd-icons-installed.txt.
Files that were already there before the first install are never overwritten or deleted.
"""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GAME = r'G:\World of Warcraft\_forever_'
LIST_NAME = '.hd-icons-installed.txt'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default=DEFAULT_GAME)
    ap.add_argument('--uninstall', action='store_true')
    ap.add_argument('--src', default=str(ROOT / 'out' / 'Interface' / 'Icons'))
    args = ap.parse_args()

    game = Path(args.game)
    if not (game / 'Interface').is_dir():
        raise SystemExit(f'No Interface folder in {game}. Pass --game <folder holding Interface>.')
    dest = game / 'Interface' / 'Icons'
    record = dest / LIST_NAME
    ours = set(record.read_text().split('\n')) - {''} if record.exists() else set()

    if args.uninstall:
        removed = 0
        for name in ours:
            p = dest / name
            if p.exists():
                p.unlink()
                removed += 1
        record.unlink(missing_ok=True)
        print(f'removed {removed} icons from {dest}')
        return

    dest.mkdir(parents=True, exist_ok=True)
    existing = {p.name.lower() for p in dest.glob('*.blp')} - {n.lower() for n in ours}
    copied, kept = 0, []
    for src in sorted(Path(args.src).glob('*.blp')):
        if src.name.lower() in existing:
            kept.append(src.name)
            continue
        shutil.copyfile(src, dest / src.name)
        ours.add(src.name)
        copied += 1
    record.write_text('\n'.join(sorted(ours)))
    print(f'installed {copied} icons into {dest}')
    if kept:
        print(f'left {len(kept)} files that were already there untouched: {", ".join(kept[:5])}'
              + (' ...' if len(kept) > 5 else ''))
    print('Restart the game fully (not /reload) to see them.')


if __name__ == '__main__':
    main()
