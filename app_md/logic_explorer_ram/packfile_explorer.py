"""
Backend para trabajar con PACKFILE.BIN.

Este módulo NO contiene ninguna interfaz gráfica ni depende de PyQt.

Responsabilidades:
    - Mantener los bytes de PACKFILE.BIN en un buffer mutable.
    - Modificar, insertar y borrar bytes.
    - Saber si el PACKFILE fue modificado.
    - Tomar una instantánea del contenido de la ISO al abrirla.
    - Detectar cambios del proyecto que requieren reconstruir la ISO.
    - Entregar los bytes finales para que el explorador principal los use
      durante la reconstrucción.
"""
import gc
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional

from PyQt5.QtGui import QIcon

from app_md.logic_iso.data_convert import DataConvert


@dataclass(frozen=True)
class IsoEntrySnapshot:
    """Estado mínimo de una entrada ISO necesario para detectar cambios."""

    path: str
    is_dir: bool
    size: int


class PackFileBuffer:
    """
    Buffer mutable de PACKFILE.BIN.

    IMPORTANTE:
        Esta clase mantiene UNA SOLA representación de los bytes:
            self.data

        No mantiene:
            - original_data
            - copia hash del PACKFILE
            - snapshots completos
            - copias completas al consultar el estado

        Los archivos de la UI deben trabajar mediante offset + length
        sobre este mismo buffer.
    """

    def __init__(
        self,
        data: bytearray,
        *,
        packfile_offset: int = 0,
        iso_size: int = 0,
        path: str = "/PACKFILE.BIN",
        contenedor,
    ) -> None:
        # Si ya recibimos bytearray, usamos exactamente ese objeto.
        # Si recibimos bytes, Python necesita crear el único buffer mutable.
        self.data = data

        self.packfile_offset = int(packfile_offset)
        self.iso_size = int(iso_size)
        self.path = str(path)

        self.psp_iso_explorer = contenedor
        self.explorer_packfile = None
        self.size_header_pack = 0

    @property
    def packfile_size(self) -> int:
        return len(self.data)

    @property
    def original_size(self) -> int:
        # Se conserva únicamente por compatibilidad.
        # No se conserva una copia del contenido original.
        return len(self.data)

    @property
    def changed(self) -> bool:
        # Sin una segunda copia no es posible saber si cambió comparándolo
        # contra el contenido original. La clase trabaja únicamente con
        # el buffer actual.
        return False

    @property
    def has_size_change(self) -> bool:
        return False

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value) -> None:
        self.data[key] = value

    def __delitem__(self, key) -> None:
        del self.data[key]

    def __len__(self) -> int:
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def get_bytes(self):
        """
        Devuelve el MISMO buffer.

        No usa bytes(self.data), porque eso crearía una copia completa
        del PACKFILE.
        """
        return self.data

    def set_byte(self, offset: int, value: int) -> None:
        offset = int(offset)
        value = int(value)

        if offset < 0 or offset >= len(self.data):
            raise IndexError("El offset está fuera de PACKFILE.BIN.")

        if value < 0 or value > 0xFF:
            raise ValueError("El byte debe estar entre 0x00 y 0xFF.")

        self.data[offset] = value

    def get_byte(self, offset: int) -> int:
        offset = int(offset)

        if offset < 0 or offset >= len(self.data):
            raise IndexError("El offset está fuera de PACKFILE.BIN.")

        return self.data[offset]

    def replace_bytes(self, offset: int, data: bytes | bytearray) -> None:
        offset = int(offset)

        if offset < 0 or offset + len(data) > len(self.data):
            raise IndexError("El rango de reemplazo está fuera de PACKFILE.BIN.")

        self.data[offset:offset + len(data)] = data

    def insert_bytes(self, offset: int, data: bytes | bytearray) -> None:
        offset = int(offset)

        if offset < 0 or offset > len(self.data):
            raise IndexError("El offset de inserción está fuera de PACKFILE.BIN.")

        self.data[offset:offset] = data

    def delete_bytes(self, offset: int, length: int) -> None:
        offset = int(offset)
        length = int(length)

        if offset < 0 or length < 0 or offset + length > len(self.data):
            raise IndexError("El rango de eliminación está fuera de PACKFILE.BIN.")

        del self.data[offset:offset + length]

    def read_bytes(self, offset: int, length: int):
        """
        Devuelve únicamente el rango solicitado.

        Esta operación sí crea un objeto de bytes del archivo solicitado,
        pero NO duplica el PACKFILE completo.
        """
        offset = int(offset)
        length = int(length)

        if offset < 0 or length < 0 or offset + length > len(self.data):
            raise IndexError("El rango de lectura está fuera de PACKFILE.BIN.")

        return bytes(self.data[offset:offset + length])

    def reload_data(self, data: bytes | bytearray) -> None:
        """
        Sustituye el único buffer actual.

        No conserva el buffer anterior.
        """
        self.data = data if isinstance(data, bytearray) else bytearray(data)

    def commit(self):
        """
        No crea ninguna copia.
        El estado actual de self.data es el único estado existente.
        """
        return self.data

    def apply(self, setter) -> None:
        """
        Entrega el mismo buffer al setter.
        """
        setter(self.data)

    def run_custom_code(
        self,
        original_entries,
        current_entries,
        modified_paths=None,
    ) -> dict:
        """
        Ejecuta código personalizado directamente sobre self.data.

        No devuelve una copia completa del PACKFILE.
        """
        status = get_iso_rebuild_status(
            original_entries,
            current_entries,
            modified_paths,
        )

        if status["required"]:
            return {
                "ok": False,
                "rebuild_required": True,
                "status": status,
                "buffer": self,
            }

        # ================================================================
        # COLOCA AQUÍ TU CÓDIGO
        # ================================================================
        if not self.explorer_packfile:
            self.size_header_pack = self.psp_iso_explorer.get_packfile_header_size()

            d_c = DataConvert(None)

            key_ttt = struct.unpack("<I", self[0:4])[0]
            num_files = struct.unpack("<I", self[4:8])[0]
            base_offset = (self.packfile_offset  + self.size_header_pack)// 0x800

            address_files = []

            for i in range(1, num_files + 1):
                record_indice = i * 0x10

                offset = struct.unpack(
                    "<I",
                    self[record_indice:record_indice + 4],
                )[0]

                offset = d_c.getOffsetConvert(
                    key=key_ttt,
                    val=offset,
                    desincript_ttt=True,
                    base_offset=base_offset,
                )

                offset *= 0x800

                length = struct.unpack(
                    "<I",
                    self[record_indice + 4:record_indice + 8],
                )[0]

                length = d_c.getSizeConvert(
                    bitR=length,
                    key=f"{i - 1}",
                    desincript_ttt=True,
                )

                address_files.append((offset, length, i))

            # mostrar la ui explorer packfile
            from app_md.logic_explorer_ram.pyqt5_explorer import mostrar_explorador
            self.psp_iso_explorer.hide()

            self.explorer_packfile = mostrar_explorador(
                files_list=address_files,
                ram_source=self
            )
            self.explorer_packfile.setWindowIcon(QIcon(str(self.psp_iso_explorer.main_app.icon)))
            self.explorer_packfile.setWindowTitle(f"PSP Packfile Explorer - {Path(self.psp_iso_explorer.iso_path).name}")
            self.explorer_packfile.set_packfile_header_size(self.size_header_pack)

            self.explorer_packfile.closed.connect(
                self.explorer_packfile_closed
            )
        else:
            self.explorer_packfile.show()


        # print(self[4:8])

        return {
            "ok": True,
            "rebuild_required": False,
            "status": status,
            "buffer": self,
            "changed": False,
            "has_size_change": False,
            "packfile_size": self.packfile_size,
            "address_files": address_files,
        }

    def explorer_packfile_closed(self):
        print("El explorador PyQt5 se cerro")
        self.explorer_packfile.hide()
        self.psp_iso_explorer.show()
        # self.explorer_packfile = None
        # self.data = None
        #
        # gc.collect()


