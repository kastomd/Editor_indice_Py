import math
import struct
from collections import defaultdict


_BONE_FLAG = {1: b'\x01\x43\x00\x12', 2: b'\x01\xC3\x00\x12',
              3: b'\x01\x43\x01\x12', 4: b'\x01\xC3\x01\x12'}

_TTT_VERSION      = 6
_HEADER_SIZE      = 0xA0
_MAT_BLOCK_SIZE   = 0x20
_WEIRD_BLOCK_SIZE = 0x20
_BONE_BLOCK_SIZE  = 0xA0
_PART_INDEX_ENTRY = 0x20
_CAMERA_BYTES     = bytes([0x00,0x00,0x20,0x42, 0x00,0x00,0xF0,0x42])


def _compute_bbox(parts: list) -> tuple:
    bx = by = bz = 0.0
    for part in parts:
        for mesh in part.get("meshes", []):
            for v in mesh.get("vertices", []):
                ax, ay, az = abs(v["x"]), abs(v["y"]), abs(v["z"])
                if ax > bx: bx = ax
                if ay > by: by = ay
                if az > bz: bz = az
    return (bx or 1.0, by or 1.0, bz or 1.0)


def _quant(val, bbox):
    v = int(round(val * 32767.0 / bbox))
    return max(-32768, min(32767, v))


# Huesos BT3 con flag especial en TTT
_SPECIAL_BONE_FLAGS = {
    0x30: 0x06,
    0x40: 0x01,
    0x41: 0x02,
    0x42: 0x07,
    0x43: 0x08,
}
_SPECIAL_BONES = set(_SPECIAL_BONE_FLAGS.keys()) | {0x33}


def _group_meshes(parts: list) -> list:
    """
    Retorna lista de (group_key, flag, [(part, mesh), ...]).
    Huesos especiales forman grupo propio por bone_id, ignorando material.
    El resto se agrupa por material, excluyendo meshes de huesos especiales.
    """
    special_groups = defaultdict(list)
    material_groups = defaultdict(list)

    for part in parts:
        bid = part.get("bone_id", 0)
        for mesh in part.get("meshes", []):
            if bid in _SPECIAL_BONES:
                special_groups[bid].append((part, mesh))
            else:
                material_groups[mesh.get("tex_id", "?")].append((part, mesh))

    result = []
    for bid, meshes in special_groups.items():
        flag = _SPECIAL_BONE_FLAGS.get(bid, 0x00)
        result.append((f"bone_{bid:#04x}", flag, meshes))
    for tid, meshes in material_groups.items():
        if meshes:
            result.append((tid, 0x00, meshes))
    return result


_W_TABLE = {
    0.0: 0x8000, 0.1: 0x740c, 0.2: 0x6719, 0.3: 0x5a26, 0.4: 0x4d33,
    0.5: 0x4040, 0.6: 0x344c, 0.7: 0x2759, 0.8: 0x1a66, 0.9: 0x0d73, 1.0: 0x0080,
}

def _w_to_peso(w: float) -> int:
    level = round(max(0.0, min(1.0, w)) * 10) / 10.0
    return _W_TABLE.get(level, max(0x0080, round((1.0 - w) * 0x8000)))


def _uv_byte(uv_f: float, coord: int, size: int) -> int:
    import math
    frac = uv_f - math.floor(uv_f)
    if frac == 0.0 and uv_f > 0.0:
        frac = 1.0
    pixel = coord + frac * size
    return max(coord, min(min(coord + size - 1, 255), round(pixel)))


def _build_ttt_part_entries(meshes_with_parts: list, bbox: tuple,
                             bt3_parts: list = None,
                             uv_map: dict = None) -> list:
    sub_entries = []
    for part, mesh in meshes_with_parts:
        verts = mesh.get("vertices", [])
        if not verts:
            continue
        bone_id  = part.get("bone_id", 0)
        bone_ids = [bone_id, 0, 0, 0]
        vb = bytearray()
        for v in verts:
            peso = _w_to_peso(v.get("w", 0.0))
            vb += struct.pack("<H", peso)
            if uv_map and mesh.get("tex_id") in uv_map:
                info  = uv_map[mesh["tex_id"]]
                ix, iy, iw, ih = info["x"], info["y"], info["w"], info["h"]
                vb += bytes([_uv_byte(v["uvx"], ix, iw), _uv_byte(v["uvy"], iy, ih)])
            else:
                vb += bytes([int(round(v["uvx"] * 255.0)) & 0xFF,
                             int(round(v["uvy"] * 255.0)) & 0xFF])
            vb += struct.pack("<h", _quant(v["x"], bbox[0]))
            vb += struct.pack("<h", _quant(v["y"], bbox[1]))
            vb += struct.pack("<h", _quant(v["z"], bbox[2]))
        sub_entries.append({"vert_count": len(verts), "bone_count": 1,
                            "bone_ids": bone_ids, "vert_data": bytes(vb)})
    return sub_entries


