#!/usr/bin/env python3
"""Ports newer FC minifaces to the Xbox 360 FIFA 19 UI.

  minifaces.py CONFIG GAME MOD [REPORT.json [FC27.json [PLAYERS.csv]]]

CONFIG lists real-player packs in oldest-to-newest order (a RAR of DDS files, or an FC .fifamod) and optionally
a generated-player pack. Real players keep EA's stable ``heads/p<player id>.dds`` naming; later packs win, while
an older pack fills ids the newer one omits, the newer pack's generic beta placeholders are rejected, and a
patterned backdrop gives way to an older pack's clean cutout for the same player.

The optional FC27.json (the update's fc27.py report) maps the game's player ids to the dump's player ids; those
pictures are copied under the ids the update gives matched-by-name and new players, where the stable name differs.
With PLAYERS.csv (the update's players table) the converter also drops pictures no database player uses and
coincidental FC pictures under ids the update assigned from CONFIG's ``assigned_from`` (260,000 by default).

This game uses 128x128, one-level DXT5 DDS files. Newer games use 180x180 DXT5, so every source is decoded,
alpha-safe Lanczos resized, recompressed and written with the same DDS header as the game's own minifaces.

Generated players are different: newer FC games request sequential ``youthheads/p460000...`` assets, while this
game requests one of the 1,007 generic ``playerheads`` appearance keys. The clean male pictures from the newer
pack are therefore matched to the game's generic pictures by colour, hair and silhouette. Empty and visibly
checker-patterned beta pictures are rejected. This makes the pack useful instead of installing paths this game
never asks for.

FETM v2/v3 .fifamod files store legacy DDS files as Frostbite Oodle blocks. Their legacy paths and blocks are in
the same order; out/tools/ooz-x86 (also used by fbmod.py) decodes blocks in batches.
"""
import csv
import hashlib
import json
import multiprocessing
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dds  # noqa: E402
import modgame  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OOZ = os.path.join(ROOT, 'out', 'tools', 'ooz-x86')
PLAYER = re.compile(r'^p(\d+)\.dds$', re.I)


def source_path(config_path, path):
    return path if os.path.isabs(path) else os.path.join(os.path.dirname(os.path.dirname(config_path)), path)


