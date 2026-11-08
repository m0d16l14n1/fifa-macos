#!/usr/bin/env python3
"""Finds flicker in a burst of consecutive presented frames (dev pad `burst`, scripts/conditions.sh).

usage: flicker.py <frame-000.ppm> <frame-001.ppm> ... [--grid N] [--min D] [--png]

Each frame is cut into an N x N grid (default 12). A tile flickers in frame i when it differs from both frames
around it (by more than D, mean absolute difference per channel, default 10) while those two frames are alike
(their difference under a third of that): something drawn for one frame only, or missing for one frame, as
opposed to motion, which changes steadily. Prints the frames and tiles that flicker; --png writes each such frame
beside it (<frame>.flicker.png) with its flickering tiles outlined. Standard library only."""
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppm2png  # noqa: E402


def tiles(path, grid):
    w, h, rgb = ppm2png.read_ppm(path)
    w2, h2, small = ppm2png.downscale(w, h, rgb, 4)
    out = []
    for ty in range(grid):
        for tx in range(grid):
            x0, x1 = tx * w2 // grid, (tx + 1) * w2 // grid
            y0, y1 = ty * h2 // grid, (ty + 1) * h2 // grid
            values = []
            for y in range(y0, y1):
                row = (y * w2) * 3
                values.extend(small[row + x0 * 3: row + x1 * 3])
            out.append(values)
    return (w, h, rgb), out


def diff(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / max(len(a), 1)


def write_png(path, w, h, rgb, boxes):
    pixels = bytearray(rgb)
    for x0, y0, x1, y1 in boxes:
        for x in range(x0, x1):
            for y in (y0, y1 - 1):
                i = (y * w + x) * 3
                pixels[i:i + 3] = b'\xff\x00\xff'
        for y in range(y0, y1):
            for x in (x0, x1 - 1):
                i = (y * w + x) * 3
                pixels[i:i + 3] = b'\xff\x00\xff'
    raw = b''.join(b'\0' + bytes(pixels[y * w * 3:(y + 1) * w * 3]) for y in range(h))

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) +
                chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def main(argv):
    grid, minimum, png, files = 12, 10.0, False, []
    i = 0
    while i < len(argv):
        if argv[i] == '--grid':
            grid = int(argv[i + 1]); i += 2
        elif argv[i] == '--min':
            minimum = float(argv[i + 1]); i += 2
        elif argv[i] == '--png':
            png = True; i += 1
        else:
            files.append(argv[i]); i += 1
    if len(files) < 3:
        print(__doc__)
        return 2
    frames = [tiles(f, grid) for f in files]
    found = 0
    for n in range(1, len(frames) - 1):
        flicker = []
        for t in range(grid * grid):
            a, b, c = frames[n - 1][1][t], frames[n][1][t], frames[n + 1][1][t]
            d1, d2, d3 = diff(a, b), diff(b, c), diff(a, c)
            if d1 > minimum and d2 > minimum and d3 < min(d1, d2) / 3:
                flicker.append((t, d1, d2, d3))
        if flicker:
            found += 1
            names = ', '.join(f'tile {t % grid},{t // grid} ({d1:.0f}/{d2:.0f} vs {d3:.0f})' for t, d1, d2, d3 in flicker[:6])
            more = f' and {len(flicker) - 6} more' if len(flicker) > 6 else ''
            print(f'{os.path.basename(files[n])}: {len(flicker)} tiles flicker: {names}{more}')
            if png:
                w, h, rgb = frames[n][0]
                boxes = [((t % grid) * w // grid, (t // grid) * h // grid, ((t % grid) + 1) * w // grid,
                          ((t // grid) + 1) * h // grid) for t, *_ in flicker]
                write_png(files[n][:-4] + '.flicker.png', w, h, rgb, boxes)
    print(f'{found} of {len(frames) - 2} frames flicker')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
