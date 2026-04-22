import os
from .swap_data import DIR_1P, DIR_ANIMS, DIR_EFF


def _resolver_ttt_ctx(carpeta_base):
    p1 = os.path.join(carpeta_base, DIR_1P)
    p2 = os.path.join(carpeta_base, DIR_ANIMS)
    p3 = os.path.join(carpeta_base, DIR_EFF)
    if all(os.path.isdir(p) for p in (p1, p2, p3)):
        return {"mode": "TTT", "base": carpeta_base, "1_p": p1, "2_anims": p2, "3_effects": p3}
    return {}


def _resolver_bt3_ctx(pak_path):
    if not pak_path.lower().endswith(".pak"):
        return {}
    base_dir = os.path.dirname(pak_path)
    c1p = c_anm = c_eff = None
    try:
        for entry in os.listdir(base_dir):
            full = os.path.join(base_dir, entry)
            if not os.path.isdir(full):
                continue
            low = entry.lower()
            if low.endswith("_1p") and c1p is None:
                c1p = full
            elif low.endswith("_anm") and c_anm is None:
                c_anm = full
            elif low.endswith("_eff") and c_eff is None:
                c_eff = full
    except Exception:
        return {}

    if all((c1p, c_anm, c_eff)):
        return {
            "mode": "BT3",
            "base": base_dir,
            "pak": pak_path,
            "1_p": c1p,
            "2_anims": c_anm,
            "3_effects": c_eff,
        }
    return {}


def _formatear_label_ctx(titulo, ctx, seleccionado):
    if not ctx:
        return f"{titulo}: ---"
    modo = ctx.get("mode", "?")
    nombre = os.path.basename(seleccionado)
    return f"{titulo} [{modo}]: {nombre}"
