"""
bt3_tex_reader.py
Lectura de archivos DBT (PS2 - DBZ Budokai Tenkaichi 3) y mapeo a tex_id del PMDL.
Extraído y adaptado de tex_viewer.py.
"""
import struct
from PIL import Image

_DBT_ENTRY_FMT  = "<iiiiiiiiiiiBBBBQii"
_DBT_ENTRY_SIZE = 64
_PSM_NAMES = {0:"PSMCT32", 2:"PSMCT16", 10:"PSMCT16S",
              19:"PSMT8", 20:"PSMT4", 26:"PSMT8H", 27:"PSMT4HL", 36:"PSMT4HH"}


def _psm(gstex0):
    return (gstex0 >> 20) & 0x3F

def _tbp0(gstex0):
    return gstex0 & 0x3FFF

def _tex0_wh(gstex0):
    return 1 << ((gstex0 >> 26) & 0xF), 1 << ((gstex0 >> 30) & 0xF)

def _ps2_alpha(a):
    return min(255, (a * 2 - 1) if a * 2 != 0 else 0)

def _dbt_parse_header(data):
    v = struct.unpack_from("<iiiii", data, 0)
    return {"image_count": v[0], "image_table_ptr": v[1]}

def _dbt_parse_entry(data, offset):
    v = struct.unpack_from(_DBT_ENTRY_FMT, data, offset)
    return {"tex_data_ptr": v[0], "pal_data_ptr": v[1],
            "tex_data_length": v[2], "pal_data_length": v[3],
            "clut_size": v[5], "gstex0": v[15]}

def _dbt_extract(data, ptr, length):
    s = ptr * 4 + 96
    return bytearray(data[s: s + length - 128])

def _dbt_classify(e, data_len):
    if e["gstex0"] == 0:
        return None
    psm = _psm(e["gstex0"])
    tl = e["tex_data_length"]; pl = e["pal_data_length"]
    tp = e["tex_data_ptr"] * 4 + 96; pp = e["pal_data_ptr"] * 4 + 96
    tr = tl - 128; pr = pl - 128
    if psm == 20:
        if tl <= 128 or pl <= 128: return None
        if tp < 0 or tp + tr > data_len: return None
        if pp < 0 or pp + pr > data_len: return None
        return "psmt4"
    elif psm == 19:
        if tl <= 128 or pl <= 128: return None
        if tp < 0 or tp + tr > data_len: return None
        if pp < 0 or pp + pr > data_len: return None
        return "psmt8"
    elif psm == 0:
        if tl <= 128: return None
        if tp < 0 or tp + tr > data_len: return None
        return "psmct32"
    return None

def _rarr(src, dst, o, n, loops):
    for _ in range(loops):
        dst[n] = src[o]; n += 1; o += 4
    return dst

def _tbr8(s, d, o, n):
    d = _rarr(s, d, o,   n,   8)
    d = _rarr(s, d, o+2, n+8, 8)
    return d

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
    h = bytes(px).hex().upper()
    chars = list(h)
    parts = []
    for i in range(len(h)):
        if i % 2 == 0: parts.append("0" + chars[i + 1])
        else:           parts.append("0" + chars[i - 1])
    return bytes.fromhex("".join(parts))

def _reorder_pixel_data(px, width, height):
    out = bytearray(len(px))
    n_ptr = o_ptr = base_offset = column_offset = 0
    cs = 32
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

