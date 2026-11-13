"""Translate extracted BHD RTXT strings to Thai through Google's free gtx endpoint.

This unofficial endpoint needs no key, but Google may change or rate-limit it.
The script keeps a cache and resumable JSONL output, and protects game tokens.
"""
import argparse
import csv
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = ROOT / "ThaiPatch" / "translation"
TOKEN_RE = re.compile(
    r"<[^<>]*>|\{[^{}]*\}|%%(?:[-+ #0-9.*]*[A-Za-z])?|%[-+ #0-9.*]*[A-Za-z]"
)
MARKER_RE = re.compile(r"ZXQPH(\d{4})QXZ", re.IGNORECASE)
ENDPOINT = "https://translate.googleapis.com/translate_a/single"
LAST_REQUEST = 0.0


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc


def write_jsonl_atomic(path, rows):
    pending = path.with_suffix(path.suffix + ".tmp")
    with pending.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    pending.replace(path)


def protect_tokens(text):
    tokens = []

    def replace(match):
        marker = f"ZXQPH{len(tokens):04d}QXZ"
        tokens.append(match.group(0))
        return marker

    return TOKEN_RE.sub(replace, text), tokens


def restore_tokens(text, tokens):
    seen = set()

    def replace(match):
        index = int(match.group(1))
        if index >= len(tokens):
            raise ValueError(f"Translation returned unknown token {match.group(0)}")
        seen.add(index)
        return tokens[index]

    restored = MARKER_RE.sub(replace, text)
    if len(seen) != len(tokens):
        missing = sorted(set(range(len(tokens))) - seen)
        raise ValueError(f"Translation lost protected game tokens: {missing}")
    return restored


def split_long_text(text, max_chars):
    """Split at paragraph/newline/space boundaries and retain separators."""
    remaining = text
    chunks = []
    while len(remaining) > max_chars:
        limit = max_chars
        cut = -1
        separator = 0
        for candidate in ("\r\n\r\n", "\n\n", "\r\n", "\n", " "):
            pos = remaining.rfind(candidate, 1, limit)
            if pos > cut:
                cut, separator = pos, len(candidate)
        if cut < 1:
            cut, separator = max_chars, 0
            # Never split a protected token marker in half.
            marker_start = remaining.rfind("ZXQPH", 0, cut)
            marker_end = remaining.find("QXZ", max(0, cut - 8))
            if marker_start >= 0 and marker_end >= cut - 1:
                cut = marker_start
        body = remaining[:cut]
        if not body:
            cut, separator = max_chars, 0
            body = remaining[:cut]
        suffix = remaining[cut:cut + separator]
        chunks.append((body, suffix))
        remaining = remaining[cut + separator:]
    if remaining:
        chunks.append((remaining, ""))
    return chunks


