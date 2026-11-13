"""Build a reversible five-label Thai atlas experiment for BHD, without EXE edits.

Windows GDI shapes each complete Thai label before it is stored as an atlas glyph.
This is a menu experiment, not a Unicode renderer for arbitrary Thai strings.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
from pathlib import Path
import shutil
import struct
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'ThaiPatch'
BACKUP = PATCH / 'backup-menu-test'
BUILD = PATCH / 'build-menu-test'
EVIDENCE = PATCH / 'evidence'
LINE_SEED_FONT = PATCH / 'assets' / 'LINESeedSansTH_Bd.ttf'
LABELS = [
    # Use printable ASCII carrier bytes so the byte-oriented game renderer
    # cannot discard the labels as unsupported high-bit characters.
    (225, ord('~'), 'เล่นคนเดียว'),
    (221, ord('^'), 'เล่นหลายคน'),
    (216, ord('|'), 'ข้อมูลผู้เล่น'),
    (222, ord('_'), 'ตั้งค่าเกมนี้'),
    (219, ord('`'), 'ออกจากเกม'),
]


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def render_labels(max_glyph_width=252, max_glyph_height=42):
    """Rasterize full Thai labels with the LINE Seed Sans TH Bold font."""
    if not LINE_SEED_FONT.is_file():
        raise FileNotFoundError(
            'Place LINESeedSansTH_Bd.ttf from the official LINE Seed TH Desktop '
            'font package at ' + str(LINE_SEED_FONT))
    g = C.WinDLL('gdi32', use_last_error=True)
    g.CreateCompatibleDC.argtypes = [W.HDC]
    g.CreateCompatibleDC.restype = W.HDC
    g.CreateDIBSection.argtypes = [W.HDC, C.c_void_p, W.UINT,
                                  C.POINTER(C.c_void_p), W.HANDLE, W.DWORD]
    g.CreateDIBSection.restype = W.HBITMAP
    g.CreateFontW.argtypes = [C.c_int] * 5 + [W.DWORD] * 8 + [W.LPCWSTR]
    g.CreateFontW.restype = W.HFONT
    g.SelectObject.argtypes = [W.HDC, W.HANDLE]
    g.SelectObject.restype = W.HANDLE
    g.SetTextColor.argtypes = [W.HDC, W.DWORD]
    g.SetBkColor.argtypes = [W.HDC, W.DWORD]
    g.ExtTextOutW.argtypes = [W.HDC, C.c_int, C.c_int, W.UINT,
                             C.c_void_p, W.LPCWSTR, W.UINT, C.c_void_p]
    g.DeleteObject.argtypes = [W.HANDLE]
    g.DeleteDC.argtypes = [W.HDC]
    g.AddFontResourceExW.argtypes = [W.LPCWSTR, W.DWORD, W.LPVOID]
    g.AddFontResourceExW.restype = C.c_int
    g.RemoveFontResourceExW.argtypes = [W.LPCWSTR, W.DWORD, W.LPVOID]
    g.RemoveFontResourceExW.restype = W.BOOL
    width, height, scale = 1600, 256, 4
    font_path = str(LINE_SEED_FONT.resolve())
    if not g.AddFontResourceExW(font_path, 0x10, None):  # FR_PRIVATE
        raise C.WinError(C.get_last_error())
    dc = g.CreateCompatibleDC(None)
    bits = C.c_void_p()
    info = C.create_string_buffer(struct.pack('<IiiHHIIiiII', 40, width, -height,
                                             1, 32, 0, width * height * 4,
                                             0, 0, 0, 0))
    bitmap = g.CreateDIBSection(dc, info, 0, C.byref(bits), None, 0)
    font = g.CreateFontW(-32 * scale, 0, 0, 0, 700, 0, 0, 0, 222, 0, 0, 4, 0,
                         'LINE Seed Sans TH')
    if not dc or not bitmap or not font:
        g.RemoveFontResourceExW(font_path, 0x10, None)
        raise C.WinError(C.get_last_error())
    previous_bitmap = g.SelectObject(dc, bitmap)
    previous_font = g.SelectObject(dc, font)
    masks = []
    try:
        g.SetTextColor(dc, 0xffffff)
        g.SetBkColor(dc, 0)
        for _, _, text in LABELS:
            C.memset(bits, 0, width * height * 4)
            if not g.ExtTextOutW(dc, 24, 24, 0, None, text, len(text), None):
                raise C.WinError(C.get_last_error())
            g.GdiFlush()
            mask = Image.frombytes('RGB', (width, height),
                                   C.string_at(bits, width * height * 4), 'raw', 'BGRX').convert('L')
            bounds = mask.getbbox()
            if not bounds:
                raise RuntimeError('Empty Thai text raster')
            masks.append((mask, bounds))
    finally:
        g.SelectObject(dc, previous_font)
        g.SelectObject(dc, previous_bitmap)
        g.DeleteObject(font)
        g.DeleteObject(bitmap)
        g.DeleteDC(dc)
        g.RemoveFontResourceExW(font_path, 0x10, None)
    # A common vertical range keeps all baselines aligned and includes both marks.
    top = min(b[1] for _, b in masks) - 8
    bottom = max(b[3] for _, b in masks) + 8
    result = []
    for mask, bounds in masks:
        cropped = mask.crop((bounds[0] - 8, top, bounds[2] + 8, bottom))
        target_width = round(cropped.width / scale)
        target_height = round(cropped.height / scale)
        cropped = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)
        if cropped.height > max_glyph_height:
            target_width = round(cropped.width * max_glyph_height / cropped.height)
            cropped = cropped.resize((target_width, max_glyph_height), Image.Resampling.LANCZOS)
        glyph = Image.new('RGBA', (cropped.width, 44), (255, 255, 255, 0))
        glyph.paste(Image.new('RGB', cropped.size, 'white'), (0, 0))
        glyph.putalpha(Image.new('L', glyph.size, 0))
        alpha = Image.new('L', glyph.size, 0)
        alpha.paste(cropped, (0, 0))
        glyph.putalpha(alpha)
        assert glyph.width < max_glyph_width
        result.append(glyph)
    return result


def parse_pff(data):
    count, stride, directory = struct.unpack_from('<III', data, 8)
    assert stride == 36
    assert directory + count * stride == len(data)
    table = bytearray(data[directory:])
    members = {}
    for i in range(count):
        record = table[i * stride:(i + 1) * stride]
        offset, size = struct.unpack_from('<II', record, 4)
        name = record[16:32].split(b'\0')[0].decode('ascii')
        assert 20 <= offset and offset + size <= directory
        members[name.lower()] = (i, offset, size)
    return directory, table, members


def build(source):
    BUILD.mkdir(exist_ok=True)
    original = source.read_bytes()
    directory, table, members = parse_pff(original)
    def member(name):
        _, start, size = members[name.lower()]
        return original[start:start + size]
    font = bytearray(member('Impact50.fnt'))
    assert font[:4] == b'FNT0'
    pages = struct.unpack_from('<I', font, 8)[0]
    assert len(font) == 4512 + pages * 262144
    atlas = Image.new('RGBA', (256, 256), (255, 255, 255, 0))
    glyphs = render_labels()
    for position, ((index, code, text), glyph) in enumerate(zip(LABELS, glyphs)):
        x, y = 2, position * 50 + 2
        atlas.paste(glyph, (x, y))
        # Each reserved byte denotes a complete shaped label for this experiment.
        # FNT0 stores the atlas page as a uint32 followed by four UV floats.
        # The loader copies five 32-bit words per glyph; encoding the page as
        # a float produces an invalid index (e.g. page 3 becomes 1077936128).
        struct.pack_into('<I4f', font, 32 + (code - 32) * 20,
                         pages, x / 256, y / 256,
                         (x + glyph.width) / 256, (y + glyph.height) / 256)
    struct.pack_into('<I', font, 8, pages + 1)
    font.extend(atlas.tobytes('raw', 'BGRA'))
    preview = Image.new('RGBA', atlas.size, 'black')
    preview.alpha_composite(atlas)
    preview.convert('RGB').resize((768, 768)).save(EVIDENCE / 'thai-menu-atlas-preview.png')
    text = bytearray(member('menutxt.bin'))
    count = struct.unpack_from('<I', text, 12)[0]
    base = 16 + count * 16
    for index, code, label in LABELS:
        relative = struct.unpack_from('<I', text, 16 + index * 16)[0]
        start = base + relative
        end = text.index(0, start)
        replacement = bytes([code])
        assert len(replacement) <= end - start
        text[start:end] = replacement + b'\0' * (end - start - len(replacement))
    replacements = {'impact50.fnt': bytes(font), 'menutxt.bin': bytes(text)}
    output = bytearray(original[:directory])
    for name, data in replacements.items():
        index, _, _ = members[name]
        struct.pack_into('<II', table, index * 36 + 4, len(output), len(data))
        output.extend(data)
    struct.pack_into('<I', output, 16, len(output))
    output.extend(table)
    target = BUILD / 'localres.pff'
    target.write_bytes(output)
    # Round-trip the built archive and verify every member, including untouched ones.
    _, _, result_members = parse_pff(output)
    for name, (_, old_start, old_size) in members.items():
        _, new_start, new_size = result_members[name]
        expected = replacements.get(name, original[old_start:old_start + old_size])
        assert output[new_start:new_start + new_size] == expected, name
    # Metadata, lookup bytes, and original string offsets are unchanged.
    assert text[:base] == member('menutxt.bin')[:base]
    manifest = dict(original_sha256=digest(source), patched_sha256=digest(target),
                    members_changed=list(replacements),
                    font='LINE Seed Sans TH Bold, privately loaded from TTF',
                    font_source_sha256=digest(LINE_SEED_FONT),
                    method='Pre-shaped full Thai labels in five FNT0 atlas slots using printable ASCII carriers; page index is uint32 and UVs are floats; not native Unicode support.',
                    labels=[dict(index=i, byte=hex(c), thai=t) for i, c, t in LABELS],
                    validation='All 3975 archive members checked after rebuilding; menu text metadata and offsets retained.',
                    runtime_validation='pending')
    (BUILD / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Built and verified', target)
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install', action='store_true')
    ap.add_argument('--restore', action='store_true')
    args = ap.parse_args()
    BACKUP.mkdir(exist_ok=True)
    original = BACKUP / 'localres.pff'
    installed = ROOT / 'localres.pff'
    if args.restore:
        manifest = json.loads((BUILD / 'manifest.json').read_text(encoding='utf-8'))
        assert digest(original) == manifest['original_sha256'], 'Backup hash mismatch'
        assert digest(installed) in (manifest['original_sha256'], manifest['patched_sha256']), 'Installed file changed; preserve it and investigate'
        shutil.copy2(original, installed)
        print('Original localres.pff restored')
        return
    if original.exists():
        manifest_path = BUILD / 'manifest.json'
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            assert digest(original) == manifest['original_sha256'], 'Backup hash mismatch'
            assert digest(installed) in (manifest['original_sha256'], manifest['patched_sha256']), 'Unexpected game version'
    else:
        shutil.copy2(installed, original)
    manifest = build(original)
    if args.install:
        # Copy to a sibling then atomically replace; retain the original backup.
        pending = ROOT / 'localres.thai-menu-pending'
        shutil.copy2(BUILD / 'localres.pff', pending)
        assert digest(pending) == manifest['patched_sha256']
        pending.replace(installed)
        print('Installed menu experiment; restore with --restore after closing the game')


if __name__ == '__main__':
    main()
