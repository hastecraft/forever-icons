"""README images: docs/logo.png (the HD Onyxia head buff icon) and docs/comparison.png (a before/after grid).

Originals are stretched with bicubic, the way the game shows a 64 px icon drawn bigger.
HD icons are decoded from the final BLPs in out/, so the images show exactly what ships.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BG, PANEL, TEXT, DIM = (17, 19, 24), (28, 31, 38), (236, 238, 242), (150, 156, 168)
LOGO = 'inv_misc_head_dragon_01'  # Rallying Cry of the Dragonslayer
GRID = ['spell_holy_flashheal', 'ability_warrior_charge', 'inv_misc_rune_01', 'spell_fire_fireball02',
        'spell_nature_lightning', 'inv_potion_54', 'spell_shadow_shadowbolt', 'spell_frost_frostbolt02',
        'spell_holy_powerwordshield', 'achievement_boss_ragnaros', 'ability_hunter_pet_wolf', 'inv_sword_04']


def font(size, bold=False):
    for name in (('segoeuib.ttf' if bold else 'segoeui.ttf'), 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def original(name, size):
    return Image.open(ROOT / 'work' / 'src' / f'{name}.png').convert('RGB').resize((size, size), Image.BICUBIC)


def hd(name, size):
    return Image.open(ROOT / 'out' / 'Interface' / 'Icons' / f'{name}.blp').convert('RGB').resize((size, size), Image.LANCZOS)


def logo(path):
    hd(LOGO, 256).save(path, optimize=True)


def grid(path, cols=3):
    tile, gap, pad, head = 168, 6, 24, 40
    pair = tile * 2 + gap
    rows = (len(GRID) + cols - 1) // cols
    w = pad * 2 + cols * pair + (cols - 1) * pad
    h = head + rows * (tile + pad) + pad // 2
    img = Image.new('RGB', (w, h), BG)
    d = ImageDraw.Draw(img)
    for c in range(cols):
        x = pad + c * (pair + pad)
        d.text((x, 10), 'Original', font=font(18, True), fill=DIM)
        d.text((x + tile + gap, 10), 'forever-icons', font=font(18, True), fill=TEXT)
    for i, name in enumerate(GRID):
        x = pad + (i % cols) * (pair + pad)
        y = head + (i // cols) * (tile + pad)
        img.paste(original(name, tile), (x, y))
        img.paste(hd(name, tile), (x + tile + gap, y))
    img.save(path, optimize=True)


def main():
    docs = ROOT / 'docs'
    docs.mkdir(exist_ok=True)
    logo(docs / 'logo.png')
    grid(docs / 'comparison.png')
    print(docs / 'logo.png', docs / 'comparison.png')


if __name__ == '__main__':
    main()
