"""Build an isolated Thai campaign-screen experiment from the latest CSV.

This changes only a copy under ThaiPatch/build-campaign-test. It pre-rasterizes
the campaign labels and one mission briefing into atlas glyphs, avoiding edits
to the original game archive. The gameplay HUD and dialogue are not covered.
"""
import csv
import hashlib
import importlib.util
import json
import struct
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "ThaiPatch"
INPUT = PATCH / "translation" / "game_text_th_latest.csv"
BUILD = PATCH / "build-campaign-test"
EVIDENCE = PATCH / "evidence"
BASE_ARCHIVE = PATCH / "backup" / "localres.pff.before-thai-campaign"
EXPANSION_ARCHIVE = PATCH / "backup" / "EXP1.pff.before-thai-localization"
MENU_FONT = "Arial22.fnt"
BRIEF_FONT = "Arial20.fnt"
FIRST_CARRIER = 0x82
LAST_CARRIER = 0xFE

MENU_TEXT_IDS = [29, 31, 32, 166, 475]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load_rows():
    with INPUT.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 6717 or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Latest translation CSV is incomplete or has duplicate IDs")
    return rows


def safe_carriers(rows):
    """Choose high bytes unused by the original localres text strings."""
    occupied = set()
    for row in rows:
        try:
            encoded = (row.get("source") or "").encode("cp1252")
        except UnicodeEncodeError:
            encoded = (row.get("source") or "").encode("cp1252", errors="ignore")
        occupied.update(b for b in encoded if FIRST_CARRIER <= b <= LAST_CARRIER)
    return [b for b in range(FIRST_CARRIER, LAST_CARRIER + 1) if b not in occupied]


