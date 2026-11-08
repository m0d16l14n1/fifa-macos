#!/usr/bin/env python3
"""Builds a modded copy of the game without touching the game's own files.

The game looks a file up in its archives (dataN.big, with the dataN.bh index of name hashes) and, when no archive
has it, opens it loose from the disc (d:\\data\\...). So a mod is a folder of loose files laid out like the disc
(data/db/fifa_ng_db.db, data/sceneassets/kit/...):
- a file no archive has is new, and the game finds it loose;
- a file an archive has replaces it: the archive's .bh index loses that entry (found by its offset in the archive's
  own table of names, so the hash function needn't be known), and the game then finds the loose file;
- strings/<language>.csv (columns stringid,text; eng_us, rus_ru, pol_pl, ara_sa) changes or adds the game's text
  (team, league and player names, menus): the mods' strings go into data/loc/<language>_upd.db, which the game
  reads beside its own and takes first.

The modded game is a folder of links: to the game's files and folders, to the mods' files, plus the rewritten .bh
indexes. It takes no space to speak of and the game folder stays as it was.

  modgame.py build --game game --out out/modgame MOD [MOD...]   later mods win over earlier ones
  modgame.py list ARCHIVE.big                                      names, offsets and sizes in an archive
  modgame.py extract ARCHIVE.big NAME OUT                          one file, as stored (chunkzip/chunklzx: see unchunk)

Run it: sh scripts/run_app.sh --game out/modgame ...
"""
import csv
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fifadb  # noqa: E402


def read_big(path):
    """The archive's table: [(name, offset, size)], names as stored (data/ui/lua/nav.lreq)."""
    with open(path, 'rb') as f:
        head = f.read(16)
        if head[:4] not in (b'BIG4', b'BIGF'):
            raise ValueError(f'{path}: not a BIG archive ({head[:4]!r})')
        count, toc_end = struct.unpack('>II', head[8:16])
        toc = f.read(toc_end - 16 + 4096)
    entries, p = [], 0
    for _ in range(count):
        offset, size = struct.unpack('>II', toc[p:p + 8])
        end = toc.index(b'\0', p + 8)
        entries.append((toc[p + 8:end].decode('latin-1'), offset, size))
        p = end + 1
    return entries


def read_bh(path):
    """The index: (16-byte header, [20-byte entries: u32 offset, u32 size, u32 0, 8-byte name hash])."""
    data = open(path, 'rb').read()
    if data[:4] != b'ViV4':
        raise ValueError(f'{path}: not a ViV4 index')
    count = struct.unpack('>I', data[8:12])[0]
    return data[:16], [data[16 + 20 * i:36 + 20 * i] for i in range(count)]


def write_bh(path, header, entries):
    body = b''.join(entries)
    size = 16 + len(body)
    header = header[:4] + struct.pack('<I', size) + struct.pack('>II', len(entries), size)
    with open(path, 'wb') as f:
        f.write(header + body)


def norm(name):
    return name.replace('\\', '/').lower().lstrip('/')


def mod_files(mods):
    """{normalized path: host file}, later mods winning."""
    files = {}
    for mod in mods:
        for root, _, names in os.walk(mod):
            for name in names:
                if name.startswith('.'):
                    continue
                host = os.path.join(root, name)
                path = norm(os.path.relpath(host, mod))
                if not path.startswith('strings/'):
                    files[path] = os.path.abspath(host)
    return files


def mod_strings(mods):
    """{language: {string id: text}} from the mods' strings/<language>.csv, later mods winning."""
    out = {}
    for mod in mods:
        folder = os.path.join(mod, 'strings')
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith('.csv'):
                continue
            strings = out.setdefault(name[:-4].lower(), {})
            with open(os.path.join(folder, name), newline='', encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):
                    text = row.get('text', row.get('sourcetext'))
                    if row.get('stringid') and text is not None:
                        strings[row['stringid']] = text
    return out