def snapshot_iso_entries(entries: Iterable) -> dict[str, IsoEntrySnapshot]:
    """
    Guarda el estado de las entradas al abrir la ISO.

    El objeto recibido solo necesita tener:
        path, is_dir y size
    """
    snapshot = {}

    for entry in entries:
        path = str(getattr(entry, "path"))
        snapshot[path] = IsoEntrySnapshot(
            path=path,
            is_dir=bool(getattr(entry, "is_dir")),
            size=int(getattr(entry, "size", 0)),
        )

    return snapshot


def get_iso_rebuild_status(
    original_entries: Mapping[str, IsoEntrySnapshot] | Mapping[str, object],
    current_entries: Iterable,
    modified_paths: Optional[Iterable[str]] = None,
) -> dict:
    """
    Determina si el proyecto tiene cambios que requieren reconstruir la ISO.

    Detecta explícitamente:
        - archivos nuevos
        - carpetas nuevas
        - archivos eliminados
        - carpetas eliminadas
        - cambio de archivo <-> directorio
        - cambio de tamaño de archivos
        - rutas marcadas manualmente como modificadas, por ejemplo cuando
          se importan bytes nuevos o se modifica PACKFILE.BIN.

    Devuelve un diccionario para que la UI decida cómo mostrar el resultado.
    """
    current_snapshot = snapshot_iso_entries(current_entries)
    original_paths = set(original_entries.keys())
    current_paths = set(current_snapshot.keys())

    added = sorted(current_paths - original_paths)
    removed = sorted(original_paths - current_paths)

    type_changed = []
    size_changed = []

    for path in sorted(original_paths & current_paths):
        original = original_entries[path]
        current = current_snapshot[path]

        original_is_dir = bool(
            getattr(original, "is_dir", False)
        )
        original_size = int(
            getattr(original, "size", 0)
        )

        if original_is_dir != current.is_dir:
            type_changed.append(path)
            continue

        if not current.is_dir and original_size != current.size:
            size_changed.append(
                {
                    "path": path,
                    "old_size": original_size,
                    "new_size": current.size,
                }
            )

    manually_modified = sorted({str(path) for path in (modified_paths or ())})

    reasons = []

    if added:
        reasons.append("Hay archivos o carpetas nuevos.")
    if removed:
        reasons.append("Hay archivos o carpetas eliminados.")
    if type_changed:
        reasons.append("Hay entradas que cambiaron entre archivo y carpeta.")
    if size_changed:
        reasons.append("Hay archivos cuyo tamaño fue modificado.")
    if manually_modified:
        reasons.append("Hay archivos o datos marcados como modificados.")

    # Cualquier modificación explícita del proyecto también exige rebuild.
    required = bool(
        added
        or removed
        or type_changed
        or size_changed
        or manually_modified
    )

    return {
        "required": required,
        "added": added,
        "removed": removed,
        "type_changed": type_changed,
        "size_changed": size_changed,
        "modified_paths": manually_modified,
        "reasons": reasons,
        "current_entries": current_snapshot,
    }


