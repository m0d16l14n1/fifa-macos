#!/usr/bin/env python3
"""Kits, crowd flags and banners from the PC game's Frosty mods (.fbmod), as this game's files, into a mod.

  fbkits.py CONFIG.json GAMEDIR MODDIR CSVDIR [CLUBS.json...]

CONFIG (leagues/kits.json): the mods, in order (a later one wins where two have the same kit), each with
  path   the .fbmod (relative to tools/modding)
  map    the mod's team id -> this game's (a mod that puts clubs in other clubs' places: the RPL's in Ireland's)
  skip   the mod's ids that aren't the club the game has under that id (the places it took), when not in map
Other ids are the game's own (EA keeps a club's id from game to game); a club only one of the update's steps made
(CLUBS.json: squads.py's, fc27.py's, league.py's teams) is found by its name in the mod's folder names.

How the PC's textures become this game's (both FIFA 19, the same kit layout; textures/rx3.py says more):
- a kit (sceneassets/kit0..2 and kit: home, away, keeper, third; kit_<team>_<type>_<n>.rx3): the jersey's colour
  (2048x2048 on PC) is the RX3's 1024x1024 DXT1; the shorts' (2048x1024) with the socks' two panels (512x256, a sock
  each) pasted over the top band is its 1024x512 DXT1 (the socks' rectangles: x 141-504 and 520-883, y 0-185); the
  crest (256x256) its 128x128 DXT5. Each with all its mips. The other textures (the far-away versions) stay. The
  RX3 is the club's own, or the game's kit of that type as a template;
- the menus' kit picture (ui/imgassets/kits0..2, kits: j<type>_<team>_<n>.dds): a shirt's shape and shading (a
  white home shirt's) filled with the jersey's front and sleeves;
- crowd flags (sceneassets/flag/flag_<team>.rx3: four 128x128) and banners (banner/banner_<team>.rx3: 1024x512).
Writes the files under MODDIR (loose, as the game reads mods) and prints what it made.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fbtex  # noqa: E402
import league as fifa  # noqa: E402
import modgame  # noqa: E402
import rx3  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
UNCHUNK = os.path.join(HERE, '..', '..', 'out', 'tools', 'unchunk')
KIT_FOLDER = {0: 'kit0', 1: 'kit1', 2: 'kit2', 3: 'kit'}
PICTURE_FOLDER = {0: 'kits0', 1: 'kits1', 2: 'kits2', 3: 'kits'}
SOCKS = [(141, 0, 505, 186), (520, 0, 884, 186)]
KIT = re.compile(r'^content/character/kit/kit_\d+/([^/]+)_(\d+)/[a-z_]+_(\d+)_(\d+)/(jersey|shorts|socks|crest)_\2_\3_\4_color$')
FLAG = re.compile(r'^content/worlds/flag/textures/flag_(\d+)/flag_\1_(\d)_color$')
BANNER = re.compile(r'^content/worlds/banner/textures/banner_(\d+)/banner_\1_color$')


def mips(image, w, h, count, fmt):
    """The image as count DXT mips (bytes, PC order), largest w x h."""
    from PIL import Image
    out = []
    for m in range(count):
        mw, mh = max(1, w >> m), max(1, h >> m)
        buf = io.BytesIO()
        image.resize((max(4, mw), max(4, mh)), Image.LANCZOS).save(buf, 'DDS', pixel_format=fmt)
        out.append(buf.getvalue()[128:])
    return out


def convert_kit(r, parts):
    """The PC kit's textures into the RX3 r (in place). Returns the jersey's image."""
    jersey = parts['jersey'][0].image(parts['jersey'][1], 1024)
    for i, fmt, w, h, count in r.textures():
        if (w, h) == (1024, 1024) and fmt == 0:
            r.replace(i, mips(jersey.resize((1024, 1024)), 1024, 1024, count, 'DXT1'))
        elif (w, h) == (1024, 512) and fmt == 0 and 'shorts' in parts:
            shorts = parts['shorts'][0].image(parts['shorts'][1], 1024).resize((1024, 512))
            if 'socks' in parts:
                socks = parts['socks'][0].image(parts['socks'][1], 512).resize((512, 256))
                for k, box in enumerate(SOCKS):
                    panel = socks.crop((256 * k, 0, 256 * (k + 1), 256))
                    shorts.paste(panel.resize((box[2] - box[0], box[3] - box[1])), box[:2])
            r.replace(i, mips(shorts, 1024, 512, count, 'DXT1'))
        elif (w, h) == (128, 128) and fmt == 2 and 'crest' in parts:
            crest = parts['crest'][0].image(parts['crest'][1], 256)
            if crest.getextrema()[3][1] > 0:  # some mods leave the crest empty (it is on the jersey)
                r.replace(i, mips(crest.resize((128, 128)), 128, 128, count, 'DXT5'))
    return jersey


class Game:
    def __init__(self, game, mod):
        import teamassets
        self.files, self.mod = teamassets.index(game), mod

    def file(self, rel):
        """A file's bytes: the mod's (an earlier step's), else the game's, unpacked; None when neither has it."""
        path = os.path.join(self.mod, rel)
        if os.path.exists(path):
            return open(path, 'rb').read()
        where = self.files.get(rel.lower())
        if where is None:
            return None
        tmp = path + '.tmp'
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        import teamassets
        teamassets.copy_entry(where, tmp)
        data = open(tmp, 'rb').read()
        os.unlink(tmp)
        return data


def picture_template(game):
    """A white home shirt's picture (Real Madrid's): its shape (alpha) and shading (luminance)."""
    from PIL import Image
    data = game.file('data/ui/imgassets/kits0/j0_243_0.dds')
    return Image.open(io.BytesIO(data)).convert('RGBA')


def picture(template, jersey):
    """The menus' kit picture: the template's shirt filled with the jersey's front (its sleeves from the
    texture's sleeves), shaded as the template is."""
    from PIL import Image, ImageChops, ImageFilter
    w, h = template.size
    tex = jersey.convert('RGB').resize((1024, 1024))
    front = tex.crop((330, 600, 694, 960)).resize((int(w * 0.62), int(h * 0.78)))
    sleeve = tex.crop((10, 380, 170, 620)).resize((int(w * 0.26), int(h * 0.32)))
    fill = Image.new('RGB', (w, h), tex.getpixel((512, 800)))
    fill.paste(sleeve, (0, int(h * 0.12)))
    fill.paste(sleeve.transpose(Image.FLIP_LEFT_RIGHT), (w - sleeve.width, int(h * 0.12)))
    fill.paste(front, ((w - front.width) // 2, int(h * 0.14)))
    # the template's folds, its sponsor and crests closed away (dark details narrower than the kernel: gone)
    shade = template.convert('L').filter(ImageFilter.MaxFilter(25)).filter(ImageFilter.MinFilter(25))
    shade = shade.filter(ImageFilter.GaussianBlur(2)).point(lambda v: min(255, int(v * 1.12)))
    lit = ImageChops.multiply(fill, Image.merge('RGB', (shade, shade, shade)))
    out = lit.convert('RGBA')
    out.putalpha(template.getchannel('A'))
    return out


def main(argv):
    if len(argv) < 5:
        print(__doc__, file=sys.stderr)
        return 2
    cfg, gamedir, moddir, csvdir = json.load(open(argv[1])), argv[2], argv[3], argv[4]
    teams = {t['teamid']: t['teamname'] for t in fifa.read(os.path.join(csvdir, 'teams.csv'))}
    made_clubs = {}
    for path in argv[5:]:
        if os.path.exists(path):
            for t in json.load(open(path)).get('teams', []):
                if not t.get('existing'):
                    made_clubs[str(t['teamid'])] = t['name']
    import squads
    game = Game(gamedir, moddir)

    # Every kit, flag and banner the mods have, by this game's team (later mods win).
    kits, flags, banners, unknown = {}, {}, {}, set()
    for spec in cfg['mods']:
        path = os.path.join(HERE, spec['path'])
        if not os.path.exists(path):
            print(f"  {spec['path']}: not there, skipped")
            continue
        tex = fbtex.Textures([path])
        mapping = {str(k): str(v) for k, v in spec.get('map', {}).items()}
        skip = {str(x) for x in spec.get('skip', [])}

        def target(pc, folder=''):
            if pc in mapping:
                return mapping[pc]
            if pc in skip:
                return None
            if pc in teams and pc not in made_clubs:
                return pc
            name = folder.rsplit('_', 1)[0].replace('_', ' ')
            if name and made_clubs:
                best = max(made_clubs, key=lambda t: squads.name_score(name, made_clubs[t]))
                if squads.name_score(name, made_clubs[best]) >= 0.85:
                    return best
            unknown.add(f'{folder or pc}')
            return None
        for name in tex.names():
            m = KIT.match(name)
            if m:
                tid = target(m.group(2), f'{m.group(1)}_{m.group(2)}')
                if tid:
                    kits.setdefault((tid, int(m.group(3)), int(m.group(4))), {})[m.group(5)] = (tex, name)
                continue
            m = FLAG.match(name)
            if m and target(m.group(1)):
                flags.setdefault(target(m.group(1)), {})[int(m.group(2))] = (tex, name)
                continue
            m = BANNER.match(name)
            if m and target(m.group(1)):
                banners[target(m.group(1))] = (tex, name)

    template = picture_template(game)
    done = {'kits': 0, 'pictures': 0, 'flags': 0, 'banners': 0}
    for (tid, kind, n), parts in sorted(kits.items(), key=lambda x: (int(x[0][0]), x[0][1], x[0][2])):
        if kind not in KIT_FOLDER or 'jersey' not in parts:
            continue
        rel = f'data/sceneassets/{KIT_FOLDER[kind]}/kit_{tid}_{kind}_{n}.rx3'
        base = game.file(rel) or game.file(f'data/sceneassets/{KIT_FOLDER[kind]}/kit_1_{kind}_0.rx3')
        if base is None:
            continue
        r = rx3.Rx3(base)
        try:
            jersey = convert_kit(r, parts)
        except (OSError, ValueError) as e:
            print(f'  kit {tid} {kind} {n}: {e}')
            continue
        os.makedirs(os.path.dirname(os.path.join(moddir, rel)), exist_ok=True)
        open(os.path.join(moddir, rel), 'wb').write(bytes(r.data))
        done['kits'] += 1
        pic = f'data/ui/imgassets/{PICTURE_FOLDER[kind]}/j{kind}_{tid}_{n}.dds'
        os.makedirs(os.path.dirname(os.path.join(moddir, pic)), exist_ok=True)
        picture(template, jersey).save(os.path.join(moddir, pic), 'DDS', pixel_format='DXT5')
        done['pictures'] += 1
    for tid, parts in sorted(flags.items()):
        rel = f'data/sceneassets/flag/flag_{tid}.rx3'
        base = game.file(rel) or game.file('data/sceneassets/flag/flag_1.rx3')
        r = rx3.Rx3(base)
        textures = [t for t in r.textures() if (t[2], t[3]) == (128, 128)]
        try:
            for k, (i, fmt, w, h, count) in enumerate(textures):
                if k in parts:
                    img = parts[k][0].image(parts[k][1], 128).resize((128, 128))
                    r.replace(i, mips(img, 128, 128, count, 'DXT1' if fmt == 0 else 'DXT5'))
        except (OSError, ValueError) as e:
            print(f'  flag {tid}: {e}')
            continue
        os.makedirs(os.path.dirname(os.path.join(moddir, rel)), exist_ok=True)
        open(os.path.join(moddir, rel), 'wb').write(bytes(r.data))
        done['flags'] += 1
    for tid, (tex, name) in sorted(banners.items()):
        rel = f'data/sceneassets/banner/banner_{tid}.rx3'
        base = game.file(rel) or game.file('data/sceneassets/banner/banner_1.rx3')
        r = rx3.Rx3(base)
        try:
            for i, fmt, w, h, count in r.textures():
                img = tex.image(name).resize((w, h))
                r.replace(i, mips(img, w, h, count, 'DXT1' if fmt == 0 else 'DXT5'))
        except (OSError, ValueError) as e:
            print(f'  banner {tid}: {e}')
            continue
        os.makedirs(os.path.dirname(os.path.join(moddir, rel)), exist_ok=True)
        open(os.path.join(moddir, rel), 'wb').write(bytes(r.data))
        done['banners'] += 1
    print(f"PC mods: {done['kits']} kits (and their menu pictures), {done['flags']} crowd flags, "
          f"{done['banners']} banners" + (f"; {len(unknown)} teams not in the game: {', '.join(sorted(unknown)[:8])}"
                                          + ('...' if len(unknown) > 8 else '') if unknown else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
