import struct, math, shutil, os
import numpy as np
from PIL import Image

RULE = {
    0x20400: 0x4400, 0x10400: 0x4400, 0x4400: 0x1400, 0x4040: 0x1040,
    0x02040: 0x1040, 0x1400:  0x0800, 0x1040: 0x0840, 0x0840: 0x0840,
    0x00800: 0x0500, 0x0500:  0x0500, 0x8040: 0x2040, 0x0840: 0x0240,
}
RULE_MAX_8BPP = (0x20400, 0x4400)
RULE_MAX_4BPP = (0x4040,  0x1040)

_SIG           = bytes([0x51, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
_DBT_ENTRY_FMT  = "<iiiiiiiiiiiBBBBQii"
_DBT_ENTRY_SIZE = 64
_QRS_SIG        = bytes([0x51, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])


def detect_pak_format(data):
    count_le = struct.unpack_from("<I", data, 0)[0]
    count_be = struct.unpack_from(">I", data, 0)[0]
    has_qrs  = _QRS_SIG in data
    if has_qrs and count_le < count_be and count_le * 4 + 8 < len(data):
        return "BT3"
    if not has_qrs and count_be * 4 + 8 < len(data):
        return "TTT"
    return "BT3"


def _psm(gstex0):      return (gstex0 >> 20) & 0x3F
def _tex0_wh(gstex0):  return 1 << ((gstex0 >> 26) & 0xF), 1 << ((gstex0 >> 30) & 0xF)
def _ps2_alpha(a):     return min(255, a * 2 - 1) if a > 0 else 0
def _p2(n):            return 1 << max(0, (max(1, n) - 1).bit_length())


def parse_pak(data):
    count = struct.unpack_from("<I", data, 0)[0]
    offs  = [struct.unpack_from("<I", data, 4 + i*4)[0] for i in range(count + 1)]
    return [(i, offs[i], offs[i+1], data[offs[i]:offs[i+1]] if offs[i+1] > offs[i] else b"")
            for i in range(count)]


def parse_pak_be(data):
    count = struct.unpack_from(">I", data, 0)[0]
    offs  = [struct.unpack_from(">I", data, 4 + i*4)[0] for i in range(count + 1)]
    return [(i, offs[i], offs[i+1], data[offs[i]:offs[i+1]] if offs[i+1] > offs[i] else b"")
            for i in range(count)]


def _is_dbt(data):
    pos = data.find(_SIG)
    while pos != -1:
        if pos + 0x21 < len(data) and data[pos + 0x10] == 0x52 and data[pos + 0x20] == 0x53:
            return True
        pos = data.find(_SIG, pos + 1)
    return False


def _is_atex(data):
    if len(data) < 0x20: return False
    count   = struct.unpack_from("<I", data, 0)[0]
    tbl_ptr = struct.unpack_from("<I", data, 4)[0]
    h3      = struct.unpack_from("<I", data, 12)[0]
    if count == 0 or count > 64: return False
    if tbl_ptr != 8:             return False
    if h3 != count * 4:          return False
    return 0x20 + count * 0x60 <= len(data)


def _dbt_header(data):
    v = struct.unpack_from("<ii", data, 0)
    return {"image_count": v[0], "image_table_ptr": v[1]}


def _dbt_entry(data, offset):
    v = struct.unpack_from(_DBT_ENTRY_FMT, data, offset)
    return {"tex_data_ptr": v[0], "pal_data_ptr": v[1],
            "tex_data_length": v[2], "pal_data_length": v[3], "gstex0": v[15]}


def _dbt_extract_raw(data, ptr, length):
    s = ptr * 4 + 96
    return bytearray(data[s: s + length - 128])


def _rarr(src, dst, o, n, loops):
    for _ in range(loops):
        dst[n] = src[o]; n += 1; o += 4
    return dst

def _tbr8(s, d, o, n):
    d = _rarr(s, d, o, n, 8); d = _rarr(s, d, o+2, n+8, 8); return d

def _tbr4(s, d, o, n):
    d = _rarr(s, d, o,    n,    4); o -= 16
    d = _rarr(s, d, o,    n+4,  4); o += 18
    d = _rarr(s, d, o,    n+8,  4); o -= 16
    d = _rarr(s, d, o,    n+12, 4)
    return d

def _transform_to_bmp_order(px, w, h):
    out = bytearray(len(px)); red = w*2; o = 0; n = len(out)-w
    for _ in range((w*h)//((w*4)*2)):
        for _ in range(2):
            for _ in range(w//16): out=_tbr8(px,out,o,n); n+=16; o+=32
            n -= red
        o -= (red*2)-17
        for _ in range(2):
            for _ in range(w//16): out=_tbr4(px,out,o,n); n+=16; o+=32
            n -= red
        o -= 1
        for _ in range(w//16): out=_tbr4(px,out,o,n); n+=16; o+=32
        n -= red
        for _ in range(w//16): out=_tbr4(px,out,o,n); n+=16; o+=32
        o -= (red*2)+15; n -= red
        for _ in range(2):
            for _ in range(w//16): out=_tbr8(px,out,o,n); n+=16; o+=32
            n -= red
        o -= 1
    return bytes(out)

def _interlacing(px):
    b = bytearray(len(px)); n = o = 0
    for _ in range(len(px)//32):
        for _ in range(2):
            c = 0
            for _ in range(8):
                for k in range(2): b[n]=px[o+c+k]; n+=1
                c += 4
            o += 2
        o += 28
    return bytes(b)

def _tex_to_0x(px):
    h = bytes(px).hex().upper(); chars = list(h); parts = []
    for i in range(len(h)):
        if i % 2 == 0: parts.append("0" + chars[i+1])
        else:           parts.append("0" + chars[i-1])
    return bytes.fromhex("".join(parts))

def _reorder_pixel_data(px, width, height):
    out = bytearray(len(px)); n_ptr = o_ptr = base_offset = column_offset = 0; cs = 32
    if width > 128: block_count=width//128; block_cols=4
    else:           block_count=1;          block_cols=width//32
    for block_row in range(height//16):
        for _ in range(8):
            bco = column_offset
            for _ in range(block_count):
                for _ in range(block_cols):
                    out[n_ptr:n_ptr+cs]=px[o_ptr:o_ptr+cs]; o_ptr+=width*16; n_ptr+=cs
                bco += 256; o_ptr = bco
            column_offset += width*2; o_ptr = column_offset
        base_offset += cs; column_offset = base_offset; o_ptr = base_offset
        if ((block_row+1)%8)==0:
            base_offset=128*width*((block_row+1)//8)//2; column_offset=base_offset; o_ptr=base_offset
    return bytes(out)

def _reorder_pal_data(pl):
    out = bytearray(len(pl)); bp = op = 0
    out[op:op+32]=pl[bp:bp+32]; bp+=32; op=64
    for _ in range(7):
        out[op:op+32]=pl[bp:bp+32]; bp+=32; op-=32
        out[op:op+32]=pl[bp:bp+32]; bp+=32; op+=64
        out[op:op+64]=pl[bp:bp+64]; bp+=64; op+=96
    out[op:op+32]=pl[bp:bp+32]; bp+=32; op-=32
    out[op:op+32]=pl[bp:bp+32]; bp+=32; op+=32
    out[bp:bp+32]=pl[bp:bp+32]
    return bytes(out)

def _dbt_to_pil(data, entry):
    gstex0 = entry["gstex0"]
    if not gstex0: return None
    psm = _psm(gstex0)
    w, h = _tex0_wh(gstex0)
    tl = entry["tex_data_length"]
    pl = entry["pal_data_length"]
    if tl <= 128: return None
    try:
        px_raw = _dbt_extract_raw(data, entry["tex_data_ptr"], tl)
        pl_raw = _dbt_extract_raw(data, entry["pal_data_ptr"], pl) if pl > 128 else None
        if psm == 19:
            indices = bytearray(_transform_to_bmp_order(bytearray(px_raw), w, h))
            pal_raw = _reorder_pal_data(bytearray(pl_raw))
            pal = []
            for i in range(256):
                r,g,b,a = pal_raw[i*4],pal_raw[i*4+1],pal_raw[i*4+2],_ps2_alpha(pal_raw[i*4+3])
                pal.extend([r,g,b,a])
            img = Image.new("RGBA", (w, h))
            img.putdata([tuple(pal[indices[y*w+x]*4:(indices[y*w+x])*4+4])
                         for y in range(h) for x in range(w)])
            return img.transpose(Image.FLIP_TOP_BOTTOM)
        elif psm == 20:
            s = _tex_to_0x(_interlacing(_reorder_pixel_data(bytearray(px_raw), w, h)))
            indices = bytearray(_transform_to_bmp_order(bytearray(s), w, h))
            pal = []
            for i in range(16):
                r,g,b,a = pl_raw[i*4],pl_raw[i*4+1],pl_raw[i*4+2],_ps2_alpha(pl_raw[i*4+3])
                pal.extend([r,g,b,a])
            img = Image.new("RGBA", (w, h))
            img.putdata([tuple(pal[indices[y*w+x]*4:indices[y*w+x]*4+4])
                         for y in range(h) for x in range(w)])
            return img.transpose(Image.FLIP_TOP_BOTTOM)
        elif psm == 0:
            img = Image.new("RGBA", (w, h))
            img.putdata([(px_raw[i*4],px_raw[i*4+1],px_raw[i*4+2],_ps2_alpha(px_raw[i*4+3]))
                         for i in range(w*h)])
            return img.transpose(Image.FLIP_TOP_BOTTOM)
    except Exception:
        return None


def parse_dbt_textures(dbt_data):
    hd        = _dbt_header(dbt_data)
    tbl_start = hd["image_table_ptr"] * 4
    textures  = []
    for i in range(hd["image_count"]):
        off = tbl_start + i * _DBT_ENTRY_SIZE
        if off + _DBT_ENTRY_SIZE > len(dbt_data): break
        e = _dbt_entry(dbt_data, off)
        if not e["gstex0"] or e["tex_data_length"] <= 128: continue
        w, h = _tex0_wh(e["gstex0"])
        idx_raw = e["tex_data_length"] - 128 if e["tex_data_length"] > 128 else 0
        pal_raw = e["pal_data_length"] - 128 if e["pal_data_length"] > 128 else 0
        raw_indices = raw_pal_bytes = None
        n_colors = 0
        try:
            psm_val = _psm(e["gstex0"])
            tl2, pl2 = e["tex_data_length"], e["pal_data_length"]
            if psm_val == 19 and pl2 > 128:
                px2 = _dbt_extract_raw(dbt_data, e["tex_data_ptr"], tl2)
                raw_indices = bytearray(_transform_to_bmp_order(bytearray(px2), w, h))
                raw_pal_bytes = bytearray(_reorder_pal_data(_dbt_extract_raw(dbt_data, e["pal_data_ptr"], pl2)))
                n_colors = 256
            elif psm_val == 20 and pl2 > 128:
                px2 = _dbt_extract_raw(dbt_data, e["tex_data_ptr"], tl2)
                s2 = _tex_to_0x(_interlacing(_reorder_pixel_data(bytearray(px2), w, h)))
                raw_indices = bytearray(_transform_to_bmp_order(bytearray(s2), w, h))
                raw_pal_bytes = bytearray(_dbt_extract_raw(dbt_data, e["pal_data_ptr"], pl2))
                n_colors = 16
        except Exception:
            pass
        textures.append({
            "w": w, "h": h,
            "psm": _psm(e["gstex0"]),
            "idx_raw": idx_raw, "pal_raw": pal_raw,
            "raw_indices": raw_indices,
            "raw_pal_bytes": raw_pal_bytes,
            "n_colors": n_colors,
            "img": _dbt_to_pil(dbt_data, e),
        })
    return textures


def _scale_dims(w, h, idx_raw, pal_raw):
    key = idx_raw + pal_raw
    if key not in RULE:
        if pal_raw == 0x400 and key > RULE_MAX_8BPP[0]:
            key = RULE_MAX_8BPP[0]
        elif pal_raw == 0x40 and key > RULE_MAX_4BPP[0]:
            key = RULE_MAX_4BPP[0]
        else:
            return w, h
    ttt_total = RULE[key]
    ttt_idx   = ttt_total - pal_raw
    if ttt_idx <= 0: return w, h
    pixels_dst = ttt_idx * (2 if pal_raw == 0x40 else 1)
    ratio = w / h if h else 1
    new_h = _p2(max(1, round(math.sqrt(pixels_dst / ratio))))
    new_w = _p2(max(1, pixels_dst // new_h))
    return new_w, new_h


def _indexed_to_atex_data(raw_indices, raw_pal, n_colors, w, h, new_w, new_h):
    pal_psp = bytearray(1024)
    for i in range(n_colors):
        r, g, b, a_raw = raw_pal[i*4], raw_pal[i*4+1], raw_pal[i*4+2], raw_pal[i*4+3]
        pal_psp[i*4]   = r; pal_psp[i*4+1] = g; pal_psp[i*4+2] = b
        pal_psp[i*4+3] = round((_ps2_alpha(a_raw) / 255) * 128)
    arr    = np.array(raw_indices, dtype='uint8').reshape(h, w)
    scaled = list(Image.fromarray(arr, mode='L').transpose(Image.FLIP_TOP_BOTTOM).resize((new_w, new_h), Image.NEAREST).tobytes())
    tile_w, tile_h = 16, 8
    idx_bytes = bytearray(new_w * new_h); n = 0
    for ty in range(new_h // tile_h):
        for tx in range(new_w // tile_w):
            for py in range(tile_h):
                for px in range(tile_w):
                    idx_bytes[n] = scaled[(ty*tile_h+py)*new_w + (tx*tile_w+px)]; n += 1
    return bytes(idx_bytes), bytes(pal_psp)


def _pil_to_atex_data(img, new_w, new_h, flip=True):
    img_prep  = img.transpose(Image.FLIP_TOP_BOTTOM) if flip else img
    scaled    = img_prep.resize((new_w, new_h), Image.NEAREST)
    has_alpha = scaled.mode == "RGBA"
    alpha_ch  = list(scaled.split()[3].tobytes()) if has_alpha else None
    if has_alpha:
        px = list(scaled.getdata())
        premul_data = [(int(r*a/255), int(g*a/255), int(b*a/255)) for r,g,b,a in px]
        premul = Image.new("RGB", (new_w, new_h)); premul.putdata(premul_data)
        to_quantize = premul
    else:
        to_quantize = scaled.convert("RGB")
    quantized = to_quantize.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    pal_raw   = quantized.getpalette()
    while len(pal_raw) < 768: pal_raw.extend([0, 0, 0])
    indices   = list(quantized.tobytes())
    alpha_max = [0] * 256
    if alpha_ch:
        for i, idx in enumerate(indices):
            if idx < 256 and alpha_ch[i] > alpha_max[idx]:
                alpha_max[idx] = alpha_ch[i]
    pal_bytes = bytearray(1024)
    for i in range(256):
        pal_bytes[i*4]   = pal_raw[i*3]; pal_bytes[i*4+1] = pal_raw[i*3+1]
        pal_bytes[i*4+2] = pal_raw[i*3+2]
        pal_bytes[i*4+3] = round((alpha_max[i]/255)*128) if has_alpha else 128
    tile_w, tile_h = 16, 8
    idx_bytes = bytearray(new_w * new_h); n = 0
    for ty in range(new_h // tile_h):
        for tx in range(new_w // tile_w):
            for py in range(tile_h):
                for px in range(tile_w):
                    idx_bytes[n] = indices[(ty*tile_h+py)*new_w + (tx*tile_w+px)]; n += 1
    return bytes(idx_bytes), bytes(pal_bytes)


def _atex_b40(idx_sz): return int(math.log2(max(idx_sz, 1))) // 2

def build_atex(tex_data_list):
    count        = len(tex_data_list)
    header_bytes = 0x20 + count * 0x60
    idx_sizes    = [w * h for w, h, _, _ in tex_data_list]
    pal_sz       = 1024
    field08      = sum(s // 64 for s in idx_sizes)
    offsets = []; cur = header_bytes
    for s in idx_sizes:
        offsets.append((cur, cur + s)); cur += s + pal_sz
    out = bytearray()
    out += struct.pack("<IIII", count, 0x8, field08, count * 4)
    out += b'\x00' * 16
    for i, (w, h, idx_b, pal_b) in enumerate(tex_data_list):
        idx_sz = idx_sizes[i]; tex_off_raw = offsets[i][0]//4; pal_off_raw = offsets[i][1]//4
        b40 = _atex_b40(idx_sz)
        d = bytearray(0x60)
        struct.pack_into("<IIIIII", d, 0, tex_off_raw, pal_off_raw, idx_sz, pal_sz, w, h)
        d[0x28]=b40; d[0x29]=b40; d[0x2A]=0x02; d[0x2B]=0x09
        d[0x34:0x40] = b'\xFF' * 12
        out += d
    for _, _, idx_b, pal_b in tex_data_list:
        out += idx_b; out += pal_b
    return bytes(out)


def _process_dbt_to_atex_bytes(dbt_data):
    textures = parse_dbt_textures(dbt_data)
    if not textures: return None
    tex_data_list = []
    for t in textures:
        new_w, new_h = _scale_dims(t["w"], t["h"], t["idx_raw"], t["pal_raw"])
        if t["img"] is not None:
            if t["psm"] in (19, 20) and t["raw_indices"] is not None:
                idx_b, pal_b = _indexed_to_atex_data(
                    t["raw_indices"], t["raw_pal_bytes"], t["n_colors"],
                    t["w"], t["h"], new_w, new_h)
            else:
                idx_b, pal_b = _pil_to_atex_data(t["img"], new_w, new_h)
        else:
            idx_b = bytes(new_w * new_h); pal_b = bytes(1024)
        tex_data_list.append((new_w, new_h, idx_b, pal_b))
    return build_atex(tex_data_list)


def _rebuild_pak_bt3_to_ttt(pak_data, atex_map):
    entries = parse_pak(pak_data)
    count   = len(entries)
    chunks  = [atex_map.get(idx, raw) for idx, start, end, raw in entries]
    # calculate correct BE header size: 4(count) + (count+1)*4, aligned to 16
    index_sz     = 4 + (count + 1) * 4
    first_offset = index_sz if index_sz % 16 == 0 else index_sz + (16 - index_sz % 16)
    cur = first_offset; offsets = []
    for c in chunks:
        offsets.append(cur); cur += len(c)
    offsets.append(cur)
    for i in range(count - 1, -1, -1):
        if not chunks[i]: offsets[i] = offsets[i+1]
    out = bytearray()
    out += struct.pack(">I", count)
    for o in offsets: out += struct.pack(">I", o)
    out += b"\x00" * (first_offset - len(out))
    for chunk in chunks: out += chunk
    return bytes(out)


def _atex_untile(idx_tiled, w, h):
    tiles_x = -(-w // 16); tiles_y = -(-h // 8)
    out = bytearray(w * h); n = 0
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            for py in range(8):
                for px in range(16):
                    ay = ty*8+py; ax = tx*16+px
                    if ay < h and ax < w: out[ay*w+ax] = idx_tiled[n]
                    n += 1
    return bytes(out)


def parse_atex(data):
    if not _is_atex(data): return []
    count = struct.unpack_from("<I", data, 0)[0]; tbl_off = 0x20
    textures = []
    for i in range(count):
        off         = tbl_off + i * 0x60
        idx_off_raw = struct.unpack_from("<I", data, off+0x00)[0]
        pal_off_raw = struct.unpack_from("<I", data, off+0x04)[0]
        idx_sz      = struct.unpack_from("<I", data, off+0x08)[0]
        pal_sz      = struct.unpack_from("<I", data, off+0x0C)[0]
        tw          = data[off+0x28]; th = data[off+0x29]
        idx_off = idx_off_raw * 4; pal_off = pal_off_raw * 4
        w = 1 << tw; h = 1 << th
        if w == 0 or h == 0: continue
        if idx_off + idx_sz > len(data): continue
        if pal_sz > 0 and pal_off + pal_sz > len(data): continue
        idx_tiled = data[idx_off:idx_off+idx_sz]
        pal_bytes = data[pal_off:pal_off+pal_sz] if pal_sz > 0 else b"\x00"*1024
        textures.append({"w": w, "h": h, "idx_linear": _atex_untile(idx_tiled, w, h), "pal_bytes": pal_bytes})
    return textures


def _psp_to_ps2_alpha(a):
    if a == 0:   return 0
    if a >= 128: return 0x80
    return round(a / 128 * 127) + 1

def _make_gstex0(w, h, psm):
    tw=w.bit_length()-1; th=h.bit_length()-1; tbw=0 if w<=64 else w//64
    lo=((th&3)<<30)|(tw<<26)|(psm<<20)|(tbw<<14); up=(1<<29)|((th>>2)&3)
    return (up<<32)|lo

def _make_gif_tex(w, h, psm, idx_raw, is_first):
    tag=bytearray(96); b2D=idx_raw//4096; b2C=0x07|((idx_raw//16)&0xFF)
    struct.pack_into("<Q",tag,0x08,(0x50<<56)|(b2D<<40)|(b2C<<32))
    struct.pack_into("<Q",tag,0x10,0x1000000000008003)
    struct.pack_into("<Q",tag,0x18,0x000000000000000E)
    struct.pack_into("<Q",tag,0x28,0x0000000000000051)
    wf=w//2; hf=h//2 if psm==19 else h//4
    struct.pack_into("<I",tag,0x30,wf); struct.pack_into("<I",tag,0x34,hf)
    struct.pack_into("<Q",tag,0x38,0x0000000000000052)
    struct.pack_into("<Q",tag,0x48,0x0000000000000053)
    struct.pack_into("<I",tag,0x50,0x8000|(idx_raw//16))
    struct.pack_into("<I",tag,0x54,0x08000000)
    return bytes(tag)

def _make_gif_pal(psm):
    tag=bytearray(96)
    if psm==19:
        pal_raw=0x400
        struct.pack_into("<Q",tag,0x08,(0x50<<56)|(0x47<<32))
        struct.pack_into("<I",tag,0x30,16); struct.pack_into("<I",tag,0x34,16)
    else:
        pal_raw=0x40
        struct.pack_into("<Q",tag,0x08,(0x50<<56)|(0x0B<<32))
        struct.pack_into("<I",tag,0x30,8); struct.pack_into("<I",tag,0x34,2)
    struct.pack_into("<Q",tag,0x10,0x1000000000008003)
    struct.pack_into("<Q",tag,0x18,0x000000000000000E)
    struct.pack_into("<Q",tag,0x28,0x0000000000000051)
    struct.pack_into("<Q",tag,0x38,0x0000000000000052)
    struct.pack_into("<Q",tag,0x48,0x0000000000000053)
    struct.pack_into("<I",tag,0x50,0x8000|(pal_raw//16))
    struct.pack_into("<I",tag,0x54,0x08000000)
    return bytes(tag), pal_raw

def _psp_pal_to_ps2(pal_psp, n_colors):
    out=bytearray(n_colors*4)
    for i in range(min(n_colors, len(pal_psp)//4)):
        r=pal_psp[i*4]; g=pal_psp[i*4+1]; b=pal_psp[i*4+2]; a=_psp_to_ps2_alpha(pal_psp[i*4+3])
        out[i*4:i*4+4]=bytes([r,g,b,a])
    return bytes(out)

def _transform_from_bmp_order(linear, w, h):
    px=bytearray(linear); out=bytearray(len(px)); red=w*2; o=0; n=len(out)-w
    def rarr_inv(src,dst,o,n,loops):
        for _ in range(loops): dst[o]=src[n]; n+=1; o+=4
        return dst
    def tbr8_inv(s,d,o,n): d=rarr_inv(s,d,o,n,8); d=rarr_inv(s,d,o+2,n+8,8); return d
    def tbr4_inv(s,d,o,n):
        d=rarr_inv(s,d,o,n,4); o-=16; d=rarr_inv(s,d,o,n+4,4); o+=18
        d=rarr_inv(s,d,o,n+8,4); o-=16; d=rarr_inv(s,d,o,n+12,4); return d
    for _ in range((w*h)//((w*4)*2)):
        for _ in range(2):
            for _ in range(w//16): out=tbr8_inv(px,out,o,n); n+=16; o+=32
            n-=red
        o-=(red*2)-17
        for _ in range(2):
            for _ in range(w//16): out=tbr4_inv(px,out,o,n); n+=16; o+=32
            n-=red
        o-=1
        for _ in range(w//16): out=tbr4_inv(px,out,o,n); n+=16; o+=32
        n-=red
        for _ in range(w//16): out=tbr4_inv(px,out,o,n); n+=16; o+=32
        o-=(red*2)+15; n-=red
        for _ in range(2):
            for _ in range(w//16): out=tbr8_inv(px,out,o,n); n+=16; o+=32
            n-=red
        o-=1
    return bytes(out)

def build_dbt(textures):
    GIF_TAG=96
    PREAMBLE=(struct.pack("<Q",0x1000000000008001)+struct.pack("<Q",0x000000000000000E)+
              struct.pack("<Q",0x0000000000000000)+struct.pack("<Q",0x000000000000003F))
    PAD_SZ=32; count=len(textures); psm=19; ENTRY_SZ=64
    idx_raws=[t["w"]*t["h"] for t in textures]; pal_raw=0x400
    tbl_off=0x20; tbl_ptr=tbl_off//4; first_gif=tbl_off+count*ENTRY_SZ
    cur=first_gif; blocks=[]
    for idx_raw in idx_raws:
        gif_tex=cur; tex_data=cur+GIF_TAG; cur=tex_data+idx_raw+PAD_SZ
        gif_pal=cur; pal_data=cur+GIF_TAG; cur=pal_data+pal_raw+PAD_SZ
        blocks.append((gif_tex,tex_data,gif_pal,pal_data))
    total=cur
    if total%64: total+=64-total%64
    out=bytearray(total)
    field08=sum(ir//256 for ir in idx_raws); total_clut_sz=count*4
    struct.pack_into("<iiii",out,0,count,tbl_ptr,field08,total_clut_sz)
    for i,t in enumerate(textures):
        w,h=t["w"],t["h"]; gif_tex,tex_data,gif_pal,pal_data=blocks[i]; idx_raw=idx_raws[i]
        tex_ptr=(tex_data-96)//4; pal_ptr=(pal_data-96)//4
        v4=idx_raw//256; v5=pal_raw//256; gstex0=_make_gstex0(w,h,psm)
        entry=bytearray(ENTRY_SZ)
        struct.pack_into("<8i",entry,0,tex_ptr,pal_ptr,idx_raw+128,pal_raw+128,v4,v5,0,0)
        struct.pack_into("<Q",entry,0x30,gstex0)
        out[tbl_off+i*ENTRY_SZ:tbl_off+(i+1)*ENTRY_SZ]=entry
    for i,t in enumerate(textures):
        w,h=t["w"],t["h"]; gif_tex,tex_data,gif_pal,pal_data=blocks[i]; idx_raw=idx_raws[i]
        out[gif_tex:gif_tex+GIF_TAG]=_make_gif_tex(w,h,psm,idx_raw,i==0)
        lin=bytes(t["idx_linear"]); arr=np.array(list(lin),dtype="uint8").reshape(h,w)
        flipped=bytearray(Image.fromarray(arr,mode="L").transpose(Image.FLIP_TOP_BOTTOM).tobytes())
        swizzled=bytearray(_transform_from_bmp_order(flipped,w,h))
        out[tex_data:tex_data+idx_raw]=swizzled
        out[tex_data+idx_raw:tex_data+idx_raw+PAD_SZ]=PREAMBLE
        gif_pal_tag,_=_make_gif_pal(psm)
        out[gif_pal:gif_pal+GIF_TAG]=gif_pal_tag
        ps2_pal=bytearray(_psp_pal_to_ps2(t["pal_bytes"],256))
        out[pal_data:pal_data+pal_raw]=_reorder_pal_data(ps2_pal)
        out[pal_data+pal_raw:pal_data+pal_raw+PAD_SZ]=PREAMBLE
    return bytes(out)


def _rebuild_pak_ttt_to_bt3(pak_data, replacements):
    entries=parse_pak_be(pak_data); count=len(entries)
    chunks=[replacements.get(idx,raw) for idx,s,e,raw in entries]
    index_sz=4+(count+1)*4
    first_offset=index_sz if index_sz%16==0 else index_sz+(16-index_sz%16)
    cur=first_offset; offsets=[]
    for c in chunks: offsets.append(cur); cur+=len(c)
    offsets.append(cur)
    for i in range(count-1,-1,-1):
        if not chunks[i]: offsets[i]=offsets[i+1]
    out=bytearray()
    out+=struct.pack("<I",count)
    for o in offsets: out+=struct.pack("<I",o)
    out+=b"\x00"*(first_offset-len(out))
    for c in chunks: out+=c
    return bytes(out)


def convert_vfx_bt3_to_ttt(data: bytes) -> tuple:
    from .pmdl.vfx_pmdl_port import port_vfx_subpak_bt3_to_ttt

    entries = parse_pak(data)
    atex_map = {}
    has_pmdl = False

    for idx, start, end, raw in entries:
        if idx == 0:
            if raw:
                try:
                    atex_map[idx] = port_vfx_subpak_bt3_to_ttt(raw)
                    has_pmdl = True
                except Exception:
                    pass
            continue

        if not _is_dbt(raw):
            continue
        atex_bytes = _process_dbt_to_atex_bytes(raw)
        if atex_bytes:
            atex_map[idx] = atex_bytes

    return _rebuild_pak_bt3_to_ttt(data, atex_map), has_pmdl


def convert_vfx_ttt_to_bt3(data: bytes) -> tuple:
    entries = parse_pak_be(data)
    replacements = {}
    for idx, s, e, raw in entries:
        if not _is_atex(raw):
            continue
        textures = parse_atex(raw)
        if not textures:
            continue
        replacements[idx] = build_dbt(textures)
    return _rebuild_pak_ttt_to_bt3(data, replacements), False