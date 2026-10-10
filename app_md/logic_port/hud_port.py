import struct
import numpy as np
from pathlib import Path
from PIL import Image

_SRC = Path(__file__).resolve().parent / "src"

_SIG           = bytes([0x51,0x00,0x00,0x00,0x00,0x00,0x00,0x00])
_DBT_ENTRY_FMT = "<iiiiiiiiiiiBBBBQii"
_DBT_ENTRY_SZ  = 64


def _psm(g):      return (g >> 20) & 0x3F
def _tex0_wh(g):  return 1 << ((g >> 26) & 0xF), 1 << ((g >> 30) & 0xF)
def _ps2_alpha(a): return min(255, a * 2 - 1) if a > 0 else 0


def _dbt_header(d):
    v = struct.unpack_from("<ii", d, 0)
    return {"image_count": v[0], "image_table_ptr": v[1]}

def _dbt_entry(d, off):
    v = struct.unpack_from(_DBT_ENTRY_FMT, d, off)
    return {"tex_data_ptr": v[0], "pal_data_ptr": v[1],
            "tex_data_length": v[2], "pal_data_length": v[3], "gstex0": v[15]}

def _dbt_extract_raw(d, ptr, length):
    s = ptr * 4 + 96
    return bytearray(d[s: s + length - 128])

def _rarr(src, dst, o, n, loops):
    for _ in range(loops):
        dst[n] = src[o]; n += 1; o += 4
    return dst

def _tbr8(s, d, o, n):
    d = _rarr(s, d, o, n, 8); d = _rarr(s, d, o+2, n+8, 8); return d

def _tbr4(s, d, o, n):
    d = _rarr(s, d, o, n, 4); o -= 16
    d = _rarr(s, d, o, n+4, 4); o += 18
    d = _rarr(s, d, o, n+8, 4); o -= 16
    d = _rarr(s, d, o, n+12, 4)
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
    g = entry["gstex0"]
    if not g: return None
    psm = _psm(g); w, h = _tex0_wh(g)
    tl = entry["tex_data_length"]; pl = entry["pal_data_length"]
    if tl <= 128: return None
    try:
        px_raw = _dbt_extract_raw(data, entry["tex_data_ptr"], tl)
        pl_raw = _dbt_extract_raw(data, entry["pal_data_ptr"], pl) if pl > 128 else None
        if psm == 19:
            indices = bytearray(_transform_to_bmp_order(bytearray(px_raw), w, h))
            pal_raw = _reorder_pal_data(bytearray(pl_raw))
            pal = []
            for i in range(256):
                r,g2,b,a = pal_raw[i*4],pal_raw[i*4+1],pal_raw[i*4+2],_ps2_alpha(pal_raw[i*4+3])
                pal.extend([r,g2,b,a])
            img = Image.new("RGBA", (w, h))
            img.putdata([tuple(pal[indices[y*w+x]*4:(indices[y*w+x])*4+4])
                         for y in range(h) for x in range(w)])
            return img.transpose(Image.FLIP_TOP_BOTTOM)
        elif psm == 0:
            img = Image.new("RGBA", (w, h))
            img.putdata([(px_raw[i*4],px_raw[i*4+1],px_raw[i*4+2],_ps2_alpha(px_raw[i*4+3]))
                         for i in range(w*h)])
            return img.transpose(Image.FLIP_TOP_BOTTOM)
    except Exception:
        return None


def _crop_solid(img, threshold=16):
    arr = np.array(img.convert("RGBA"))
    mask = arr[:,:,3] >= threshold
    rows = np.any(mask, axis=1); cols = np.any(mask, axis=0)
    if not rows.any(): return img
    r0,r1 = np.where(rows)[0][[0,-1]]; c0,c1 = np.where(cols)[0][[0,-1]]
    return img.crop((c0, r0, c1+1, r1+1))

