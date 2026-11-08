#!/usr/bin/env python3
"""Assets for the new teams a league build made (league.py's league.json): kits and crests, as loose files.

  teamassets.py LEAGUE.json GAMEDIR MODDIR [LOGODIR]

- Kits: the kit models (sceneassets/kit0..2, kit) and the menus' kit pictures (ui/imgassets/kits*) of the team's
  kit donor (a club whose home colours are nearest, chosen by league.py), under the new team's id.
- The league's logo (LEAGUE.json's league_logos: light and dark) in the menus' league sizes (league,
  league512x128, leaguelogos_sm, leaguelogos_tiny).
- Crests: the club's logo (LEAGUE.json's logo URL, fetched once into LOGODIR) as the menus' crests in every size
  the game has (crest, crest16x16 ... crest256x256, and their dark versions); or, for a team with crest_from (the
  Legends: pcsquads.py's legends.json), that club's own crests, crowd flags and banners.
- A league logo given as text (league_logos: {"text": [lines]}) is drawn (Pillow).
- Players copied to a new id (legends.json's player_copies: new id -> the game's) get his head, face and hair.
Entries are unpacked (out/tools/unchunk) so the game reads them as plain files.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dds  # noqa: E402
import modgame  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
UNCHUNK = os.path.join(ROOT, 'out', 'tools', 'unchunk')
LEAGUE_SIZES = {'league': (256, 256), 'league512x128': (512, 128), 'leaguelogos_sm': (256, 256),
                'leaguelogos_tiny': (256, 64)}
CREST_SIZES = {'crest': (256, 'dxt3'), 'crest16x16': (16, 'argb'), 'crest32x32': (32, 'argb'),
               'crest64x64': (64, 'dxt5'), 'crest256x256': (256, 'dxt5')}


def index(game):
    """{entry name: (archive, offset, size)} over the game's archives."""
    out = {}
    for name in sorted(os.listdir(game)):
        if name.lower().endswith('.big'):
            for entry, offset, size in modgame.read_big(os.path.join(game, name)):
                out.setdefault(entry.lower(), (os.path.join(game, name), offset, size))
    return out


def drawn_logo(lines, color):
    """(w, h, rows) of a logo of text lines (dds.read_png's form), drawn with Pillow."""
    from PIL import Image, ImageDraw, ImageFont
    size = 512
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = None
    for path in ('/System/Library/Fonts/Supplemental/Impact.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
                 '/System/Library/Fonts/Helvetica.ttc'):
        if os.path.exists(path):
            font = path
            break
    heights = [0.34, 0.2][:len(lines)] + [0.2] * max(0, len(lines) - 2)
    y = size * (1 - sum(heights) - 0.06 * (len(lines) - 1)) / 2
    for text, share in zip(lines, heights):
        f = ImageFont.truetype(font, int(size * share)) if font else ImageFont.load_default()
        while f and font and d.textlength(text, font=f) > size * 0.94:
            f = ImageFont.truetype(font, int(f.size * 0.92))
        w = d.textlength(text, font=f)
        d.text(((size - w) / 2, y), text, font=f, fill=color + (255,))
        y += size * (share + 0.06)
    gold = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(gold).rectangle([size * 0.08, y - size * 0.03, size * 0.92, y - size * 0.015],
                                   fill=(201, 162, 39, 255))
    img = Image.alpha_composite(img, gold)
    raw = img.tobytes()
    return size, size, [bytearray(raw[r * size * 4:(r + 1) * size * 4]) for r in range(size)]


def copy_entry(where, target):
    archive, offset, size = where
    os.makedirs(os.path.dirname(target), exist_ok=True)
    stored = target + '.stored'
    with open(archive, 'rb') as f:
        f.seek(offset)
        open(stored, 'wb').write(f.read(size))
    subprocess.run([UNCHUNK, stored, target], check=True, stdout=subprocess.DEVNULL)
    os.unlink(stored)


