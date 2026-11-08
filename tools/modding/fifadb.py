#!/usr/bin/env python3
"""FIFA 19 (Xbox 360) database: fifa_ng_db.db with its fifa_ng_db-meta.xml (EA's t3db), to CSV and back.

usage:
  fifadb.py info   <db> <meta>                      tables, their records and fields
  fifadb.py export <db> <meta> <dir>                every table to <dir>/<table>.csv (columns by field name)
  fifadb.py import <db> <meta> <dir> <out.db>       the tables whose CSV is in <dir> replaced, the rest as is
  fifadb.py check  <db> <meta>                      rebuilds the database unchanged and compares (round trip)

Unpack the two files from data0.big first (tools/modding/modgame.py extract, then out/tools/unchunk). Standard library only.

Format (big-endian on the Xbox 360), worked out from the game's own files:
  file:   "DB\\0\\x08" u8[4] (01 00 00 00), u32 file size, u32 0, u32 table count, u32 crc of bytes 0-20,
          table count x {char[4] short name, u32 offset from the end of the index}, u32 crc of the index
  table:  u32 flags (2; 0x20 plain strings, 0x40 Huffman-coded strings), u32 record bytes, u32 record bits, u32 compressed string bytes, u16 records, u16 records,
          u32 0x0000ffff, u8 fields, u8[7], u32 crc of the 32 bytes before it,
          fields x {u32 type (0 string, 3 integer, 4 float...), u32 bit offset, char[4] short name, u32 bits},
          records x record bytes (bit fields MSB first; an integer is stored as value - rangelow from the meta),
          the string block (compressed string bytes: for type-13 and type-14 (long) fields, whose record holds a
          32-bit offset into it or ffffffff, each string a length byte (2 for type 14) and its text; or, flag
          0x40 (the big name tables, the locale's text), Huffman-coded:
          the block starts with the tree, nodes of two 2-byte children (NN 00 an inner node, 00 cc a leaf byte,
          node 0 the root, bit 0 the first child), each string its length (in UTF-8 bytes) and its code,
          MSB first, from a whole byte), zero padding to 4 bytes, and a u32 crc of everything from the field
          list to it
  crc:    CRC-32 without reflection, polynomial 04C11DB7, initial ffffffff, no final xor (CRC-32/MPEG-2)
"""
import csv
import os
import re
import struct
import sys

_TABLE = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if _c & 0x80000000 else (_c << 1) & 0xFFFFFFFF
    _TABLE.append(_c)


def crc(data):
    c = 0xFFFFFFFF
    for x in data:
        c = ((c << 8) & 0xFFFFFFFF) ^ _TABLE[((c >> 24) ^ x) & 0xFF]
    return c


def read_meta(path):
    """{table short name: (table name, {field short name: (field name, type, rangelow)})}"""
    text = open(path, encoding='utf-8').read()
    tables = {}
    for m in re.finditer(r'<table name="([^"]+)" shortname="([^"]+)"[^>]*>(.*?)</table>', text, re.S):
        fields = {}
        for f in re.finditer(r'<field ([^>]*)/>', m.group(3)):
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', f.group(1)))
            fields[attrs['shortname']] = (attrs['name'], attrs['type'], int(attrs.get('rangelow', '0') or 0))
        tables[m.group(2)] = (m.group(1), fields)
    return tables


# A table's record counts are 16-bit. The meta's maxinsert is no limit: the game boots with
# 8,000 more players and links than the table had and 5,000 more names (maxinsert 3282, and none for names).
MAX_RECORDS = 65535

# Fields whose record holds a 32-bit offset into the string block: 13 a string, 14 a long one (the locale's text).
STRING_TYPES = (13, 14)


