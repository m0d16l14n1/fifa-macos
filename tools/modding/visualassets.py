#!/usr/bin/env python3
"""Ports current FC adboards, menu crests, crowd flags and banners to this game's formats.

  visualassets.py GAMEDIR MODDIR CSV_DIR [SOURCE_DIR]

SOURCE_DIR defaults to tools/modding/sources and contains the extracted ``adboards``, ``crests`` and
``fc-26-banners-flags`` packs. Only clubs present in CSV_DIR/teams.csv are emitted; competition/general
adboards (ids below 1,000,000) are also kept.

Newer adboards have the same vertical atlas at twice the game's resolution. Banners have the same 1024x512
layout. Crowd flags supply six rectangular and two square designs; the first four rectangular designs replace
the four 128x128 DXT1 textures in the game's flag RX3. RX3 models always come from this game (the club's own
when available, otherwise its generic template), so Frostbite meshes are never copied into the Xbox game.
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dds  # noqa: E402
import fbkits  # noqa: E402
import rx3  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def team_ids(csv_dir):
    with open(os.path.join(csv_dir, 'teams.csv'), newline='', encoding='utf-8-sig') as f:
        return {int(row['teamid']) for row in csv.DictReader(f)}


def pngs(root, pattern):
    out = {}
    if not os.path.isdir(root):
        return out
    regex = re.compile(pattern, re.I)
    for base, _, names in os.walk(root):
        for name in names:
            match = regex.match(name)
            if match:
                out[tuple(int(x) for x in match.groups())] = os.path.join(base, name)
    return out


def write_rx3(path, asset):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(bytes(asset.data))


def dxt(fmt):
    """RX3 texture format -> Pillow DDS format; None for a texture this converter doesn't write."""
    return {0: 'DXT1', 1: 'DXT3', 2: 'DXT5'}.get(fmt)


def convert_crests(source, mod, teams):
    # Use the pack's hand-authored small variants where present. Its 50px crest is the closest small UI design
    # to FIFA 19's 64px slot; both 256px slots use the full crest.
    specs = {
        'crest': ('crest', 256, 'dxt5'),
        'crest16x16': ('crest16x16', 16, 'argb'),
        'crest32x32': ('crest32x32', 32, 'argb'),
        'crest64x64': ('crest50x50', 64, 'argb'),
        'crest256x256': ('crest', 256, 'dxt5'),
    }
    made, clubs = 0, set()
    for target_folder, (source_folder, size, fmt) in specs.items():
        for sub in ('light', 'dark'):
            folder = os.path.join(source, 'crests', source_folder, sub)
            for (ident,), path in sorted(pngs(folder, r'l(\d+)\.png').items()):
                if ident not in teams:
                    continue
                w, h, rows = dds.read_png(path)
                target_sub = '' if sub == 'light' else 'dark'
                target = os.path.join(mod, 'data', 'ui', 'imgassets', target_folder, target_sub, f'l{ident}.dds')
                os.makedirs(os.path.dirname(target), exist_ok=True)
                # Keep the game's own layouts: its big light crest is DXT3, the dark one DXT5.
                target_fmt = 'dxt3' if (target_folder, sub, fmt) == ('crest256x256', 'light', 'dxt5') else fmt
                dds.write_dds(target, dds.resize(w, h, rows, size), size, target_fmt)
                made += 1
                clubs.add(ident)
    return made, clubs


def convert_adboards(source, game, mod, teams):
    from PIL import Image
    files = pngs(os.path.join(source, 'adboards'), r'adboard_(\d+)_color\.png')
    made = 0
    for (ident,), path in sorted(files.items()):
        if ident >= 1_000_000 and ident - 1_000_000 not in teams:
            continue
        rel = f'data/sceneassets/adboard/adboard_{ident}_0.rx3'
        base = game.file(rel) or game.file('data/sceneassets/adboard/adboard_0_0.rx3')
        if base is None:
            continue
        asset = rx3.Rx3(base)
        image = Image.open(path).convert('RGBA')
        textures = [t for t in asset.textures() if (t[2], t[3]) == (512, 1024) and dxt(t[1])]
        if not textures:
            continue
        for index, fmt, width, height, count in textures:
            asset.replace(index, fbkits.mips(image, width, height, count, dxt(fmt)))
        write_rx3(os.path.join(mod, rel), asset)
        made += 1
    return made


def convert_banners(source, game, mod, teams):
    from PIL import Image
    root = os.path.join(source, 'fc-26-banners-flags', 'Banner', 'textures')
    files = pngs(root, r'banner_(\d+)_color\.png')
    made = 0
    for (ident,), path in sorted(files.items()):
        if ident not in teams:
            continue
        rel = f'data/sceneassets/banner/banner_{ident}.rx3'
        base = game.file(rel) or game.file('data/sceneassets/banner/banner_1.rx3')
        if base is None:
            continue
        asset = rx3.Rx3(base)
        image = Image.open(path).convert('RGBA')
        for index, fmt, width, height, count in asset.textures():
            if not dxt(fmt):
                continue
            asset.replace(index, fbkits.mips(image, width, height, count, dxt(fmt)))
        write_rx3(os.path.join(mod, rel), asset)
        made += 1
    return made


def convert_flags(source, game, mod, teams):
    from PIL import Image, ImageOps
    root = os.path.join(source, 'fc-26-banners-flags', 'Flags', 'textures')
    files = pngs(root, r'flag_(\d+)_([0-5])_color\.png')
    by_club = {}
    for (ident, variant), path in files.items():
        if ident in teams and variant < 4:
            by_club.setdefault(ident, {})[variant] = path
    made = 0
    for ident, variants in sorted(by_club.items()):
        rel = f'data/sceneassets/flag/flag_{ident}.rx3'
        base = game.file(rel) or game.file('data/sceneassets/flag/flag_1.rx3')
        if base is None:
            continue
        asset = rx3.Rx3(base)
        textures = [t for t in asset.textures() if (t[2], t[3]) == (128, 128) and dxt(t[1])]
        for variant, (index, fmt, width, height, count) in enumerate(textures[:4]):
            if variant not in variants:
                continue
            # Modern flag textures are 2:1, whereas every legacy RX3 slot is square. Crop around the central
            # artwork instead of squeezing it horizontally (which would make crests visibly too narrow).
            image = ImageOps.fit(Image.open(variants[variant]).convert('RGBA'), (width, height),
                                 method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
            asset.replace(index, fbkits.mips(image, width, height, count, dxt(fmt)))
        write_rx3(os.path.join(mod, rel), asset)
        made += 1
    return made


def main(argv):
    if len(argv) not in (4, 5):
        print(__doc__, file=sys.stderr)
        return 2
    game_dir, mod, csv_dir = map(os.path.abspath, argv[1:4])
    source = os.path.abspath(argv[4]) if len(argv) == 5 else os.path.join(os.path.dirname(__file__), 'sources')
    teams = team_ids(csv_dir)
    game = fbkits.Game(game_dir, mod)
    crest_files, crest_clubs = convert_crests(source, mod, teams)
    adboards = convert_adboards(source, game, mod, teams)
    banners = convert_banners(source, game, mod, teams)
    flags = convert_flags(source, game, mod, teams)
    print(f'current visuals: {adboards} adboards, {len(crest_clubs)} clubs / {crest_files} crest DDS files, '
          f'{banners} banners, {flags} flags')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