def _assemble_ttt_part(sub_entries: list) -> bytes:
    """Ensambla el binario de una parte TTT desde la lista de subpartes."""
    if not sub_entries:
        return b""

    index_raw   = 4 + len(sub_entries) * 0x10
    index_size  = index_raw + (16 - index_raw % 16) % 16
    data_offset = index_size
    idx = bytearray()
    idx += struct.pack("<I", len(sub_entries))
    for e in sub_entries:
        idx += struct.pack("<H", e["vert_count"])
        idx += struct.pack("<H", e["bone_count"])
        idx += bytes(e["bone_ids"][:4])
        idx += _BONE_FLAG[min(e["bone_count"], 4)]
        idx += struct.pack("<I", data_offset)
        data_offset += len(e["vert_data"])
    while len(idx) < index_size:
        idx += b'\x00'

    body = bytes(idx) + b"".join(e["vert_data"] for e in sub_entries)
    return body + b'\x00' * ((16 - len(body) % 16) % 16)


def _read_bones_from_parts(bt3_parts: list) -> list:
    huesos, pila = [], []
    for i, part in enumerate(bt3_parts):
        bone_id   = part.get("bone_id", 0)
        anclaje   = part.get("anclaje", 0)
        bone_pos  = part.get("bone_pos") or (0.0, 0.0, 0.0)
        padre_idx = pila[-1] if pila else None
        huesos.append({"idx": i, "bone_id": bone_id, "anclaje": anclaje,
                       "pos": bone_pos, "padre_idx": padre_idx,
                       "_blob": part.get("_blob", b"")})
        pila.append(i)
        for _ in range(anclaje):
            if pila:
                pila.pop()
    return huesos


def _padre_bone_id(bt3_parts: list, part_idx: int) -> int:
    """Retorna el bone_id del padre de la parte en la jerarquía BT3."""
    pila = []
    for i, part in enumerate(bt3_parts):
        padre = pila[-1] if pila else None
        if i == part_idx:
            if padre is not None:
                return bt3_parts[padre].get("bone_id", 0)
            return 0
        pila.append(i)
        for _ in range(part.get("anclaje", 0)):
            if pila:
                pila.pop()
    return 0


def _get_depth(huesos, idx: int) -> int:
    d, cur = 0, idx
    while huesos[cur]["padre_idx"] is not None:
        cur = huesos[cur]["padre_idx"]
        d += 1
        if d > len(huesos):
            break
    return d


def _build_ttt_bones(bt3_parts: list) -> bytes:
    print("  [huesos] Construyendo jerarquía desde partes BT3...")
    huesos = _read_bones_from_parts(bt3_parts)
    if not huesos:
        print("  [huesos] Sin huesos.")
        return b""
    print(f"  [huesos] {len(huesos)} huesos. Calculando pop_levels...")

    depths = [_get_depth(huesos, i) for i in range(len(huesos))]

    out = bytearray()
    for i, h in enumerate(huesos):
        bone = bytearray(_BONE_BLOCK_SIZE)

        struct.pack_into("<I", bone, 0x00, 0xA0)

        if i == len(huesos) - 1:
            pop = 0x00010000
        elif huesos[i+1]["padre_idx"] != i:
            pop = max(0, depths[i] - depths[i+1] + 1)
        else:
            pop = 0
        struct.pack_into("<I", bone, 0x04, pop)

        struct.pack_into("<H", bone, 0x08, 0x0001)
        bone[0x0A] = h["bone_id"]

        # TTT[0x10:0x40] = BT3_blob[0x10:0x40] directo (incluye X lateral en 0x10)
        # TTT[0x40:0x60] = BT3_blob_siguiente[0x10:0x30]
        blob = h.get("_blob", b"")
        if len(blob) >= 0x40:
            bone[0x10:0x40] = blob[0x10:0x40]
            if i != 0:
                struct.pack_into("<f", bone, 0x3C, 0.0)
            if len(blob) >= 0x60:
                bone[0x40:0x60] = blob[0x40:0x60]
        else:
            px, py, pz = h["pos"]
            struct.pack_into("<4f", bone, 0x10, 0.0, px, py, pz)
            if h["padre_idx"] is not None:
                ppx, ppy, ppz = huesos[h["padre_idx"]]["pos"]
            else:
                ppx, ppy, ppz = 0.0, 0.0, 0.0
            struct.pack_into("<4f", bone, 0x20, 0.0, ppx, ppy, ppz)
            struct.pack_into("<4f", bone, 0x30, 0.0, px-ppx, py-ppy, pz-ppz)

        out += bone

    print(f"  [huesos] Bloque construido ({len(out)} bytes).")
    return bytes(out)


