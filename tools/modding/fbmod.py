#!/usr/bin/env python3
"""Reads Frosty Mod Manager mods (.fbmod: the PC FIFA's Frostbite mods) - what they change and their data.

  fbmod.py list MOD.fbmod [PATTERN]          the resources: type, name, size, handler (PATTERN: a substring)
  fbmod.py info MOD.fbmod                    the mod's details and its resource counts by type
  fbmod.py extract MOD.fbmod NAME OUT        one resource's data, uncompressed (--raw: as stored)

The format (FrostyToolsuite 1.0.6, FrostyModReader): "FROSTY\\0\\1", a version (3-5), the data's offset and count,
the profile ("FIFA19"), the game's version, the details (title, author, category, version, description; a link
from version 5), then the resources: a type (0 embedded, 1 ebx, 2 res, 3 chunk, 4 bundle), the data's index (-1:
none), a name, and with data its SHA-1, size, flags, handler hash and user data, then the bundles it goes into;
res adds its type, rid and meta, chunks their range, logical offset and size, h32 and first mip, bundles their
super bundle. The data: (offset, size) pairs, then the blobs.

A blob is Frostbite's compressed blocks, each: big-endian u32 size (low 24 bits), a code (high byte: 0x0f zstd,
0x11/0x15/0x19 Oodle, 0x02 zlib, 0x00 stored; low nibble of the low byte: bits 16-19 of the packed size), u16
packed size, the data. zstd and zlib are Python's; Oodle (closed) is out/tools/ooz-x86 (powzix's ooz, built for
x86_64 by tools/modding/build_ooz.sh and run under Rosetta).
"""
import os
import struct
import subprocess
import sys
import tempfile
import zlib

OOZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'out', 'tools', 'ooz-x86')

TYPES = {0: 'embedded', 1: 'ebx', 2: 'res', 3: 'chunk', 4: 'bundle'}


class Reader:
    def __init__(self, path):
        self.f = open(path, 'rb')
        if self.f.read(8) != b'FROSTY\x00\x01':
            raise SystemExit(f'{path}: not a Frosty mod')
        self.version, = self.u('<I')
        self.data_offset, self.data_count = self.u('<qi')
        self.profile = self.f.read(self.f.read(1)[0]).decode()
        self.game_version, = self.u('<i')
        fields = ['title', 'author', 'category', 'version', 'description'] + (['link'] if self.version >= 5 else [])
        self.details = {k: self.cstr() for k in fields}
        self.resources = [self.resource() for _ in range(self.u('<i')[0])]

    def u(self, fmt):
        return struct.unpack(fmt, self.f.read(struct.calcsize(fmt)))

    def cstr(self):
        out = bytearray()
        while True:
            c = self.f.read(1)
            if not c or c == b'\x00':
                return out.decode('utf-8', 'replace')
            out += c

    def resource(self):
        r = {'type': TYPES.get(self.f.read(1)[0], '?')}
        r['index'], = self.u('<i')
        r['name'] = self.cstr() if (self.version <= 3 and r['index'] != -1) or self.version > 3 else ''
        if r['index'] != -1:
            r['sha1'] = self.f.read(20).hex()
            r['size'], r['flags'], r['handler'] = self.u('<qBi')
            r['userdata'] = self.cstr() if self.version >= 3 else ''
        if self.version <= 3 and r['index'] != -1:
            for _ in range(self.u('<i')[0]):
                self.u('<i')
            r['bundles'] = [self.u('<i')[0] for _ in range(self.u('<i')[0])]
        elif self.version > 3:
            r['bundles'] = [self.u('<i')[0] for _ in range(self.u('<i')[0])]
        if r['type'] == 'res':
            r['res_type'], r['rid'] = self.u('<IQ')
            r['meta'] = self.f.read(self.u('<i')[0]).hex()
        elif r['type'] == 'chunk':
            (r['range_start'], r['range_end'], r['logical_offset'], r['logical_size'], r['h32'],
             r['first_mip']) = self.u('<IIIIii')
        elif r['type'] == 'bundle':
            r['bundle'] = self.cstr()
            r['superbundle'], = self.u('<i')
        return r

    def data(self, r):
        if r['index'] < 0:
            return b''
        self.f.seek(self.data_offset + r['index'] * 16)
        offset, size = self.u('<qq')
        self.f.seek(self.data_offset + self.data_count * 16 + offset)
        return self.f.read(size)


def decompress(blob):
    """Frostbite's compressed blocks to bytes."""
    out, oodle, at = [], [], 0
    while at + 8 <= len(blob):
        size = int.from_bytes(blob[at:at + 4], 'big') & 0xFFFFFF
        code = int.from_bytes(blob[at + 4:at + 6], 'big')
        packed = int.from_bytes(blob[at + 6:at + 8], 'big') + ((code & 0x0F) << 16)
        kind, data = code >> 8, blob[at + 8:at + 8 + packed]
        at += 8 + packed
        if kind == 0x0F:
            import zstandard
            out.append(zstandard.ZstdDecompressor().decompress(data, max_output_size=size))
        elif kind in (0x11, 0x15, 0x19):
            out.append(None)
            oodle.append((len(out) - 1, data, size))
        elif kind == 0x02:
            out.append(zlib.decompress(data))
        elif kind == 0x00:
            out.append(data[:size])
        else:
            raise ValueError(f'compression {kind:#x} unknown')
    if oodle:
        if not os.path.exists(OOZ):
            raise SystemExit(f'{OOZ} missing: sh tools/modding/build_ooz.sh')
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = os.path.join(tmp, 'in'), os.path.join(tmp, 'out')
            with open(src, 'wb') as f:
                for _, data, size in oodle:
                    f.write(struct.pack('<II', len(data), size) + data)
            subprocess.run(['arch', '-x86_64', OOZ, src, dst], check=True)
            raw = open(dst, 'rb').read()
        pos = 0
        for i, _, size in oodle:
            out[i] = raw[pos:pos + size]
            pos += size
    return b''.join(out)


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    m = Reader(argv[2])
    if argv[1] == 'info':
        print(f"{m.details['title']} by {m.details['author']} ({m.details['category']}, {m.details['version']}); "
              f"Frosty mod v{m.version}, {m.profile} {m.game_version}")
        counts = {}
        for r in m.resources:
            counts[r['type']] = counts.get(r['type'], 0) + 1
        print(', '.join(f'{v} {k}' for k, v in sorted(counts.items())))
    elif argv[1] == 'list':
        pattern = argv[3].lower() if len(argv) > 3 else ''
        for r in m.resources:
            if pattern in r['name'].lower():
                print(f"{r['type']:8} {r.get('size', 0):10} {r.get('handler', 0) & 0xffffffff:08x} {r['name']}"
                      + (f"  [{r['userdata']}]" if r.get('userdata') else ''))
    elif argv[1] == 'extract' and len(argv) in (5, 6):
        r = next(r for r in m.resources if r['name'] == argv[3])
        data = m.data(r)
        open(argv[4], 'wb').write(data if argv[-1] == '--raw' else decompress(data))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