def _fit_into(crop, cw, ch, margin_v):
    sw, sh = crop.size
    scale = min(cw/sw, (ch - margin_v*2)/sh)
    nw, nh = max(1,round(sw*scale)), max(1,round(sh*scale))
    canvas = Image.new("RGBA", (cw, ch), (0,0,0,0))
    r = crop.resize((nw,nh), Image.LANCZOS)
    canvas.paste(r, ((cw-nw)//2,(ch-nh)//2), r)
    return canvas

def _build_hud_images(src_img):
    cropped = _crop_solid(src_img)
    hud1 = _fit_into(cropped, 64, 32, 1)
    hud2 = _fit_into(cropped, 64, 32, 0)
    hud3 = Image.new("RGBA", (256, 64), (0,0,0,0))
    hud3.paste(cropped, (0, 0), cropped)
    return hud1, hud2, hud3

def _img_to_rhg_data(img, w, h):
    scaled = img.resize((w, h), Image.LANCZOS).convert("RGBA")
    arr = np.array(scaled)
    alpha_ch = arr[:,:,3].flatten()
    quantized = scaled.convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    pal_raw = quantized.getpalette()
    while len(pal_raw) < 768: pal_raw.extend([0,0,0])
    raw_indices = np.array(quantized).flatten()
    indices = (raw_indices + 1).tolist()
    for i in range(len(indices)):
        if alpha_ch[i] < 16: indices[i] = 0
    pal_bytes = bytearray(1024)
    for i in range(255):
        pal_bytes[(i+1)*4]   = pal_raw[i*3]
        pal_bytes[(i+1)*4+1] = pal_raw[i*3+1]
        pal_bytes[(i+1)*4+2] = pal_raw[i*3+2]
        pal_bytes[(i+1)*4+3] = 255
    tile_w, tile_h = 16, 8
    idx_bytes = bytearray(w * h); n = 0
    for ty in range(h // tile_h):
        for tx in range(w // tile_w):
            for py in range(tile_h):
                for p in range(tile_w):
                    idx_bytes[n] = indices[(ty*tile_h+py)*w + (tx*tile_w+p)]; n += 1
    return bytes(idx_bytes), bytes(pal_bytes)

def _patch_rhg(img, rhg_bytes):
    w   = struct.unpack_from('<I', rhg_bytes, 0x44)[0]
    h   = struct.unpack_from('<I', rhg_bytes, 0x48)[0]
    isz = struct.unpack_from('<I', rhg_bytes, 0x74)[0]
    psz = struct.unpack_from('<I', rhg_bytes, 0x98)[0]
    idx_off = 0x100
    pal_off = idx_off + isz
    idx, pal = _img_to_rhg_data(img, w, h)
    result = bytearray(rhg_bytes)
    result[idx_off:idx_off+isz] = idx
    result[pal_off:pal_off+psz] = pal
    return bytes(result)


def convert_hud_from_dbt(dbt_data: bytes) -> tuple:
    hd  = _dbt_header(dbt_data)
    tbl = hd["image_table_ptr"] * 4
    e   = _dbt_entry(dbt_data, tbl)
    img = _dbt_to_pil(dbt_data, e)
    if img is None:
        raise ValueError("Could not decode HUD texture from DBT")

    hud1, hud2, hud3 = _build_hud_images(img)

    specs = [
        ("045_hud_1.rhg",     hud1),
        ("047_hud_2.rhg",     hud2),
        ("049_hud_clash.rhg", hud3),
    ]
    results = {}
    for name, hud_img in specs:
        rhg_path = _SRC / name
        if not rhg_path.exists():
            raise FileNotFoundError(f"RHG template not found: {rhg_path}")
        rhg_orig = rhg_path.read_bytes()
        results[name] = _patch_rhg(hud_img, rhg_orig)

    ags_names = ["044_hud_1.ags", "046_hud_2.ags", "048_hud_clash.ags"]
    for name in ags_names:
        ags_path = _SRC / name
        if not ags_path.exists():
            raise FileNotFoundError(f"AGS template not found: {ags_path}")
        results[name] = ags_path.read_bytes()

    return results
