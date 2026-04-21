import struct

_HEADER_SIZE = 0x60
_STRIDE      = 48
_BONE_ID     = 0x30

_TEX_ID_DEFAULT = ""


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
        base = v_start + v * _STRIDE
        if base + _STRIDE > len(part_blob):
            break
        x,  y,  z,  w  = struct.unpack_from('<4f', part_blob, base)
        nx, ny, nz, _  = struct.unpack_from('<4f', part_blob, base + 0x10)
        u,  v2, _,  _  = struct.unpack_from('<4f', part_blob, base + 0x20)
        verts.append({'x': x, 'y': y, 'z': z, 'w': w,
                      'nx': nx, 'ny': ny, 'nz': nz,
                      'uvx': u, 'uvy': v2})
    return verts


def parse_bt3_face(blob: bytes) -> list:
    # Face extra BT3: same mesh format as pmdl, starts at offset 8
    # (C# MeshStartOffset=8 for ExtraFace)
    data = bytes(blob)
    subparts = []
    off = 8

    while True:
        mesh_blob, new_off = _get_individual(data, off)
        if mesh_blob is None:
            break

        tex_id = mesh_blob[20:28].hex().upper() if len(mesh_blob) >= 28 else ""
        num    = data[off + 2] * 16
        vstart = 8 + num
        vc_idx = vstart - 20
        vc     = mesh_blob[vc_idx] if vc_idx < len(mesh_blob) else 0
        vs_abs = off + vstart
        verts  = _read_verts(data, vs_abs, vc) if vc > 0 else []

        if verts:
            subparts.append({
                'bone_id': _BONE_ID,
                'tex_id':  tex_id,
                'verts':   verts,
            })
        off = new_off

    return subparts


def face_to_bt3_parts(subparts: list) -> list:
    meshes = [{'bone_id': _BONE_ID, 'tex_id': sp['tex_id'], 'vertices': sp['verts']}
              for sp in subparts]
    total_verts = sum(len(sp['verts']) for sp in subparts)
    return [{'bone_id': _BONE_ID, 'meshes': meshes,
             'total_verts': total_verts, 'length': total_verts * _STRIDE,
             'is_face_extra': True}]


def get_face_tex_ids(blob: bytes) -> list:
    subparts = parse_bt3_face(blob)
    seen, result = set(), []
    for sp in subparts:
        tid = sp['tex_id']
        if tid and tid not in seen:
            seen.add(tid); result.append(tid)
    return result


def face_tex_tbps(blob: bytes) -> set:
    ids = get_face_tex_ids(blob)
    tbps = set()
    for tid in ids:
        try: tbps.add(int.from_bytes(bytes.fromhex(tid[:4]), 'little') & 0x3FFF)
        except: pass
    return tbps