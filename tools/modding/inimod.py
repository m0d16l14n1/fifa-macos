#!/usr/bin/env python3
"""A PC FIFA 19 Frosty mod of Career's settings (the footballcompeng INI files: transfers, wages, contracts, the
sim, the board, scouts...) as a mod for this game: patches of the keys it changes.

  inimod.py MOD.fbmod OUTMOD [GAMEDIR]       GAMEDIR: game

Both games have the same files with mostly the same keys. For each INI the mod has (legacy files), the keys the
game has and the mod sets differently go into OUTMOD/<path>.patch (modgame.py merges them into the file as it is
by then, so the update's own changes, Career's first day, stay); keys only the PC has are left out, and Career's
first day (CALSTART_*) is never taken. Other files (tables: gpattributemodifiers.txt, ratingcurvetable.txt) are
taken whole when they have the game's shape (rows and columns), else left out. Prints what it took.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fbmod  # noqa: E402
import modgame  # noqa: E402

NEVER = re.compile(r'^CALSTART_')


def keys(text):
    out, section = {}, ''
    for line in text.replace('\r\n', '\n').split('\n'):
        body = line.split('//')[0].strip()
        if body.startswith('[') and body.endswith(']'):
            section = body[1:-1].strip().upper()
        elif '=' in body and not body.startswith(';'):
            k, v = body.split('=', 1)
            out[(section, k.strip().upper())] = (k.strip(), v.strip())
    return out


def shape(text):
    rows = [line.split('//')[0].strip() for line in text.replace('\r\n', '\n').split('\n')]
    return [len(re.split(r'[\s,]+', r)) for r in rows if r]


def main(argv):
    if len(argv) not in (3, 4):
        print(__doc__, file=sys.stderr)
        return 2
    mod, out, game = fbmod.Reader(argv[1]), argv[2], argv[3] if len(argv) > 3 else 'game'
    taken = []
    for r in mod.resources:
        legacy = r.get('userdata', '')
        if not legacy.startswith('legacy;dlc/') or r['index'] < 0:
            continue
        path = modgame.norm(legacy[len('legacy;'):])
        theirs = fbmod.decompress(mod.data(r)).decode('utf-8', 'replace')
        ours = modgame.game_file(game, path)
        if ours is None:
            print(f'  {path}: not in the game, left out')
            continue
        ours = ours.decode('utf-8', 'replace')
        target = os.path.join(out, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if path.endswith('.ini'):
            mine, pc = keys(ours), keys(theirs)
            changed = {k: v for k, v in pc.items() if k in mine and mine[k][1] != v[1] and not NEVER.match(k[1])}
            if not changed:
                continue
            lines, section = [], None
            for (sec, _), (name, value) in sorted(changed.items()):
                if sec != section:
                    lines.append(f'[{sec}]')
                    section = sec
                lines.append(f'{name} = {value}')
            open(target + '.patch', 'w', newline='\r\n').write('\n'.join(lines) + '\n')
            taken.append(f'{os.path.basename(path)} {len(changed)}')
        elif shape(theirs) == shape(ours):
            open(target, 'w', newline='').write(theirs)
            taken.append(f'{os.path.basename(path)} (whole)')
        else:
            print(f'  {path}: not the game\'s shape, left out')
    print(f"{mod.details['title']}: " + ', '.join(taken))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