def translate_request(text, source_lang, target_lang, timeout):
    query = urlencode({
        "client": "gtx",
        "sl": source_lang,
        "tl": target_lang,
        "dt": "t",
        "q": text,
    })
    request = Request(
        f"{ENDPOINT}?{query}",
        headers={"User-Agent": "Mozilla/5.0 (compatible; BHD-Thai-Mod/1.0)"},
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    pieces = payload[0]
    return "".join(piece[0] for piece in pieces if piece and piece[0])


def google_translate(text, source_lang, target_lang, timeout, delay, retries, max_chars):
    global LAST_REQUEST
    protected, tokens = protect_tokens(text)
    translated_chunks = []
    for chunk, separator in split_long_text(protected, max_chars):
        error = None
        for attempt in range(retries + 1):
            try:
                pause = delay - (time.monotonic() - LAST_REQUEST)
                if pause > 0:
                    time.sleep(pause)
                LAST_REQUEST = time.monotonic()
                translated_chunks.append(translate_request(
                    chunk, source_lang, target_lang, timeout
                ))
                error = None
                break
            except (HTTPError, URLError, TimeoutError, ValueError, IndexError, KeyError) as exc:
                error = f"{type(exc).__name__}: {exc}"
                if attempt < retries:
                    wait = min(60.0, (2 ** attempt) + random.random())
                    print(f"Retry {attempt + 1}/{retries} after {error}; wait {wait:.1f}s",
                          file=sys.stderr)
                    time.sleep(wait)
        if error:
            raise RuntimeError(error)
        if separator:
            translated_chunks.append(separator)
    return restore_tokens("".join(translated_chunks), tokens)


def cache_key(text, source_lang, target_lang):
    return f"{source_lang}>{target_lang}:{text}"


def save_outputs(out_jsonl, out_csv, rows):
    write_jsonl_atomic(out_jsonl, rows)
    with out_csv.with_suffix(out_csv.suffix + ".tmp").open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        fields = ["id", "archive", "member", "string_index", "source", "translation"]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    out_csv.with_suffix(out_csv.suffix + ".tmp").replace(out_csv)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_DIR / "game_text_source.jsonl")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--source-lang", default="en", help="Google language code (default: en)")
    parser.add_argument("--target-lang", default="th", help="Google language code (default: th)")
    parser.add_argument("--delay", type=float, default=0.65,
                        help="Minimum pause between uncached requests in seconds")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--max-chars", type=int, default=1500,
                        help="Split long source strings at whitespace (default: 1500)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Translate at most this many untranslated rows; 0 means all")
    parser.add_argument("--force", action="store_true", help="Ignore cached and prior translations")
    args = parser.parse_args()
    if args.delay < 0 or args.timeout <= 0 or args.retries < 0 or args.max_chars < 200:
        parser.error("delay >= 0, timeout > 0, retries >= 0, and max-chars >= 200 required")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_jsonl = args.out_dir / "game_text_th.jsonl"
    out_csv = args.out_dir / "game_text_th.csv"
    cache_path = args.out_dir / "google_cache.json"
    errors_path = args.out_dir / "translation_errors.jsonl"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    prior = {}
    if out_jsonl.exists() and not args.force:
        prior = {row["id"]: row.get("translation", "") for row in read_jsonl(out_jsonl)}
    rows = list(read_jsonl(args.input))
    failures = []
    completed_this_run = 0

    for row in rows:
        text = row.get("source", "")
        if not text:
            row["translation"] = ""
            continue
        key = cache_key(text, args.source_lang, args.target_lang)
        existing = "" if args.force else prior.get(row["id"], "")
        if existing:
            row["translation"] = existing
            continue
        if not args.force and key in cache:
            row["translation"] = cache[key]
            continue
        if args.limit and completed_this_run >= args.limit:
            row["translation"] = ""
            continue

        error = None
        try:
            translation = google_translate(
                text, args.source_lang, args.target_lang, args.timeout,
                args.delay, args.retries, args.max_chars
            )
            cache[key] = translation
            row["translation"] = translation
            completed_this_run += 1
        except (HTTPError, URLError, TimeoutError, ValueError, IndexError, KeyError,
                RuntimeError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        if error:
            row["translation"] = ""
            failures.append({"id": row["id"], "error": error})
            print(f"FAILED {row['id']}: {error}", file=sys.stderr)
            # Stop on the first exhausted request. A blocked endpoint or
            # rate-limit should not trigger thousands of identical retries.
            save_outputs(out_jsonl, out_csv, rows)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
            write_jsonl_atomic(errors_path, failures)
            raise SystemExit(1)

        if completed_this_run and completed_this_run % 10 == 0:
            save_outputs(out_jsonl, out_csv, rows)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Progress: translated {completed_this_run} new rows")

    save_outputs(out_jsonl, out_csv, rows)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    write_jsonl_atomic(errors_path, failures)
    translated_count = sum(bool(row.get("translation")) for row in rows)
    print(f"Rows: {len(rows)}; translated: {translated_count}; failures this run: {len(failures)}")
    print("JSONL:", out_jsonl)
    print("CSV:  ", out_csv)
    print("Cache:", cache_path)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
