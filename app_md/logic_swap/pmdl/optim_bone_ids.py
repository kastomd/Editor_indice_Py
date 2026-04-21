def _get_col_state(prev_col_ids: list, col: int) -> int:
    """Último ID válido (!=0xFF, !=0x00) visto en esa columna, o None."""
    for part_cols in reversed(prev_col_ids):
        if col < len(part_cols):
            val = part_cols[col]
            if val not in (0x00, 0xFF):
                return val
    return None


def optimize_part_ids(ttt_parts_entries: list) -> list:
    # Estado de las 4 columnas: último ID válido visto
    col_state = [None, None, None, None]
    result = []

    for part_entries in ttt_parts_entries:
        new_part = []
        for sub in part_entries:
            bone_ids   = list(sub["bone_ids"])  # 4 bytes, padding 0x00
            bone_count = sub["bone_count"]
            new_ids    = list(bone_ids)

            for col in range(4):
                raw = bone_ids[col]
                if col >= bone_count:
                    # Slot vacío, no afecta estado ni se optimiza
                    new_ids[col] = 0x00
                    continue
                if raw == 0x00:
                    # Slot vacío activo (no debería pasar si bone_count es correcto)
                    continue
                if col_state[col] is not None and raw == col_state[col]:
                    new_ids[col] = 0xFF
                else:
                    col_state[col] = raw  # actualizar estado con nuevo ID válido

            new_part.append({**sub, "bone_ids": new_ids})
        result.append(new_part)

    return result
