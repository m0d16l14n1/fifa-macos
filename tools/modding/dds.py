#!/usr/bin/env python3
"""DDS images as the game's UI uses them (crests, league logos): DXT1/3/5 or 32-bit, plain little-endian layout.

  dds.py topng IN.dds OUT.png                     the top mip level as a PNG
  dds.py frompng IN.png OUT.dds SIZE [FORMAT]     a square SIZE x SIZE image, FORMAT dxt5 (default), dxt3 or argb

PNG reading and writing are this file's own (8-bit RGB/RGBA, no interlace); resizing is a box/bilinear filter.
Standard library only.
"""
import struct
import sys
import zlib


# --- PNG ---------------------------------------------------------------------------------------------------------
def read_png(path):
    """(width, height, [r,g,b,a bytes per row])."""
    d = open(path, 'rb').read()
    if d[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'{path}: not a PNG')
    p, idat, palette, trns = 8, b'', None, None
    while p < len(d):
        n = struct.unpack('>I', d[p:p + 4])[0]
        kind, body = d[p + 4:p + 8], d[p + 8:p + 8 + n]
        if kind == b'IHDR':
            w, h, depth, ctype, _, _, interlace = struct.unpack('>IIBBBBB', body)
        elif kind == b'PLTE':
            palette = body
        elif kind == b'tRNS':
            trns = body
        elif kind == b'IDAT':
            idat += body
        p += 12 + n
    if depth != 8 or interlace:
        raise ValueError(f'{path}: only 8-bit, non-interlaced PNGs')
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = w * channels
    rows, prev, q = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[q]
        line = bytearray(raw[q + 1:q + 1 + stride])
        q += 1 + stride
        for i in range(stride):
            a = line[i - channels] if i >= channels else 0
            b = prev[i]
            c = prev[i - channels] if i >= channels else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        prev = line
        out = bytearray()
        for x in range(w):
            px = line[x * channels:(x + 1) * channels]
            if ctype == 6:
                out += px
            elif ctype == 2:
                out += px + b'\xff'
            elif ctype == 0:
                out += bytes([px[0]] * 3) + b'\xff'
            elif ctype == 4:
                out += bytes([px[0]] * 3) + bytes([px[1]])
            else:
                i = px[0]
                alpha = trns[i] if trns and i < len(trns) else 255
                out += palette[3 * i:3 * i + 3] + bytes([alpha])
        rows.append(bytes(out))
    return w, h, rows