def _build_ttt_header(bt3_blob, bone_count, num_materials,
                      bones_offset, mats_offset, weird_offset,
                      part_count, parts_index_offset, bbox):
    hdr = bytearray(_HEADER_SIZE)
    hdr[0:4] = b'pMdl'
    struct.pack_into("<I", hdr, 0x04, _TTT_VERSION)
    struct.pack_into("<I", hdr, 0x08, bone_count)
    hdr[0x10:0x18] = _CAMERA_BYTES
    if len(bt3_blob) >= 0x28:
        hdr[0x18:0x28] = bt3_blob[0x18:0x28]
    struct.pack_into("<f", hdr, 0x40, bbox[0])
    struct.pack_into("<f", hdr, 0x44, bbox[1])
    struct.pack_into("<f", hdr, 0x48, bbox[2])
    struct.pack_into("<I", hdr, 0x50, bones_offset)
    struct.pack_into("<I", hdr, 0x54, num_materials)
    struct.pack_into("<I", hdr, 0x58, mats_offset)
    struct.pack_into("<I", hdr, 0x5C, part_count)
    struct.pack_into("<I", hdr, 0x60, parts_index_offset)
    struct.pack_into("<I", hdr, 0x68, weird_offset)
    return bytes(hdr)


def _build_materials_block(n):
    out = bytearray()
    for i in range(n):
        b = bytearray(_MAT_BLOCK_SIZE)
        struct.pack_into("<I", b, 0x00, i)
        struct.pack_into("<I", b, 0x04, n)  # siempre igual a num_materiales
        out += b
    return bytes(out)


def _build_weird_block(bones_offset):
    b = bytearray(_WEIRD_BLOCK_SIZE)
    struct.pack_into("<I", b, 0x00, bones_offset)
    struct.pack_into("<I", b, 0x10, bones_offset)
    return bytes(b)


def _build_parts_index(parts_data, parts_start):
    out, cursor = bytearray(), parts_start
    for part_bytes, opacity, part_id, flag in parts_data:
        e = bytearray(_PART_INDEX_ENTRY)
        struct.pack_into("<H", e, 0x00, part_id & 0xFFFF)
        struct.pack_into("<H", e, 0x02, opacity & 0xFFFF)
        struct.pack_into("<I", e, 0x04, cursor)
        struct.pack_into("<I", e, 0x08, len(part_bytes))
        struct.pack_into("<I", e, 0x0C, flag)
        out += e
        cursor += len(part_bytes)
    return bytes(out)


def convert_bt3_to_ttt(bt3_blob: bytes, bt3_parts: list, uv_map: dict = None) -> bytes:
    from .optim_bone_ids import optimize_part_ids

    print("\n=== Iniciando conversión BT3 → TTT ===")

    print(f"[1/6] Calculando bounding box desde {sum(len(p.get('meshes',[])) for p in bt3_parts)} meshes...")
    bbox = _compute_bbox(bt3_parts)
    print(f"      bbox = X:{bbox[0]:.4f}  Y:{bbox[1]:.4f}  Z:{bbox[2]:.4f}")

    print("[2/6] Agrupando meshes por material/hueso especial...")
    grouped = _group_meshes(bt3_parts)
    print(f"      {len(grouped)} grupos")

    print("[3/6] Construyendo entradas de subpartes...")
    all_part_entries = []
    part_flags = []
    for i, (key, flag, meshes) in enumerate(grouped):
        total_v = sum(len(m.get("vertices", [])) for _, m in meshes)
        print(f"      Grupo {i+1}/{len(grouped)}: key={key} flag={flag:#04x} subpartes={len(meshes)} verts={total_v}")
        entries = _build_ttt_part_entries(meshes, bbox, uv_map=uv_map)
        all_part_entries.append(entries)
        part_flags.append(flag)

    print("      Optimizando IDs de huesos (FF repeats)...")
    all_part_entries = optimize_part_ids(all_part_entries)

    print("      Ensamblando partes TTT...")
    assembled = [(p, f) for p, f in zip(
        (_assemble_ttt_part(e) for e in all_part_entries), part_flags) if p]
    ttt_parts  = [p for p, _ in assembled]
    ttt_flags  = [f for _, f in assembled]
    print(f"      {len(ttt_parts)} partes TTT generadas.")

    print("[4/6] Construyendo bloque de huesos TTT...")
    bones_blob = _build_ttt_bones(bt3_parts)
    bone_count = len(bt3_parts)

    print("[5/6] Calculando offsets...")
    num_mats           = len(grouped)
    mats_offset        = _HEADER_SIZE
    weird_offset       = mats_offset + num_mats * _MAT_BLOCK_SIZE
    bones_offset       = weird_offset + _WEIRD_BLOCK_SIZE
    parts_index_offset = bones_offset + len(bones_blob)
    parts_index_size   = len(ttt_parts) * _PART_INDEX_ENTRY
    parts_start        = parts_index_offset + parts_index_size
    pad                = (16 - parts_start % 16) % 16
    parts_start       += pad
    print(f"      mats@{mats_offset:#x}  weird@{weird_offset:#x}  huesos@{bones_offset:#x}  "
          f"partsIdx@{parts_index_offset:#x}  partes@{parts_start:#x}")

    print("[6/6] Ensamblando binario final...")
    parts_data = [(p, 0xFFFF, i, f) for i, (p, f) in enumerate(zip(ttt_parts, ttt_flags))]
    result = (
        _build_ttt_header(bt3_blob, bone_count, num_mats,
                          bones_offset, mats_offset, weird_offset,
                          len(ttt_parts), parts_index_offset, bbox)
        + _build_materials_block(num_mats)
        + _build_weird_block(bones_offset)
        + bones_blob
        + _build_parts_index(parts_data, parts_start)
        + b'\x00' * pad
        + b"".join(ttt_parts)
    )
    print(f"=== Conversión completa: {len(result)} bytes ({len(result)/1024:.1f} KB) ===\n")
    return result