class Table:
    def __init__(self, short, blob):
        self.short = short
        self.blob = blob  # the table's bytes as in the file
        (self.version, self.record_bytes, self.record_bits, self.string_bytes, self.records, self.records2,
         self.unk, self.nfields) = struct.unpack('>IIIIHHIB', blob[:25])
        self.pad = blob[25:32]
        self.fields = []
        p = 36
        for _ in range(self.nfields):
            ftype, offset, fshort, bits = struct.unpack('>II4sI', blob[p:p + 16])
            self.fields.append((fshort.decode('latin1'), ftype, offset, bits))
            p += 16
        self.fields_end = p
        self.data_start = p
        self.data_end = p + self.record_bytes * self.records2
        self.strings = blob[self.data_end:self.data_end + self.string_bytes]
        # The header's first word is flags: 0x40 Huffman-coded strings (the tree first), 0x20 plain ones.
        self.huffman = bool(self.version & 0x40)
        offsets = [0]
        for short, ftype, offset, _ in self.fields:
            if ftype in STRING_TYPES:
                for r in range(self.records):
                    rec = blob[self.data_start + r * self.record_bytes:self.data_start + (r + 1) * self.record_bytes]
                    v = (int.from_bytes(rec, 'big') >> (len(rec) * 8 - offset - 32)) & 0xFFFFFFFF
                    if v != 0xFFFFFFFF:
                        offsets.append(v)
        offsets = [o for o in offsets if o] or [len(self.strings)]
        self.tree = huffman_tree(self.strings, min(offsets)) if self.huffman else None

    def rows(self):
        out = []
        for r in range(self.records):
            rec = self.blob[self.data_start + r * self.record_bytes:self.data_start + (r + 1) * self.record_bytes]
            row = decode_record(rec, self.fields)
            for short, ftype, _, _ in self.fields:
                if ftype in STRING_TYPES:
                    off = row[short]
                    if off == 0xFFFFFFFF or off >= len(self.strings):
                        row[short] = ''
                    elif self.huffman:
                        row[short] = huffman_decode(self.strings, off, self.tree, ftype == 14).decode('utf-8', 'replace')
                    else:
                        size = 2 if ftype == 14 else 1
                        n = int.from_bytes(self.strings[off:off + size], 'big')
                        row[short] = self.strings[off + size:off + size + n].decode('utf-8', 'replace')
            out.append(row)
        return out


def huffman_tree(block, tree_bytes):
    """[(child0, child1)] per node: ('n', index) or ('l', byte)."""
    nodes = []
    for i in range(tree_bytes // 4):
        pair = []
        for k in (0, 2):
            a, b = block[4 * i + k], block[4 * i + k + 1]
            pair.append(('l', b) if a == 0 else ('n', a))
        nodes.append(tuple(pair))
    return nodes


def huffman_decode(block, offset, tree, long=False):
    """A string's bytes: its length (1 byte, or 2 for a type-14 field), then its code."""
    n = int.from_bytes(block[offset:offset + 2], 'big') if long else block[offset]
    p, bit, node, out = offset + (2 if long else 1), 0, 0, bytearray()
    while len(out) < n and p < len(block):
        b = (block[p] >> (7 - bit)) & 1
        bit += 1
        if bit == 8:
            bit, p = 0, p + 1
        kind, v = tree[node][b]
        if kind == 'l':
            out.append(v)
            node = 0
        else:
            node = v
    return bytes(out)


MAX_CODE_BITS = 11  # the game's own tables never use longer codes (its decoder may not take them)


def code_lengths(freq, limit):
    """Optimal code lengths no longer than limit bits (package-merge)."""
    symbols = sorted(freq, key=lambda x: (freq[x], x))
    if len(symbols) == 1:
        return {symbols[0]: 1}
    leaves = [(freq[x], (x,)) for x in symbols]
    current = list(leaves)
    for _ in range(limit - 1):
        packages = [(current[i][0] + current[i + 1][0], current[i][1] + current[i + 1][1])
                    for i in range(0, len(current) - 1, 2)]
        current = sorted(leaves + packages, key=lambda t: t[0])
    lengths = {x: 0 for x in symbols}
    for _, members in current[:2 * len(symbols) - 2]:
        for x in members:
            lengths[x] += 1
    return lengths


def huffman_build(strings):
    """A tree for these strings' bytes, as the game's block begins with it, and each byte's code (bits): a
    canonical code of at most MAX_CODE_BITS bits a byte, inner nodes numbered breadth-first from the root (0)."""
    freq = {}
    for s in strings:
        for x in s:
            freq[x] = freq.get(x, 0) + 1
    if len(freq) < 2:  # a tree needs two leaves
        for x in (32, 101):
            freq.setdefault(x, 1)
    lengths = code_lengths(freq, MAX_CODE_BITS)
    codes, code, prev = {}, 0, 0
    for x in sorted(lengths, key=lambda x: (lengths[x], x)):
        code <<= lengths[x] - prev
        prev = lengths[x]
        codes[x] = format(code, f'0{prev}b')
        code += 1
    root = {}
    for x, bits in codes.items():
        node = root
        for b in bits[:-1]:
            node = node.setdefault(b, {})
        node[bits[-1]] = x
    order, queue = [], [root]
    while queue:
        node = queue.pop(0)
        order.append(node)
        queue += [node[b] for b in '01' if isinstance(node[b], dict)]
    if len(order) > 255:
        raise ValueError('too many different characters for one Huffman tree')
    index = {id(n): i for i, n in enumerate(order)}
    tree = bytearray()
    for node in order:
        for b in '01':
            child = node[b]
            tree += bytes([index[id(child)], 0]) if isinstance(child, dict) else bytes([0, child])
    return bytes(tree), codes


def huffman_encode(raw, codes, long=False):
    bits = ''.join(codes[x] for x in raw)
    bits += '0' * (-len(bits) % 8)
    return length_prefix(raw, long) + bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))


