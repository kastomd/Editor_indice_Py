import os
import shutil
from pathlib import Path


from .swap_data import (
    BASE_DICC,
    CAMARAS_POR_ATAQUE, MINICAM_OFFSETS, TAMANO_MINICAM,
    NOMBRES_OFFSETS, TAMANO_NOMBRE,
    DATOS_ATAQUES, DATOS_ATAQUES_PARAMS_ONLY,
    obtener_datos_habilidad
)
from .swap_vfx import convert_vfx_bt3_to_ttt, convert_vfx_ttt_to_bt3
from .anim_converter import (
    encontrar_animacion, anim_ext_for_mode, get_dest_anim_path,
    convert_anim_between_modes
)


def buscar_subcarpeta_fija(ruta_base, nombre):
    ruta = os.path.join(ruta_base, nombre)
    return ruta if os.path.isdir(ruta) else None


def get_cman_path(root_effects: str, mode: str, camera_filename: str):
    if mode == "TTT":
        return os.path.join(root_effects, "05_effect_common", "1_effect_common", "07_skill_cameras", "1_cman", camera_filename)
    else:
        return os.path.join(root_effects, "05_effect_common", "07_skill_cameras", camera_filename)


def encontrar_efecto(carpeta_eff, base_name):
    ruta = os.path.join(carpeta_eff, base_name + ".pak")
    return ruta if os.path.exists(ruta) else None


def cargar_animaciones_por_ataque():
    ruta = BASE_DICC / "attack.txt"
    if not ruta.exists():
        return {}

    anim_dict = {"Ataque 1": [], "Ataque 2": [], "Ataque 3": []}
    tipo_actual = None

    with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
        for linea in f:
            linea = linea.strip()
            if linea == "ATAQUE 1:":
                tipo_actual = "Ataque 1"
            elif linea == "ATAQUE 2:":
                tipo_actual = "Ataque 2"
            elif linea == "ATAQUE 3:":
                tipo_actual = "Ataque 3"
            elif tipo_actual and linea:
                anim_dict[tipo_actual].append(linea)

    return anim_dict


