import struct
import tempfile
import os
from pathlib import Path

from app_md.logic_port.param_convert import convert_param17, convert_skill_cameras_pak
from app_md.logic_swap.anim_converter import canm_to_tanm
from app_md.logic_swap.swap_vfx import (
    convert_vfx_bt3_to_ttt, parse_pak,
    _pil_to_atex_data, build_atex
)
from app_md.logic_swap.pmdl.bt3_to_ttt import convert_bt3_to_ttt, convert_bt3_face_to_ttt

_SIG_TTT          = 0x000001F1
_IDX_PARAM17      = 17
_IDX_DBT          = 11
_IDX_1P_EMPTY     = {12, 13, 14, 15, 16, 43}
_IDX_FACES        = set(range(3, 11))
_IDX_HUD_AGS      = {44: "044_hud_1.ags", 46: "046_hud_2.ags", 48: "048_hud_clash.ags"}
_IDX_HUD_RHG      = {45: "045_hud_1.rhg", 47: "047_hud_2.rhg", 49: "049_hud_clash.rhg"}
_EFF_COMMON_SLOT  = 7


def _parse_le_pak_exact(data: bytes):
    count = struct.unpack_from("<I", data, 0)[0]
    offs  = [struct.unpack_from("<I", data, 4 + i*4)[0] for i in range(count + 1)]
    return [(i, offs[i], offs[i+1], data[offs[i]:offs[i+1]] if offs[i+1] > offs[i] else b'')
            for i in range(count)]


def _build_be_pak(entries: list) -> bytes:
    count     = len(entries)
    index_raw = 4 + (count + 1) * 4
    pad       = (16 - index_raw % 16) % 16
    first_off = index_raw + pad
    cur       = first_off
    offsets   = []
    for e in entries:
        offsets.append(cur); cur += len(e)
    offsets.append(cur)
    out = bytearray()
    out += struct.pack(">I", count)
    for o in offsets: out += struct.pack(">I", o)
    out += b'\x00' * pad
    for e in entries: out += e
    return bytes(out)


def _convert_effect_pak(bt3_data: bytes) -> bytes:
    result, _ = convert_vfx_bt3_to_ttt(bt3_data)
    return result


def _convert_effect_common(bt3_data: bytes) -> bytes:
    entries = _parse_le_pak_exact(bt3_data)
    out = []
    for i, s, e, raw in entries:
        if not raw:
            out.append(b'')
        elif i == 0:
            print(f"[port]   effect_common[{i:02d}]: common_param copy 1:1")
            out.append(raw)
        elif i == _EFF_COMMON_SLOT:
            print(f"[port]   effect_common[{i:02d}]: skill_cameras LE→BE")
            out.append(convert_skill_cameras_pak(raw))
        else:
            print(f"[port]   effect_common[{i:02d}]: converting effect pak ({len(raw):,}b)...")
            converted, _ = convert_vfx_bt3_to_ttt(raw)
            out.append(converted)
    return _build_be_pak(out)