def main(argv):
    if len(argv) < 4:
        print(__doc__, file=sys.stderr)
        return 2
    league, game, mod = json.load(open(argv[1])), argv[2], argv[3]
    logos = argv[4] if len(argv) > 4 else os.path.join(ROOT, 'out', 'moddata', 'logos')
    if not os.path.exists(UNCHUNK):
        subprocess.run(['sh', os.path.join(os.path.dirname(__file__), 'build.sh')], check=True)
    files = index(game)
    kit_pattern = re.compile(r'^data/(sceneassets/kit\d?/kit_|ui/imgassets/kits\d?/j\d+_)(\d+)(_\d+(_\d+)?\.(rx3|dds))$')
    by_team = {}
    for name in files:
        m = kit_pattern.match(name)
        if m:
            by_team.setdefault(int(m.group(2)), []).append((name, m))
    made = 0

    def fetch_png(url, name):
        png = os.path.join(logos, name)
        if not os.path.exists(png):
            os.makedirs(logos, exist_ok=True)
            req = urllib.request.Request(url, headers={'User-Agent': 'fifa-macos-modding/1.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                open(png, 'wb').write(r.read())
        return dds.read_png(png)

    def crests(images, ident):
        """images: {'': (w, h, rows), 'dark/': ...}: every crest size the game has, light and dark."""
        n = 0
        for folder, (size, fmt) in CREST_SIZES.items():
            for sub, (w, h, rows) in images.items():
                target = os.path.join(mod, 'data', 'ui', 'imgassets', folder, sub, f'l{ident}.dds')
                os.makedirs(os.path.dirname(target), exist_ok=True)
                dds.write_dds(target, dds.resize(w, h, rows, size), size, fmt)
                n += 1
        return n

    logos_of_league = league.get('league_logos') or {}
    if logos_of_league.get('text'):
        light = drawn_logo(logos_of_league['text'], (24, 24, 24))
        dark = drawn_logo(logos_of_league['text'], (240, 240, 240))
    elif logos_of_league.get('light'):
        light = fetch_png(logos_of_league['light'], f"league-{league['league_id']}.png")
        dark = fetch_png(logos_of_league['dark'], f"league-{league['league_id']}-dark.png") \
            if logos_of_league.get('dark') else light
    if logos_of_league.get('text') or logos_of_league.get('light'):
        for folder, (w, h) in LEAGUE_SIZES.items():
            for sub, image in (('', light), ('dark/', dark)):
                target = os.path.join(mod, 'data', 'ui', 'imgassets', folder, sub, f"l{league['league_id']}.dds")
                os.makedirs(os.path.dirname(target), exist_ok=True)
                dds.write_dds(target, dds.resize(*image, w, h), w, 'dxt5', h)
                made += 1
        print(f"league {league['league_id']}: logo")
    for team in league['teams']:
        if team['existing']:
            continue
        tid, donor = team['teamid'], team.get('kit_donor')
        for name, m in by_team.get(donor, []):
            target = os.path.join(mod, 'data', m.group(1) + str(tid) + m.group(3))
            copy_entry(files[name], target)
            made += 1
        club = team.get('crest_from')
        if club:
            for name in files:
                m = re.match(r'^data/(ui/imgassets/crest[^/]*/(?:dark/)?l|sceneassets/(?:flag/flag|banner/banner)_)'
                             r'%d(\.(?:dds|rx3))$' % club, name)
                if m:
                    copy_entry(files[name], os.path.join(mod, 'data', m.group(1) + str(tid) + m.group(2)))
                    made += 1
            print(f"{tid} {team['name']}: kits, crests, flags and banners from {club}")
            continue
        url = team.get('logo')
        if not url:
            continue
        image = fetch_png(url, f"{team['source_id']}.png")
        made += crests({'': image, 'dark/': image}, tid)
        print(f"{tid} {team['name']}: kits from {donor}, crest from {url.rsplit('/', 1)[-1]}")
    copies = league.get('player_copies') or {}
    if copies:
        heads = re.compile(r'^data/sceneassets/(heads/head|faces/face|hair/hair|hairlod/hairlod)_(\d+)(_.*)$')
        by_player = {}
        for name in files:
            m = heads.match(name)
            if m:
                by_player.setdefault(m.group(2), []).append((name, m))
        for new, old in copies.items():
            for name, m in by_player.get(str(old), []):
                copy_entry(files[name], os.path.join(mod, 'data', 'sceneassets', f'{m.group(1)}_{new}{m.group(3)}'))
                made += 1
        print(f'{len(copies)} players copied: their heads, faces and hair')
    print(f'{made} files in {mod}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
