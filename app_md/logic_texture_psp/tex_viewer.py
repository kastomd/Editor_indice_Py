import os
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from PyQt5.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QImage, QPixmap, QPainter, QColor, QFont
from PyQt5.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QMessageBox, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

try:
    from ..ui import rutas
except ImportError:
    class rutas:
        _last = {}

        @staticmethod
        def inicial(kind, name=""):
            d = rutas._last.get(kind, "")
            return os.path.join(d, name) if name else d

        @staticmethod
        def recordar(kind, path):
            rutas._last[kind] = path if os.path.isdir(path) else os.path.dirname(path)

try:
    from ..core.idioma import t as _tr
except ImportError:
    def _tr(s):
        return s

_THUMB = 52
_TEX_EXTS = {".atex", ".rhg"}


def _pil_to_qpixmap(img):
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


def _checker(size):
    sq, bg = 8, Image.new("RGBA", (size, size))
    for y in range(size):
        for x in range(size):
            c = 200 if ((x // sq) + (y // sq)) % 2 == 0 else 160
            bg.putpixel((x, y), (c, c, c, 255))
    return bg


def _thumbnail(img, index, size=_THUMB):
    bg = _checker(size)
    thumb = img.copy()
    scale = min(size / thumb.width, size / thumb.height)
    new_w = max(1, round(thumb.width * scale))
    new_h = max(1, round(thumb.height * scale))
    thumb = thumb.resize((new_w, new_h), Image.NEAREST)
    bg.paste(thumb, ((size - thumb.width) // 2, (size - thumb.height) // 2), thumb)
    px = _pil_to_qpixmap(bg)
    result = QPixmap(size, size)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.drawPixmap(0, 0, px)
    font = QFont()
    font.setPointSize(8)
    font.setBold(True)
    painter.setFont(font)
    num = str(index)
    for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
        painter.setPen(QColor(0, 0, 0, 220))
        painter.drawText(size - 14 + dx, 0 + dy, 14, 12, Qt.AlignRight | Qt.AlignTop, num)
    painter.setPen(QColor(255, 255, 255, 255))
    painter.drawText(size - 14, 0, 14, 12, Qt.AlignRight | Qt.AlignTop, num)
    painter.end()
    return result


def _render(index_bytes, pal_bytes, w, h, psp_alpha, bpp=8):
    mul = 2 if psp_alpha else 1
    pal = [(pal_bytes[i*4], pal_bytes[i*4+1], pal_bytes[i*4+2],
            min(255, pal_bytes[i*4+3] * mul)) for i in range(len(pal_bytes) // 4)]
    if not pal:
        raise ValueError("empty palette")
    # the PSP tile is 16 bytes x 8 rows and applies to the row pitch in bytes,
    # not to the width in pixels
    pitch = w // 2 if bpp == 4 else w
    if pitch == 0 or h == 0:
        raise ValueError(f"invalid dimensions {w}x{h}")
    if len(index_bytes) < pitch * h:
        raise ValueError(f"index too short: {len(index_bytes)} < {pitch * h}")
    pixels = [(0, 0, 0, 0)] * (w * h)

    def _put(n, y, xb):
        byte = index_bytes[n]
        if bpp == 4:
            x = xb * 2
            pixels[y * w + x]     = pal[byte & 0x0F]
            pixels[y * w + x + 1] = pal[(byte >> 4) & 0x0F]
        else:
            pixels[y * w + xb] = pal[byte % len(pal)]

    if pitch % 16 != 0 or h % 8 != 0:
        # too small (or not aligned) to be swizzled: stored linearly
        for y in range(h):
            for xb in range(pitch):
                _put(y * pitch + xb, y, xb)
    else:
        n = 0
        for by in range(0, h, 8):
            for bx in range(0, pitch, 16):
                for r in range(8):
                    for c in range(16):
                        _put(n, by + r, bx + c)
                        n += 1
    img = Image.new("RGBA", (w, h))
    img.putdata(pixels)
    return img


# ── encode: RGBA PIL image → (index_bytes, pal_bytes) in tiled format ──────────

def _encode(img_rgba, n_colors, bpp, psp_alpha):
    try:
        from ..core.textures import encode
    except ImportError:
        return _encode_local(img_rgba, n_colors, bpp, psp_alpha)
    return encode(img_rgba, n_colors, bpp, psp_alpha)


# standalone fallback when the host app has no core.textures
def _encode_local(img_rgba, n_colors, bpp, psp_alpha):
    w, h = img_rgba.size
    q = img_rgba.quantize(colors=n_colors, method=Image.Quantize.FASTOCTREE, dither=0)
    pal_raw = q.getpalette()
    idx_map = list(q.getdata())
    a_sum, a_cnt = [0] * n_colors, [0] * n_colors
    for iv, px in zip(idx_map, img_rgba.getdata()):
        if iv < n_colors:
            a_sum[iv] += (px[3] * 128 // 255) if psp_alpha else px[3]
            a_cnt[iv] += 1
    pal_bytes = bytearray()
    for i in range(n_colors):
        pal_bytes += bytes((pal_raw[i * 3:i * 3 + 3] + [0, 0, 0])[:3] + [a_sum[i] // a_cnt[i] if a_cnt[i] else 0])
    tile_w = 32 if bpp == 4 else 16
    idx_bytes = bytearray()
    for ty in range(0, h, 8):
        for tx in range(0, w, tile_w):
            for py in range(8):
                row = (ty + py) * w + tx
                if bpp == 4:
                    for px in range(0, tile_w, 2):
                        idx_bytes.append((idx_map[row + px] & 0x0F) | ((idx_map[row + px + 1] & 0x0F) << 4))
                else:
                    for px in range(tile_w):
                        idx_bytes.append(idx_map[row + px] % n_colors)
    return bytes(idx_bytes), bytes(pal_bytes)


def _is_swizzled(w, h, bpp):
    pitch = w // 2 if bpp == 4 else w
    return pitch % 16 == 0 and h % 8 == 0


def _inject_atex(file_data, tex_meta, img_rgba):
    """Return modified atex bytes with the texture replaced."""
    w, h = tex_meta["w"], tex_meta["h"]
    if img_rgba.size != (w, h):
        raise ValueError(f"Size mismatch: expected {w}×{h}, got {img_rgba.size[0]}×{img_rgba.size[1]}")

    n_colors  = tex_meta["pal_sz"] // 4
    bpp       = tex_meta.get("bpp") or (4 if 0 < n_colors <= 16 else 8)
    if not _is_swizzled(w, h, bpp):
        raise ValueError(f"{w}×{h} is stored unswizzled; writing it back is not supported yet")

    idx_bytes, pal_bytes = _encode(img_rgba, n_colors, bpp, psp_alpha=True)

    data = bytearray(file_data)
    idx_off = tex_meta["idx_off"]
    pal_off = tex_meta["pal_off"]
    data[idx_off : idx_off + len(idx_bytes)] = idx_bytes
    data[pal_off : pal_off + len(pal_bytes)] = pal_bytes
    return bytes(data)


def _append_atex_texture(file_data, img_rgba, n_colors):
    """Return atex bytes with a new texture appended as the last index."""
    w, h = img_rgba.size
    bpp = 4 if n_colors <= 16 else 8
    if w & (w - 1) or h & (h - 1):
        raise ValueError("width and height must be powers of two")
    if not _is_swizzled(w, h, bpp):
        raise ValueError(f"minimum texture size is {32 if bpp == 4 else 16}x8 for {n_colors} colors")
    tw, th = w.bit_length() - 1, h.bit_length() - 1

    data = bytearray(file_data)
    count   = struct.unpack_from("<I", data, 0)[0]
    tbl_off = struct.unpack_from("<I", data, 4)[0] * 4
    if count == 0 or tbl_off >= len(data):
        raise ValueError("invalid atex file")

    idx_bytes, pal_bytes = _encode(img_rgba, n_colors, bpp, psp_alpha=True)

    shift = 0x60
    for i in range(count):
        e = tbl_off + i * 0x60
        idx_off_w, pal_off_w = struct.unpack_from("<II", data, e)
        struct.pack_into("<II", data, e, idx_off_w + shift // 4, pal_off_w + shift // 4)

    template_off = tbl_off + (count - 1) * 0x60
    new_entry = bytearray(data[template_off:template_off + 0x60])

    new_idx_off = len(data) + shift
    new_pal_off = new_idx_off + len(idx_bytes)
    struct.pack_into("<IIII", new_entry, 0,
                      new_idx_off // 4, new_pal_off // 4, len(idx_bytes), len(pal_bytes))
    new_entry[0x28] = th
    new_entry[0x29] = tw

    insert_pos = tbl_off + count * 0x60
    result = bytearray(data[:insert_pos]) + new_entry + bytearray(data[insert_pos:]) + idx_bytes + pal_bytes
    struct.pack_into("<I", result, 0, count + 1)
    return bytes(result)


def _replace_atex_texture(file_data, index, img_rgba, n_colors):
    """Return atex bytes with texture #index replaced, possibly changing size/colors."""
    w, h = img_rgba.size
    bpp = 4 if n_colors <= 16 else 8
    if w & (w - 1) or h & (h - 1):
        raise ValueError("width and height must be powers of two")
    if not _is_swizzled(w, h, bpp):
        raise ValueError(f"minimum texture size is {32 if bpp == 4 else 16}x8 for {n_colors} colors")
    tw, th = w.bit_length() - 1, h.bit_length() - 1

    data = bytearray(file_data)
    count   = struct.unpack_from("<I", data, 0)[0]
    tbl_off = struct.unpack_from("<I", data, 4)[0] * 4
    if not (0 <= index < count):
        raise ValueError("texture index out of range")

    blobs = []
    for i in range(count):
        e = tbl_off + i * 0x60
        idx_off_w, pal_off_w, idx_sz, pal_sz = struct.unpack_from("<IIII", data, e)
        idx_off, pal_off = idx_off_w * 4, pal_off_w * 4
        blobs.append((bytes(data[idx_off:idx_off + idx_sz]), bytes(data[pal_off:pal_off + pal_sz])))

    idx_bytes, pal_bytes = _encode(img_rgba, n_colors, bpp, psp_alpha=True)
    blobs[index] = (idx_bytes, pal_bytes)

    cursor = tbl_off + count * 0x60
    for i, (idx_blob, pal_blob) in enumerate(blobs):
        e = tbl_off + i * 0x60
        idx_off = cursor
        pal_off = idx_off + len(idx_blob)
        cursor = pal_off + len(pal_blob)
        struct.pack_into("<IIII", data, e, idx_off // 4, pal_off // 4, len(idx_blob), len(pal_blob))
    data[tbl_off + index * 0x60 + 0x28] = th
    data[tbl_off + index * 0x60 + 0x29] = tw

    result = bytearray(data[:tbl_off + count * 0x60])
    for idx_blob, pal_blob in blobs:
        result += idx_blob + pal_blob
    return bytes(result)


def _inject_rhg(file_data, tex_meta, img_rgba):
    """Return modified rhg bytes with the texture replaced."""
    w, h = tex_meta["w"], tex_meta["h"]
    if img_rgba.size != (w, h):
        raise ValueError(f"Size mismatch: expected {w}×{h}, got {img_rgba.size[0]}×{img_rgba.size[1]}")

    n_colors  = tex_meta["pal_sz"] // 4
    bpp       = 4 if n_colors <= 16 else 8
    if not _is_swizzled(w, h, bpp):
        raise ValueError(f"{w}×{h} is stored unswizzled; writing it back is not supported yet")
    idx_bytes, pal_bytes = _encode(img_rgba, n_colors, bpp, psp_alpha=False)

    data = bytearray(file_data)
    idx_off = tex_meta["idx_off"]
    pal_off = tex_meta["pal_off"]
    data[idx_off : idx_off + len(idx_bytes)] = idx_bytes
    data[pal_off : pal_off + len(pal_bytes)] = pal_bytes
    return bytes(data)


def _rhg_entries(file_data):
    textures = parse_rhg(file_data)
    if not textures:
        raise ValueError("invalid or unsupported rhg file")
    entries = []
    for t in textures:
        entries.append({
            "w": t["w"], "h": t["h"],
            "bpp": 4 if t["pal_sz"] // 4 <= 16 else 8,
            "idx": file_data[t["idx_off"]:t["idx_off"] + t["idx_sz"]],
            "pal": file_data[t["pal_off"]:t["pal_off"] + t["pal_sz"]],
        })
    return entries


def _build_rhg(header_src, entries):
    """Rebuild a full rhg file from a list of {w,h,bpp,idx,pal} entries."""
    count = len(entries)

    group = bytearray()
    for i, e in enumerate(entries):
        group += struct.pack("<10I", 0, i, i, 0, 0, 0, 1, i + 1, i + 1, 0)
    while len(group) % 16:
        group += b"\x00" * 4

    # lod array: 9-dword entry, format 17=8bpp / 18=4bpp
    lod = bytearray()
    for e in entries:
        fmt = 17 if e["bpp"] == 8 else 18
        pitch = e["w"] if e["bpp"] == 8 else e["w"] // 2
        lod += struct.pack("<9I", 2, fmt, e["w"], e["h"], 0, len(e["idx"]), pitch, 0, 0)
    while len(lod) % 16:
        lod += b"\x00" * 4

    # palette array: 6-dword entry padded to 0x20
    pal_desc = bytearray()
    for e in entries:
        nc = len(e["pal"]) // 4
        pal_desc += struct.pack("<6I", 0x14, 0, len(e["pal"]), nc, 2, 0)
        pal_desc += b"\x00" * 8

    idx_tail = b"".join(e["idx"] for e in entries)
    pal_tail = bytearray()
    for i, e in enumerate(entries):
        pal_tail += e["pal"]
        if e["bpp"] == 4 and i < count - 1:
            pal_tail += b"\x00" * 64

    header = bytearray(header_src[:0x30])
    struct.pack_into("<I", header, 0x14, count)
    struct.pack_into("<I", header, 0x1c, count)
    struct.pack_into("<I", header, 0x24, count)

    body = bytearray(header) + group + lod + pal_desc
    while len(body) % 0x80:
        body += b"\x00" * 16

    return bytes(body) + idx_tail + bytes(pal_tail)


def _rhg_check_dims(w, h, n_colors):
    bpp = 4 if n_colors <= 16 else 8
    tile_w = 32 if bpp == 4 else 16
    if w % tile_w != 0 or h % 8 != 0:
        raise ValueError(f"width must be a multiple of {tile_w} and height a multiple of 8")
    return bpp


def _append_rhg_texture(file_data, img_rgba, n_colors):
    """Return rhg bytes with a new texture appended as the last index."""
    w, h = img_rgba.size
    bpp = _rhg_check_dims(w, h, n_colors)
    entries = _rhg_entries(file_data)
    idx_bytes, pal_bytes = _encode(img_rgba, n_colors, bpp, psp_alpha=False)
    entries.append({"w": w, "h": h, "bpp": bpp, "idx": idx_bytes, "pal": pal_bytes})
    return _build_rhg(file_data, entries)


def _replace_rhg_texture(file_data, index, img_rgba, n_colors):
    """Return rhg bytes with texture #index replaced, possibly changing size/colors."""
    w, h = img_rgba.size
    bpp = _rhg_check_dims(w, h, n_colors)
    entries = _rhg_entries(file_data)
    if not (0 <= index < len(entries)):
        raise ValueError("texture index out of range")
    idx_bytes, pal_bytes = _encode(img_rgba, n_colors, bpp, psp_alpha=False)
    entries[index] = {"w": w, "h": h, "bpp": bpp, "idx": idx_bytes, "pal": pal_bytes}
    return _build_rhg(file_data, entries)


# ── parsers ─────────────────────────────────────────────────────────────────────

def parse_atex(data):
    if len(data) < 8:
        return []
    count   = struct.unpack_from("<I", data, 0)[0]
    tbl_off = struct.unpack_from("<I", data, 4)[0] * 4
    if count == 0 or count > 512 or tbl_off >= len(data):
        return []
    textures = []
    for i in range(count):
        e = tbl_off + i * 0x60
        if e + 0x30 > len(data):
            break
        v = struct.unpack_from("<IIIIII", data, e)
        idx_off, pal_off, idx_sz, pal_sz = v[0]*4, v[1]*4, v[2], v[3]
        # +0x28 is log2(height) and +0x29 is log2(width), not the other way round
        th = data[e + 0x28]
        tw = data[e + 0x29]
        w, h = 1 << tw, 1 << th
        # bpp is not stored: the game derives it from the palette size (16 colors = 4bpp)
        n_colors = pal_sz // 4
        bpp = 4 if 0 < n_colors <= 16 else 8
        if w * h and idx_sz * 8 == w * h:
            bpp = 8
        meta = {"index": i, "w": w, "h": h, "bpp": bpp, "idx_sz": idx_sz, "pal_sz": pal_sz,
                "idx_off": idx_off, "pal_off": pal_off, "img": None, "error": None}
        try:
            if idx_sz == 0 or pal_sz == 0:
                raise ValueError("entry has no pixel or palette data")
            meta["img"] = _render(data[idx_off:idx_off+idx_sz],
                                   data[pal_off:pal_off+pal_sz], w, h, True, bpp)
        except Exception as exc:
            meta["error"] = str(exc)
        textures.append(meta)
    return textures


def _rhg_align(n, a):
    return (n + a - 1) // a * a


def parse_rhg(data):

    if len(data) < 0x30 or data[:4] != b"RHG\x00":
        return []
    try:
        tex_count = struct.unpack_from("<I", data, 0x14)[0]
        dat_count = struct.unpack_from("<I", data, 0x1C)[0]
        pal_count = struct.unpack_from("<I", data, 0x24)[0]
    except struct.error:
        return []
    total = tex_count + dat_count + pal_count
    if tex_count == 0 or total > 65535:
        return []

    # TEX (reference) entries: 40 bytes each, starting at 0x30.
    tex_base = 0x30
    tex_entries = []
    for n in range(tex_count):
        e = tex_base + n * 40
        if e + 12 > len(data):
            return []
        dat_idx, pal_idx = struct.unpack_from("<II", data, e + 4)
        tex_entries.append((dat_idx, pal_idx))

    # DAT entries: 36 bytes each. width/height/index-data-size live here.
    dat_base = tex_base + _rhg_align(tex_count * 40, 16)
    dat_entries = []
    dat_cum = []
    running = 0
    for n in range(dat_count):
        e = dat_base + n * 36
        if e + 24 > len(data):
            return []
        _marker, _fmt, w, h, _res, data_size = struct.unpack_from("<IIIIII", data, e)
        dat_entries.append((w, h, data_size))
        dat_cum.append(running)
        running += data_size

    # PAL entries: 32 bytes each. color-count/palette-size live here.
    pal_base = dat_base + _rhg_align(dat_count * 36, 16)
    pal_color_counts = []
    pal_cum = []
    for n in range(pal_count):
        e = pal_base + n * 32
        if e + 16 > len(data):
            return []
        pal_size, color_count = struct.unpack_from("<II", data, e + 8)
        pal_color_counts.append(color_count)
        pal_cum.append(running)
        is_last_overall = (n + tex_count + dat_count) == (total - 1)
        # GU hardcodes 128 total bytes for any non-final 16-color (4bpp)
        # palette regardless of the size field, matching PSP alignment.
        if color_count == 16 and not is_last_overall:
            running += 128
        else:
            running += pal_size

    data_start = len(data) - running
    if data_start < 0:
        return []

    textures = []
    for n, (dat_idx, pal_idx) in enumerate(tex_entries):
        if not (0 <= dat_idx < dat_count) or not (0 <= pal_idx < pal_count):
            textures.append({"index": n, "w": 0, "h": 0, "idx_sz": 0, "pal_sz": 0,
                              "idx_off": 0, "pal_off": 0, "img": None,
                              "error": "invalid dat/pal index"})
            continue
        w, h, idx_sz = dat_entries[dat_idx]
        color_count = pal_color_counts[pal_idx]
        pal_sz = color_count * 4
        bpp = 4 if color_count <= 16 else 8
        idx_off = data_start + dat_cum[dat_idx]
        pal_off = data_start + pal_cum[pal_idx]
        meta = {"index": n, "w": w, "h": h, "idx_sz": idx_sz, "pal_sz": pal_sz,
                "idx_off": idx_off, "pal_off": pal_off, "img": None, "error": None,
                "dat_idx": dat_idx, "pal_idx": pal_idx}
        try:
            meta["img"] = _render(data[idx_off:idx_off+idx_sz],
                                   data[pal_off:pal_off+pal_sz], w, h, False, bpp)
        except Exception as exc:
            meta["error"] = str(exc)
        textures.append(meta)
    return textures


# ── worker ───────────────────────────────────────────────────────────────────────

class _LoadWorker(QThread):
    finished = pyqtSignal(list, str)

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            data = open(self.path, "rb").read()
            ext  = os.path.splitext(self.path)[1].lower()
            texs = parse_rhg(data) if ext == ".rhg" else parse_atex(data)
            self.finished.emit(texs, "")
        except Exception as exc:
            self.finished.emit([], str(exc))


# ── UI widgets ───────────────────────────────────────────────────────────────────

class _ThumbBtn(QPushButton):
    def __init__(self, px, index, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(_THUMB + 8, _THUMB + 8)
        self.setIconSize(QSize(_THUMB, _THUMB))
        self.setIcon(QIcon(px))
        self.setStyleSheet("""
            QPushButton { border: 2px solid transparent; border-radius: 4px; padding: 1px; background: transparent; }
            QPushButton:hover { border-color: #6699ff; }
            QPushButton:checked { border-color: #ffffff; background: rgba(100,150,255,40); }
        """)


class TexViewer(QDialog):
    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle(_tr("Visor de texturas"))
        self.setFixedWidth(430)
        self.setMinimumHeight(520)
        self._textures   = []
        self._current    = -1
        self._worker     = None
        self._file_path  = None
        self._file_data  = None   # raw bytes of the open file (for inject)
        self._file_ext   = None
        self._thumb_btns = []
        self._pil_px     = None
        self._build_ui()
        self.setAcceptDrops(True)
        from PyQt5.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        if path:
            self._load(path)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pil_px and not self._pil_px.isNull():
            avail = self._preview_container.size()
            max_w = max(avail.width() - 8, 100)
            max_h = max(avail.height() - 8, 100)
            self._preview.setPixmap(
                self._pil_px.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.FastTransformation)
            )

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0].toLocalFile()
            ext = os.path.splitext(url)[1].lower()
            if ext in (".atex", ".rhg"):
                event.acceptProposedAction()
                return
            if ext == ".png" and self._current >= 0:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        url = event.mimeData().urls()[0].toLocalFile()
        ext = os.path.splitext(url)[1].lower()
        if ext in (".atex", ".rhg"):
            self._load(url)
        elif ext == ".png" and self._current >= 0:
            self._do_import(url)

    def eventFilter(self, obj, event):
        from PyQt5.QtCore import QEvent
        if event.type() == QEvent.KeyPress and self._textures and self.isVisible():
            if event.key() == Qt.Key_Left:
                self._select(max(0, self._current - 1))
                return True
            elif event.key() == Qt.Key_Right:
                self._select(min(len(self._textures) - 1, self._current + 1))
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        from PyQt5.QtWidgets import QApplication
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Botón para abrir un archivo usando la misma lógica que Drag & Drop.
        open_row = QHBoxLayout()
        self._btn_open = QPushButton(_tr("Abrir archivo"))
        self._btn_open.clicked.connect(self._open_file_dialog)
        open_row.addWidget(self._btn_open)
        root.addLayout(open_row)

        self._file_lbl = QLabel(_tr("Ningún archivo cargado"))
        self._file_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._file_lbl)

        thumb_scroll = QScrollArea()
        thumb_scroll.setFixedHeight(_THUMB + 40)
        thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        thumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        thumb_scroll.setWidgetResizable(True)
        thumb_inner = QWidget()
        self._thumb_row = QHBoxLayout(thumb_inner)
        self._thumb_row.setContentsMargins(4, 2, 4, 2)
        self._thumb_row.setSpacing(3)
        self._thumb_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        thumb_scroll.setWidget(thumb_inner)
        root.addWidget(thumb_scroll)

        from PyQt5.QtWidgets import QSizePolicy
        self._preview_container = QWidget()
        self._preview_container.setMinimumHeight(200)
        pl = QVBoxLayout(self._preview_container)
        pl.setContentsMargins(0, 0, 0, 0)
        self._preview = QLabel(_tr("Suelta aquí un archivo .atex o .rhg"))
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        pl.addWidget(self._preview)
        root.addWidget(self._preview_container, 1)

        self._info_lbl = QLabel()
        self._info_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._info_lbl)

        btn_row = QHBoxLayout()
        self._btn_export = QPushButton(_tr("Exportar PNG"))
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._export_current)
        self._btn_export_all = QPushButton(_tr("Exportar todo"))
        self._btn_export_all.setEnabled(False)
        self._btn_export_all.clicked.connect(self._export_all)
        self._btn_import = QPushButton(_tr("Importar PNG"))
        self._btn_import.setEnabled(False)
        self._btn_import.clicked.connect(self._import_dialog)
        self._btn_add = QPushButton(_tr("Añadir textura"))
        self._btn_add.setEnabled(False)
        self._btn_add.clicked.connect(self._add_texture_dialog)
        btn_row.addWidget(self._btn_export)
        btn_row.addWidget(self._btn_export_all)
        btn_row.addWidget(self._btn_import)
        btn_row.addWidget(self._btn_add)
        root.addLayout(btn_row)

    def _open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            _tr("Abrir archivo"),
            rutas.inicial("tex"),
            _tr("Archivos de textura (*.atex *.rhg);;ATEX (*.atex);;RHG (*.rhg);;All files (*.*)")
        )

        if not path:
            return

        if Path(path).suffix == ".bin":

            return

        rutas.recordar("tex", path)

        # Misma lógica de carga que al arrastrar y soltar.
        self._load(path)

    def _load(self, path):
        self._file_path = path
        self._file_ext  = os.path.splitext(path)[1].lower()
        self._file_data = open(path, "rb").read()
        self._textures  = []
        self._current   = -1
        self._thumb_btns = []
        self._btn_export.setEnabled(False)
        self._btn_export_all.setEnabled(False)
        self._btn_import.setEnabled(False)
        self._btn_add.setEnabled(False)
        self._preview.setPixmap(QPixmap())
        self._preview.setText(_tr("Cargando…"))
        self._info_lbl.setText("")
        self._file_lbl.setText(os.path.basename(path))
        while self._thumb_row.count():
            w = self._thumb_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._worker = _LoadWorker(path)
        self._worker.finished.connect(self._on_loaded)
        self._worker.start()

    def _on_loaded(self, textures, error):
        if error:
            self._preview.setText(_tr("Error: {0}").format(error))
            return
        if not textures:
            self._preview.setText(_tr("No se encontraron texturas."))
            return
        self._textures = textures
        for i, t in enumerate(textures):
            if t["img"]:
                px = _thumbnail(t["img"], t["index"])
                btn = _ThumbBtn(px, t["index"])
            else:
                btn = _ThumbBtn(QPixmap(), t["index"])
                btn.setText(_tr("✗"))
            btn.clicked.connect(lambda _, r=i: self._select(r))
            self._thumb_btns.append(btn)
            self._thumb_row.addWidget(btn)

        ok = sum(1 for t in textures if t["img"])
        self._btn_export_all.setEnabled(ok > 0)
        self._btn_add.setEnabled(self._file_ext in (".atex", ".rhg"))
        self._select(0)

    def _select(self, row):
        for i, btn in enumerate(self._thumb_btns):
            btn.setChecked(i == row)
        self._current = row
        if not (0 <= row < len(self._textures)):
            return
        t = self._textures[row]
        if t["img"] is None:
            self._preview.setPixmap(QPixmap())
            self._preview.setText(_tr("⚠ {0}").format(t.get('error', 'render error')))
            self._info_lbl.setText("")
            self._btn_export.setEnabled(False)
            self._btn_import.setEnabled(False)
            return
        img = t["img"]
        px  = _pil_to_qpixmap(img)
        w, h = img.width, img.height
        avail = self._preview_container.size()
        max_w = max(avail.width() - 8, 100)
        max_h = max(avail.height() - 8, 100)
        self._pil_px = px
        self._preview.setPixmap(px.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.FastTransformation))
        self._preview.setText("")
        self._info_lbl.setText(_tr("{0}×{1}px  │  idx {2:,}B  │  pal {3} colors").format(w, h, t['idx_sz'], t['pal_sz']//4))
        self._btn_export.setEnabled(True)
        self._btn_import.setEnabled(True)

    # ── import ──────────────────────────────────────────────────────────────────

    def _import_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, _tr("Importar PNG"), rutas.inicial("png"), _tr("PNG (*.png)")
        )
        if path:
            rutas.recordar("png", path)
            self._do_import(path)

    def _do_import(self, png_path):
        if not (0 <= self._current < len(self._textures)):
            return
        t = self._textures[self._current]

        try:
            img = Image.open(png_path).convert("RGBA")
        except Exception as exc:
            QMessageBox.critical(self, "Import error", f"Cannot open image:\n{exc}")
            return

        same_size = img.size == (t["w"], t["h"])

        if same_size:
            n_colors = t["pal_sz"] // 4
            try:
                if self._file_ext == ".rhg":
                    new_data = _inject_rhg(self._file_data, t, img)
                else:
                    new_data = _inject_atex(self._file_data, t, img)
            except Exception as exc:
                QMessageBox.critical(self, "Import error", str(exc))
                return
        else:
            w, h = img.size
            if self._file_ext == ".atex" and (w & (w - 1) or h & (h - 1) or w < 16 or h < 8):
                QMessageBox.critical(
                    self, "Import error",
                    f"Invalid size {w}×{h}. Width and height must be powers of "
                    "two (min 16×8)."
                )
                return

            cur_colors = t["pal_sz"] // 4
            n_colors, ok = QInputDialog.getInt(
                self, "Resize texture",
                f"Texture #{t['index']} will be resized from {t['w']}×{t['h']} "
                f"to {w}×{h}.\nNumber of palette colors (2-256):",
                cur_colors, 2, 256
            )
            if not ok:
                return

            tile_w = 32 if n_colors <= 16 else 16
            if w % tile_w != 0 or h % 8 != 0:
                QMessageBox.critical(
                    self, "Import error",
                    f"Invalid size {w}×{h} for {n_colors} colors. Width "
                    f"must be a multiple of {tile_w} and height a "
                    "multiple of 8."
                )
                return

            try:
                if self._file_ext == ".rhg":
                    new_data = _replace_rhg_texture(self._file_data, t["index"], img, n_colors)
                else:
                    new_data = _replace_atex_texture(self._file_data, t["index"], img, n_colors)
            except Exception as exc:
                QMessageBox.critical(self, "Import error", str(exc))
                return

        # Save back to the source file
        try:
            with open(self._file_path, "wb") as f:
                f.write(new_data)
        except Exception as exc:
            QMessageBox.critical(self, "Import error", f"Cannot write file:\n{exc}")
            return

        # Reload to reflect the change
        self._file_data = new_data
        QMessageBox.information(
            self, "Import OK",
            f"Texture #{t['index']} imported and quantized to {n_colors} colors.\n"
            "File saved."
        )
        cur = self._current
        self._load(self._file_path)
        # restore selection after reload
        self._worker.finished.connect(lambda texs, err, c=cur: self._select(c) if not err else None)

    # ── add texture ─────────────────────────────────────────────────────────────

    def _add_texture_dialog(self):
        if self._file_ext not in (".atex", ".rhg"):
            return
        path, _ = QFileDialog.getOpenFileName(self, "Add texture from PNG",
                                              rutas.inicial("png"), _tr("PNG (*.png)"))
        if not path:
            return
        rutas.recordar("png", path)

        try:
            img = Image.open(path).convert("RGBA")
        except Exception as exc:
            QMessageBox.critical(self, "Add texture error", f"Cannot open image:\n{exc}")
            return

        w, h = img.size
        if self._file_ext == ".atex" and (w & (w - 1) or h & (h - 1) or w < 16 or h < 8):
            QMessageBox.critical(
                self, "Add texture error",
                f"Invalid size {w}×{h}. Width and height must be powers of two "
                "(min 16×8)."
            )
            return

        n_colors, ok = QInputDialog.getInt(
            self, "Palette colors", "Number of colors (2-256):", 256, 2, 256
        )
        if not ok:
            return

        tile_w = 32 if n_colors <= 16 else 16
        if w % tile_w != 0 or h % 8 != 0:
            QMessageBox.critical(
                self, "Add texture error",
                f"Invalid size {w}×{h} for {n_colors} colors. Width must be "
                f"a multiple of {tile_w} and height a multiple of 8."
            )
            return

        try:
            if self._file_ext == ".rhg":
                new_data = _append_rhg_texture(self._file_data, img, n_colors)
            else:
                new_data = _append_atex_texture(self._file_data, img, n_colors)
        except Exception as exc:
            QMessageBox.critical(self, "Add texture error", str(exc))
            return

        try:
            with open(self._file_path, "wb") as f:
                f.write(new_data)
        except Exception as exc:
            QMessageBox.critical(self, "Add texture error", f"Cannot write file:\n{exc}")
            return

        self._file_data = new_data
        QMessageBox.information(self, "Add texture OK", "Texture added. File saved.")
        self._load(self._file_path)

    # ── export ──────────────────────────────────────────────────────────────────

    def _export_current(self):
        if not (0 <= self._current < len(self._textures)):
            return
        t = self._textures[self._current]
        if not t["img"]:
            return
        base = os.path.splitext(os.path.basename(self._file_path or "tex"))[0]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export texture",
            rutas.inicial("png", f"{base}_tex{t['index']:02d}.png"), _tr("PNG (*.png)")
        )
        if path:
            rutas.recordar("png", path)
            try:
                t["img"].save(path)
            except Exception as exc:
                QMessageBox.critical(self, "Export error", str(exc))

    def _export_all(self):
        folder = QFileDialog.getExistingDirectory(self, "Select export folder",
                                                  rutas.inicial("png"))
        if not folder:
            return
        rutas.recordar("png", folder)
        base = os.path.splitext(os.path.basename(self._file_path or "tex"))[0]
        for t in self._textures:
            if t["img"]:
                try:
                    t["img"].save(os.path.join(folder, f"{base}_tex{t['index']:02d}.png"))
                except Exception:
                    pass
