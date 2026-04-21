from pathlib import Path

# idea propuesta por los ijueg30s
_path_list_rename = Path(__file__).resolve().parent.parent / "windows" / "scr" / "LISTA_PACKFILE.txt"

def build_packfile_index(file_path: Path) -> dict[str, str]:
    """
    Parsea LISTA_PACKFILE.txt y devuelve un diccionario:
    { archivo_unk : ruta_relativa_con_nombre_reemplazado }
    """
    index = {}
    current_folder = ""

    if not file_path.exists():
        file_path = _path_list_rename

    with open(file_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()

            if not line:
                continue

            # Detecta nueva carpeta (termina en :)
            if line.endswith(":"):
                current_folder = line[:-1]  # quitar ":"
                continue

            # Detecta archivo
            if ":" in line:
                unk_name, real_name = map(str.strip, line.split(":", 1))

                # Construir ruta final
                # if current_folder == "Main":
                #     # Main es raíz
                #     final_path = real_name
                # else:
                #     final_path = f"{current_folder}/{real_name}"

                final_path = f"{current_folder}/{real_name}"
                index[unk_name] = final_path

    return index


def get_real_path(unk_filename: str, index: dict[str, str]) -> Path:
    return Path(index.get(unk_filename, unk_filename))