def swap_habilidad(solo_params, donador_var, receptor_var, ctx_donador, ctx_receptor, include_effect=True):
    if not ctx_donador or not ctx_receptor:
        raise ValueError("Select donor and receptor first.")

    origen  = obtener_datos_habilidad(donador_var.get())
    destino = obtener_datos_habilidad(receptor_var.get())

    carpeta_d_anm = ctx_donador.get("2_anims")
    carpeta_d_eff = ctx_donador.get("3_effects")
    carpeta_d_1p  = ctx_donador.get("1_p")
    mode_d = ctx_donador.get("mode")

    carpeta_r_anm = ctx_receptor.get("2_anims")
    carpeta_r_eff = ctx_receptor.get("3_effects")
    carpeta_r_1p  = ctx_receptor.get("1_p")
    mode_r = ctx_receptor.get("mode")

    if not all([carpeta_d_anm, carpeta_d_eff, carpeta_d_1p, carpeta_r_anm, carpeta_r_eff, carpeta_r_1p]):
        raise ValueError("Incomplete context (1_p, 2_anims, 3_effects).")

    cross_platform = (mode_d != mode_r)
    errores = []

    anim_src = encontrar_animacion(carpeta_d_anm, origen["anim"], mode_d)
    anim_omitida = False
    try:
        if not solo_params:
            if anim_src:
                if cross_platform:
                    try:
                        converted_data = convert_anim_between_modes(Path(anim_src), mode_d, mode_r)
                        dest_anim = get_dest_anim_path(carpeta_r_anm, destino["anim"], mode_r, prefer_ext=anim_ext_for_mode(mode_r))
                        Path(dest_anim).write_bytes(converted_data)
                    except Exception:
                        anim_omitida = True
                else:
                    pref = os.path.splitext(anim_src)[1]
                    dest_anim = get_dest_anim_path(carpeta_r_anm, destino["anim"], mode_r, prefer_ext=pref)
                    shutil.copy2(anim_src, dest_anim)
            else:
                anim_omitida = True
    except Exception:
        anim_omitida = True

    eff_has_pmdl = False
    if not solo_params and include_effect:
        eff_src = encontrar_efecto(carpeta_d_eff, origen["eff"])
        eff_dst = os.path.join(carpeta_r_eff, destino["eff"] + ".pak")
        if eff_src and os.path.exists(eff_src):
            try:
                if cross_platform:
                    data_eff = open(eff_src, "rb").read()
                    converted_eff, eff_has_pmdl = convert_vfx_bt3_to_ttt(data_eff) if mode_d == "BT3" else convert_vfx_ttt_to_bt3(data_eff)
                    open(eff_dst, "wb").write(converted_eff)
                else:
                    shutil.copy2(eff_src, eff_dst)
            except Exception as e:
                errores.append(f"Error copying effect: {e}")
        else:
            errores.append("Effect file not found (skipped)")

    ruta_param_origen  = os.path.join(carpeta_d_1p, "024_skill_param.dat")
    ruta_param_destino = os.path.join(carpeta_r_1p, "024_skill_param.dat")

    if os.path.exists(ruta_param_origen) and os.path.exists(ruta_param_destino):
        try:
            with open(ruta_param_origen, "rb") as f:
                bin_origen = f.read()
            with open(ruta_param_destino, "rb") as f:
                bin_destino = bytearray(f.read())

            for o, d in zip(origen.get("offsets_4b", []), destino.get("offsets_4b", [])):
                bin_destino[d:d+4] = bin_origen[o:o+4]
            for o, d in zip(origen.get("offsets_2b", []), destino.get("offsets_2b", [])):
                bin_destino[d:d+2] = bin_origen[o:o+2]
            for o, d in zip(origen.get("offsets_1b", []), destino.get("offsets_1b", [])):
                bin_destino[d] = bin_origen[o]

            with open(ruta_param_destino, "wb") as f:
                f.write(bin_destino)
        except Exception as e:
            errores.append(f"Error in 024_skill_param: {e}")
    else:
        errores.append("024_skill_param.dat not found in donor or receptor")

    if (not solo_params) and (mode_d == "TTT") and (mode_r == "TTT"):
        offset_origen  = NOMBRES_OFFSETS[donador_var.get()]
        offset_destino = NOMBRES_OFFSETS[receptor_var.get()]
        nombre_dat = "043_move_list_name.dat"

        ruta_nombre_origen  = os.path.join(carpeta_d_1p, nombre_dat)
        ruta_nombre_destino = os.path.join(carpeta_r_1p, nombre_dat)

        if os.path.exists(ruta_nombre_origen) and os.path.exists(ruta_nombre_destino):
            try:
                with open(ruta_nombre_origen, "rb") as f:
                    datos_o = f.read()
                with open(ruta_nombre_destino, "rb") as f:
                    datos_r = bytearray(f.read())

                datos_r[offset_destino:offset_destino+TAMANO_NOMBRE] = datos_o[offset_origen:offset_origen+TAMANO_NOMBRE]

                with open(ruta_nombre_destino, "wb") as f:
                    f.write(datos_r)
            except Exception as e:
                errores.append(f"Error copying skill name: {e}")
        else:
            errores.append("043_move_list_name.dat not found in donor or receptor.")

    if errores:
        raise ValueError("\n".join(errores))

    if solo_params:
        return "Skill parameters copied!"

    eff_info = ""
    if not solo_params:
        eff_src = encontrar_efecto(carpeta_d_eff, origen["eff"])
        eff_ok = eff_src and os.path.exists(eff_src)
        if eff_ok:
            eff_info = " (with effect + pmdl)" if eff_has_pmdl else " (with effect)"
        elif not include_effect:
            eff_info = " (effect skipped)"
        else:
            eff_info = " (no effect)"
    msg = f"Skill swap done{eff_info}!"
    if cross_platform and anim_omitida:
        msg += "\n1 animation was skipped (missing or error)."
    return msg


