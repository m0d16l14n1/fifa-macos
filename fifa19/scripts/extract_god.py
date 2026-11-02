"""Extract every file of a Games-on-Demand (SVOD) package, including the enhanced GDF layout.
usage: extract_god.py <header file> <out dir> [--list]"""
import os, struct, sys

hdr_path, out_dir = sys.argv[1], sys.argv[2]
data_dir = hdr_path + '.data'
h = open(hdr_path, 'rb').read(0x1800)
be32 = lambda b, o: struct.unpack('>I', b[o:o+4])[0]
flags = h[0x391]
start_block = h[0x395] | (h[0x396] << 8) | (h[0x397] << 16)
egdf = bool(flags & 0x40)
print(f"title {be32(h, 0x360):08X} egdf {egdf} start_data_block {start_block:#x}")

BLOCK, HASH, PER_L0, PER_FILE = 0x800, 0x1000, 0x198, 0x14388
files = {}
def fh(i):
    f = files.get(i)
    if f is None:
        f = files[i] = open(os.path.join(data_dir, f'Data{i:04d}'), 'rb')
    return f

def read(disc_off, size):
    out = bytearray()
    while size:
        sector, within = divmod(disc_off, BLOCK)
        tb = sector - start_block * 2 + (2 if egdf else 0)
        index, fb = divmod(tb, PER_FILE)
        run = PER_L0 - fb % PER_L0  # blocks left before the next level-0 hash block
        chunk = min(size, run * BLOCK - within)
        f = fh(index)
        f.seek(fb * BLOCK + (fb // PER_L0 + 1) * HASH + HASH + within)
        data = f.read(chunk)
        assert len(data) == chunk, (disc_off, chunk)
        out += data
        disc_off += chunk; size -= chunk
    return bytes(out)

desc = 0x2000
d0 = fh(0); d0.seek(desc)
vd = d0.read(0x20)
assert vd[:20] == b'MICROSOFT*XBOX*MEDIA'
root_sector, root_size = struct.unpack('<II', vd[20:28])

def walk(sector, size, prefix=''):
    table = read(sector * BLOCK, size)
    stack, out = [0], []
    while stack:
        off = stack.pop() * 4
        if off + 14 > len(table) or table[off:off+4] == b'\xff\xff\xff\xff':
            continue
        left, right, start, length, attr, nlen = struct.unpack('<HHIIBB', table[off:off+14])
        name = prefix + table[off+14:off+14+nlen].decode('latin-1')
        if attr & 0x10:
            out.append((name, start, length, True))
            if length:
                out += walk(start, length, name + '/')
        else:
            out.append((name, start, length, False))
        stack += [x for x in (left, right) if x]
    return out

entries = sorted(walk(root_sector, root_size))
total = sum(e[2] for e in entries if not e[3])
print(f"{len(entries)} entries, {total / 2**30:.2f} GiB")
if '--list' in sys.argv:
    for name, start, length, is_dir in entries:
        print(f"  {'<dir>' if is_dir else f'{length:>12}'}  {name}")
    sys.exit()
for name, start, length, is_dir in entries:
    path = os.path.join(out_dir, name)
    if is_dir:
        os.makedirs(path, exist_ok=True); continue
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) == length:
        continue
    with open(path + '.part', 'wb') as out:
        for pos in range(0, length, 0x1000000):
            out.write(read(start * BLOCK + pos, min(0x1000000, length - pos)))
    os.replace(path + '.part', path)
print("done")