def length_prefix(raw, long):
    return len(raw).to_bytes(2 if long else 1, 'big')


def get_bits(rec, offset, bits):
    value = int.from_bytes(rec, 'big')
    total = len(rec) * 8
    return (value >> (total - offset - bits)) & ((1 << bits) - 1)


def decode_record(rec, fields):
    values = {}
    big = int.from_bytes(rec, 'big')
    total = len(rec) * 8
    for short, ftype, offset, bits in fields:
        if ftype == 0:  # fixed-length string
            raw = rec[offset // 8:offset // 8 + bits // 8]
            values[short] = raw.split(b'\0')[0].decode('utf-8', 'replace')
        elif ftype in STRING_TYPES:  # an offset into the string block
            values[short] = (big >> (total - offset - 32)) & 0xFFFFFFFF
        elif ftype == 4 and bits == 32:  # float
            values[short] = struct.unpack('>f', ((big >> (total - offset - 32)) & 0xFFFFFFFF).to_bytes(4, 'big'))[0]
        else:
            values[short] = (big >> (total - offset - bits)) & ((1 << bits) - 1)
    return values


def encode_record(values, fields, record_bytes, template=None):
    total = record_bytes * 8
    big = int.from_bytes(template, 'big') if template else 0
    strings = []
    for short, ftype, offset, bits in fields:
        v = values[short]
        if ftype in STRING_TYPES:
            bits = 32
        if ftype == 0:
            strings.append((offset // 8, bits // 8, str(v).encode('utf-8')[:bits // 8 - 1]))
            continue
        if ftype == 4 and bits == 32:
            v = int.from_bytes(struct.pack('>f', float(v)), 'big')
        v = int(v) & ((1 << bits) - 1)
        shift = total - offset - bits
        big = (big & ~(((1 << bits) - 1) << shift)) | (v << shift)
    rec = bytearray(big.to_bytes(record_bytes, 'big'))
    for start, length, raw in strings:
        rec[start:start + length] = raw.ljust(length, b'\0')
    return bytes(rec)


def read_db(path):
    d = open(path, 'rb').read()
    if d[:2] != b'DB':
        raise SystemExit(f'{path}: not a t3db database (unpack it from the archive first)')
    count = struct.unpack('>I', d[16:20])[0]
    base = 24 + 8 * count + 4
    index = []
    for i in range(count):
        short = d[24 + 8 * i:28 + 8 * i].decode('latin1')
        offset = struct.unpack('>I', d[28 + 8 * i:32 + 8 * i])[0]
        index.append((short, offset))
    order = sorted(index, key=lambda x: x[1])
    ends = {s: (order[k + 1][1] if k + 1 < len(order) else len(d) - base) for k, (s, _) in enumerate(order)}
    tables = [Table(s, d[base + off:base + ends[s]]) for s, off in index]
    return d[:16], tables


def max_length(ftype):
    return 65535 if ftype == 14 else 255


def build_table(t, rows=None):
    """The table's bytes, with new rows (dicts by field short name) or its own."""
    if rows is None:
        data = t.blob[t.data_start:t.data_end]
        strings = t.strings
        n, n_valid = t.records2, t.records
    else:
        strings = bytearray()
        placed = {}
        out = bytearray()
        codes = None
        if t.huffman:
            texts = [str(v[short]).encode('utf-8')[:max_length(ftype)] for v in rows
                     for short, ftype, _, _ in t.fields if ftype in STRING_TYPES and str(v[short])]
            tree, codes = huffman_build(texts)
            strings += tree
        for values in rows:
            values = dict(values)
            for short, ftype, _, _ in t.fields:
                if ftype in STRING_TYPES:
                    text = str(values[short])
                    if not text:
                        values[short] = 0xFFFFFFFF
                        continue
                    key = (ftype == 14, text)
                    if key not in placed:
                        raw = text.encode('utf-8')[:max_length(ftype)]
                        placed[key] = len(strings)
                        strings += (huffman_encode(raw, codes, ftype == 14) if codes is not None
                                    else length_prefix(raw, ftype == 14) + raw)
                    values[short] = placed[key]
            out += encode_record(values, t.fields, t.record_bytes)
        data, strings = bytes(out), bytes(strings)
        n = n_valid = len(rows)
    head = struct.pack('>IIIIHHIB', t.version, t.record_bytes, t.record_bits, len(strings), n_valid, n, t.unk,
                       t.nfields) + t.pad
    head += struct.pack('>I', crc(head))
    if rows is None:  # exactly as it was (the game's padding after the strings varies)
        body = t.blob[36:len(t.blob) - 4]
    else:
        body = t.blob[36:t.fields_end] + data + strings
        body += b'\0' * (-(36 + len(body)) % 4)
    return head + body + struct.pack('>I', crc(body))


def write_db(path, head16, tables, blobs):
    count = len(tables)
    index = bytearray()
    body = bytearray()
    offsets = {}
    # Same order of tables in the file as in the index (the game's files have them so).
    for t, blob in zip(tables, blobs):
        offsets[t.short] = len(body)
        body += blob
    for t in tables:
        index += t.short.encode('latin1') + struct.pack('>I', offsets[t.short])
    size = 24 + len(index) + 4 + len(body)
    header = bytearray(head16[:8]) + struct.pack('>II', size, 0) + struct.pack('>I', count)
    header += struct.pack('>I', crc(bytes(header)))
    out = bytes(header) + bytes(index) + struct.pack('>I', crc(bytes(index))) + bytes(body)
    open(path, 'wb').write(out)
    return out



# The locale's strings (data/loc/<lang>.db, one table, LanguageStrings): looked up by the hash of their id. The
# game reads data/loc/<lang>_upd.db (with <lang>_upd-meta.xml, whose database must be named <lang>_upd) beside
# its own when it is there, and takes a string from it first: an update needs only the strings it changes.
_CRC_TABLE = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ 0xEDB88320 if _c & 1 else _c >> 1
    _CRC_TABLE.append(_c)


def string_hash(stringid):
    """A string id's hash (the record's raw hashid): CRC-32's table, each byte with bit 5 cleared (so letters
    are upper case), from 0 and without the final inversion (the game's sub_826191D8)."""
    h = 0
    for c in stringid.encode('utf-8'):
        h = _CRC_TABLE[((c & 0xDF) ^ h) & 0xFF] ^ (h >> 8)
    return h


LANGUAGE_META = '''\ufeff<?xml version="1.0" encoding="utf-8"?>
<!--This is the meta XML file for a t3db database.-->
<database name="{name}" shortname="u_up" writename="{name}_write" writeshortname="etup" version="6">
  <parameters />
  <indices>
    <index shortname="ppiA" tableshortname="GJCv">
      <indexfields>
        <indexfield shortname="jKhj" sortdirection="0" />
      </indexfields>
    </index>
  </indices>
  <table name="LanguageStrings" shortname="GJCv" difflistproperty="ENABLED">
    <fields>
      <field name="hashid" shortname="jKhj" type="DBOFIELDTYPE_INTEGER" depth="32" null="False" rangehigh="2147483647" rangelow="-2147483648" key="True" />
      <field name="stringid" shortname="VhAs" type="DBOFIELDTYPE_STRING" depth="800" null="False" rangehigh="0" rangelow="0" />
      <field name="sourcetext" shortname="bYbZ" type="DBOFIELDTYPE_STRING" depth="32000" null="False" rangehigh="0" rangelow="0" />
    </fields>
  </table>
</database>
'''


def language_db(path, strings):
    """Writes a locale database of these strings ({id: text}) as the game's own are made (Huffman-coded, the
    records in hash order for the index)."""
    head = struct.pack('>IIIIHHIB', 0x42, 16, 127, 0, 0, 0, 0xFFFF, 3) + bytes(7)
    head += struct.pack('>I', crc(head))
    fields = b''.join(struct.pack('>II4sI', ftype, offset, short.encode('latin1'), bits)
                      for short, ftype, offset, bits in (('VhAs', 13, 0, 800), ('bYbZ', 14, 32, 32000),
                                                          ('jKhj', 3, 64, 32)))
    table = Table('GJCv', head + fields)
    rows = [{'VhAs': i, 'bYbZ': text, 'jKhj': string_hash(i)} for i, text in strings.items()]
    rows.sort(key=lambda r: r['jKhj'])
    write_db(path, b'DB\0\x08\x01\0\0\0', [table], [build_table(table, rows)])


def language_meta(path, name):
    with open(path, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(LANGUAGE_META.format(name=name))


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd, db, meta = argv[0], argv[1], argv[2]
    names = read_meta(meta)
    head16, tables = read_db(db)
    if cmd == 'info':
        for t in sorted(tables, key=lambda t: names.get(t.short, (t.short,))[0]):
            tname = names.get(t.short, (t.short, {}))[0]
            print(f'{tname:40} {t.records:6} records, {len(t.fields):3} fields, {t.record_bytes} bytes each'
                  + (f', {t.string_bytes} bytes of compressed strings' if t.string_bytes else ''))
        return 0
    if cmd == 'export':
        out = argv[3]
        os.makedirs(out, exist_ok=True)
        for t in tables:
            tname, fmeta = names.get(t.short, (t.short, {}))
            cols = [(s, fmeta.get(s, (s, '', 0))) for s, _, _, _ in t.fields]
            with open(os.path.join(out, tname + '.csv'), 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow([c[1][0] for c in cols])
                for row in t.rows():
                    w.writerow([row[s] + m[2] if isinstance(row[s], int) else row[s] for s, m in cols])
        print(f'{len(tables)} tables to {out}')
        return 0
    if cmd == 'import':
        src, out = argv[3], argv[4]
        blobs = []
        for t in tables:
            tname, fmeta = names.get(t.short, (t.short, {}))
            path = os.path.join(src, tname + '.csv')
            if not os.path.exists(path):
                blobs.append(build_table(t))
                continue
            by_name = {fmeta.get(s, (s,))[0]: (s, fmeta.get(s, (s, '', 0))[2]) for s, _, _, _ in t.fields}
            rows = []
            with open(path, newline='', encoding='utf-8') as f:
                for r in csv.DictReader(f):
                    values = {}
                    for col, (s, low) in by_name.items():
                        ftype = next(ft for fs, ft, _, _ in t.fields if fs == s)
                        v = r[col]
                        values[s] = v if ftype == 0 or ftype in STRING_TYPES else (float(v) if ftype == 4 else int(v) - low)
                    rows.append(values)
            if len(rows) > MAX_RECORDS:
                raise SystemExit(f'{tname}: {len(rows)} records, more than a table holds ({MAX_RECORDS})')
            blobs.append(build_table(t, rows))
            print(f'{tname}: {len(rows)} records (was {t.records})')
        write_db(out, head16, tables, blobs)
        print(f'wrote {out}')
        return 0
    if cmd == 'check':
        original = open(db, 'rb').read()
        rebuilt = write_db(os.devnull, head16, tables, [build_table(t) for t in tables])
        print('identical' if rebuilt == original else f'different ({len(rebuilt)} against {len(original)} bytes)')
        return 0 if rebuilt == original else 1
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