def procesar_swap_ataques(nombre_donador, nombre_receptor, ctx_donador, ctx_receptor, include_effect=True, include_cman=True):
    errores = []

    if not ctx_donador or not ctx_receptor:
        return

    if not all([nombre_donador, nombre_receptor]):
        return

    donador_data  = DATOS_ATAQUES[nombre_donador]
    receptor_data = DATOS_ATAQUES[nombre_receptor]

    carpeta_d_anm = ctx_donador.get("2_anims")
    carpeta_d_eff = ctx_donador.get("3_effects")
    carpeta_d_1p  = ctx_donador.get("1_p")
    mode_d = ctx_donador.get("mode")

    carpeta_r_anm = ctx_receptor.get("2_anims")
    carpeta_r_eff = ctx_receptor.get("3_effects")
    carpeta_r_1p  = ctx_receptor.get("1_p")
    mode_r = ctx_receptor.get("mode")

    if not all([carpeta_d_anm, carpeta_d_eff, carpeta_d_1p, carpeta_r_anm, carpeta_r_eff, carpeta_r_1p]):
        return

    cross_platform = (mode_d != mode_r)

    animaciones_dict = cargar_animaciones_por_ataque()
    anim_donador  = animaciones_dict.get(nombre_donador, [])
    anim_receptor = animaciones_dict.get(nombre_receptor, [])

    if not anim_donador or not anim_receptor:
        return

    limite = 34
    if nombre_donador == "Ataque 3" and nombre_receptor == "Ataque 3":
        limite = 35

    anim_donador  = anim_donador[:limite]
    anim_receptor = anim_receptor[:limite]

    anim_omitidas  = []
    camera_copiada = False

    for base_donador, base_receptor in zip(anim_donador, anim_receptor):
        base_d = str(base_donador)
        base_r = str(base_receptor)
        src_anim = encontrar_animacion(carpeta_d_anm, base_d, mode_d)
        if not src_anim:
            anim_omitidas.append(base_d)
            continue
        try:
            if cross_platform:
                if os.path.getsize(src_anim) == 0:
                    dest_anim = get_dest_anim_path(
                        carpeta_r_anm, base_r, mode_r,
                        prefer_ext=anim_ext_for_mode(mode_r)
                    )
                    open(dest_anim, "wb").close()
                else:
                    conv_data = convert_anim_between_modes(
                        Path(src_anim), mode_d, mode_r
                    )
                    dest_anim = get_dest_anim_path(
                        carpeta_r_anm, base_r, mode_r,
                        prefer_ext=anim_ext_for_mode(mode_r)
                    )
                    Path(dest_anim).write_bytes(conv_data)
            else:
                pref = os.path.splitext(src_anim)[1]
                dest_anim = get_dest_anim_path(carpeta_r_anm, base_r, mode_r, prefer_ext=pref)
                shutil.copy2(src_anim, dest_anim)
        except Exception:
            anim_omitidas.append(base_d)
            continue

    efecto_origen  = os.path.join(carpeta_d_eff, donador_data["effect"])
    efecto_destino = os.path.join(carpeta_r_eff, receptor_data["effect"])
    atk_has_pmdl = False
    if include_effect and os.path.exists(efecto_origen):
        try:
            if cross_platform:
                data_eff = open(efecto_origen, "rb").read()
                converted_eff, atk_has_pmdl = convert_vfx_bt3_to_ttt(data_eff) if mode_d == "BT3" else convert_vfx_ttt_to_bt3(data_eff)
                open(efecto_destino, "wb").write(converted_eff)
            else:
                shutil.copy2(efecto_origen, efecto_destino)
        except Exception as e:
            errores.append(f"Error copying effect: {e}")

    param_archivo = "023_blast_param.dat"
    ruta_d_param  = os.path.join(carpeta_d_1p, param_archivo)
    ruta_r_param  = os.path.join(carpeta_r_1p, param_archivo)

    try:
        with open(ruta_d_param, "rb") as f:
            datos_d = bytearray(f.read())
        with open(ruta_r_param, "rb") as f:
            datos_r = bytearray(f.read())
    except Exception:
        errores.append("Could not open parameter files.")
        return

    for offset_d, offset_r in zip(donador_data.get("offsets_4b", []), receptor_data.get("offsets_4b", [])):
        datos_r[offset_r:offset_r+4] = datos_d[offset_d:offset_d+4]
    for offset_d, offset_r in zip(donador_data.get("offsets_2b", []), receptor_data.get("offsets_2b", [])):
        datos_r[offset_r:offset_r+2] = datos_d[offset_d:offset_d+2]
    for offset_d, offset_r in zip(donador_data.get("offsets_1b", []), receptor_data.get("offsets_1b", [])):
        datos_r[offset_r] = datos_d[offset_d]

    with open(ruta_r_param, "wb") as f:
        f.write(datos_r)

    cam_param      = "027_camera_param.dat"
    ruta_minicam_d = os.path.join(carpeta_d_1p, cam_param)
    ruta_minicam_r = os.path.join(carpeta_r_1p, cam_param)

    if os.path.exists(ruta_minicam_d) and os.path.exists(ruta_minicam_r):
        try:
            with open(ruta_minicam_d, "rb") as f:
                data_d = f.read()
            with open(ruta_minicam_r, "rb") as f:
                data_r = bytearray(f.read())

            offset_d = MINICAM_OFFSETS[nombre_donador]
            offset_r = MINICAM_OFFSETS[nombre_receptor]
            data_r[offset_r:offset_r+TAMANO_MINICAM] = data_d[offset_d:offset_d+TAMANO_MINICAM]

            if nombre_donador == "Ataque 3" and nombre_receptor == "Ataque 3":
                extra_offset = MINICAM_OFFSETS["Ataque 3 extra"]
                data_r[extra_offset:extra_offset+TAMANO_MINICAM] = data_d[extra_offset:extra_offset+TAMANO_MINICAM]

            with open(ruta_minicam_r, "wb") as f:
                f.write(data_r)
        except Exception as e:
            errores.append(f"Error copying minicamera: {e}")
    else:
        errores.append("027_camera_param.dat not found in donor or receptor.")

    if (mode_d == "TTT") and (mode_r == "TTT"):
        offset_origen  = NOMBRES_OFFSETS[nombre_donador]
        offset_destino = NOMBRES_OFFSETS[nombre_receptor]
        nombre_dat = "043_move_list_name.dat"

        ruta_nombre_origen  = os.path.join(carpeta_d_1p, nombre_dat)
        ruta_nombre_destino = os.path.join(carpeta_r_1p, nombre_dat)

        if os.path.exists(ruta_nombre_origen) and os.path.exists(ruta_nombre_destino):
            try:
                with open(ruta_nombre_origen, "rb") as f:
                    datos_o = f.read()
                with open(ruta_nombre_destino, "rb") as f:
                    datos_r = bytearray(f.read())

                datos_r[offset_destino:offset_destino+TAMANO_NOMBRE] = datos_o[offset_origen:offset_origen+TAMANO_NOMBRE]

                with open(ruta_nombre_destino, "wb") as f:
                    f.write(datos_r)
            except Exception as e:
                errores.append(f"Error copying attack name: {e}")
        else:
            errores.append("043_move_list_name.dat not found in donor or receptor.")

    nombre_camara         = CAMARAS_POR_ATAQUE.get(nombre_donador)
    nombre_camara_destino = CAMARAS_POR_ATAQUE.get(nombre_receptor)
    if include_cman and nombre_camara:
        ruta_cman_donador  = get_cman_path(carpeta_d_eff, mode_d, nombre_camara)
        ruta_cman_receptor = get_cman_path(carpeta_r_eff, mode_r, nombre_camara_destino)
        dst_dir = os.path.dirname(ruta_cman_receptor)

        if os.path.exists(dst_dir):
            try:
                donor_exists = os.path.exists(ruta_cman_donador)
                donor_empty  = donor_exists and os.path.getsize(ruta_cman_donador) == 0

                if donor_exists and not donor_empty:
                    # donor has content: copy normally
                    shutil.copy2(ruta_cman_donador, ruta_cman_receptor)
                    camera_copiada = True
                elif donor_empty:
                    # donor is empty (TTT empty cam): receptor must not have the file (BT3) or be empty (TTT)
                    if mode_r == "BT3":
                        if os.path.exists(ruta_cman_receptor):
                            os.remove(ruta_cman_receptor)
                    else:
                        open(ruta_cman_receptor, "wb").close()
                    camera_copiada = True
                else:
                    # donor file does not exist (BT3 no cam): receptor gets empty file (TTT) or nothing (BT3)
                    if mode_r == "TTT":
                        open(ruta_cman_receptor, "wb").close()
                    elif os.path.exists(ruta_cman_receptor):
                        os.remove(ruta_cman_receptor)
                    camera_copiada = True
            except Exception:
                camera_copiada = False
        else:
            camera_copiada = False
    else:
        camera_copiada = False

    if errores:
        raise ValueError("\n".join(errores))

    if include_effect:
        if os.path.exists(efecto_origen):
            eff_info = "effect + pmdl" if atk_has_pmdl else "effect"
        else:
            eff_info = "no effect"
    else:
        eff_info = "effect skipped"
    cam_info = "camera" if camera_copiada else ("cman skipped" if not include_cman else "no camera")
    msg = f"Attack swap done ({eff_info}, {cam_info})!"
    if anim_omitidas:
        msg += f"\n{len(anim_omitidas)} animations skipped (missing or error)."
    return msg


