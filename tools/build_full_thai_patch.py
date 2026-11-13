"""Build all translated RTXT strings and per-font Thai glyph atlases.

The game is byte-oriented. Translated entries are marked and stored as UTF-8;
ThaiRuntime.dll shapes marked strings into atlas carriers immediately before
the original renderer measures/draws them.
"""
import csv
import hashlib
import importlib.util
import json
import math
import struct
from collections import defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "ThaiPatch"
CSV_PATH = PATCH / "translation" / "game_text_th_latest.csv"
OUT = PATCH / "build-full-thai"
BACKUPS = {
    "localres.pff": PATCH / "backup" / "localres.pff.before-thai-campaign",
    "EXP1.pff": PATCH / "backup" / "EXP1.pff.before-thai-localization",
    "resource.pff": (PATCH / "backup" / "resource.pff.original")
    if (PATCH / "backup" / "resource.pff.original").is_file()
    else (ROOT / "resource.pff"),
}
MARKER = b"\x01THAI\x01"
FIRST_CARRIER, LAST_CARRIER = 0x82, 0xFE
FONT_RECORDS = 224
FONT_HEADER = 32 + FONT_RECORDS * 20
PAGE_BYTES = 256 * 256 * 4


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_rows():
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 6700 or not {"id", "archive", "member", "string_index", "source", "translation"}.issubset(rows[0]):
        raise ValueError("The latest full-game translation CSV is missing or incomplete")
    return rows


def thai_clusters(s):
    """Keep leading vowels, bases, and following marks in one shaped glyph."""
    out = []
    i = 0
    while i < len(s):
        start = i
        cp = ord(s[i])
        if 0x0E40 <= cp <= 0x0E44 and i + 1 < len(s) and 0x0E01 <= ord(s[i + 1]) <= 0x0E2E:
            i += 2
        elif 0x0E01 <= cp <= 0x0E2E:
            i += 1
        else:
            i += 1
        while i < len(s) and (0x0E31 <= ord(s[i]) <= 0x0E3A or
                              0x0E47 <= ord(s[i]) <= 0x0E4E or ord(s[i]) == 0x0E33):
            i += 1
        # A standalone non-ASCII scalar (punctuation, etc.) also gets a glyph.
        out.append(s[start:i])
    return out


def safe_carriers(rows):
    used = set()
    for r in rows:
        try:
            used.update(b for b in (r.get("source") or "").encode("cp1252") if FIRST_CARRIER <= b <= LAST_CARRIER)
        except UnicodeEncodeError:
            pass
    return [b for b in range(FIRST_CARRIER, LAST_CARRIER + 1) if b not in used]


def parse_pff(data):
    count, stride, directory = struct.unpack_from("<III", data, 8)
    if stride != 36 or directory + count * stride > len(data):
        raise ValueError("Unexpected PFF directory layout")
    table = bytearray(data[directory:])
    members = {}
    for i in range(count):
        rec = table[i * stride:(i + 1) * stride]
        offset, size = struct.unpack_from("<II", rec, 4)
        name = rec[16:32].split(b"\0", 1)[0].decode("ascii")
        if offset < 20 or offset + size > directory:
            raise ValueError(f"Invalid PFF bounds: {name}")
        members[name.lower()] = (i, offset, size, name)
    return directory, table, members


def parse_rtxt(data):
    if data[:4] != b"RTXT":
        raise ValueError("Expected RTXT resource")
    n = struct.unpack_from("<I", data, 12)[0]
    base = 16 + n * 16
    entries = []
    max_end = base
    for i in range(n):
        rel = struct.unpack_from("<I", data, 16 + i * 16)[0]
        start = base + rel
        end = data.find(b"\0", start)
        if start < base or end < 0:
            raise ValueError(f"Malformed RTXT entry {i}")
        entries.append((start, end))
        max_end = max(max_end, end + 1)
    return n, base, entries, max_end


def rebuild_rtxt(data, replacements):
    n, base, entries, max_end = parse_rtxt(data)
    table = bytearray(data[:base])
    pool = bytearray()
    for i, (start, end) in enumerate(entries):
        value = replacements.get(i, data[start:end])
        struct.pack_into("<I", table, 16 + i * 16, len(pool))
        pool.extend(value)
        pool.append(0)
    # Preserve opaque bytes that follow all referenced strings. RTXT stores
    # the length of this first block at +4 and the opaque trailing block at
    # +8; keeping the old first length makes the game allocate too little
    # space for translated strings and corrupt its heap during resource load.
    rebuilt = bytearray(table + pool + data[max_end:])
    first_block_size = struct.unpack_from("<I", data, 4)[0]
    struct.pack_into("<I", rebuilt, 4, first_block_size + len(rebuilt) - len(data))
    return bytes(rebuilt)


