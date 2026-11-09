"""Frostbite textures in Frosty mods (fbmod.py's), as Pillow images.

A texture is a res (its header: mip offsets, format, size, mips, the chunk with its pixels, each mip's size) and
the chunk; the mips run largest first. The formats are FIFA 19's (TextureFormat): 55 BC1, 61 BC3, 67 BC7 (and the
sRGB twins one above), read through Pillow's DDS reader (a DX10 header put on).
"""
import io
import os
import struct
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fbmod  # noqa: E402

DXGI = {55: 71, 67: 98}
BYTES_PER_BLOCK = {71: 8, 72: 8, 80: 8}


def header(raw):
    fmt, = struct.unpack_from('<I', raw, 12)
    w, h = struct.unpack_from('<HH', raw, 0x16)
    mips = raw[0x1e]
    chunk = str(uuid.UUID(bytes_le=raw[0x20:0x30]))
    sizes = struct.unpack_from('<15I', raw, 0x30)[:mips]
    return {'format': fmt, 'width': w, 'height': h, 'mips': mips, 'chunk': chunk, 'sizes': sizes}


def dds_image(w, h, dxgi, data):
    """A block-compressed mip as RGBA (a size that isn't whole blocks: decoded at whole blocks, cropped)."""
    from PIL import Image
    width, height = w, h
    w, h = (w + 3) // 4 * 4, (h + 3) // 4 * 4
    flags = 0x1007 | 0x80000
    hdr = struct.pack('<4sIIIIIII44s', b'DDS ', 124, flags, h, w, len(data), 0, 1, b'\0' * 44)
    pf = struct.pack('<II4sIIIII', 32, 4, b'DX10', 0, 0, 0, 0, 0)
    caps = struct.pack('<IIIII', 0x1000, 0, 0, 0, 0)
    dx10 = struct.pack('<IIIII', dxgi, 3, 0, 1, 0)
    im = Image.open(io.BytesIO(hdr + pf + caps + dx10 + data)).convert('RGBA')
    return im if (w, h) == (width, height) else im.crop((0, 0, width, height))


class Textures:
    """The textures of one or more mods (later ones win), by their res names."""
    def __init__(self, paths):
        self.mods = [fbmod.Reader(p) for p in paths]
        self.res, self.chunks = {}, {}
        for m in self.mods:
            for r in m.resources:
                if r['type'] == 'res':
                    self.res[r['name']] = (m, r)
                elif r['type'] == 'chunk':
                    self.chunks[r['name']] = (m, r)

    def names(self):
        return self.res.keys()

    def image(self, name, max_size=None):
        """The texture's largest mip no bigger than max_size (a width), as RGBA."""
        m, r = self.res[name]
        h = header(fbmod.decompress(m.data(r)))
        if h['chunk'] not in self.chunks:
            return None
        cm, c = self.chunks[h['chunk']]
        data = fbmod.decompress(cm.data(c))
        w, hh, at = h['width'], h['height'], 0
        sizes = list(h['sizes'])
        while sizes and sum(sizes) > len(data):  # the largest mips are in another chunk: what this one has
            sizes.pop(0)
            w, hh = max(1, w // 2), max(1, hh // 2)
        h['sizes'] = sizes
        for size in h['sizes']:
            if max_size is None or w <= max_size or size == h['sizes'][-1]:
                return decode(h['format'], w, hh, data[at:at + size])
            at += size
            w, hh = max(1, w // 2), max(1, hh // 2)


def decode(fmt, w, h, data):
    """A mip as RGBA: the format's DXGI when known; else by its size (half a byte a pixel BC1; a byte BC7, or BC3
    when BC7 gives nothing: FIFA's enum isn't documented)."""
    if fmt in DXGI:
        return dds_image(w, h, DXGI[fmt], data)
    blocks = max(1, (w + 3) // 4) * max(1, (h + 3) // 4)
    if len(data) == blocks * 8:
        return dds_image(w, h, 71, data)
    for dxgi in (98, 77):
        im = dds_image(w, h, dxgi, data)
        if any(hi > 0 for lo, hi in im.getextrema()):
            return im
    return im
