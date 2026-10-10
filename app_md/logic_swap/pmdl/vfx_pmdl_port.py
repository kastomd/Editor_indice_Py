import struct
from PIL import Image

from .parser import parse_bt3
from .file_detector import detect_format
from .bt3_tex_reader import load_dbt, map_dbt_to_tex_ids
from .bt3_to_ttt import convert_bt3_to_ttt


_INDEX_SIZE  = 0x400
_PMDL_IDX   = 0x0C
_DBT_IDX    = 0x30
_TEX_SIZE   = 256
_PAK_SIG_TTT = 0x000000FA


def _read_le_entry(data: bytes, idx_off: int):
    start = struct.unpack_from("<I", data, idx_off)[0]
    end   = struct.unpack_from("<I", data, idx_off + 4)[0]
    return data[start:end] if end > start else b""


def _parse_vfx_subpak(data: bytes):
    pmdl = _read_le_entry(data, _PMDL_IDX)
    dbt  = _read_le_entry(data, _DBT_IDX)
    return pmdl, dbt


def _scale_to_256(img: Image.Image) -> Image.Image:
    if img.size == (_TEX_SIZE, _TEX_SIZE):
        return img
    return img.resize((_TEX_SIZE, _TEX_SIZE), Image.NEAREST)


def _build_uv_map(tex_id: str) -> dict:
    return {tex_id: {"x": 0, "y": 0, "w": _TEX_SIZE, "h": _TEX_SIZE}}


def _pil_to_atex_256(img: Image.Image) -> bytes:
    from ..swap_vfx import build_atex, _pil_to_atex_data
    idx_b, pal_b = _pil_to_atex_data(img.convert("RGBA"), _TEX_SIZE, _TEX_SIZE, flip=False)
    return build_atex([(_TEX_SIZE, _TEX_SIZE, idx_b, pal_b)])


def _build_ttt_subpak(pmdl_ttt: bytes, atex: bytes) -> bytes:
    # offsets físicos: índice = 0x400 bytes, luego pmdl, luego atex
    pmdl_start = _INDEX_SIZE
    pmdl_end   = pmdl_start + len(pmdl_ttt)
    atex_start = pmdl_end
    atex_end   = atex_start + len(atex)

    idx = bytearray(_INDEX_SIZE)

    # firma BE
    struct.pack_into(">I", idx, 0x00, _PAK_SIG_TTT)

    # 0x04 y 0x08: pmdl_start en BE
    struct.pack_into(">I", idx, 0x04, pmdl_start)
    struct.pack_into(">I", idx, 0x08, pmdl_start)

    # 0x0C: pmdl_start, 0x10: pmdl_end
    struct.pack_into(">I", idx, 0x0C, pmdl_start)
    struct.pack_into(">I", idx, 0x10, pmdl_end)

    # 0x14 a 0x2C: repetir pmdl_end (relleno entre pmdl y atex)
    for off in range(0x14, 0x30, 4):
        struct.pack_into(">I", idx, off, pmdl_end)

    # 0x30: atex_start, 0x34: atex_end
    struct.pack_into(">I", idx, 0x30, atex_start)
    struct.pack_into(">I", idx, 0x34, atex_end)

    # 0x38 a 0x3F0: repetir atex_end
    for off in range(0x38, 0x3F0, 4):
        struct.pack_into(">I", idx, off, atex_end)

    # 0x3F0 a 0x400: padding de 00 (ya está por defecto en bytearray)

    return bytes(idx) + pmdl_ttt + atex


def port_vfx_subpak_bt3_to_ttt(subpak_data: bytes) -> bytes:
    pmdl_blob, dbt_blob = _parse_vfx_subpak(subpak_data)

    if not pmdl_blob or not dbt_blob:
        raise ValueError("vfx subpak: could not read pmdl or dbt entries")

    if detect_format(pmdl_blob) != "bt3":
        raise ValueError("vfx subpak: pmdl is not a valid BT3 model")

    _, parts = parse_bt3(pmdl_blob)
    if not parts:
        raise ValueError("vfx subpak: no parts found in pmdl")

    # extraer tex_id de la primera (y única) textura del modelo
    tex_id = None
    for part in parts:
        for mesh in part.get("meshes", []):
            tex_id = mesh.get("tex_id")
            if tex_id:
                break
        if tex_id:
            break

    if not tex_id:
        raise ValueError("vfx subpak: no tex_id found in pmdl meshes")

    # leer DBT desde bytes usando archivo temporal
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dbt")
    try:
        tmp.write(dbt_blob); tmp.flush(); tmp.close()
        entries, raw_data, tbl_offset = load_dbt(tmp.name)
    finally:
        try: os.unlink(tmp.name)
        except: pass

    mapped = map_dbt_to_tex_ids(entries, [tex_id], raw_data=raw_data, table_offset=tbl_offset)
    tex_img = mapped.get(tex_id)

    if tex_img is None:
        # fallback: tomar la primera entrada válida
        for e in entries:
            if e.get("image") is not None:
                tex_img = e["image"]
                break

    if tex_img is None:
        raise ValueError("vfx subpak: could not extract texture from dbt")

    tex_img_256 = _scale_to_256(tex_img)
    uv_map      = _build_uv_map(tex_id)

    pmdl_ttt = convert_bt3_to_ttt(pmdl_blob, parts, uv_map=uv_map)
    atex     = _pil_to_atex_256(tex_img_256)

    return _build_ttt_subpak(pmdl_ttt, atex)