def load_renderer():
    spec = importlib.util.spec_from_file_location(
        "menu_builder", PATCH / "tools" / "build_menu_test.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_pff(data):
    count, stride, directory = struct.unpack_from("<III", data, 8)
    if stride != 36 or directory + count * stride > len(data):
        raise ValueError("Invalid PFF directory")
    table = bytearray(data[directory:directory + count * stride])
    members = {}
    for i in range(count):
        rec = table[i * stride:(i + 1) * stride]
        offset, size = struct.unpack_from("<II", rec, 4)
        name = rec[16:32].split(b"\0", 1)[0].decode("ascii")
        if offset < 20 or offset + size > directory:
            raise ValueError(f"Invalid member bounds: {name}")
        members[name.lower()] = (i, offset, size, name)
    return directory, table, members


def rtxt_strings(data):
    if data[:4] != b"RTXT":
        raise ValueError("Expected RTXT member")
    count = struct.unpack_from("<I", data, 12)[0]
    base = 16 + count * 16
    if base > len(data):
        raise ValueError("Invalid RTXT table")
    entries = []
    for index in range(count):
        rec = 16 + index * 16
        start = base + struct.unpack_from("<I", data, rec)[0]
        end = data.find(b"\0", start)
        if start < base or end < 0:
            raise ValueError(f"Invalid RTXT string {index}")
        entries.append((start, end))
    return entries


def replace_rtxt(data, index, replacement):
    out = bytearray(data)
    start, end = rtxt_strings(data)[index]
    if len(replacement) > end - start:
        raise ValueError(
            f"Replacement {index} is too long ({len(replacement)} > {end-start})"
        )
    out[start:end] = replacement + b"\0" * (end - start - len(replacement))
    return bytes(out)


def thai_clusters(text):
    """Small Thai grapheme approximation: lead vowels + consonant + marks."""
    result = []
    i = 0

    def mark(ch):
        n = ord(ch)
        return 0x0E31 <= n <= 0x0E3A or 0x0E47 <= n <= 0x0E4E

    def lead(ch):
        return 0x0E40 <= ord(ch) <= 0x0E44

    while i < len(text):
        start = i
        if lead(text[i]) and i + 1 < len(text) and 0x0E01 <= ord(text[i + 1]) <= 0x0E2E:
            i += 2
        else:
            i += 1
        while i < len(text) and mark(text[i]):
            i += 1
        result.append(text[start:i])
    return result


def chunk_brief(text, max_clusters=50, chunk_clusters=18):
    """Encode wrapped lines as short, independently rasterized glyph chunks."""
    visual_lines = []
    for paragraph in text.split("\n"):
        clusters = thai_clusters(paragraph)
        if not clusters:
            visual_lines.append([])
            continue
        for pos in range(0, len(clusters), max_clusters):
            visual_lines.append(clusters[pos:pos + max_clusters])

    chunks = []
    for line in visual_lines:
        if not line:
            chunks.append(("", True))
            continue
        line_chunks = [line[i:i + chunk_clusters]
                       for i in range(0, len(line), chunk_clusters)]
        for i, part in enumerate(line_chunks):
            value = "".join(part)
            # Glyph atlas rectangles omit leading/trailing spaces; keep a real
            # font-space byte between adjacent pre-rasterized chunks.
            leading = value.startswith(" ")
            trailing = value.endswith(" ")
            value = value.strip(" ")
            if not value:
                continue
            chunks.append((value, False))
            if trailing or (i + 1 < len(line_chunks) and leading):
                chunks.append((" ", False))
        chunks.append(("\n", True))
    return [s for s, is_newline in chunks], [is_newline for _, is_newline in chunks]


def pack_font(font_data, rendered, codes):
    font = bytearray(font_data)
    if font[:4] != b"FNT0":
        raise ValueError("Bad FNT0 font")
    old_pages = struct.unpack_from("<I", font, 8)[0]
    if len(font) != 4512 + old_pages * 262144:
        raise ValueError("Unexpected FNT0 size")
    pages = []
    page = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
    x = y = row_h = 2
    for code, glyph in zip(codes, rendered):
        if glyph.width > 252 or glyph.height > 252:
            raise ValueError(f"Glyph {code:#x} too large: {glyph.size}")
        if x + glyph.width + 2 > 256:
            x, y = 2, y + row_h + 2
            row_h = 0
        if y + glyph.height + 2 > 256:
            pages.append(page)
            page = Image.new("RGBA", (256, 256), (255, 255, 255, 0))
            x = y = row_h = 2
        page.paste(glyph, (x, y), glyph)
        page_index = old_pages + len(pages)
        struct.pack_into(
            "<I4f", font, 32 + (code - 32) * 20,
            page_index, x / 256, y / 256,
            (x + glyph.width) / 256, (y + glyph.height) / 256,
        )
        x += glyph.width + 2
        row_h = max(row_h, glyph.height)
    if pages or rendered:
        pages.append(page)
    struct.pack_into("<I", font, 8, old_pages + len(pages))
    for atlas in pages:
        font.extend(atlas.tobytes("raw", "BGRA"))
    return bytes(font), pages


def build():
    rows = load_rows()
    by_id = {r["id"]: r for r in rows}
    carriers = safe_carriers(rows)
    renderer = load_renderer()
    base = BASE_ARCHIVE.read_bytes()
    directory, table, members = parse_pff(base)
    exp_base = EXPANSION_ARCHIVE.read_bytes()
    exp_directory, exp_table, exp_members = parse_pff(exp_base)

    def get_member(name):
        _, offset, size, _ = members[name.lower()]
        return base[offset:offset + size]

    def get_exp_member(name):
        _, offset, size, _ = exp_members[name.lower()]
        return exp_base[offset:offset + size]

    # Replace fixed campaign-screen labels and campaign mission names with
    # one fully shaped glyph per displayed phrase.
    menu_member = bytearray(get_member("menutxt.bin"))
    menu_texts = []
    for index in MENU_TEXT_IDS:
        row = by_id[f"localres.pff/menutxt.bin/{index:04d}"]
        menu_texts.append(("localres.pff", "menutxt.bin", index, row["translation"]))
    # Campaign names displayed in the campaign selector.
    for index in (499, 500, 501):
        row = by_id[f"localres.pff/Game.bin/{index:04d}"]
        menu_texts.append(("localres.pff", "Game.bin", index, row["translation"]))
    # Find all mission title rows by matching them with the first line of each
    # translated summary. Index positions differ between mission files.
    missions_by_member = {}
    for row in rows:
        if (row["archive"] in ("localres.pff", "EXP1.pff") and
                row["member"].lower().startswith(("spbhd_", "tsbhd_"))):
            missions_by_member.setdefault((row["archive"], row["member"].lower()), []).append(row)
    title_members = []
    seen_title_ids = set()
    for (archive_name, _), mission_rows in missions_by_member.items():
        for summary in mission_rows:
            source = summary.get("source") or ""
            if (not summary.get("translation") or
                    ("Date:" not in source and "Time:" not in source) or
                    "<cFC8932>" in source):
                continue
            title = next((line.strip() for line in source.splitlines() if line.strip()), "")
            if not title:
                continue
            candidates = [r for r in mission_rows
                          if (r.get("source") or "").strip() == title and r.get("translation")]
            if not candidates:
                continue
            title_row = candidates[0]
            if title_row["id"] in seen_title_ids:
                continue
            seen_title_ids.add(title_row["id"])
            _, member, index = title_row["id"].rsplit("/", 2)
            title_members.append((archive_name, member, int(index), title_row["translation"]))
    labels = menu_texts + title_members
    if len(labels) > len(carriers):
        raise ValueError("Too many labels for available carrier bytes")
    menu_codes = carriers[:len(labels)]

    # Translate the briefings for every mission visible on this campaign page.
    # Archive entry indices differ: River Raid's title is /0000 and briefing
    # is /0001, while Marka and Bandit's Crossing use /0001 and /0002.
    briefing_specs = [
        ("localres.pff", "SPBHD_01.bin", 2, "localres.pff/SPBHD_01.bin/0002"),
        ("localres.pff", "SPBHD_02.bin", 2, "localres.pff/SPBHD_02.bin/0002"),
        ("localres.pff", "SPBHD_03.bin", 1, "localres.pff/SPBHD_03.bin/0001"),
        ("EXP1.pff", "tsbhd_01.bin", 37, "EXP1.pff/tsbhd_01.bin/0037"),
        ("EXP1.pff", "tsBHD_02.bin", 4, "EXP1.pff/tsBHD_02.bin/0004"),
        ("EXP1.pff", "tsbhd_03.bin", 53, "EXP1.pff/tsbhd_03.bin/0053"),
    ]
    briefing_jobs = []
    briefing_labels = []
    next_brief_carrier = 0
    for archive_name, member_name, string_index, row_id in briefing_specs:
        row = by_id[row_id]
        chunks, flags = chunk_brief(row["translation"])
        visible = [text for text in chunks if text not in ("", " ", "\n")]
        end = next_brief_carrier + len(visible)
        if end > len(carriers):
            raise ValueError("Campaign briefings need more carrier glyphs than available")
        codes = carriers[next_brief_carrier:end]
        next_brief_carrier = end
        encoded = bytearray()
        visible_index = 0
        for text in chunks:
            if text == "\n":
                encoded.extend(b"\n")
            elif text == " ":
                encoded.extend(b" ")
            elif text:
                code = codes[visible_index]
                briefing_labels.append((len(briefing_labels), code, text))
                encoded.append(code)
                visible_index += 1
        briefing_jobs.append((archive_name, member_name, string_index, bytes(encoded), len(visible)))

    # GDI shapes each complete Thai fragment. The existing menu experiment
    # supplies the same Windows Unicode rasterization path already validated.
    renderer.LABELS = [
        (i, code, text) for i, ((_, _, _, text), code) in
        enumerate(zip(labels, menu_codes))
    ]
    menu_glyphs = renderer.render_labels(max_glyph_width=1600, max_glyph_height=1600)
    renderer.LABELS = briefing_labels
    brief_glyphs = renderer.render_labels(max_glyph_width=1600, max_glyph_height=1600)
    # Match raster dimensions to the existing Arial atlas glyph height while
    # retaining Windows GDI's Thai mark placement.
    def fit_glyphs(glyphs, font):
        target_h = 17 if font == MENU_FONT else 15
        out = []
        for glyph in glyphs:
            alpha = glyph.getchannel("A")
            bbox = alpha.getbbox()
            if not bbox:
                raise ValueError("GDI returned an empty glyph")
            left, _, right, _ = bbox
            crop = glyph.crop((left, 0, right, glyph.height))
            width = max(1, round(crop.width * target_h / crop.height))
            crop = crop.resize((width, target_h), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (crop.width, crop.height), (255, 255, 255, 0))
            canvas.alpha_composite(crop)
            out.append(canvas)
        return out

    menu_glyphs = fit_glyphs(menu_glyphs, MENU_FONT)
    brief_glyphs = fit_glyphs(brief_glyphs, BRIEF_FONT)

    menu_font, menu_pages = pack_font(get_member(MENU_FONT), menu_glyphs, menu_codes)
    visible_brief_codes = [code for _, code, _ in briefing_labels]
    brief_font, brief_pages = pack_font(get_member(BRIEF_FONT), brief_glyphs,
                                        visible_brief_codes)

    replacements = {
        MENU_FONT.lower(): menu_font,
        BRIEF_FONT.lower(): brief_font,
        "menutxt.bin": get_member("menutxt.bin"),
    }
    exp_replacements = {}
    for (archive_name, name, index, _), code in zip(labels, menu_codes):
        key = name.lower()
        if archive_name == "localres.pff":
            replacements[key] = replace_rtxt(
                replacements.get(key, get_member(name)), index, bytes([code])
            )
        else:
            exp_replacements[key] = replace_rtxt(
                exp_replacements.get(key, get_exp_member(name)), index, bytes([code])
            )
    for archive_name, member_name, string_index, encoded, _ in briefing_jobs:
        key = member_name.lower()
        if archive_name == "localres.pff":
            member = replacements.get(key, get_member(member_name))
            replacements[key] = replace_rtxt(member, string_index, encoded)
        else:
            member = exp_replacements.get(key, get_exp_member(member_name))
            exp_replacements[key] = replace_rtxt(member, string_index, encoded)

    # Ensure title substitution did not damage River Raid's adjacent briefing.
    river_original = get_member("SPBHD_03.bin")
    river_patched = replacements["spbhd_03.bin"]
    river_brief_span = rtxt_strings(river_original)[1]
    if river_original[river_brief_span[0]:river_brief_span[1]] == river_patched[river_brief_span[0]:river_brief_span[1]]:
        raise AssertionError("River Raid briefing replacement was not applied")

    BUILD.mkdir(parents=True, exist_ok=True)
    def pack_archive(archive_data, archive_directory, archive_table,
                     archive_members, archive_replacements, filename):
        output = bytearray(archive_data[:archive_directory])
        for name, data in archive_replacements.items():
            index, _, _, _ = archive_members[name]
            struct.pack_into("<II", archive_table, index * 36 + 4, len(output), len(data))
            output.extend(data)
        struct.pack_into("<I", output, 16, len(output))
        output.extend(archive_table)
        output.extend(archive_data[archive_directory + len(archive_table):])
        target = BUILD / filename
        target.write_bytes(output)
        _, _, new_members = parse_pff(output)
        for name, (_, old_off, old_size, old_name) in archive_members.items():
            _, new_off, new_size, _ = new_members[name]
            expected = archive_replacements.get(name, archive_data[old_off:old_off + old_size])
            if output[new_off:new_off + new_size] != expected:
                raise AssertionError(f"PFF round-trip failed: {old_name}")
        return output

    output = pack_archive(base, directory, table, members, replacements, "localres.pff")
    exp_output = pack_archive(exp_base, exp_directory, exp_table, exp_members,
                              exp_replacements, "EXP1.pff")

    manifest = {
        "source_archives_sha256": {"localres.pff": digest(base), "EXP1.pff": digest(exp_base)},
        "test_archives_sha256": {"localres.pff": digest(output), "EXP1.pff": digest(exp_output)},
        "translation_csv_sha256": digest(INPUT.read_bytes()),
        "members_changed": {"localres.pff": list(replacements), "EXP1.pff": list(exp_replacements)},
        "campaign_labels_and_mission_titles": len(labels),
        "briefings_translated": len(briefing_jobs),
        "briefing_glyph_chunks": len(visible_brief_codes),
        "briefings": {f"{archive}/{name}/{index:04d}": {"glyph_chunks": count, "bytes": len(encoded)}
                      for archive, name, index, encoded, count in briefing_jobs},
        "mission_titles_translated": len(title_members),
        "scope": "campaign names and mission titles across the translated SPBHD/TSBHD records; six campaign summaries; gameplay objectives, OPORD briefings, HUD and dialogue remain untranslated",
        "validation": "all members in both archives round-tripped; original archive backups retained",
    }
    (BUILD / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Save the generated pages so their glyphs can be visually inspected.
    for prefix, pages in (("campaign-labels", menu_pages), ("campaign-briefings", brief_pages)):
        for i, page in enumerate(pages):
            page.save(EVIDENCE / f"{prefix}-{i+1}.png")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
