"""Extract all RTXT string-table entries from the installed BHD PFF archives.

Writes a lossless JSONL source plus a review-friendly CSV. The source bytes,
archive/member/index identity, and RTXT metadata are retained for later rebuilds.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = ("localres.pff", "resource.pff", "EXP1.pff")
DEFAULT_OUT = ROOT / "ThaiPatch" / "translation"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def extract_archive(path):
    archive_hash = sha256(path)
    rows = []
    file_size = path.stat().st_size
    with path.open("rb") as f:
        header = f.read(20)
        if len(header) != 20:
            raise ValueError(f"Truncated PFF header: {path.name}")
        count, stride, directory = struct.unpack_from("<III", header, 8)
        if stride != 36 or directory + count * stride > file_size:
            raise ValueError(f"Invalid PFF directory bounds: {path.name}")
        f.seek(directory)
        table = f.read(count * stride)
        if len(table) != count * stride:
            raise ValueError(f"Truncated PFF directory: {path.name}")

        for member_number in range(count):
            record = table[member_number * stride:(member_number + 1) * stride]
            _, offset, size, _ = struct.unpack_from("<4I", record)
            raw_name = record[16:32].split(b"\0", 1)[0]
            name = raw_name.decode("ascii", errors="strict")
            if offset < 20 or offset + size > directory:
                raise ValueError(f"Invalid member bounds: {path.name}:{name}")
            if not name.lower().endswith(".bin"):
                continue
            f.seek(offset)
            data = f.read(size)
            if len(data) != size or data[:4] != b"RTXT":
                continue
            if size < 16:
                raise ValueError(f"Truncated RTXT member: {path.name}:{name}")
            string_count = struct.unpack_from("<I", data, 12)[0]
            string_base = 16 + 16 * string_count
            if string_base > size:
                raise ValueError(f"Invalid RTXT record table: {path.name}:{name}")

            for index in range(string_count):
                record_start = 16 + index * 16
                record_bytes = data[record_start:record_start + 16]
                relative = struct.unpack_from("<I", record_bytes)[0]
                start = string_base + relative
                if start < string_base or start >= size:
                    raise ValueError(
                        f"Invalid string offset: {path.name}:{name}[{index}]"
                    )
                end = data.find(b"\0", start)
                if end < 0:
                    raise ValueError(
                        f"Unterminated string: {path.name}:{name}[{index}]"
                    )
                raw_text = data[start:end]
                rows.append({
                    "id": f"{path.name}/{name}/{index:04d}",
                    "archive": path.name,
                    "archive_sha256": archive_hash,
                    "member": name,
                    "member_index": member_number,
                    "string_index": index,
                    "record_hex": record_bytes.hex(),
                    "source_bytes_hex": raw_text.hex(),
                    "source_encoding": "cp1252 (original bytes retained in source_bytes_hex)",
                    "source": raw_text.decode("cp1252", errors="replace"),
                    "translation": "",
                })
    return rows


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    with pending.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    pending.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    all_rows = []
    for archive in ARCHIVES:
        path = ROOT / archive
        if not path.is_file():
            raise SystemExit(f"Missing archive: {path}")
        rows = extract_archive(path)
        all_rows.extend(rows)
        print(f"{archive}: extracted {len(rows)} RTXT strings")

    jsonl_path = args.out_dir / "game_text_source.jsonl"
    csv_path = args.out_dir / "game_text_source.csv"
    write_jsonl(jsonl_path, all_rows)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        fields = ["id", "archive", "member", "string_index", "source", "translation"]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Total: {len(all_rows)} strings")
    print("JSONL:", jsonl_path)
    print("CSV:  ", csv_path)


if __name__ == "__main__":
    main()
