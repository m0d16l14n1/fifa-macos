#!/usr/bin/env python3
"""Converts the presenter's binary PPM captures (dev pad `shot`, metal_present_capture) to PNG.

usage: ppm2png.py <file.ppm>... [--scale N] [--crop X,Y,W,H]
writes <file>.png next to each (N: 1/N size, default 1; the crop is in the PPM's pixels, before scaling)
Standard library only."""
import struct
import sys
import zlib


def read_ppm(path):
    data = open(path, 'rb').read()
    fields, pos = [], 0
    while len(fields) < 4:  # P6, width, height, maxval; '#' comments allowed between them
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b'#':
            pos = data.index(b'\n', pos) + 1
            continue
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        fields.append(data[pos:end])
        pos = end
    if fields[0] != b'P6' or int(fields[3]) != 255:
        raise ValueError(f'{path}: not an 8-bit binary PPM')
    width, height = int(fields[1]), int(fields[2])
    return width, height, data[pos + 1:pos + 1 + width * height * 3]


def write_png(path, width, height, rgb):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF)
    stride = width * 3
    raw = b''.join(b'\x00' + rgb[y * stride:(y + 1) * stride] for y in range(height))
    with open(path, 'wb') as out:
        out.write(b'\x89PNG\r\n\x1a\n')
        out.write(chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)))
        out.write(chunk(b'IDAT', zlib.compress(raw, 6)))
        out.write(chunk(b'IEND', b''))


def downscale(width, height, rgb, n):
    w, h = width // n, height // n
    out = bytearray(w * h * 3)
    for y in range(h):
        row = (y * n) * width * 3
        for x in range(w):
            s = row + x * n * 3
            out[(y * w + x) * 3:(y * w + x) * 3 + 3] = rgb[s:s + 3]
    return w, h, bytes(out)


def crop(width, height, rgb, x, y, w, h):
    w, h = min(w, width - x), min(h, height - y)
    rows = (rgb[((y + r) * width + x) * 3:((y + r) * width + x + w) * 3] for r in range(h))
    return w, h, b''.join(rows)


def main(argv):
    scale, box = 1, None
    if '--crop' in argv:
        i = argv.index('--crop')
        box = tuple(int(v) for v in argv[i + 1].split(','))
        del argv[i:i + 2]
    if '--scale' in argv:
        i = argv.index('--scale')
        scale = int(argv[i + 1])
        del argv[i:i + 2]
    if not argv:
        print(__doc__)
        return 2
    for path in argv:
        width, height, rgb = read_ppm(path)
        if box:
            width, height, rgb = crop(width, height, rgb, *box)
        if scale > 1:
            width, height, rgb = downscale(width, height, rgb, scale)
        target = path[:-4] + '.png' if path.endswith('.ppm') else path + '.png'
        write_png(target, width, height, rgb)
        print(f'{target} ({width}x{height})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