def iso_requires_rebuild(
    original_entries: Mapping[str, IsoEntrySnapshot] | Mapping[str, object],
    current_entries: Iterable,
    modified_paths: Optional[Iterable[str]] = None,
) -> bool:
    """Atajo que devuelve únicamente True/False."""
    return get_iso_rebuild_status(
        original_entries,
        current_entries,
        modified_paths,
    )["required"]


def format_rebuild_message(status: dict) -> str:
    """
    Genera un texto listo para que la UI informe por qué hay que reconstruir.
    No muestra ningún diálogo por sí mismo.
    """
    if not status.get("required"):
        return "No hay modificaciones que requieran reconstruir la ISO."

    lines = [
        "Es necesario reconstruir la ISO antes de continuar.",
        "",
    ]

    added = status.get("added", [])
    removed = status.get("removed", [])
    type_changed = status.get("type_changed", [])
    size_changed = status.get("size_changed", [])
    modified_paths = status.get("modified_paths", [])

    if added:
        lines.append("Archivos/carpetas nuevos:")
        lines.extend(f"  - {path}" for path in added[:20])

    if removed:
        lines.append("Archivos/carpetas eliminados:")
        lines.extend(f"  - {path}" for path in removed[:20])

    if type_changed:
        lines.append("Entradas cuyo tipo cambió:")
        lines.extend(f"  - {path}" for path in type_changed[:20])

    if size_changed:
        lines.append("Archivos con cambio de tamaño:")
        for item in size_changed[:20]:
            lines.append(
                f"  - {item['path']}: "
                f"0x{item['old_size']:X} -> 0x{item['new_size']:X}"
            )

    if modified_paths:
        lines.append("Entradas marcadas como modificadas:")
        lines.extend(f"  - {path}" for path in modified_paths[:20])

    total_items = (
        len(added)
        + len(removed)
        + len(type_changed)
        + len(size_changed)
        + len(modified_paths)
    )

    if total_items > 100:
        lines.append(f"... y {total_items - 100} cambios adicionales.")

    return "\n".join(lines)
