"""Install or remove the HD icons in a game folder.

  install.py                 copy out/Interface into the game's Interface folder
  install.py --uninstall     delete exactly the files a previous install added
  --game <folder>            the game folder holding Interface (default: WoW Forever)
  --src <folder>             the pack to install, e.g. out-frame8 for the black-frame pack

Most files go to Interface/Icons; the few extras (the key ring, see extract.EXTRAS) go to their own
folders. The list of installed files, relative to Interface, is kept in
<game>/Interface/Icons/.hd-icons-installed.txt.
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
    ap.add_argument('--src', default=str(ROOT / 'out'))
    args = ap.parse_args()

    src = Path(args.src)
    if src.name.lower() == 'icons':  # the old form, <pack>/Interface/Icons
        src = src.parent.parent
    src = src / 'Interface'
    game = Path(args.game)
    if not (game / 'Interface').is_dir():
        raise SystemExit(f'No Interface folder in {game}. Pass --game <folder holding Interface>.')
    interface = game / 'Interface'
    record = interface / 'Icons' / LIST_NAME
    # entries are relative to Interface; older installs recorded bare names in Icons
    ours = {e if '/' in e else f'Icons/{e}' for e in record.read_text().split('\n') if e} if record.exists() else set()

    if args.uninstall:
        removed = 0
        for rel in ours:
            p = interface / rel
            if p.exists():
                p.unlink()
                removed += 1
        record.unlink(missing_ok=True)
        print(f'removed {removed} files from {interface}')
        return

    if not src.is_dir():
        raise SystemExit(f'No Interface folder in {src.parent}. Run encode.py first or pass --src.')
    ours_low = {o.lower() for o in ours}
    copied, kept = 0, []
    for f in sorted(src.rglob('*.blp')):
        rel = f.relative_to(src).as_posix()
        target = interface / rel
        if target.exists() and rel.lower() not in ours_low:
            kept.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, target)
        if rel.lower() not in ours_low:
            ours.add(rel)
            ours_low.add(rel.lower())
        copied += 1
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text('\n'.join(sorted(ours)))
    print(f'installed {copied} files into {interface}')
    if kept:
        print(f'left {len(kept)} files that were already there untouched: {", ".join(kept[:5])}'
              + (' ...' if len(kept) > 5 else ''))
    print('Restart the game fully (not /reload) to see them.')


if __name__ == '__main__':
    main()