def _build_image(px_raw, pl_raw, w, h, mode):
    if mode == "psmt4":
        s1 = _reorder_pixel_data(bytearray(px_raw), w, h)
        s2 = _interlacing(s1)
        s3 = _tex_to_0x(s2)
        s4 = _transform_to_bmp_order(bytearray(s3), w, h)
        pal = []
        for i in range(len(pl_raw)//4):
            b=i*4; pal.append((pl_raw[b],pl_raw[b+1],pl_raw[b+2],_ps2_alpha(pl_raw[b+3])))
        img = Image.new("RGBA",(w,h)); pix=img.load()
        for y in range(h):
            for x in range(w):
                ci = s4[(h-1-y)*w + x]
                pix[x, y] = pal[ci % len(pal)]
    elif mode == "psmt8":
        s = _transform_to_bmp_order(bytearray(px_raw), w, h)
        pl = _reorder_pal_data(pl_raw)
        pal = []
        for i in range(len(pl)//4):
            b=i*4; pal.append((pl[b],pl[b+1],pl[b+2],_ps2_alpha(pl[b+3])))
        img = Image.new("RGBA",(w,h)); pix=img.load()
        for y in range(h):
            for x in range(w):
                ci=s[y*w+x]
                if ci < len(pal): pix[x, h-1-y]=pal[ci]
    elif mode == "psmct32":
        img = Image.new("RGBA",(w,h)); pix=img.load()
        for y in range(h):
            for x in range(w):
                o=(y*w+x)*4
                if o+4 <= len(px_raw):
                    r,g,b,a=px_raw[o],px_raw[o+1],px_raw[o+2],px_raw[o+3]
                    pix[x,y]=(r,g,b,_ps2_alpha(a))
    else:
        raise ValueError(f"modo desconocido: {mode}")
    return img


def load_dbt(filepath):
    """
    Carga un archivo DBT. Retorna (entries, raw_data, table_offset).
    entries: lista de dicts con index, width, height, psm, tbp0, image, error.
    raw_data + table_offset se usan para el matching exacto por material_id.
    """
    with open(filepath, "rb") as f:
        data = f.read()

    hd  = _dbt_parse_header(data)
    tbl = hd["image_table_ptr"] * 4
    results = []

    for i in range(hd["image_count"]):
        offset = tbl + i * _DBT_ENTRY_SIZE
        e      = _dbt_parse_entry(data, offset)
        mode   = _dbt_classify(e, len(data))

        gstex    = e["gstex0"]
        psm      = _psm(gstex)
        tbp      = _tbp0(gstex)
        w, h     = _tex0_wh(gstex)
        psm_name = _PSM_NAMES.get(psm, f"PSM{psm}")

        if mode is None:
            results.append({"index": i, "width": w, "height": h,
                             "psm": psm_name, "tbp0": tbp,
                             "image": None, "error": "entrada no soportada"})
            continue
        try:
            px     = _dbt_extract(data, e["tex_data_ptr"], e["tex_data_length"])
            pl_raw = _dbt_extract(data, e["pal_data_ptr"], e["pal_data_length"]) if mode != "psmct32" else bytearray()
            img    = _build_image(px, pl_raw, w, h, mode)
            results.append({"index": i, "width": w, "height": h,
                             "psm": psm_name, "tbp0": tbp,
                             "image": img, "error": None})
        except Exception as ex:
            results.append({"index": i, "width": w, "height": h,
                             "psm": psm_name, "tbp0": tbp,
                             "image": None, "error": str(ex)})

    return results, data, tbl


def material_id_from_entry(data: bytes, entry_offset: int, tex_count: int) -> str:
    """
    Reconstruye el tex_id de 8 bytes de un entry DBT, igual que C# SetParameters.
    Retorna el hex string en mayúsculas (mismo formato que el parser BT3).
    entry_offset = PalStart (inicio del entry en la tabla).
    tex_count = índice del entry (para calcular numero2).
    """
    numero  = struct.unpack_from("<i", data, entry_offset + 28)[0]
    numero2 = data[entry_offset + 48] + 4 + 32 * tex_count

    def to_4bytes_be(n):
        return [(n >> 24) & 0xFF, (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF]

    a2 = to_4bytes_be(numero)
    a3 = to_4bytes_be(numero2)

    arr = [0] * 8
    arr[0] = a2[3]
    arr[1] = (a2[2] + data[entry_offset + 45]) & 0xFF
    arr[2] = data[entry_offset + 46]
    arr[3] = data[entry_offset + 47]
    arr[4] = a3[3]
    arr[5] = a3[2]
    arr[6] = data[entry_offset + 50]
    arr[7] = data[entry_offset + 51]

    return bytes(arr).hex().upper()


def map_dbt_to_tex_ids(dbt_entries, tex_ids, raw_data: bytes = None, table_offset: int = 0):
    """
    Mapea entradas DBT a tex_id del PMDL.
    Si raw_data está disponible, usa matching exacto por material_id (igual que C#).
    Si no, cae a matching ordinal como fallback.
    tex_ids: lista de strings hex ordenados por TBP0.
    Retorna dict {tex_id_hex: PIL.Image}
    """
    valid = [e for e in dbt_entries if e.get("image") is not None]

    # Matching exacto por ID
    if raw_data:
        entry_size = 64
        id_to_img  = {}
        for i, e in enumerate(valid):
            offset = table_offset + i * entry_size
            try:
                mid = material_id_from_entry(raw_data, offset, i)
                id_to_img[mid] = e["image"]
            except Exception:
                pass
        result = {}
        for tid in tex_ids:
            if tid.upper() in id_to_img:
                result[tid] = id_to_img[tid.upper()]
        if result:
            return result

    # Fallback ordinal
    result = {}
    for i, tid in enumerate(tex_ids):
        if i < len(valid):
            result[tid] = valid[i]["image"]
    return result