def write_png(path, w, h, rgba):
    raw = b''.join(b'\0' + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def resize(w, h, rows, size, height=None):
    """RGBA rows to a size x height image (height = size if not given; the picture fitted and centred,
    transparent around it): box filter."""
    height = height or size
    scale = max(w / size, h / height)
    nw, nh = max(1, round(w / scale)), max(1, round(h / scale))
    ox, oy = (size - nw) // 2, (height - nh) // 2
    out = bytearray(size * height * 4)
    for y in range(nh):
        y0, y1 = int(y * scale), max(int(y * scale) + 1, int((y + 1) * scale))
        for x in range(nw):
            x0, x1 = int(x * scale), max(int(x * scale) + 1, int((x + 1) * scale))
            acc = [0, 0, 0, 0]
            n = 0
            for yy in range(y0, min(y1, h)):
                row = rows[yy]
                for xx in range(x0, min(x1, w)):
                    r, g, b, a = row[4 * xx:4 * xx + 4]
                    acc[0] += r * a; acc[1] += g * a; acc[2] += b * a; acc[3] += a
                    n += 1
            o = 4 * ((y + oy) * size + x + ox)
            if acc[3]:
                out[o:o + 4] = bytes([acc[0] // acc[3], acc[1] // acc[3], acc[2] // acc[3], acc[3] // max(n, 1)])
    return bytes(out)


# --- DXT ---------------------------------------------------------------------------------------------------------
def _565(c):
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def _colors(c0, c1, dxt1):
    a, b = _565(c0), _565(c1)
    if c0 > c1 or not dxt1:
        return [a + (255,), b + (255,), tuple((2 * x + y) // 3 for x, y in zip(a, b)) + (255,),
                tuple((x + 2 * y) // 3 for x, y in zip(a, b)) + (255,)]
    return [a + (255,), b + (255,), tuple((x + y) // 2 for x, y in zip(a, b)) + (255,), (0, 0, 0, 0)]


def decode(data, w, h, fourcc):
    out = bytearray(w * h * 4)
    if fourcc is None:  # A8R8G8B8 (BGRA in memory)
        for i in range(w * h):
            b, g, r, a = data[4 * i:4 * i + 4]
            out[4 * i:4 * i + 4] = bytes([r, g, b, a])
        return bytes(out)
    block = 8 if fourcc == b'DXT1' else 16
    p = 0
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            blk = data[p:p + block]
            p += block
            alpha = [255] * 16
            if fourcc == b'DXT3':
                bits = int.from_bytes(blk[:8], 'little')
                alpha = [((bits >> (4 * i)) & 15) * 17 for i in range(16)]
            elif fourcc == b'DXT5':
                a0, a1 = blk[0], blk[1]
                pal = [a0, a1] + ([((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)] if a0 > a1 else
                                  [((4 - i) * a0 + (i + 1) * a1) // 5 for i in range(4)] + [0, 255])
                bits = int.from_bytes(blk[2:8], 'little')
                alpha = [pal[(bits >> (3 * i)) & 7] for i in range(16)]
            c = blk[-8:]
            c0, c1, idx = struct.unpack('<HHI', c)
            cols = _colors(c0, c1, fourcc == b'DXT1')
            for i in range(16):
                x, y = bx + i % 4, by + i // 4
                if x < w and y < h:
                    r, g, b, a = cols[(idx >> (2 * i)) & 3]
                    out[4 * (y * w + x):4 * (y * w + x) + 4] = bytes([r, g, b, min(a, alpha[i])])
    return bytes(out)


def _to565(r, g, b):
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def encode_dxt(rgba, w, h, fourcc):
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            px = []
            for i in range(16):
                x, y = min(bx + i % 4, w - 1), min(by + i // 4, h - 1)
                px.append(rgba[4 * (y * w + x):4 * (y * w + x) + 4])
            alphas = [p[3] for p in px]
            if fourcc == b'DXT3':
                bits = 0
                for i, a in enumerate(alphas):
                    bits |= ((a * 15 + 127) // 255) << (4 * i)
                out += bits.to_bytes(8, 'little')
            else:  # DXT5: 8 interpolated alphas between the block's min and max
                a0, a1 = max(alphas), min(alphas)
                if a0 == a1:
                    out += bytes([a0, a1]) + bytes(6)
                else:
                    pal = [a0, a1] + [((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)]
                    bits = 0
                    for i, a in enumerate(alphas):
                        bits |= min(range(8), key=lambda k: abs(pal[k] - a)) << (3 * i)
                    out += bytes([a0, a1]) + bits.to_bytes(6, 'little')
            # Colour: the two most distant opaque colours as the ends (a simple, good-enough fit).
            solid = [p[:3] for p in px if p[3] > 16] or [p[:3] for p in px]
            lo = min(solid, key=lambda c: c[0] * 3 + c[1] * 6 + c[2])
            hi = max(solid, key=lambda c: c[0] * 3 + c[1] * 6 + c[2])
            c0, c1 = _to565(*hi), _to565(*lo)
            if c0 < c1:
                c0, c1 = c1, c0
            if c0 == c1:
                out += struct.pack('<HHI', c0, c1, 0)
                continue
            cols = _colors(c0, c1, False)
            idx = 0
            for i, p in enumerate(px):
                k = min(range(4), key=lambda j: sum((cols[j][t] - p[t]) ** 2 for t in range(3)))
                idx |= k << (2 * i)
            out += struct.pack('<HHI', c0, c1, idx)
    return bytes(out)


def read_dds(path):
    d = open(path, 'rb').read()
    h, w = struct.unpack('<II', d[12:20])
    flags = struct.unpack('<I', d[80:84])[0]
    fourcc = d[84:88] if flags & 4 else None
    return w, h, fourcc, d[128:]


def write_dds(path, rgba, size, fmt='dxt5', height=None):
    """One mip level, like the game's crests (DDSD caps 0x1007 | linear size, pitch flags as the originals)."""
    height = height or size
    if fmt == 'argb':
        data = b''.join(bytes([rgba[i + 2], rgba[i + 1], rgba[i], rgba[i + 3]]) for i in range(0, len(rgba), 4))
        pf = struct.pack('<II4sIIIII', 32, 0x41, b'\0\0\0\0', 32, 0x00ff0000, 0x0000ff00, 0x000000ff, 0xff000000)
        flags, pitch = 0x00081007, size * 4  # as the game's own 32-bit crests
    else:
        fourcc = b'DXT5' if fmt == 'dxt5' else b'DXT3'
        data = encode_dxt(rgba, size, height, fourcc)
        pf = struct.pack('<II4sIIIII', 32, 4, fourcc, 0, 0, 0, 0, 0)
        flags, pitch = 0x00081007, len(data)
    header = struct.pack('<4sIIIIIII', b'DDS ', 124, flags, height, size, pitch, 0, 0) + bytes(44) + pf
    header += struct.pack('<IIIII', 0x1000, 0, 0, 0, 0)
    open(path, 'wb').write(header + data)


def main(argv):
    if len(argv) == 4 and argv[1] == 'topng':
        w, h, fourcc, data = read_dds(argv[2])
        write_png(argv[3], w, h, decode(data, w, h, fourcc))
    elif len(argv) in (5, 6) and argv[1] == 'frompng':
        w, h, rows = read_png(argv[2])
        size = int(argv[4])
        write_dds(argv[3], resize(w, h, rows, size), size, argv[5] if len(argv) == 6 else 'dxt5')
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