def load_renderer():
    path = PATCH / "tools" / "build_menu_test.py"
    spec = importlib.util.spec_from_file_location("thai_menu_renderer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def font_target_height(font_bytes):
    heights = []
    for i in range(FONT_RECORDS):
        _, _, v0, _, v1 = struct.unpack_from("<I4f", font_bytes, 32 + i * 20)
        h = round((v1 - v0) * 256)
        if h > 0:
            heights.append(h)
    if not heights:
        raise ValueError("Font has no measurable glyphs")
    heights.sort()
    return heights[len(heights) // 2]


def pack_cluster_atlases(glyphs, target_height, max_pages=None):
    pack_h = target_height
    while True:
        pages = []
        page = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
        x = y = row_h = 2
        rects = {}
        for cluster, source in glyphs.items():
            alpha = source.getchannel("A")
            bbox = alpha.getbbox()
            if not bbox:
                raise ValueError(f"Empty shaped cluster {cluster!r}")
            # Preserve the common baseline/mark position; trim only horizontal padding.
            crop = source.crop((bbox[0], 0, bbox[2], source.height))
            w = max(1, round(crop.width * pack_h / crop.height))
            crop = crop.resize((w, pack_h), Image.Resampling.LANCZOS)
            pad_r = max(2, round(pack_h * 0.20))
            adv_w = crop.width + pad_r
            if adv_w > 250 or pack_h > 250:
                raise ValueError(f"Glyph too large for FNT0 atlas: {cluster!r}")
            if x + adv_w + 2 > 256:
                x, y, row_h = 2, y + row_h + 2, 0
            if y + pack_h + 2 > 256:
                pages.append(page)
                page = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
                x = y = row_h = 2
            page.alpha_composite(crop, (x, y))
            rects[cluster] = (len(pages), x / 256, y / 256,
                              (x + adv_w) / 256, (y + pack_h) / 256)
            x += adv_w + 2
            row_h = max(row_h, pack_h)
        if x > 2 or y > 2:
            pages.append(page)
        if max_pages is None or len(pages) <= max_pages or pack_h <= 10:
            return pages, rects
        pack_h -= 1


def build():
    OUT.mkdir(exist_ok=True)
    rows = read_rows()
    carriers = safe_carriers(rows)
    if len(carriers) < 32:
        raise ValueError("Not enough unused high-byte glyph slots")
    translated = {}
    clusters = set()
    for row in rows:
        text = (row.get("translation") or "").strip()
        if not text or text.casefold() == "null":
            continue
        key = (row["archive"].lower(), row["member"].lower(), int(row["string_index"]))
        translated[key] = text
        for c in thai_clusters(text):
            if any(ord(ch) > 127 for ch in c):
                clusters.add(c)

    # Render all unique Thai graphemes once with GDI's Unicode shaper.
    renderer = load_renderer()
    sorted_clusters = sorted(clusters)
    renderer.LABELS = [(i, 0x20, c) for i, c in enumerate(sorted_clusters)]
    rendered = renderer.render_labels(max_glyph_width=240, max_glyph_height=256)
    rendered_by_cluster = dict(zip(sorted_clusters, rendered))

    # Build full replacement string tables from pristine archives.
    changed = {}
    for archive, path in BACKUPS.items():
        source = path.read_bytes()
        _, table, members = parse_pff(source)
        replacements_by_member = defaultdict(dict)
        for (a, member, index), text in translated.items():
            if a != archive.lower() or member not in members:
                continue
            # The splash artwork already contains a baked-in "Current Player" label
            # and name at the lower right. Hide the redundant live overlay row.
            if archive.lower() == "localres.pff" and member == "menutxt.bin" and index == 218:
                replacements_by_member[member][index] = MARKER + b"\x01HIDE\x01"
            else:
                replacements_by_member[member][index] = MARKER + text.encode("utf-8")
        directory, table, members = parse_pff(source)
        trailer = source[directory + len(table):]
        output = bytearray(source[:directory])
        for member, changes in replacements_by_member.items():
            if member.endswith(".fnt"):
                continue
            _, off, size, _ = members[member]
            blob = source[off:off + size]
            if blob[:4] != b"RTXT":
                continue
            new_blob = rebuild_rtxt(blob, changes)
            i = members[member][0]
            struct.pack_into("<II", table, i * 36 + 4, len(output), len(new_blob))
            output.extend(new_blob)
            changed.setdefault(archive, []).append(member)

        # Embed a cluster atlas in each font at the font's own glyph height.
        if archive.lower() == "localres.pff":
            font_maps = {}
            atlas_page_counts = {}
            base_pages_by_height = {}
            for name, (_, off, size, _) in members.items():
                if not name.endswith(".fnt"): continue
                font = source[off:off + size]
                if font[:4] != b"FNT0": continue
                h = font_target_height(font)
                base_pages_by_height[h] = max(base_pages_by_height.get(h, 0), struct.unpack_from("<I", font, 8)[0])
            for name, (i, off, size, _) in members.items():
                if not name.endswith(".fnt"):
                    continue
                font = source[off:off + size]
                if font[:4] != b"FNT0":
                    continue
                old_pages = struct.unpack_from("<I", font, 8)[0]
                if len(font) != FONT_HEADER + old_pages * PAGE_BYTES:
                    raise ValueError(f"Unexpected font layout: {name}")
                height = font_target_height(font)
                base_pages = base_pages_by_height[height]
                pages, rects = pack_cluster_atlases(rendered_by_cluster, height, max_pages=16 - base_pages)
                if base_pages + len(pages) > 16:
                    raise ValueError(f"{name} would exceed renderer's 16-page table ({base_pages}+{len(pages)})")
                patched = bytearray(font)
                struct.pack_into("<I", patched, 8, base_pages + len(pages))
                blank_page = bytes(PAGE_BYTES)
                for _ in range(base_pages - old_pages):
                    patched.extend(blank_page)
                for page in pages:
                    patched.extend(page.tobytes("raw", "BGRA"))
                struct.pack_into("<II", table, i * 36 + 4, len(output), len(patched))
                output.extend(patched)
                font_maps[name] = {"target_height": height, "original_pages": old_pages}
                atlas_page_counts[height] = max(atlas_page_counts.get(height, 0), len(pages))
                changed.setdefault(archive, []).append(name)
            write_map(OUT / "thai_glyph_map.bin", rendered_by_cluster, font_maps, atlas_page_counts, base_pages_by_height, carriers)

        struct.pack_into("<I", output, 16, len(output))
        output.extend(table)
        output.extend(trailer)
        target = OUT / archive
        target.write_bytes(output)
        # Validate directory and every new member boundary.
        parse_pff(output)
        print(f"Built {archive}: {len(changed.get(archive, []))} members changed, {len(output):,} bytes")

    manifest = {
        "translations": len(translated), "unique_non_ascii_clusters": len(clusters),
        "carrier_bytes": [hex(x) for x in carriers], "changed_members": changed,
        "font_profiles": font_maps,
        "atlas_pages_by_height": atlas_page_counts,
        "base_pages_by_height": base_pages_by_height,
        "archives": {name: sha((OUT / name).read_bytes()) for name in BACKUPS},
        "method": "RTXT UTF-8 markers plus runtime cluster shaping into appended FNT0 atlases",
        "runtime_validation": "pending",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def write_map(path, glyphs, font_maps, atlas_page_counts, base_pages_by_height, carriers):
    # Height header stores height, atlas page count, original-page base.
    # Glyph records are: height:u8, cluster_len:u8, page:u8, UTF-8, UV floats.
    heights = sorted(atlas_page_counts)
    with path.open("wb") as f:
        f.write(b"THM1")
        f.write(struct.pack("<HHH", len(glyphs), len(carriers), len(heights)))
        f.write(bytes(carriers))
        for h in heights:
            f.write(struct.pack("<BBB", h, atlas_page_counts[h], base_pages_by_height[h]))
        for h in heights:
            pages, rects = pack_cluster_atlases(glyphs, h, max_pages=16 - base_pages_by_height[h])
            for cluster, (page, u0, v0, u1, v1) in rects.items():
                b = cluster.encode("utf-8")
                if len(b) > 64:
                    raise ValueError("Unexpectedly long grapheme cluster")
                f.write(struct.pack("<BBB", h, len(b), page))
                f.write(b)
                f.write(struct.pack("<4f", u0, v0, u1, v1))


if __name__ == "__main__":
    result = build()
    print(f"Built {result['translations']} translated strings across {len(result['archives'])} archives; "
          f"shaped {result['unique_non_ascii_clusters']} Unicode clusters.")
    for name, digest in result["archives"].items():
        print(f"{name}: {digest}")