def procesar_swap_ataques_params_only(nombre_donador, nombre_receptor, ctx_donador, ctx_receptor):
    errores = []

    if not ctx_donador or not ctx_receptor:
        return

    if not all([nombre_donador, nombre_receptor]):
        return

    carpeta_d_1p = ctx_donador.get("1_p")
    carpeta_r_1p = ctx_receptor.get("1_p")
    if not all([carpeta_d_1p, carpeta_r_1p]):
        return

    donador_data  = DATOS_ATAQUES_PARAMS_ONLY.get(nombre_donador)
    receptor_data = DATOS_ATAQUES_PARAMS_ONLY.get(nombre_receptor)
    if not donador_data or not receptor_data:
        return

    param_archivo = "023_blast_param.dat"
    ruta_d_param  = os.path.join(carpeta_d_1p, param_archivo)
    ruta_r_param  = os.path.join(carpeta_r_1p, param_archivo)

    if not (os.path.exists(ruta_d_param) and os.path.exists(ruta_r_param)):
        errores.append("023_blast_param.dat not found in donor or receptor.")
    else:
        try:
            with open(ruta_d_param, "rb") as f:
                datos_d = bytearray(f.read())
            with open(ruta_r_param, "rb") as f:
                datos_r = bytearray(f.read())

            for offset_d, offset_r in zip(donador_data.get("offsets_4b", []), receptor_data.get("offsets_4b", [])):
                datos_r[offset_r:offset_r+4] = datos_d[offset_d:offset_d+4]
            for offset_d, offset_r in zip(donador_data.get("offsets_2b", []), receptor_data.get("offsets_2b", [])):
                datos_r[offset_r:offset_r+2] = datos_d[offset_d:offset_d+2]
            for offset_d, offset_r in zip(donador_data.get("offsets_1b", []), receptor_data.get("offsets_1b", [])):
                datos_r[offset_r] = datos_d[offset_d]

            with open(ruta_r_param, "wb") as f:
                f.write(datos_r)
        except Exception as e:
            errores.append(f"Error in 023_blast_param: {e}")

    if errores:
        raise ValueError("\n".join(errores))
    return "Attack parameters copied!"