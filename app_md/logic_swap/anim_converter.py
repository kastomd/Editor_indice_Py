import os
import struct
import zlib
from pathlib import Path


BLOCKSIZE = 5000
HASHSIZE  = 4096
MAXCHARS  = 200
THRESHOLD = 3


def _bpe_lookup(lh, rh, ch, a, b):
    i = (a ^ (b << 5)) & (HASHSIZE - 1)
    while (lh[i] != a or rh[i] != b) and ch[i] != 0:
        i = (i + 1) & (HASHSIZE - 1)
    lh[i] = a; rh[i] = b
    return i


def bpe_compress(data: bytes) -> bytes:
    out = bytearray()
    pos = 0
    n   = len(data)

    while pos <= n:
        ch = bytearray(HASHSIZE)
        lh = bytearray(HASHSIZE)
        rh = bytearray(HASHSIZE)
        lc = bytearray(range(256))
        rc = bytearray(256)
        buf  = bytearray()
        used = 0
        eof  = pos >= n

        while len(buf) < BLOCKSIZE and used < MAXCHARS and pos < n:
            c = data[pos]; pos += 1
            if buf:
                idx = _bpe_lookup(lh, rh, ch, buf[-1], c)
                if ch[idx] < 255: ch[idx] += 1
            buf.append(c)
            if not rc[c]:
                rc[c] = 1; used += 1

        if not buf:
            break

        size = len(buf)
        code = 256

        while True:
            code -= 1
            while code >= 0:
                if lc[code] == code and rc[code] == 0: break
                code -= 1
            if code < 0: break

            best = THRESHOLD - 1; lch = rch = 0
            for i in range(HASHSIZE):
                if ch[i] > best:
                    best = ch[i]; lch = lh[i]; rch = rh[i]
            if best < THRESHOLD: break

            old = size - 1; w = r = 0
            while r < old:
                if buf[r] == lch and buf[r+1] == rch:
                    if w > 0:
                        idx = _bpe_lookup(lh, rh, ch, buf[w-1], lch)
                        if ch[idx] > 1: ch[idx] -= 1
                        idx = _bpe_lookup(lh, rh, ch, buf[w-1], code)
                        if ch[idx] < 255: ch[idx] += 1
                    if r < old - 1:
                        idx = _bpe_lookup(lh, rh, ch, rch, buf[r+2])
                        if ch[idx] > 1: ch[idx] -= 1
                        idx = _bpe_lookup(lh, rh, ch, code, buf[r+2])
                        if ch[idx] < 255: ch[idx] += 1
                    buf[w] = code; w += 1; r += 2; size -= 1
                else:
                    buf[w] = buf[r]; w += 1; r += 1
            if r == old: buf[w] = buf[r]

            lc[code] = lch; rc[code] = rch
            ch[_bpe_lookup(lh, rh, ch, lch, rch)] = 1

        c = 0
        while c < 256:
            if lc[c] == c:
                ln = 1; c += 1
                while ln < 127 and c < 256 and lc[c] == c: ln += 1; c += 1
                out.append(ln + 127); ln = 0
                if c == 256: break
            else:
                ln = 0; c += 1
                while (ln < 127 and c < 256 and lc[c] != c) or \
                      (ln < 125 and c < 254 and lc[c+1] != c+1):
                    ln += 1; c += 1
                out.append(ln); c -= ln + 1
            for _ in range(ln + 1):
                out.append(lc[c])
                if c != lc[c]: out.append(rc[c])
                c += 1

        out.append(size // 256); out.append(size % 256)
        out += buf[:size]
        if eof: break

    return bytes(out)


def bpe_decompress(data: bytes, out_size: int) -> bytes:
    out = bytearray()
    pos = 0

    while pos < len(data) and len(out) < out_size:
        left  = bytearray(range(256))
        right = bytearray(256)
        count = data[pos]; pos += 1
        c = 0

        while True:
            if count > 127: c += count - 127; count = 0
            if c == 256: break
            for _ in range(count + 1):
                if c >= 256: break
                left[c] = data[pos]; pos += 1
                if c != left[c]: right[c] = data[pos]; pos += 1
                c += 1
            if c == 256: break
            count = data[pos]; pos += 1

        size = 256 * data[pos] + data[pos+1]; pos += 2
        stack = []; i = 0

        while i < size:
            if stack:
                c = stack.pop()
            else:
                c = data[pos]; pos += 1; i += 1
            if c == left[c]:
                out.append(c)
            else:
                stack.append(right[c]); stack.append(left[c])

    return bytes(out)


def canm_to_anm(d: bytes) -> bytes:
    size, zs = struct.unpack_from('<II', d)
    return bpe_decompress(d[8:8+zs], size)

def anm_to_canm(d: bytes) -> bytes:
    c = bpe_compress(d)
    return struct.pack('<II', len(d), len(c)) + c

def tanm_to_anm(d: bytes) -> bytes:
    size, zs = struct.unpack_from('>II', d)
    return zlib.decompress(d[8:8+zs])

def anm_to_tanm(d: bytes) -> bytes:
    c = zlib.compress(d, 9)
    return struct.pack('>II', len(d), len(c)) + c

def canm_to_tanm(d: bytes) -> bytes: return anm_to_tanm(canm_to_anm(d))
def tanm_to_canm(d: bytes) -> bytes: return anm_to_canm(tanm_to_anm(d))


def encontrar_animacion(carpeta_anims, base_name, mode):
    exts = [".tanm", ".anm"] if mode == "TTT" else [".canm", ".anm"]
    for ext in exts:
        p = os.path.join(carpeta_anims, base_name + ext)
        if os.path.exists(p):
            return p
    p_noext = os.path.join(carpeta_anims, base_name)
    if os.path.exists(p_noext):
        return p_noext
    for ext in [".tanm", ".canm", ".anm"]:
        p = os.path.join(carpeta_anims, base_name + ext)
        if os.path.exists(p):
            return p
    return None


def anim_ext_for_mode(mode):
    return ".tanm" if mode == "TTT" else ".canm"


def get_dest_anim_path(dest_folder, dest_base, target_mode, prefer_ext=None):
    for ext in [".tanm", ".canm", ".anm"]:
        cand = os.path.join(dest_folder, dest_base + ext)
        if os.path.exists(cand):
            return cand
    ext = prefer_ext if prefer_ext else anim_ext_for_mode(target_mode)
    return os.path.join(dest_folder, dest_base + ext)


def convert_anim_between_modes(src_path: Path, from_mode: str, to_mode: str) -> bytes:
    data = Path(src_path).read_bytes()
    if from_mode == to_mode:
        return data
    if from_mode == "BT3" and to_mode == "TTT":
        return canm_to_tanm(data)
    if from_mode == "TTT" and to_mode == "BT3":
        return tanm_to_canm(data)
    return data