def link_tree(game, out, overrides, rel=''):
    """Links game/rel into out/rel: a whole file or folder when nothing in it changes, else folder by folder.
    overrides: {normalized path: host file}; a path no game file has is added."""
    src = os.path.join(game, rel)
    dst = os.path.join(out, rel)
    os.makedirs(dst, exist_ok=True)
    here = {}
    for name in os.listdir(src):
        here[name.lower()] = name
    pending = {}
    for path, host in overrides.items():
        prefix = norm(rel) + '/' if rel else ''
        if path.startswith(prefix):
            first, _, rest = path[len(prefix):].partition('/')
            pending.setdefault(first, {})[path] = host
    for low, name in here.items():
        game_path = os.path.join(src, name)
        if low not in pending:
            os.symlink(os.path.abspath(game_path), os.path.join(dst, name))
        elif os.path.isdir(game_path):
            link_tree(game, out, pending[low], os.path.join(rel, name))
        else:
            os.symlink(next(iter(pending[low].values())), os.path.join(dst, name))
    for low, items in pending.items():
        if low in here:
            continue
        for path, host in items.items():  # a new file or folder
            target = os.path.join(out, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            os.symlink(host, target)


def build(game, out, mods):
    if os.path.exists(out) and os.listdir(out):
        if not os.path.isdir(os.path.join(out, '.modgame')):
            raise SystemExit(f'{out}: not a modded game this made; choose an empty or new folder')
        for root, dirs, names in os.walk(out, topdown=False):  # links and the rewritten indexes only
            for name in names:
                os.unlink(os.path.join(root, name))
            for name in dirs:
                path = os.path.join(root, name)
                os.unlink(path) if os.path.islink(path) else os.rmdir(path)
    os.makedirs(out, exist_ok=True)
    files = mod_files(mods)
    overrides = dict(files)
    generated = os.path.join(out, '.modgame')
    os.makedirs(generated, exist_ok=True)
    for language, strings in sorted(mod_strings(mods).items()):
        name = f'{language}_upd'
        fifadb.language_db(os.path.join(generated, name + '.db'), strings)
        fifadb.language_meta(os.path.join(generated, name + '-meta.xml'), name)
        overrides[f'data/loc/{name}.db'] = os.path.join(generated, name + '.db')
        overrides[f'data/loc/{name}-meta.xml'] = os.path.join(generated, name + '-meta.xml')
        print(f'data/loc/{name}.db: {len(strings)} strings')
    replaced = 0
    for root, _, names in os.walk(game):
        for name in sorted(names):
            if not name.lower().endswith('.big'):
                continue
            big = os.path.join(root, name)
            bh = big[:-4] + '.bh'
            if not os.path.exists(bh):
                continue
            hits = {offset: entry for entry, offset, _ in read_big(big) if norm(entry) in files}
            if not hits:
                continue
            header, entries = read_bh(bh)
            kept = [e for e in entries if struct.unpack('>I', e[:4])[0] not in hits]
            rel = os.path.relpath(bh, game)
            index = os.path.join(generated, rel.replace('/', '_'))
            write_bh(index, header, kept)
            overrides[norm(rel)] = index
            for offset, entry in sorted(hits.items()):
                print(f'{rel[:-3]}.big: {entry} replaced')
            replaced += len(entries) - len(kept)
    link_tree(game, out, overrides)
    print(f'{out}: {len(files)} mod files, {replaced} archive entries replaced, {len(files) - replaced} new')


def main(argv):
    if len(argv) >= 2 and argv[1] == 'list':
        for name, offset, size in read_big(argv[2]):
            print(f'{offset:10x} {size:10d} {name}')
    elif len(argv) == 5 and argv[1] == 'extract':
        for name, offset, size in read_big(argv[2]):
            if norm(name) == norm(argv[3]):
                with open(argv[2], 'rb') as f:
                    f.seek(offset)
                    open(argv[4], 'wb').write(f.read(size))
                return 0
        print(f'{argv[3]}: not in {argv[2]}', file=sys.stderr)
        return 1
    elif len(argv) >= 6 and argv[1] == 'build' and argv[2] == '--game' and argv[4] == '--out':
        build(argv[3], argv[5], argv[6:])
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