def decode_dxt5(data, width, height):
    """Vectorised equivalent of dds.decode(..., DXT5)."""
    import numpy as np
    block_width, block_height = (width + 3) // 4, (height + 3) // 4
    blocks = np.frombuffer(data, dtype=np.uint8, count=block_width * block_height * 16).reshape(-1, 16)
    count = len(blocks)
    rows = np.arange(count)

    a0, a1 = blocks[:, 0].astype(np.int32), blocks[:, 1].astype(np.int32)
    alpha_palette = np.empty((count, 8), dtype=np.int32)
    alpha_palette[:, 0], alpha_palette[:, 1] = a0, a1
    greater = a0 > a1
    for index in range(6):
        smooth = ((6 - index) * a0 + (index + 1) * a1) // 7
        if index < 4:
            stepped = ((4 - index) * a0 + (index + 1) * a1) // 5
        else:
            stepped = np.full(count, 0 if index == 4 else 255)
        alpha_palette[:, index + 2] = np.where(greater, smooth, stepped)
    alpha_bits = np.zeros(count, dtype=np.uint64)
    for byte in range(6):
        alpha_bits |= blocks[:, 2 + byte].astype(np.uint64) << (byte * 8)
    alpha_index = ((alpha_bits[:, None] >> (np.arange(16, dtype=np.uint64) * 3)) & 7).astype(np.intp)
    alpha = alpha_palette[rows[:, None], alpha_index]

    c0 = blocks[:, 8].astype(np.int32) | (blocks[:, 9].astype(np.int32) << 8)
    c1 = blocks[:, 10].astype(np.int32) | (blocks[:, 11].astype(np.int32) << 8)

    def from565(colour):
        return np.stack((((colour >> 11) & 31) * 255 // 31,
                         ((colour >> 5) & 63) * 255 // 63,
                         (colour & 31) * 255 // 31), axis=1)

    first, second = from565(c0), from565(c1)
    colours = np.stack((first, second, (2 * first + second) // 3, (first + 2 * second) // 3), axis=1)
    colour_bits = np.zeros(count, dtype=np.uint32)
    for byte in range(4):
        colour_bits |= blocks[:, 12 + byte].astype(np.uint32) << (byte * 8)
    colour_index = ((colour_bits[:, None] >> (np.arange(16, dtype=np.uint32) * 2)) & 3).astype(np.intp)
    rgba = np.empty((count, 16, 4), dtype=np.uint8)
    rgba[:, :, :3] = colours[rows[:, None], colour_index]
    rgba[:, :, 3] = alpha
    rgba = rgba.reshape(block_height, block_width, 4, 4, 4).transpose(0, 2, 1, 3, 4)
    return rgba.reshape(block_height * 4, block_width * 4, 4)[:height, :width].tobytes()


def dds_rgba(raw):
    """A source DDS as a Pillow RGBA image."""
    from PIL import Image
    if raw[:4] != b'DDS ' or len(raw) < 128:
        raise ValueError('not a DDS')
    h, w = struct.unpack_from('<II', raw, 12)
    pf_flags, = struct.unpack_from('<I', raw, 80)
    tagged = raw[84:88]
    # Several beta youth DDS files forgot DDPF_FOURCC even though the field and payload are valid DXT5.
    fourcc = tagged if (pf_flags & 4 or tagged in (b'DXT1', b'DXT3', b'DXT5')) else None
    pixels = decode_dxt5(raw[128:], w, h) if fourcc == b'DXT5' else dds.decode(raw[128:], w, h, fourcc)
    return Image.frombytes('RGBA', (w, h), pixels)


def encode_dxt5(rgba, width, height):
    """Vectorised equivalent of dds.encode_dxt(..., DXT5) for portrait-sized batches."""
    import numpy as np
    pixels = np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4)
    if width % 4 or height % 4:
        pixels = np.pad(pixels, ((0, -height % 4), (0, -width % 4), (0, 0)), mode='edge')
    blocks = pixels.reshape(pixels.shape[0] // 4, 4, pixels.shape[1] // 4, 4, 4)
    blocks = blocks.transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4).astype(np.int32)
    count = len(blocks)
    out = np.empty((count, 16), dtype=np.uint8)

    alpha = blocks[:, :, 3]
    a0, a1 = alpha.max(axis=1), alpha.min(axis=1)
    palette = np.empty((count, 8), dtype=np.int32)
    palette[:, 0], palette[:, 1] = a0, a1
    for index in range(6):
        palette[:, index + 2] = ((6 - index) * a0 + (index + 1) * a1) // 7
    alpha_index = np.abs(alpha[:, :, None] - palette[:, None, :]).argmin(axis=2).astype(np.uint64)
    alpha_bits = np.sum(alpha_index << (np.arange(16, dtype=np.uint64) * 3), axis=1)
    out[:, 0], out[:, 1] = a0, a1
    for byte in range(6):
        out[:, 2 + byte] = alpha_bits >> (byte * 8)

    rgb = blocks[:, :, :3]
    score = rgb[:, :, 0] * 3 + rgb[:, :, 1] * 6 + rgb[:, :, 2]
    solid = alpha > 16
    valid = solid | ~solid.any(axis=1)[:, None]
    rows = np.arange(count)
    lo = rgb[rows, np.where(valid, score, 1 << 30).argmin(axis=1)]
    hi = rgb[rows, np.where(valid, score, -1).argmax(axis=1)]

    def to565(colour):
        return (((colour[:, 0] * 31 + 127) // 255) << 11
                | ((colour[:, 1] * 63 + 127) // 255) << 5
                | ((colour[:, 2] * 31 + 127) // 255))

    c0, c1 = to565(hi), to565(lo)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)

    def from565(colour):
        return np.stack((((colour >> 11) & 31) * 255 // 31,
                         ((colour >> 5) & 63) * 255 // 63,
                         (colour & 31) * 255 // 31), axis=1)

    first, second = from565(c0), from565(c1)
    colours = np.stack((first, second, (2 * first + second) // 3, (first + 2 * second) // 3), axis=1)
    distance = ((rgb[:, :, None, :] - colours[:, None, :, :]) ** 2).sum(axis=3)
    colour_index = distance.argmin(axis=2).astype(np.uint32)
    colour_bits = np.sum(colour_index << (np.arange(16, dtype=np.uint32) * 2), axis=1, dtype=np.uint32)
    colour_bits[c0 == c1] = 0
    out[:, 8], out[:, 9] = c0, c0 >> 8
    out[:, 10], out[:, 11] = c1, c1 >> 8
    for byte in range(4):
        out[:, 12 + byte] = colour_bits >> (byte * 8)
    return out.tobytes()


def alpha_stats(image):
    """(holes, edge, opaque, transparent): how much a portrait's alpha is a screen-door coverage pattern."""
    import numpy as np
    from PIL import Image, ImageFilter
    alpha = np.asarray(image.convert('RGBA'), dtype=np.int16)[:, :, 3]
    opaque = alpha > 240
    transparent = alpha < 15
    covered = Image.fromarray((opaque * 255).astype(np.uint8)).filter(ImageFilter.BoxBlur(1))
    neighbour = np.asarray(covered, dtype=np.float32) / 255.0
    # An isolated transparent pixel inside an otherwise opaque area: the pack's malformed DXT5 alpha writes
    # index 6 (FIFA's unused 0 alpha) inside blocks whose two endpoints are both 255.
    holes = float(np.mean(transparent & (neighbour > 0.7))) if transparent.any() else 0.0
    edge = max(float(np.mean(np.abs(np.diff(alpha, axis=0)))),
               float(np.mean(np.abs(np.diff(alpha, axis=1)))))
    return holes, edge, float(np.mean(opaque)), float(np.mean(transparent))


def beta_picture(image):
    """True for the FC 27 real-player pack's unrecoverable beta images: no alpha holes, only noise."""
    _, _, opaque, transparent = alpha_stats(image)
    return opaque > 0.95 and transparent < 0.01


def repair_coverage(image):
    """The pack's screen-door alpha turned into an ordinary cutout.
    Its alpha averages about 0.9 over the player and 0.15-0.3 over the pattern behind, so a blurred coverage
    threshold separates them; the Lanczos resize to 128 leaves soft cutout edges again. A high threshold (0.75)
    also drops the bright checkerboard patches some pictures carry behind the head."""
    from PIL import Image, ImageFilter
    alpha = image.convert('RGBA').getchannel('A')
    radius = max(2, round(min(alpha.size) / 60))
    mask = alpha.filter(ImageFilter.BoxBlur(radius)).point(lambda value: 255 if value >= 191 else 0)
    image = image.convert('RGBA')
    image.putalpha(mask)
    return image


def game_dds(image, repair_alpha=False):
    """Image as the exact useful portion of a game miniface: 128x128 DXT5, one level, no archive padding."""
    from PIL import Image
    if repair_alpha:
        holes, edge, _, _ = alpha_stats(image)
        # FC 25 minifaces have a clean cutout; FC 27's screen-door alpha has holes in every solid area (and a
        # high-frequency edge). Only the latter needs the coverage mask, so FC 25's own soft edges are kept.
        if holes > 0.002 or edge > 12.0:
            image = repair_coverage(image)
    # Premultiplied resizing prevents dark/coloured fringes around hair and shoulders.
    image = image.convert('RGBa').resize((128, 128), Image.Resampling.LANCZOS).convert('RGBA')
    # Pillow's DXT5 writer introduces a visible alpha checker on these portraits. The project's encoder is
    # deterministic and keeps the smooth cutout intact.
    payload = encode_dxt5(image.tobytes(), 128, 128)
    pf = struct.pack('<II4sIIIII', 32, 4, b'DXT5', 0, 0, 0, 0, 0)
    header = struct.pack('<4sIIIIIII', b'DDS ', 124, 0x81007, 128, 128, len(payload), 0, 0)
    header += bytes(44) + pf + struct.pack('<IIIII', 0x1002, 0, 0, 0, 0)
    return header + payload


def fifamod_entries(path, folder):
    """[(name, compressed Frostbite block)] for one legacy image folder in an FETM v2/v3 .fifamod."""
    data = open(path, 'rb').read()
    if data[:4] != b'FETM' or data[4] not in (2, 3):
        raise ValueError(f'{path}: unsupported .fifamod (expected FETM v2/v3)')
    pattern = re.compile(rb'data/ui/imgAssets/' + re.escape(folder.encode()) + rb'/([^\x00-\x1f/]{1,80}\.dds)', re.I)
    matches = list(pattern.finditer(data))
    if not matches:
        raise ValueError(f'{path}: no {folder} legacy DDS files')
    table_end = max(m.end() for m in matches)
    at = data.find(b'\x00\x00\x7f\x10', table_end)
    if at < 0:
        raise ValueError(f'{path}: miniface data blocks not found')
    # Each resource record contains the SHA-1 of its stored block shortly before the legacy path. FETM uses
    # variable-length integers there, so the exact gap varies. Index the small possible window, then match the
    # actual blocks by hash. This also handles added assets whose RES/chunk records are interleaved in the data.
    candidates = {}
    for m in matches:
        name = m.group(1).decode('ascii')
        for gap in range(20, 65):
            start = m.start() - gap
            if start >= 0:
                candidates.setdefault(data[start:start + 20], []).append(name)
    out, found = [], set()
    while at + 8 <= len(data) and len(found) < len(matches):
        size = int.from_bytes(data[at:at + 4], 'big') & 0xffffff
        code = int.from_bytes(data[at + 4:at + 6], 'big')
        packed = int.from_bytes(data[at + 6:at + 8], 'big') + ((code & 0x0f) << 16)
        end = at + 8 + packed
        if not size or not packed or end > len(data) or code >> 8 not in (0x00, 0x02, 0x0f, 0x11, 0x15, 0x19):
            break
        frame = data[at:end]
        names = candidates.get(hashlib.sha1(frame).digest(), ())
        name = next((n for n in names if n not in found), None)
        if name is not None:
            if size != 32528 or code >> 8 not in (0x11, 0x15, 0x19):
                raise ValueError(f'{path}: {name} is not an Oodle-compressed 180x180 DDS')
            out.append((name, frame))
            found.add(name)
        at = end
    if len(found) != len(matches):
        missing = [m.group(1).decode('ascii') for m in matches if m.group(1).decode('ascii') not in found]
        # A mod may carry an unchanged legacy resource record (resource index -1), which deliberately has no data.
        if len(missing) > 10:
            raise ValueError(f'{path}: matched {len(found)} of {len(matches)} legacy DDS blocks; missing {missing[:3]}')
        print(f"{os.path.basename(path)}: {', '.join(missing)} has no image data, skipped")
    return out


def decode_oodle(entries, batch=512):
    """Yield (name, raw DDS), decoding many Oodle frames per helper invocation."""
    if not os.path.exists(OOZ):
        raise SystemExit(f'{OOZ} missing: sh tools/modding/build_ooz.sh')
    command = ['arch', '-x86_64', OOZ] if platform.system() == 'Darwin' else [OOZ]
    with tempfile.TemporaryDirectory(prefix='fifa-minifaces-ooz-') as tmp:
        src, dst = os.path.join(tmp, 'in'), os.path.join(tmp, 'out')
        for start in range(0, len(entries), batch):
            group = entries[start:start + batch]
            sizes = []
            with open(src, 'wb') as f:
                for _, frame in group:
                    size = int.from_bytes(frame[:4], 'big') & 0xffffff
                    code = int.from_bytes(frame[4:6], 'big')
                    packed = int.from_bytes(frame[6:8], 'big') + ((code & 0x0f) << 16)
                    f.write(struct.pack('<II', packed, size) + frame[8:8 + packed])
                    sizes.append(size)
            subprocess.run(command + [src, dst], check=True, stdout=subprocess.DEVNULL)
            raw, pos = open(dst, 'rb').read(), 0
            if len(raw) != sum(sizes):
                raise ValueError(f'{OOZ}: returned {len(raw)} bytes, expected {sum(sizes)}')
            for (name, _), size in zip(group, sizes):
                yield name, raw[pos:pos + size]
                pos += size


def rar_ids(path):
    listing = subprocess.check_output(['bsdtar', '-tf', path], text=True)
    return {int(m.group(1)) for line in listing.splitlines() if (m := PLAYER.match(os.path.basename(line)))}


def fifamod_ids(path, folder):
    return {int(m.group(1)) for name, _ in fifamod_entries(path, folder) if (m := PLAYER.match(name))}


def framed_picture(image, band=6):
    """True when the picture has a full backdrop rather than a cutout: its top/side edges are mostly opaque."""
    import numpy as np
    alpha = np.asarray(image.convert('RGBA'))[:, :, 3] > 128
    edge = np.concatenate((alpha[:band, :].ravel(), alpha[:, :band].ravel(), alpha[:, -band:].ravel()))
    return float(np.mean(edge)) > 0.5


def _converted(task):
    ident, raw, repair_alpha, strict = task
    image = dds_rgba(raw)
    # A few FC 27 files are beta placeholders: a noise texture with a full alpha channel. There is no portrait to
    # recover, so leave the path to an older pack (or the game's generic picture).
    if repair_alpha and beta_picture(image):
        return ident, None
    # When an older pack has the same player, prefer its clean cutout over FC 27's patterned backdrop. An
    # FC 27-only picture keeps its backdrop: a portrait is better than the generic one.
    if repair_alpha and strict and framed_picture(image):
        return ident, None
    return ident, game_dds(image, repair_alpha=repair_alpha)


def write_converted(tasks, outdir):
    """Convert independent pictures across CPU cores and write them as they finish; returns the ids written."""
    written = set()
    workers = max(1, min(8, os.cpu_count() or 1))
    # macOS defaults to ``spawn``.  Besides being much slower for this large
    # batch, that mode cannot start workers when the converter is imported by
    # a validation script running on stdin.  The converter is Unix-only (its
    # other helpers rely on bsdtar), so use copy-on-write workers when present.
    methods = multiprocessing.get_all_start_methods()
    context = multiprocessing.get_context('fork' if 'fork' in methods else methods[0])
    with context.Pool(workers) as pool:
        for ident, raw in pool.imap_unordered(_converted, tasks, chunksize=8):
            if raw is None:
                continue
            with open(os.path.join(outdir, f'p{ident}.dds'), 'wb') as f:
                f.write(raw)
            written.add(ident)
    return written


def write_real_pack(spec, path, wanted, outdir, strict_ids=()):
    if spec['kind'] == 'rar':
        with tempfile.TemporaryDirectory(prefix='fifa-minifaces-rar-') as tmp:
            subprocess.run(['bsdtar', '-xf', path, '-C', tmp], check=True)
            files = {}
            for root, _, names in os.walk(tmp):
                for name in names:
                    if (m := PLAYER.match(name)) and int(m.group(1)) in wanted:
                        files[int(m.group(1))] = os.path.join(root, name)
            tasks = ((ident, open(files[ident], 'rb').read(), True, ident in strict_ids)
                     for ident in sorted(files))
            return write_converted(tasks, outdir)
    elif spec['kind'] == 'fifamod':
        entries = [(name, frame) for name, frame in fifamod_entries(path, spec.get('folder', 'heads'))
                   if (m := PLAYER.match(name)) and int(m.group(1)) in wanted]
        tasks = ((int(PLAYER.match(name).group(1)), raw, True, int(PLAYER.match(name).group(1)) in strict_ids)
                 for name, raw in decode_oodle(entries))
        return write_converted(tasks, outdir)
    else:
        raise ValueError(f"{path}: unknown source kind {spec['kind']}")


def assign_pictures(mapping, heads):
    """Copy FC pictures to the ids the update's database gives their players (hard links when possible).
    Returns the target ids that have a correct picture. A target whose source is missing is not returned, so the
    caller can drop a coincidental direct picture left under a newly assigned id. Sources are staged first: a DB
    id can equal another player's FC id, and replacing that path before reading it must not feed the wrong face
    into a later copy."""
    assigned = set()
    staged = {}
    staging = tempfile.mkdtemp(prefix='.minifaces-', dir=heads)
    try:
        for target, source in sorted(mapping.items()):
            src = os.path.join(heads, f'p{source}.dds')
            if not os.path.exists(src):
                continue
            if target == source:
                assigned.add(int(target))
                continue
            tmp = os.path.join(staging, f'p{target}.dds')
            try:
                os.link(src, tmp)
            except OSError:
                shutil.copyfile(src, tmp)
            staged[target] = tmp
        for target, tmp in sorted(staged.items()):
            os.replace(tmp, os.path.join(heads, f'p{target}.dds'))
            assigned.add(int(target))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return assigned


def keep_database_pictures(heads, players_csv, assigned_from, assigned, remapped, sources):
    """Drop pictures the database has no player for, coincidental FC pictures under newly assigned ids, a direct
    picture under a DB id that the mapping says belongs to another FC player (no fallback picture), and a direct
    picture whose FC player was used as another database player's picture."""
    with open(players_csv, newline='', encoding='utf-8-sig') as f:
        database = {int(row['playerid']) for row in csv.DictReader(f) if row.get('playerid', '').isdigit()}
    removed = 0
    for name in os.listdir(heads):
        match = PLAYER.match(name)
        if not match:
            continue
        ident = int(match.group(1))
        keep = ident in database and (ident in assigned or
                                      (ident < assigned_from and ident not in remapped
                                       and ident not in sources))
        if not keep:
            os.unlink(os.path.join(heads, name))
            removed += 1
    return removed


def unchunkzip(data):
    """The playerheads archive uses chunkzip; handle it in-process instead of spawning 1,007 tools."""
    if data[:8] != b'chunkzip':
        return modgame.unchunked(data)
    total, chunk, count = struct.unpack_from('>III', data, 12)
    pos, out = 0x28, bytearray()
    for _ in range(count):
        pos = (pos + 8 + 15) // 16 * 16 - 8
        packed, kind = struct.unpack_from('>II', data, pos)
        pos += 8
        want = min(chunk, total - len(out))
        body = data[pos:pos + packed]
        out += body[:want] if kind == 0 or packed == want else zlib.decompress(body, -15)
        pos += packed
    if len(out) != total:
        raise ValueError(f'chunkzip returned {len(out)} bytes, expected {total}')
    return bytes(out)


def generic_heads(game):
    """{appearance key: RGBA image} from the game's nested playerHeads archive."""
    archive = os.path.join(game, 'data', 'ui', 'imgAssets', 'playerHeads', '2dheads.big')
    entries = modgame.read_big(archive)
    data, out = open(archive, 'rb').read(), {}
    for name, offset, size in entries:
        m = re.search(r'/p(\d+)\.dds$', name, re.I)
        if m:
            out[int(m.group(1))] = dds_rgba(unchunkzip(data[offset:offset + size]))
    if not out:
        raise ValueError(f'{archive}: no generic player heads')
    return out


def image_feature(image):
    """Small premultiplied portrait descriptor: face/hair colour plus transparent silhouette."""
    import numpy as np
    from PIL import Image
    im = image.convert('RGBa').resize((8, 8), Image.Resampling.LANCZOS).convert('RGBA')
    a = np.asarray(im, dtype=np.float32) / 255.0
    rgb = a[:, :, :3] * a[:, :, 3:4]
    # Silhouette is weighted more strongly than clothes/background colour.
    return np.concatenate((rgb.reshape(-1), (a[:, :, 3] * 1.5).reshape(-1)))


def clean_generated(image, max_edge):
    """Reject blank/incomplete pictures and the beta pack's obvious alpha checker pattern."""
    import numpy as np
    a = np.asarray(image.convert('RGBA'), dtype=np.int16)[:, :, 3]
    center = a[max(0, a.shape[0] // 12):a.shape[0] * 5 // 6, a.shape[1] // 8:a.shape[1] * 7 // 8]
    opaque = float(np.mean(center > 240))
    edge = max(float(np.mean(np.abs(np.diff(center, axis=0)))), float(np.mean(np.abs(np.diff(center, axis=1)))))
    return 0.18 < opaque < 0.90 and edge <= max_edge, opaque, edge


def write_generated(spec, path, game, outdir):
    import numpy as np
    targets = generic_heads(game)
    entries = [(name, frame) for name, frame in fifamod_entries(path, spec.get('folder', 'youthheads'))
               if (m := PLAYER.match(name)) and int(m.group(1)) <= spec.get('male_max_id', 2 ** 31 - 1)]
    candidates, rejected = [], 0
    with tempfile.TemporaryDirectory(prefix='fifa-generated-heads-') as tmp:
        raw_path = os.path.join(tmp, 'candidates.dds')
        offsets = {}
        with open(raw_path, 'wb') as store:
            for name, raw in decode_oodle(entries):
                ident = int(PLAYER.match(name).group(1))
                try:
                    image = dds_rgba(raw)
                except Exception:
                    # The beta contains a few partially written DDS files; they are not candidates for the port.
                    rejected += 1
                    continue
                clean, opaque, edge = clean_generated(image, spec.get('max_alpha_edge_score', 12.0))
                if not clean:
                    rejected += 1
                    continue
                offsets[ident] = (store.tell(), len(raw))
                store.write(raw)
                candidates.append((ident, image_feature(image), opaque, edge))
        if len(candidates) < len(targets):
            raise ValueError(f'{path}: only {len(candidates)} clean generated pictures for {len(targets)} keys')

        candidate_features = np.stack([x[1] for x in candidates])
        target_ids = sorted(targets)
        target_features = np.stack([image_feature(targets[i]) for i in target_ids])
        # Squared Euclidean distances without a 1007 x N x feature temporary.
        distances = ((target_features * target_features).sum(1)[:, None]
                     + (candidate_features * candidate_features).sum(1)[None, :]
                     - 2 * target_features @ candidate_features.T)
        order = np.argsort(distances, axis=1)
        # Assign the most constrained/closest targets first, keeping every portrait unique.
        target_order = np.argsort(distances.min(axis=1))
        used, mapping = set(), {}
        for ti in target_order:
            ci = next(int(x) for x in order[ti] if int(x) not in used)
            used.add(ci)
            mapping[target_ids[int(ti)]] = candidates[ci][0]

        def generated_tasks():
            with open(raw_path, 'rb') as store:
                for target in sorted(mapping):
                    source = mapping[target]
                    offset, size = offsets[source]
                    store.seek(offset)
                    yield target, store.read(size), False, False
        write_converted(generated_tasks(), outdir)
    return mapping, len(candidates), rejected


def main(argv):
    if len(argv) not in (4, 5, 6, 7):
        print(__doc__, file=sys.stderr)
        return 2
    config_path, game, mod = map(os.path.abspath, argv[1:4])
    report_path = os.path.abspath(argv[4]) if len(argv) >= 5 else None
    pictures_path = os.path.abspath(argv[5]) if len(argv) >= 6 else None
    players_path = os.path.abspath(argv[6]) if len(argv) == 7 else None
    config = json.load(open(config_path))
    real = []
    for spec in config.get('real', []):
        path = source_path(config_path, spec['path'])
        if not os.path.exists(path):
            print(f"{spec['name']}: missing ({path}), skipped")
            continue
        ids = rar_ids(path) if spec['kind'] == 'rar' else fifamod_ids(path, spec.get('folder', 'heads'))
        real.append((spec, path, ids))
    if not real and not config.get('generated'):
        print('no miniface sources')
        return 0

    heads = os.path.join(mod, 'data', 'ui', 'imgassets', 'heads')
    playerheads = os.path.join(mod, 'data', 'ui', 'imgassets', 'playerheads')
    os.makedirs(heads, exist_ok=True)
    report = {'real': [], 'generated': None}
    written_by = {}
    done = set()
    # Newest first. A pack only fills the ids no newer pack wrote: an id whose newest file is a rejected beta
    # placeholder is not marked done, so the next older pack's usable picture takes it. An id that an older pack
    # also has is processed strictly: a patterned FC 27 backdrop gives way to the older pack's clean cutout.
    order = list(reversed(real))
    older_after = [set() for _ in order]
    older = set()
    for i in range(len(order) - 1, -1, -1):
        older_after[i] = set(older)
        older |= order[i][2]
    for i, (spec, path, ids) in enumerate(order):
        mine = ids - done
        if not mine:
            continue
        written = write_real_pack(spec, path, mine, heads, mine & older_after[i])
        done |= written
        written_by[spec['name']] = written
        print(f"{spec['name']}: {len(written)} real-player minifaces")
    for spec, path, ids in real:  # report in the config's oldest-to-newest order
        if spec['name'] in written_by:
            report['real'].append({'name': spec['name'], 'source': os.path.basename(path),
                                   'written': len(written_by[spec['name']])})

    assigned = set()
    remapped = set()
    sources = set()
    pairs = {}
    if pictures_path and os.path.exists(pictures_path):
        pictures = json.load(open(pictures_path)).get('pictures') or {}
        pairs = {str(k): str(v) for k, v in pictures.items()
                 if str(k).lstrip('-').isdigit() and str(v).lstrip('-').isdigit()}
        remapped = {int(k) for k, v in pairs.items() if k != v}
        sources = {int(v) for k, v in pairs.items() if k != v}
        assigned = assign_pictures(pairs, heads)
        print(f"assigned {len(assigned)} real-player pictures to the update's player ids")
    report['assigned'] = len(assigned)

    if players_path and pictures_path and pairs and os.path.exists(players_path) and os.path.exists(pictures_path):
        removed = keep_database_pictures(heads, players_path, int(config.get('assigned_from', 260000)),
                                         assigned, remapped, sources)
        report['removed'] = removed
        print(f"left out {removed} pictures for players not in the update's database")
    report['kept'] = len([n for n in os.listdir(heads) if PLAYER.match(n)])

    generated = config.get('generated')
    if generated:
        path = source_path(config_path, generated['path'])
        if os.path.exists(path):
            os.makedirs(playerheads, exist_ok=True)
            mapping, clean, rejected = write_generated(generated, path, game, playerheads)
            report['generated'] = {'name': generated['name'], 'source': os.path.basename(path),
                                   'written': len(mapping), 'clean_candidates': clean, 'rejected': rejected,
                                   'mapping': {str(k): v for k, v in sorted(mapping.items())}}
            print(f"{generated['name']}: {len(mapping)} generic playerheads from {clean} clean pictures "
                  f"({rejected} incomplete/checkered rejected)")
        else:
            print(f"{generated['name']}: missing ({path}), skipped")
    if report_path:
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
            f.write('\n')
    print(f"minifaces: {sum(x['written'] for x in report['real'])} real, "
          f"{report['generated']['written'] if report['generated'] else 0} generated, "
          f"{report['assigned']} assigned, {report['kept']} in the mod")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
