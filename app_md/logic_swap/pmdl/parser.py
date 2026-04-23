import struct
import os

MESH_START_OFFSET = 0x68
VERT_SIZE         = 48


def _ru8(b, o):  return b[o]
def _ru32(b, o): return struct.unpack_from("<I", b, o)[0]
def _rf32(b, o): return struct.unpack_from("<f", b, o)[0]


def _get_individual(part_blob, index):
    if len(part_blob) <= 100 or index + 4 > len(part_blob):
        return None, 0
    if part_blob[index + 1] != 0x80:
        return None, 0
    num  = part_blob[index + 2] * 16
    if index + 4 + num + 3 > len(part_blob):
        return None, 0
    num2 = part_blob[index + 4 + num + 2] * 16
    num3 = 8 + num + num2 + 4
    if index + num3 > len(part_blob):
        return None, 0
    return bytes(part_blob[index: index + num3]), index + num3


def _read_verts(part_blob, v_start, vc):
    verts = []
    for v in range(vc):
        base = v_start + v * VERT_SIZE
        if base + VERT_SIZE > len(part_blob):
            break
        verts.append({
            "x":   _rf32(part_blob, base),
            "y":   _rf32(part_blob, base + 4),
            "z":   _rf32(part_blob, base + 8),
            "w":   _rf32(part_blob, base + 12),
            "nx":  _rf32(part_blob, base + 16),
            "ny":  _rf32(part_blob, base + 20),
            "nz":  _rf32(part_blob, base + 24),
            "uvx": _rf32(part_blob, base + 32),
            "uvy": _rf32(part_blob, base + 36),
        })
    return verts


def _parse_meshes(part_blob):
    meshes = []
    index  = MESH_START_OFFSET

    while True:
        mesh_blob, new_index = _get_individual(part_blob, index)
        if mesh_blob is None:
            break

        tex_id     = mesh_blob[20:28].hex().upper() if len(mesh_blob) >= 28 else "?"
        raw_shader = struct.unpack_from("<H", mesh_blob, 40)[0] if len(mesh_blob) >= 42 else 14
        shader     = max(0, (raw_shader - 14) // 128)
        refl       = bool(mesh_blob[116]) if len(mesh_blob) > 116 else False

        num    = part_blob[index + 2] * 16
        vstart = 8 + num
        vc     = mesh_blob[vstart - 20] if vstart >= 20 else 0
        vs_abs = index + vstart
        verts  = _read_verts(part_blob, vs_abs, vc) if vc > 0 else []

        meshes.append({
            "index":        len(meshes),
            "offset":       index,
            "tex_id":       tex_id,
            "shader":       shader,
            "reflective":   refl,
            "vertex_count": vc,
            "vertices":     verts,
            "strips":       [verts] if verts else [],
            "_raw_blob":    mesh_blob,
        })
        index = new_index

    return meshes


def parse_part(blob, offset, part_idx):
    if offset + 16 > len(blob):
        return None
    length = _ru32(blob, offset)
    if length == 0 or offset + length > len(blob):
        return None

    anclaje   = _ru8(blob, offset + 4)
    bone_id   = _ru8(blob, offset + 10)
    refl      = bool(blob[offset + 12])
    part_blob = blob[offset: offset + length]
    bone_pos  = (_rf32(part_blob, 0x14), _rf32(part_blob, 0x18), _rf32(part_blob, 0x1C)) if length >= 0x20 else None

    if length <= 64:
        return {
            "index": part_idx, "offset": offset, "length": length,
            "bone_id": bone_id, "anclaje": anclaje, "reflective": refl,
            "bone_pos": bone_pos, "meshes": [], "total_verts": 0,
            "_blob": part_blob,
        }

    meshes      = _parse_meshes(part_blob)
    total_verts = sum(m["vertex_count"] for m in meshes)

    return {
        "index": part_idx, "offset": offset, "length": length,
        "bone_id": bone_id, "anclaje": anclaje, "reflective": refl,
        "bone_pos": bone_pos, "meshes": meshes, "total_verts": total_verts,
        "_blob": part_blob,
    }


def parse_bt3(blob: bytes) -> tuple:
    """
    Parsea un blob BT3 completo.
    Devuelve (header_dict, parts_list).
    """
    magic = blob[0:4].decode("ascii", errors="replace")

    header = {
        "magic":       magic,
        "bone_count":  blob[0x08],
        "parts_start": struct.unpack_from("<I", blob, 0x6C)[0],
    }

    parts, cursor = [], header["parts_start"]
    for _ in range(512):
        if cursor >= len(blob) - 16:
            break
        p = parse_part(blob, cursor, len(parts))
        if p is None:
            break
        parts.append(p)
        cursor += p["length"]

    return header, parts
