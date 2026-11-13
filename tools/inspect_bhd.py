"""Read-only inventory of this BHD installation; outputs analysis files only."""
from pathlib import Path
import collections
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'ThaiPatch' / 'evidence'


def inspect():
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for archive in ('localres.pff', 'resource.pff', 'EXP1.pff'):
        path = ROOT / archive
        rows, text_tables, fonts = [], [], []
        with path.open('rb') as f:
            header = f.read(20)
            count, stride, directory = struct.unpack_from('<III', header, 8)
            assert stride == 36 and directory + count * stride <= path.stat().st_size
            f.seek(directory)
            table = f.read(count * stride)
            for i in range(count):
                raw = table[i * stride:(i + 1) * stride]
                flags, offset, size, timestamp = struct.unpack_from('<4I', raw)
                name = raw[16:32].split(b'\0')[0].decode('ascii')
                assert 20 <= offset <= directory and offset + size <= directory
                row = dict(name=name, offset=offset, size=size, flags=flags,
                           timestamp_raw=timestamp, trailer_hex=raw[32:].hex())
                rows.append(row)
                if name.lower().endswith(('.bin', '.fnt', '.mnu')):
                    f.seek(offset)
                    data = f.read(size)
                    if data[:4] == b'RTXT':
                        n = struct.unpack_from('<I', data, 12)[0]
                        base = 16 + 16 * n
                        assert base <= len(data)
                        entries = []
                        for j in range(n):
                            record = data[16 + j * 16:32 + j * 16]
                            relative = struct.unpack_from('<I', record)[0]
                            start = base + relative
                            assert base <= start < len(data)
                            end = data.index(b'\0', start)
                            entries.append(dict(index=j, record_hex=record.hex(),
                                                relative_offset=relative,
                                                text_bytes_hex=data[start:end].hex(),
                                                text_cp1252=data[start:end].decode('cp1252', errors='replace')))
                        target = f'{archive}.{name}.json'
                        result = dict(archive=archive, member=name,
                                      sha256=hashlib.sha256(data).hexdigest(),
                                      header_hex=data[:16].hex(), string_base=base,
                                      note='CP1252 is a reversible-analysis candidate, not confirmed engine encoding. Record fields except offset and trailing lookup data remain uninterpreted.',
                                      entries=entries)
                        (OUT / target).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                        text_tables.append(dict(name=name, count=n, evidence=target))
                    elif data[:4] == b'FNT0':
                        fonts.append(dict(name=name, size=size, header_hex=data[:32].hex(),
                                          sha256=hashlib.sha256(data).hexdigest()))
                    elif name.lower().endswith('.mnu'):
                        (OUT / f'{archive}.{name}.txt').write_text(data.decode('cp1252'), encoding='utf-8')
        (OUT / f'{archive}.inventory.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
        summary[archive] = dict(member_count=count,
                               trailing_bytes=path.stat().st_size - (directory + count * stride),
                               extensions=dict(collections.Counter(Path(r['name']).suffix.lower() for r in rows)),
                               text_tables=text_tables, fonts=fonts)
    (OUT / 'inventory-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    for name, result in summary.items():
        print(name, result['member_count'], 'members;', len(result['fonts']), 'fonts;',
              len(result['text_tables']), 'RTXT tables;',
              sum(t['count'] for t in result['text_tables']), 'text records')


if __name__ == '__main__':
    inspect()