def _build_face_bone() -> bytes:
    bone = bytearray(_BONE_BLOCK_SIZE)
    struct.pack_into("<I", bone, 0x00, 0xA0)
    struct.pack_into("<I", bone, 0x04, 0x00010000)
    struct.pack_into("<H", bone, 0x08, 0x0001)
    bone[0x0A] = 0x30
    return bytes(bone)


def _group_meshes_face(parts: list) -> list:
    from collections import defaultdict
    mat_groups = defaultdict(list)
    for part in parts:
        for mesh in part.get("meshes", []):
            mat_groups[mesh.get("tex_id", "?")].append((part, mesh))
    return [(tid, 0x06, meshes) for tid, meshes in mat_groups.items() if meshes]


def convert_bt3_face_to_ttt(face_blob: bytes, uv_map: dict = None,
                             bbox: tuple = None) -> bytes:
    from .bt3_face_parser import parse_bt3_face
    from .optim_bone_ids import optimize_part_ids

    subparts = parse_bt3_face(face_blob)
    if not subparts:
        return b''

    fake_parts = [
        {'bone_id': 0x30, 'meshes': [{'tex_id': sp['tex_id'], 'vertices': sp['verts']}]}
        for sp in subparts
    ]

    if bbox is None:
        bx = by = bz = 0.0
        for sp in subparts:
            for v in sp['verts']:
                bx = max(bx, abs(v['x'])); by = max(by, abs(v['y'])); bz = max(bz, abs(v['z']))
        bbox = (bx or 1.0, by or 1.0, bz or 1.0)

    grouped = _group_meshes_face(fake_parts)
    all_entries = [_build_ttt_part_entries(m, bbox, uv_map=uv_map) for _, _, m in grouped]
    flags       = [f for _, f, _ in grouped]
    all_entries = optimize_part_ids(all_entries)

    assembled  = [(p, f) for p, f in zip((_assemble_ttt_part(e) for e in all_entries), flags) if p]
    ttt_parts  = [p for p, _ in assembled]
    ttt_flags  = [f for _, f in assembled]

    bones_blob = _build_face_bone()
    num_mats   = len(grouped)
    mats_off   = _HEADER_SIZE
    weird_off  = mats_off + num_mats * _MAT_BLOCK_SIZE
    bones_off  = weird_off + _WEIRD_BLOCK_SIZE
    pi_off     = bones_off + len(bones_blob)
    ps         = pi_off + len(ttt_parts) * _PART_INDEX_ENTRY
    pad        = (16 - ps % 16) % 16
    ps        += pad

    parts_data = [(p, 0xFFFF, i, f) for i, (p, f) in enumerate(zip(ttt_parts, ttt_flags))]
    hdr = bytearray(_build_ttt_header(face_blob, 1, num_mats,
                                      bones_off, mats_off, weird_off,
                                      len(ttt_parts), pi_off, bbox))
    hdr[0:4] = b'pMdF'

    return (bytes(hdr)
            + _build_materials_block(num_mats)
            + _build_weird_block(bones_off)
            + bones_blob
            + _build_parts_index(parts_data, ps)
            + b'\x00' * pad
            + b''.join(ttt_parts))