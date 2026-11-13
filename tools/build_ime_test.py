"""Create an isolated startup experiment calling ImmDisableIME before the game CRT.

Only ThaiPatch/RunMenuTest/dfbhd.exe is changed; the root EXE stays original.
"""
from pathlib import Path
import hashlib
import json
import struct
import pefile

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / 'dfbhd.exe'
target = ROOT / 'ThaiPatch/RunMenuTest/dfbhd.exe'
data = bytearray(source.read_bytes())
pe = pefile.PE(data=data)
assert hashlib.sha256(data).hexdigest() == '693676b5fb96012d32ee395ac23b4a8bf4d7dd9a9f25ae8e500749a2f0df34ea'
assert pe.FILE_HEADER.Machine == 0x14c and pe.OPTIONAL_HEADER.DllCharacteristics == 0
align = lambda n, a: (n + a - 1) // a * a
base = pe.OPTIONAL_HEADER.ImageBase
entry = pe.OPTIONAL_HEADER.AddressOfEntryPoint
rva = align(max(s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData) for s in pe.sections), pe.OPTIONAL_HEADER.SectionAlignment)
raw = align(len(data), pe.OPTIONAL_HEADER.FileAlignment)
imports = {i.name: i.address for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports if i.name}
pack = lambda x: struct.pack('<I', x)
code = bytearray(b'\x9c\x60')  # preserve flags and registers
string_fixes = []
code += b'\x68'; string_fixes.append((len(code), 'dll')); code += b'\0'*4
code += b'\xff\x15' + pack(imports[b'LoadLibraryA'])
code += b'\x85\xc0\x74'; jump1 = len(code); code += b'\0'
code += b'\x68'; string_fixes.append((len(code), 'function')); code += b'\0'*4
code += b'\x50\xff\x15' + pack(imports[b'GetProcAddress'])
code += b'\x85\xc0\x74'; jump2 = len(code); code += b'\0'
code += b'\x6a\xff\xff\xd0'  # ImmDisableIME(0xffffffff), this process's threads
skip = len(code)
code += b'\x61\x9d\xe9'
code += struct.pack('<i', (base + entry) - (base + rva + len(code) + 4))
positions = {'dll': len(code)}
code += b'imm32.dll\0'
positions['function'] = len(code)
code += b'ImmDisableIME\0'
for offset, name in string_fixes:
    struct.pack_into('<I', code, offset, base + rva + positions[name])
code[jump1] = skip - jump1 - 1
code[jump2] = skip - jump2 - 1
assert code[jump1] < 128 and code[jump2] < 128
size = align(len(code), pe.OPTIONAL_HEADER.FileAlignment)
new_header = pe.sections[-1].get_file_offset() + 40
assert new_header + 40 <= pe.sections[0].PointerToRawData
data.extend(b'\0' * (raw - len(data)))
data.extend(code + b'\0' * (size - len(code)))
section = struct.pack('<8sIIIIIIHHI', b'.thime\0\0', len(code), rva, size, raw, 0, 0, 0, 0, 0x60000020)
data[new_header:new_header+40] = section
struct.pack_into('<H', data, pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'), pe.FILE_HEADER.NumberOfSections + 1)
struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('AddressOfEntryPoint'), rva)
struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'), align(rva + len(code), pe.OPTIONAL_HEADER.SectionAlignment))
struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum'), 0)
check = pefile.PE(data=data)
assert check.OPTIONAL_HEADER.AddressOfEntryPoint == rva
assert check.get_data(rva, len(code)) == code
for old in pe.sections:
    assert data[old.PointerToRawData:old.PointerToRawData+old.SizeOfRawData] == source.read_bytes()[old.PointerToRawData:old.PointerToRawData+old.SizeOfRawData]
target.write_bytes(data)
manifest = dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                patched_sha256=hashlib.sha256(data).hexdigest(),
                original_entry_rva=hex(entry), new_entry_rva=hex(rva),
                startup_code_hex=code.hex(), target=str(target),
                purpose='Isolated MSCTF/IME startup experiment; no root EXE modification.')
(ROOT / 'ThaiPatch/evidence/ime-test-manifest.json').write_text(json.dumps(manifest, indent=2))
print('Built isolated IME experiment', target)
