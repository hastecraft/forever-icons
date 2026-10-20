"""Minimal read-only reader for a local CASC install (the game's Data folder).

Opens one product's build from .build.info and reads files by FileDataID:
local indices -> data.### archives -> BLTE, with the encoding file mapping
content keys to encoded keys and the root file mapping FileDataIDs to content keys.
Encrypted files (BLTE 'E' chunks) are reported as unreadable.
"""
import struct
import zlib
from pathlib import Path

LOCALE_ENUS = 0x2
CONTENT_LOW_VIOLENCE = 0x80


class Encrypted(Exception):
    pass


def blte_decode(data):
    if data[:4] != b'BLTE':
        raise ValueError('not BLTE')
    header_size = struct.unpack('>I', data[4:8])[0]
    if header_size == 0:
        return _blte_chunk(data[8:])
    flags_count = struct.unpack('>I', data[8:12])[0]
    count = flags_count & 0xFFFFFF
    pos = 12
    chunks = []
    for _ in range(count):
        comp, _decomp = struct.unpack('>II', data[pos:pos + 8])
        chunks.append(comp)
        pos += 24
    pos = header_size
    out = []
    for comp in chunks:
        out.append(_blte_chunk(data[pos:pos + comp]))
        pos += comp
    return b''.join(out)


def _blte_chunk(chunk):
    mode = chunk[:1]
    if mode == b'N':
        return chunk[1:]
    if mode == b'Z':
        return zlib.decompress(chunk[1:])
    if mode == b'E':
        raise Encrypted()
    if mode == b'4':
        import lz4.block  # rare in WoW; only needed if it shows up
        return lz4.block.decompress(chunk[1:])
    raise ValueError(f'unknown BLTE chunk mode {mode!r}')


def _read_config(path):
    cfg = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if ' = ' in line and not line.startswith('#'):
            k, v = line.split(' = ', 1)
            cfg[k.strip()] = v.split()
    return cfg


class Casc:
    def __init__(self, wow_dir, product):
        self.root_dir = Path(wow_dir)
        self.data_dir = self.root_dir / 'Data' / 'data'
        build_key = self._build_key(product)
        cfg_path = self.root_dir / 'Data' / 'config' / build_key[:2] / build_key[2:4] / build_key
        self.build = _read_config(cfg_path)
        self.build_name = self.build.get('build-name', ['?'])[0]
        self._load_indices()
        self._archives = {}
        self._load_encoding()
        self._load_root()

    def _build_key(self, product):
        lines = (self.root_dir / '.build.info').read_text(encoding='utf-8').splitlines()
        cols = [c.split('!')[0] for c in lines[0].split('|')]
        for line in lines[1:]:
            row = dict(zip(cols, line.split('|')))
            if row.get('Product') == product:
                return row['Build Key']
        raise KeyError(f'product {product} not in .build.info')

    # --- local indices: 9-byte encoded key prefix -> (archive, offset, size)
    def _load_indices(self):
        newest = {}
        for p in self.data_dir.glob('*.idx'):
            bucket, version = int(p.stem[:2], 16), int(p.stem[2:], 16)
            if bucket not in newest or version > newest[bucket][0]:
                newest[bucket] = (version, p)
        self.index = {}
        for _, p in newest.values():
            buf = p.read_bytes()
            hdr_size = struct.unpack_from('<I', buf, 0)[0]
            _ver, _bucket, _extra, size_len, off_len, key_len, off_bits = struct.unpack_from('<HBBBBBB', buf, 8)
            pos = (8 + hdr_size + 15) & ~15  # entries block is 16-byte aligned
            entries_size = struct.unpack_from('<I', buf, pos)[0]
            pos += 8
            stride = key_len + off_len + size_len
            mask = (1 << off_bits) - 1
            for i in range(pos, pos + entries_size, stride):
                key = buf[i:i + key_len]
                packed = int.from_bytes(buf[i + key_len:i + key_len + off_len], 'big')
                size = int.from_bytes(buf[i + key_len + off_len:i + stride], 'little')
                self.index.setdefault(key, (packed >> off_bits, packed & mask, size))

    def read_ekey(self, ekey):
        loc = self.index.get(ekey[:9])
        if loc is None:
            raise KeyError(f'encoded key {ekey.hex()} not in local storage')
        archive, offset, size = loc
        f = self._archives.get(archive)
        if f is None:
            f = self._archives[archive] = open(self.data_dir / f'data.{archive:03d}', 'rb')
        f.seek(offset + 0x1E)
        return blte_decode(f.read(size - 0x1E))

    # --- encoding file: content key -> encoded key
    def _load_encoding(self):
        buf = self.read_ekey(bytes.fromhex(self.build['encoding'][1]))
        if buf[:2] != b'EN':
            raise ValueError('bad encoding file')
        ckey_len, ekey_len = buf[3], buf[4]
        ce_page_kb = struct.unpack_from('>H', buf, 5)[0]
        ce_pages = struct.unpack_from('>I', buf, 9)[0]
        espec_size = struct.unpack_from('>I', buf, 18)[0]
        pos = 22 + espec_size + ce_pages * 32
        page_size = ce_page_kb * 1024
        self.encoding = {}
        for p in range(ce_pages):
            start = pos + p * page_size
            i, end = start, start + page_size
            while i < end:
                count = buf[i]
                if count == 0:
                    break
                ckey = buf[i + 6:i + 6 + ckey_len]
                self.encoding[ckey] = buf[i + 6 + ckey_len:i + 6 + ckey_len + ekey_len]
                i += 6 + ckey_len + ekey_len * count

    def read_ckey(self, ckey):
        return self.read_ekey(self.encoding[ckey])

    # --- root file: FileDataID -> content key
    def _load_root(self):
        buf = self.read_ckey(bytes.fromhex(self.build['root'][0]))
        self.root = {}
        pos = 0
        version = 0
        allow_unnamed = False
        if buf[:4] == b'TSFM':
            a, b = struct.unpack_from('<II', buf, 4)
            if a < 100 and b in (1, 2):  # header size, version
                header_size, version = a, b
                total, named = struct.unpack_from('<II', buf, 12)
                pos = header_size
            else:
                total, named = a, b
                pos = 12
            allow_unnamed = total != named
        while pos < len(buf):
            if version == 2:
                count, locale, cf1, cf2 = struct.unpack_from('<IIII', buf, pos)
                cf3 = buf[pos + 16]
                content = cf1 | cf2 | (cf3 << 17)
                pos += 17
            else:
                count, content, locale = struct.unpack_from('<III', buf, pos)
                pos += 12
            deltas = struct.unpack_from(f'<{count}i', buf, pos)
            pos += 4 * count
            ckeys = pos
            pos += 16 * count
            if not (allow_unnamed and content & 0x10000000):
                pos += 8 * count
            if not (locale & LOCALE_ENUS) or content & CONTENT_LOW_VIOLENCE:
                continue
            fdid = -1
            for n, d in enumerate(deltas):
                fdid += 1 + d
                self.root[fdid] = buf[ckeys + 16 * n:ckeys + 16 * n + 16]

    def read_fdid(self, fdid):
        return self.read_ckey(self.root[fdid])

    def has_local(self, fdid):
        ckey = self.root.get(fdid)
        ekey = ckey and self.encoding.get(ckey)
        return bool(ekey) and ekey[:9] in self.index
