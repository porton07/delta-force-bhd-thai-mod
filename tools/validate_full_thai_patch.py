"""Offline integrity check for the generated full-game Thai archives."""
import csv
import hashlib
import importlib.util
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("full_patch", ROOT / "ThaiPatch/tools/build_full_thai_patch.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


manifest = json.loads((builder.OUT / "manifest.json").read_text(encoding="utf-8"))
rows = list(csv.DictReader(builder.CSV_PATH.open("r", encoding="utf-8-sig", newline="")))
checked = 0
for archive, original_path in builder.BACKUPS.items():
    path = builder.OUT / archive
    if digest(path) != manifest["archives"][archive]:
        raise SystemExit(f"Archive hash mismatch: {archive}")
    original = original_path.read_bytes()
    candidate = path.read_bytes()
    _, _, old_members = builder.parse_pff(original)
    _, _, members = builder.parse_pff(candidate)
    changed_names = {x.lower() for x in manifest["changed_members"].get(archive, [])}
    if set(old_members) != set(members):
        raise SystemExit(f"PFF member list changed: {archive}")
    parsed = {}
    for name, (_, off, size, _) in members.items():
        blob = candidate[off:off + size]
        if name.endswith(".bin") and blob[:4] == b"RTXT":
            _, _, spans, _ = builder.parse_rtxt(blob)
            parsed[name] = (blob, spans)
    for row in rows:
        if row["archive"].lower() != archive.lower():
            continue
        value = (row.get("translation") or "").strip()
        if not value or value.casefold() == "null":
            continue
        name = row["member"].lower()
        if name not in parsed:
            raise SystemExit(f"Missing translated member: {row['id']}")
        blob, spans = parsed[name]
        a, b = spans[int(row["string_index"])]
        if row["archive"].lower() == "localres.pff" and name == "menutxt.bin" and int(row["string_index"]) == 218:
            expected = builder.MARKER + b"\x01HIDE\x01"
        else:
            expected = builder.MARKER + value.encode("utf-8")
        if blob[a:b] != expected:
            raise SystemExit(f"Translation mismatch: {row['id']}")
        checked += 1
    for name, (_, old_off, old_size, _) in old_members.items():
        _, new_off, new_size, _ = members[name]
        old_blob = original[old_off:old_off + old_size]
        new_blob = candidate[new_off:new_off + new_size]
        if name.endswith(".fnt") and name in changed_names:
            height = builder.font_target_height(old_blob)
            old_pages = struct.unpack_from("<I", old_blob, 8)[0]
            expected_pages = manifest["base_pages_by_height"][str(height)] + manifest["atlas_pages_by_height"][str(height)]
            if struct.unpack_from("<I", new_blob, 8)[0] != expected_pages:
                raise SystemExit(f"Font atlas page count mismatch: {archive}/{name}")
        elif name not in parsed and name not in changed_names and old_blob != new_blob:
            raise SystemExit(f"Unexpected non-text member change: {archive}/{name}")

map_data = (builder.OUT / "thai_glyph_map.bin").read_bytes()
if map_data[:4] != b"THM1":
    raise SystemExit("Glyph map signature mismatch")
clusters, carriers, heights = struct.unpack_from("<HHH", map_data, 4)
if checked != manifest["translations"] or clusters != manifest["unique_non_ascii_clusters"] or carriers < 100 or heights < 1:
    raise SystemExit("Manifest, glyph map, and translation CSV counts disagree")
print(f"PASS: {checked} translations, {clusters} shaped clusters, {heights} font profiles, 3 PFF archives")
