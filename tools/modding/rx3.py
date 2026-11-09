#!/usr/bin/env python3
"""The game's RX3 files (models and textures: kits, crowd flags, banners...) - their textures, read and replaced.

  rx3.py list FILE.rx3                       the sections and textures
  rx3.py png FILE.rx3 INDEX OUT.png          a texture's first mip as a picture

The format, as the Xbox 360 game has it ("RX3l": little-endian): "RX3l", u32 version (4), u32 file size, u32
section count, then a section table (u32 type hash, u32 offset, u32 size, u32 0). Textures are the sections of
type 0x7a0b60da (the first section, 0x6bd085dc, lists them): a 16-byte header (u32 size, u8 type 1, u8 format:
0 DXT1, 1 DXT3, 2 DXT5, 7 A8R8G8B8; u16, u16 width, u16 height, u16 faces, u16 mips), then each mip: u32 pitch,
u32 rows (of blocks), u32 size, u32 0, and its data, linear (not tiled) but in the Xbox's 16-bit byte order
(each pair of bytes swapped from the PC's DDS).
"""
import struct
import sys

TEXTURE = 0x7A0B60DA
FORMATS = {0: b'DXT1', 1: b'DXT3', 2: b'DXT5', 7: None}


def swap16(data):
    a = bytearray(data)
    a[0::2], a[1::2] = data[1::2], data[0::2]
    return bytes(a)


class Rx3:
    def __init__(self, data):
        if data[:4] != b'RX3l':
            raise ValueError('not a little-endian RX3')
        self.data = bytearray(data)
        n = struct.unpack_from('<I', data, 12)[0]
        self.sections = [list(struct.unpack_from('<IIII', data, 16 + 16 * i)) for i in range(n)]

    def textures(self):
        """[(section index, format, width, height, mips)]"""
        out = []
        for i, (kind, off, size, _) in enumerate(self.sections):
            if kind == TEXTURE:
                _, typ, fmt, _, w, h, faces, mips = struct.unpack_from('<IBBHHHHH', self.data, off)
                out.append((i, fmt, w, h, mips))
        return out

    def mips(self, index):
        """The texture's mips: [(width, height, data in PC byte order)]"""
        kind, off, size, _ = self.sections[index]
        _, typ, fmt, _, w, h, faces, mips = struct.unpack_from('<IBBHHHHH', self.data, off)
        at, out = off + 16, []
        for m in range(mips):
            pitch, rows, msize, _ = struct.unpack_from('<IIII', self.data, at)
            out.append((max(1, w >> m), max(1, h >> m), swap16(bytes(self.data[at + 16:at + 16 + msize]))))
            at += 16 + msize
        return out

    def replace(self, index, mips):
        """New data for a texture of the same format and size: mips as [data in PC byte order], largest first;
        fewer than the texture has: the rest stay."""
        kind, off, size, _ = self.sections[index]
        _, typ, fmt, _, w, h, faces, count = struct.unpack_from('<IBBHHHHH', self.data, off)
        at = off + 16
        for m in range(count):
            pitch, rows, msize, _ = struct.unpack_from('<IIII', self.data, at)
            if m < len(mips):
                if len(mips[m]) != msize:
                    raise ValueError(f'mip {m}: {len(mips[m])} bytes for {msize}')
                self.data[at + 16:at + 16 + msize] = swap16(mips[m])
            at += 16 + msize


def main(argv):
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    r = Rx3(open(argv[2], 'rb').read())
    if argv[1] == 'list':
        for kind, off, size, _ in r.sections:
            print(f'{kind:08x} {off:8x} {size:8x}')
        for i, fmt, w, h, mips in r.textures():
            print(f'texture {i}: {w}x{h} {FORMATS.get(fmt, fmt)} {mips} mips')
    elif argv[1] == 'png' and len(argv) == 5:
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import dds
        i = int(argv[3])
        fmt = next(t[1] for t in r.textures() if t[0] == i)
        w, h, data = r.mips(i)[0]
        dds.write_png(argv[4], w, h, dds.decode(data, w, h, FORMATS[fmt]))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