def _build_1p_slots(bt3_data, atlas_image, pack_result, tex_id_order, bt3_parts, face_blobs=None, face_tex_override=None):
    from app_md.logic_port.hud_port import convert_hud_from_dbt
    if face_blobs is None: face_blobs = {}
    if face_tex_override is None: face_tex_override = {}
    bt3_map = {idx: raw for idx, _, _, raw in _parse_le_pak_exact(bt3_data)}
    uv_map  = {tex_id_order[info["orig_index"]]: info for info in pack_result}

    print("[port] 1_p: converting pmdl BT3→TTT...")
    pmdl_ttt = convert_bt3_to_ttt(bt3_map.get(2, b''), bt3_parts, uv_map=uv_map)
    print(f"[port] 1_p: pmdl done ({len(pmdl_ttt):,} bytes)")

    print("[port] 1_p: building ATEX from atlas...")
    idx_b, pal_b = _pil_to_atex_data(atlas_image.convert("RGBA"), 256, 256, flip=False)
    atex = build_atex([(256, 256, idx_b, pal_b)])

    print("[port] 1_p: converting HUDs...")
    hud_data = {}
    dbt_hud = bt3_map.get(0, b'')
    if dbt_hud:
        try:
            hud_data = convert_hud_from_dbt(dbt_hud)
            print(f"[port] 1_p: HUDs generated: {list(hud_data.keys())}")
        except Exception as ex:
            print(f"[port] 1_p: WARNING HUD failed ({ex}), slots 44-49 empty")

    from app_md.logic_swap.pmdl.bt3_to_ttt import _compute_bbox
    pmdl_bbox = _compute_bbox(bt3_parts)
    print(f"[port] 1_p: converting faces (received slots: {list(face_blobs.keys())}, bbox={pmdl_bbox})...")
    face_ttt = {}
    for slot in _IDX_FACES:
        raw = face_blobs.get(slot, b'')
        if not raw:
            continue
        try:
            from app_md.logic_swap.pmdl.bt3_face_parser import get_face_tex_ids
            face_tids = get_face_tex_ids(raw)
            face_uv = dict(uv_map)
            if slot in face_tex_override:
                orig_tid, unique_tid = face_tex_override[slot]
                if unique_tid in uv_map:
                    face_uv[orig_tid] = uv_map[unique_tid]
                    print(f"[port] face {slot}: remapped {orig_tid} → {unique_tid}")
            result = convert_bt3_face_to_ttt(raw, uv_map=face_uv, bbox=pmdl_bbox)
            if result:
                face_ttt[slot] = result
                print(f"[port] 1_p: face slot {slot} converted ({len(result):,}b)")
            else:
                print(f"[port] 1_p: face slot {slot} returned empty (no subparts parsed)")
        except Exception as ex:
            print(f"[port] 1_p: face slot {slot} failed ({ex})")

    slots = []
    for slot in range(50):
        raw = bt3_map.get(slot, b'')
        if slot == 0:
            slots.append(b'')
        elif slot == 1:
            slots.append(raw)
        elif slot in _IDX_FACES:
            slots.append(face_ttt.get(slot, b''))
        elif slot in _IDX_1P_EMPTY:
            slots.append(b'')
        elif slot == 2:
            slots.append(pmdl_ttt)
        elif slot == _IDX_DBT:
            slots.append(atex)
        elif slot == _IDX_PARAM17:
            slots.append(convert_param17(raw) if raw else b'')
        elif slot in _IDX_HUD_AGS:
            slots.append(hud_data.get(_IDX_HUD_AGS[slot], b''))
        elif slot in _IDX_HUD_RHG:
            slots.append(hud_data.get(_IDX_HUD_RHG[slot], b''))
        else:
            slots.append(raw)

    print(f"[port] 1_p: {len(slots)} slots ready")
    return slots


def _build_anm_slots(bt3_data: bytes) -> list:
    entries   = _parse_le_pak_exact(bt3_data)
    slots     = []
    converted = 0
    for idx, s, e, raw in entries:
        if raw:
            try:
                slots.append(canm_to_tanm(raw)); converted += 1
            except Exception:
                slots.append(raw)
        else:
            slots.append(b'')
    print(f"[port] 2_anm: {converted}/{len(entries)} animations converted canm→tanm")
    return slots


def _build_eff_slots(bt3_data: bytes) -> list:
    entries = _parse_le_pak_exact(bt3_data)
    bt3_map = {idx: raw for idx, s, e, raw in entries}
    slots   = []
    for idx in range(7):
        raw = bt3_map.get(idx, b'')
        if not raw:
            slots.append(b'')
        elif idx == 5:
            print(f"[port] 3_eff[{idx}]: converting effect_common...")
            slots.append(_convert_effect_common(raw))
        elif idx == 6:
            print(f"[port] 3_eff[{idx}]: patch_param (copy 1:1)")
            slots.append(raw)
        else:
            print(f"[port] 3_eff[{idx}]: converting effect pak ({len(raw):,}b)...")
            slots.append(_convert_effect_pak(raw))
    print(f"[port] 3_eff: {len(entries)} entries → {len(slots)} slots")
    return slots


def port_character(bt3_1p: bytes, bt3_2anm: bytes, bt3_3eff: bytes,
                   atlas_image, pack_result, tex_id_order, bt3_parts,
                   face_blobs=None, face_tex_override=None) -> bytes:

    print("[port] --- 1_p ---")
    slots_1p = _build_1p_slots(bt3_1p, atlas_image, pack_result, tex_id_order, bt3_parts, face_blobs=face_blobs or {}, face_tex_override=face_tex_override or {})

    print("[port] --- 2_anm ---")
    slots_anm = _build_anm_slots(bt3_2anm)

    print("[port] --- 3_eff ---")
    slots_eff = _build_eff_slots(bt3_3eff)

    def _pad16(b): return b + b'\x00' * ((16 - len(b) % 16) % 16)
    all_slots = [_pad16(e) for e in slots_1p + slots_anm + slots_eff]
    print(f"[port] Assembling PCK1: {len(all_slots)} total slots (1p={len(slots_1p)}, anm={len(slots_anm)}, eff={len(slots_eff)})")

    count     = len(all_slots)
    index_raw = 4 + (count + 1) * 4
    first_off = 0x800
    pad       = first_off - index_raw
    cur       = first_off
    offsets   = []
    for e in all_slots:
        offsets.append(cur); cur += len(e)
    offsets.append(cur)

    out = bytearray()
    out += struct.pack(">I", _SIG_TTT)
    for o in offsets: out += struct.pack(">I", o)
    out += b'\x00' * pad
    for e in all_slots: out += e

    print(f"[port] PCK1 built: {len(out):,} bytes")
    return bytes(out)