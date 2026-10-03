import struct
import sys
import os
import shutil
import os
import subprocess
import tempfile
import gc

import qdarkstyle
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt5.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QFont
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, QDialog,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QRadioButton,
    QButtonGroup, QTreeWidget, QTreeWidgetItem, QSplitter,
    QProgressBar, QStatusBar, QAction, QWidget, QStyle, QInputDialog, QAbstractItemView,
    QMenu, QLineEdit, QFormLayout
)
from app_md.logic_iso.data_convert import DataConvert
from app_md.logic_explorer_ram.packfile_explorer import (
    PackFileBuffer,
    format_rebuild_message,
    get_iso_rebuild_status,
    snapshot_iso_entries,
)


SECTOR_SIZE = 0x800
PVD_SECTOR = 16


class StorageModeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modo de almacenamiento")
        self.setModal(True)
        self.resize(440, 190)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "<b>¿Cómo quieres manejar los datos de la ISO?</b><br><br>"
            "RAM: los archivos extraídos se mantienen en memoria. "
            "Es más rápido, pero consume RAM.<br>"
            "Disco: los archivos se guardan físicamente en una carpeta "
            "de trabajo. Recomendado para ISOs grandes."
        ))

        self.ram = QRadioButton("RAM — más rápido, mayor consumo de memoria")
        self.disk = QRadioButton("Disco — menor consumo de RAM")
        self.disk.setChecked(True)

        self.group = QButtonGroup(self)
        self.group.addButton(self.ram)
        self.group.addButton(self.disk)

        layout.addWidget(self.ram)
        layout.addWidget(self.disk)

        buttons = QHBoxLayout()
        buttons.addStretch()
        ok = QPushButton("Continuar")
        cancel = QPushButton("Cancelar")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

    @property
    def mode(self):
        return "ram" if self.ram.isChecked() else "disk"


class IsoEntry:
    def __init__(self, name, path, is_dir, extent=0, size=0):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.extent = extent
        self.size = size


class IsoReader:
    """ISO9660 reader using raw sectors. Suitable for PSP UMD ISO layouts."""

    def __init__(self, filename):
        self.filename = filename
        self.fp = None
        self.entries = []
        self.volume_id = ""

    def open(self):
        self.fp = open(self.filename, "rb")

        try:
            self._validate()
            self._read_pvd()
            self.entries = []
            self._read_directory(
                self.root_extent,
                self.root_size,
                "/"
            )

            if self.entries:
                return self.entries

            # Some images are accepted by pycdlib even when the raw parser
            # cannot enumerate their directory records.
            if self.open_with_pycdlib():
                return self.entries

            raise ValueError(
                "Se encontró el PVD ISO9660, pero el directorio raíz "
                "no contiene registros válidos."
            )

        except Exception:
            # Keep the original exception for the caller.
            raise

    def close(self):
        if self.fp:
            self.fp.close()
            self.fp = None

    def _validate(self):
        self.fp.seek(0, os.SEEK_END)
        size = self.fp.tell()
        if size < (PVD_SECTOR + 1) * SECTOR_SIZE:
            raise ValueError("El archivo es demasiado pequeño para ser una ISO9660.")
        self.fp.seek(PVD_SECTOR * SECTOR_SIZE)
        pvd = self.fp.read(SECTOR_SIZE)
        if len(pvd) != SECTOR_SIZE or pvd[1:6] != b"CD001":
            raise ValueError("No se encontró un Primary Volume Descriptor ISO9660.")
        if pvd[0] != 1:
            raise ValueError("El descriptor ISO9660 no es un PVD válido.")

    def _read_pvd(self):
        self.fp.seek(PVD_SECTOR * SECTOR_SIZE)
        pvd = self.fp.read(SECTOR_SIZE)
        self.volume_id = pvd[40:72].decode("ascii", "replace").rstrip(" ")

        # Root Directory Record starts at byte 156 of the PVD.
        root_record = pvd[156:190]
        if len(root_record) < 34:
            raise ValueError("El Root Directory Record está incompleto.")

        self.root_extent = int.from_bytes(root_record[2:6], "little")
        self.root_size = int.from_bytes(root_record[10:14], "little")

        if self.root_extent == 0 or self.root_size == 0:
            raise ValueError(
                f"Root Directory inválido: LBA={self.root_extent}, "
                f"tamaño={self.root_size}"
            )

    def _read_directory(self, extent, size, parent, root_name="/"):
        """Parse ISO9660 directory records recursively."""
        base = extent * SECTOR_SIZE
        self.fp.seek(base)
        data = self.fp.read(size)

        pos = 0
        data_len = len(data)

        while pos < data_len:
            # A zero-length record means padding until the next sector.
            record_length = data[pos]
            if record_length == 0:
                next_sector = ((pos // SECTOR_SIZE) + 1) * SECTOR_SIZE
                if next_sector <= pos:
                    break
                pos = next_sector
                continue

            if record_length < 34 or pos + record_length > data_len:
                # Bad/corrupt record: advance one byte instead of losing
                # the rest of the directory.
                pos += 1
                continue

            rec = data[pos:pos + record_length]

            extent_lba = int.from_bytes(rec[2:6], "little")
            data_length = int.from_bytes(rec[10:14], "little")
            flags = rec[25]
            name_len = rec[32]

            if 33 + name_len > len(rec):
                pos += record_length
                continue

            raw_name = rec[33:33 + name_len]

            # ISO9660 special entries: 0 = current directory, 1 = parent.
            if name_len == 1 and raw_name in (b"\x00", b"\x01"):
                pos += record_length
                continue

            try:
                name = raw_name.decode("ascii", "replace")
            except Exception:
                name = raw_name.decode("latin-1", "replace")

            if not name:
                pos += record_length
                continue

            is_dir = bool(flags & 0x02)

            # ISO9660 files commonly have ;1 version suffix.
            clean_name = name
            if not is_dir and ";" in clean_name:
                suffix = clean_name.rsplit(";", 1)[-1]
                if suffix.isdigit():
                    clean_name = clean_name.rsplit(";", 1)[0]

            full_path = (
                parent.rstrip("/") + "/" + clean_name
                if parent != "/"
                else "/" + clean_name
            )

            entry = IsoEntry(
                clean_name,
                full_path,
                is_dir,
                extent_lba,
                data_length
            )
            self.entries.append(entry)

            # Recurse into directories, but never recurse into itself.
            if is_dir and data_length > 0 and extent_lba != extent:
                self._read_directory(
                    extent_lba,
                    data_length,
                    full_path,
                    clean_name
                )

            pos += record_length

    def open_with_pycdlib(self):
        """Fallback parser for ISO9660 images that the raw parser rejects."""
        try:
            import pycdlib
        except ImportError:
            return False

        iso = pycdlib.PyCdlib()
        try:
            iso.open(self.filename)

            self.entries = []

            def walk(iso_path, display_path):
                children = []
                try:
                    for child in iso.list_children(iso_path=iso_path):
                        name = child.file_identifier().decode(
                            "utf-8", "replace"
                        ).rstrip("\x00")

                        if name in (".", "..", "", "\x00", "\x01"):
                            continue

                        is_dir = child.is_dir()
                        clean_name = name

                        if not is_dir and ";" in clean_name:
                            base, suffix = clean_name.rsplit(";", 1)
                            if suffix.isdigit():
                                clean_name = base

                        full_path = (
                            display_path.rstrip("/") + "/" + clean_name
                            if display_path != "/"
                            else "/" + clean_name
                        )

                        if is_dir:
                            # pycdlib does not expose the same raw extent
                            # information here in a stable API, but we can
                            # still expose the directory in the UI.
                            entry = IsoEntry(
                                clean_name, full_path, True, 0, 0
                            )
                            self.entries.append(entry)
                            walk(
                                iso_path.rstrip("/") + "/" + name,
                                full_path
                            )
                        else:
                            size = child.data_length()
                            entry = IsoEntry(
                                clean_name, full_path, False, 0, size
                            )
                            self.entries.append(entry)

                except Exception:
                    pass

            walk("/", "/")
            return len(self.entries) > 0

        finally:
            try:
                iso.close()
            except Exception:
                pass

    def read_file(self, entry):
        if entry.is_dir:
            return bytearray()

        # Mantiene compatibilidad con los lugares que esperan un valor
        # completo, pero el explorador en RAM usa read_file_into() para no
        # crear primero un objeto bytes y luego convertirlo a bytearray.
        self.fp.seek(entry.extent * SECTOR_SIZE)
        return bytearray(self.fp.read(entry.size))

    def read_file_into(self, entry, buffer, chunk_size=1024 * 1024):
        """
        Lee un archivo directamente dentro del bytearray recibido.

        No crea un objeto bytes que contenga _todo el archivo.
        Solo existe temporalmente cada bloque leído desde el ISO.
        """
        if entry.is_dir:
            return 0

        if not isinstance(buffer, bytearray):
            raise TypeError("buffer debe ser un bytearray")

        if len(buffer) != int(entry.size):
            raise ValueError(
                f"El buffer tiene {len(buffer)} bytes y el archivo requiere "
                f"{int(entry.size)} bytes."
            )

        self.fp.seek(int(entry.extent) * SECTOR_SIZE)

        view = memoryview(buffer)
        total = 0

        try:
            while total < len(buffer):
                amount = min(int(chunk_size), len(buffer) - total)
                chunk = self.fp.read(amount)

                if not chunk:
                    raise EOFError(
                        f"No se pudieron leer todos los datos de {entry.path}. "
                        f"Leídos: {total}, esperados: {len(buffer)}."
                    )

                view[total:total + len(chunk)] = chunk
                total += len(chunk)
        finally:
            view.release()

        return total

    def extract_file_to(self, entry, output_path, chunk_size=1024 * 1024):
        if entry.is_dir:
            return

        self.fp.seek(entry.extent * SECTOR_SIZE)
        remaining = entry.size

        with open(output_path, "wb") as out:
            while remaining:
                chunk = self.fp.read(min(chunk_size, remaining))
                if not chunk:
                    raise IOError("Fin inesperado de la ISO.")
                out.write(chunk)
                remaining -= len(chunk)


class IsoWorker(QThread):
    progress = pyqtSignal(int, str)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, reader, entries, destination, mode):
        super().__init__()
        self.reader = reader
        self.entries = entries
        self.destination = destination
        self.mode = mode

    def run(self):
        try:
            files = [e for e in self.entries if not e.is_dir]
            total = max(1, len(files))

            if self.mode == "disk":
                for e in self.entries:
                    if e.is_dir:
                        (self.destination / e.path.lstrip("/")).mkdir(
                            parents=True, exist_ok=True
                        )

                for i, e in enumerate(files, 1):
                    out = self.destination / e.path.lstrip("/")
                    out.parent.mkdir(parents=True, exist_ok=True)
                    self.reader.extract_file_to(e, out)
                    self.progress.emit(
                        int(i * 100 / total), f"Extrayendo {e.path}"
                    )
                self.finished_ok.emit(str(self.destination))

            else:
                memory = {}
                for i, e in enumerate(files, 1):
                    memory[e.path] = self.reader.read_file(e)
                    self.progress.emit(
                        int(i * 100 / total), f"Cargando {e.path}"
                    )
                self.finished_ok.emit(memory)

        except Exception as exc:
            self.failed.emit(str(exc))



# Extensible "Open with" registry.
# Add future handlers here:
#
# OPEN_WITH_HANDLERS[".ext"] = [
#     ("Program name", callback_function),
# ]
#
# The callback receives the extracted physical file path.
OPEN_WITH_HANDLERS = {}


def register_open_with(extension, name, callback):
    """Register an application/action for a file extension."""
    extension = extension.lower()
    if not extension.startswith("."):
        extension = "." + extension

    OPEN_WITH_HANDLERS.setdefault(extension, []).append(
        (name, callback)
    )


def open_with_windows_image_viewer(file_path):
    """Open an image using the Windows default image application."""
    os.startfile(str(file_path))


def open_with_system_default(file_path):
    """Open using the Windows application associated with the extension."""
    os.startfile(str(file_path))


# Default image handler.
for _ext in (
    ".png", ".jpg", ".jpeg", ".bmp", ".gif",
    ".tif", ".tiff", ".webp", ".ico"
):
    register_open_with(
        _ext,
        "Visualizador de imágenes de Windows",
        open_with_windows_image_viewer
    )


class PackFileConfigDialog(QDialog):
    """Configuración del explorador relacionada con PACKFILE.BIN."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent_explorer = parent

        self.setWindowTitle("Configuración")
        self.setModal(True)
        self.resize(420, 150)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.header_size_edit = QLineEdit(
            f"0x{self.parent_explorer.get_packfile_header_size():X}"
        )
        self.header_size_edit.setPlaceholderText("Ej. 0x38000")
        form.addRow("Tamaño del header PACKFILE:", self.header_size_edit)
        self.header_size_edit.returnPressed.connect(self.apply_config)
        layout.addLayout(form)

        info = QLabel(
            "Puedes introducir el tamaño en hexadecimal (0x...) "
            "o en decimal."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel = QPushButton("Cancelar")
        apply_button = QPushButton("Aplicar")

        cancel.clicked.connect(self.reject)
        apply_button.clicked.connect(self.apply_config)

        buttons.addWidget(cancel)
        buttons.addWidget(apply_button)
        layout.addLayout(buttons)

    def apply_config(self):
        value = self.header_size_edit.text().strip()

        try:
            if value.lower().startswith("0x"):
                size = int(value, 16)
            else:
                size = int(value, 10)

            if size < 0:
                raise ValueError

        except ValueError:
            QMessageBox.warning(
                self,
                "Valor inválido",
                "Introduce un tamaño válido.\n\n"
                "Ejemplos:\n"
                "0x38000\n"
                "229376"
            )
            return

        self.parent_explorer.set_packfile_header_size(size)
        self.accept()


class CreditsDialog(QDialog):
    """Ventana de créditos de PSP ISO Explorer."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Credits")
        self.setModal(True)
        self.resize(500, 390)

        layout = QVBoxLayout(self)

        # Imagen base generada en tiempo de ejecución para no depender
        # de un archivo externo.
        image = QPixmap(420, 145)
        image.fill(QColor("#202020"))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(QPen(QColor("#58A6FF"), 3))
        painter.setBrush(QBrush(QColor("#161B22")))
        painter.drawRoundedRect(8, 8, 404, 129, 16, 16)

        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Segoe UI", 24, QFont.Bold))
        painter.drawText(
            20, 35, 380, 45,
            Qt.AlignCenter,
            "PSP ISO Explorer"
        )

        painter.setFont(QFont("Segoe UI", 11))
        painter.setPen(QColor("#B8C1CC"))
        painter.drawText(
            20, 82, 380, 25,
            Qt.AlignCenter,
            "ISO9660 / PSP UMD Explorer"
        )

        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#58A6FF"))
        painter.drawText(
            20, 108, 380, 22,
            Qt.AlignCenter,
            "KASTO MD"
        )
        painter.end()

        image_label = QLabel()
        image_label.setPixmap(image)
        image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(image_label)

        title = QLabel("<b>PSP ISO Explorer</b>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        description = QLabel(
            "Herramienta para explorar y modificar el contenido de "
            "imágenes ISO de PSP. Permite navegar por la estructura "
            "ISO9660, trabajar en modo RAM o Disco, importar, exportar, "
            "insertar y eliminar archivos, además de preparar y "
            "reconstruir contenido como PACKFILE.BIN."
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignCenter)
        layout.addWidget(description)

        author = QLabel(
            'Autor: <a href="https://www.youtube.com/@KASTOMODDER15">'
            'kasto MD</a>'
            ' | Data: <a href="https://www.youtube.com/@Zero-Devs">'
            'Zero Devs</a>'
        )
        author.setOpenExternalLinks(True)
        author.setAlignment(Qt.AlignCenter)
        layout.addWidget(author)

        github = QLabel(
            '<a href="https://github.com/kastomd/Editor_indice_Py">'
            'GitHub</a>'
        )
        github.setOpenExternalLinks(True)
        github.setAlignment(Qt.AlignCenter)
        layout.addWidget(github)

        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)


class IsoExplorer(QMainWindow):
    def __init__(self, contenedor=None):
        super().__init__()
        self.setWindowTitle("PSP ISO Explorer")
        self.resize(900, 400)
        self.main_app = contenedor

        self.reader = None
        self.iso_path = None
        self.mode = None
        self.storage_root = None
        self.memory_files = {}
        self.entries = []
        self.entries_by_path = {}
        self.modified = set()
        self.original_entries_snapshot = {}
        # Buffer original de PACKFILE.BIN. Nunca se reemplaza durante
        # una reconstrucción generada por el explorador RAM.
        self.packfile_buffer = None
        self.packfile_entry = None

        # Buffer temporal/nuevo generado por pyqt5_explorer.guardar().
        # Se usa para reconstruir la ISO sin modificar packfile_buffer.
        self.new_packfile_buffer = None

        # Configuración del formato PACKFILE.BIN.
        # Puede actualizarse desde otros scripts mediante:
        # explorer.set_packfile_header_size(0x38000)
        self.packfile_header_size = 0x38000

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Archivo / Directorio", "Tipo", "Tamaño", "Offset"])
        self.tree.setColumnWidth(0, 560)

        # Allow selecting multiple files with Ctrl/Shift.
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # Menu contextual para archivos y carpetas.
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_tree_context_menu)

        self.tree.itemDoubleClicked.connect(self.open_entry)

        self.progress = QProgressBar()
        self.progress.setVisible(False)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        center = QWidget()
        layout = QVBoxLayout(center)
        layout.addWidget(self.tree)
        layout.addWidget(self.progress)
        self.setCentralWidget(center)

        self._create_menu()

    def _create_menu(self):
        menubar = self.menuBar()

        # File: operaciones sobre la ISO.
        file_menu = menubar.addMenu("File")

        open_action = QAction("Open ISO...", self)
        open_action.triggered.connect(self.choose_iso)
        file_menu.addAction(open_action)

        rebuild_action = QAction("Rebuild ISO...", self)
        rebuild_action.triggered.connect(self.rebuild_iso)
        file_menu.addAction(rebuild_action)

        file_menu.addSeparator()

        close_action = QAction("Close ISO", self)
        close_action.triggered.connect(self.close_iso)
        file_menu.addAction(close_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Tools: operaciones sobre el contenido de la ISO.
        tools_menu = menubar.addMenu("Tools")

        import_action = QAction("Import...", self)
        import_action.triggered.connect(self.import_file)
        tools_menu.addAction(import_action)

        insert_action = QAction("Insert file...", self)
        insert_action.triggered.connect(self.insert_file)
        tools_menu.addAction(insert_action)

        create_folder_action = QAction("Create folder...", self)
        create_folder_action.triggered.connect(self.create_folder)
        tools_menu.addAction(create_folder_action)

        delete_action = QAction("Delete...", self)
        delete_action.triggered.connect(self.delete_selected)
        tools_menu.addAction(delete_action)

        tools_menu.addSeparator()

        export_action = QAction("Export...", self)
        export_action.triggered.connect(self.export_selected_multiple)
        tools_menu.addAction(export_action)

        edit_size_action = QAction("Edit file size...", self)
        edit_size_action.triggered.connect(self.edit_selected_size)
        tools_menu.addAction(edit_size_action)

        # Help: configuración y créditos del programa.
        help_menu = menubar.addMenu("Help")

        config_action = QAction("Config", self)
        config_action.triggered.connect(self.show_config)
        help_menu.addAction(config_action)

        credits_action = QAction("Credits", self)
        credits_action.triggered.connect(self.show_credits)
        help_menu.addAction(credits_action)

    def get_packfile_header_size(self):
        """Devuelve el tamaño configurado del header de PACKFILE.BIN."""
        return int(self.packfile_header_size)

    def set_packfile_header_size(self, value):
        """
        Actualiza el tamaño del header de PACKFILE.BIN.

        Puede recibir un int o un texto hexadecimal/decimal.
        Ejemplos:
            self.set_packfile_header_size(0x38000)
            self.set_packfile_header_size("0x38000")
            self.set_packfile_header_size("229376")
        """
        if isinstance(value, str):
            value = value.strip()
            if value.lower().startswith("0x"):
                value = int(value, 16)
            else:
                value = int(value, 10)

        value = int(value)

        if value < 0:
            raise ValueError("El tamaño del header no puede ser negativo.")

        self.packfile_header_size = value

        if hasattr(self, "status") and self.status is not None:
            self.status.showMessage(
                f"Tamaño header PACKFILE: 0x{value:X} ({value} bytes)"
            )

        return self.packfile_header_size

    def show_config(self):
        """Abre la ventana de configuración."""
        PackFileConfigDialog(self).exec_()

    def show_credits(self):
        """Abre la ventana de créditos."""
        CreditsDialog(self).exec_()

    def choose_iso(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir ISO",
            "",
            "ISO / CSO (*.iso *.ISO *.cso *.CSO);;Todos los archivos (*)"
        )
        if not path:
            return

        dlg = StorageModeDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return

        self.mode = dlg.mode
        self.open_iso(path)

    def open_iso(self, path):
        self.close_iso()

        self.iso_path = path
        self.reader = IsoReader(path)

        try:
            entries = self.reader.open()
        except Exception as exc:
            root_extent = getattr(self.reader, "root_extent", "N/D")
            root_size = getattr(self.reader, "root_size", "N/D")
            volume_id = getattr(self.reader, "volume_id", "")
            try:
                self.reader.close()
            except Exception:
                pass
            self.reader = None

            QMessageBox.critical(
                self,
                "Error al abrir ISO",
                f"{exc}\n\n"
                "Datos detectados durante la lectura:\n"
                f"Archivo: {path}\n"
                f"Sector PVD: 16 (0x8000)\n"
                f"Root LBA: {root_extent}\n"
                f"Root size: {root_size}\n"
                f"Volume ID: {volume_id}"
            )
            return

        # Keep the master entry list synchronized with the index used by the UI.
        # Without this, operations that rebuild the tree (such as Delete) would
        # see an empty self.entries list and make the whole tree disappear.
        self.entries = list(entries)
        self.entries_by_path = {e.path: e for e in self.entries}
        self.original_entries_snapshot = snapshot_iso_entries(self.entries)
        self.packfile_buffer = None
        self.packfile_entry = None
        self.new_packfile_buffer = None
        self.tree.clear()

        if not entries:
            QMessageBox.warning(
                self,
                "ISO sin archivos",
                "La ISO fue abierta, pero no se encontraron entradas "
                "en el directorio raíz.\n\n"
                "Puede que no sea una ISO9660 estándar, que esté "
                "comprimida (CSO), o que use una estructura que este "
                "lector todavía no interpreta."
            )
        self.memory_files.clear()
        self.modified.clear()

        if self.mode == "disk":
            self.storage_root = Path(tempfile.mkdtemp(prefix="psp_iso_"))
            self.status.showMessage(
                f"Modo disco. Carpeta de trabajo: {self.storage_root}"
            )
        else:
            self.storage_root = None
            self.status.showMessage("Modo RAM seleccionado.")

        self._populate_tree(entries)

        files_count = sum(1 for e in entries if not e.is_dir)
        dirs_count = sum(1 for e in entries if e.is_dir)

        self.status.showMessage(
            f"ISO abierta: {files_count} archivos, {dirs_count} directorios"
        )

        self.setWindowTitle(
            f"PSP ISO Explorer — {Path(path).name} — "
            f"{'RAM' if self.mode == 'ram' else 'Disco'}"
        )

    def _get_entry_icon(self, entry):
        """Return a native Qt icon according to the ISO entry type."""
        style = self.style()

        if entry.is_dir:
            return style.standardIcon(QStyle.SP_DirIcon)

        ext = Path(entry.name).suffix.lower()

        # Music / audio files commonly found in PSP games.
        if ext in {
            ".at3", ".at9", ".wav", ".mp3", ".ogg",
            ".aac", ".flac", ".m4a", ".vag"
        }:
            return style.standardIcon(QStyle.SP_MediaVolume)

        # PNG images.
        if ext == ".png":
            return style.standardIcon(QStyle.SP_FileDialogDetailedView)

        # Generic file.
        return style.standardIcon(QStyle.SP_FileIcon)

    def _populate_tree(self, entries):
        """Build a hierarchical tree from ISO paths."""
        root = self.tree.invisibleRootItem()
        nodes = {"/": root}

        # Directories before files; shallow paths before deep paths.
        ordered = sorted(
            entries,
            key=lambda e: (
                e.path.count("/"),
                0 if e.is_dir else 1,
                e.path.lower()
            )
        )

        for entry in ordered:
            parts = [part for part in entry.path.split("/") if part]
            parent_item = root
            current_path = ""

            for index, part in enumerate(parts):
                current_path += "/" + part

                item = nodes.get(current_path)

                if item is None:
                    item = QTreeWidgetItem(parent_item)
                    item.setText(0, part)
                    item.setData(0, Qt.UserRole, current_path)

                    # Use the entry icon when this is the final component.
                    if index == len(parts) - 1:
                        item.setIcon(0, self._get_entry_icon(entry))

                    nodes[current_path] = item

                # The actual entry determines whether this is a file.
                if index == len(parts) - 1:
                    item.setIcon(0, self._get_entry_icon(entry))

                    if entry.is_dir:
                        item.setText(1, "Directorio")
                        item.setText(2, "")
                        item.setText(3, f"0x{entry.extent * SECTOR_SIZE:X}")
                    else:
                        item.setText(1, "Archivo")
                        item.setText(2, self.format_size(entry.size))
                        item.setText(3, f"0x{entry.extent * SECTOR_SIZE:X}")

                parent_item = item

        self.tree.expandToDepth(0)

    @staticmethod
    def format_size(size):
        if size < 1024:
            return f"{size} B"
        if size < 1024 ** 2:
            return f"{size / 1024:.2f} KB"
        if size < 1024 ** 3:
            return f"{size / 1024 ** 2:.2f} MB"
        return f"{size / 1024 ** 3:.2f} GB"

    def show_tree_context_menu(self, position):
        item = self.tree.itemAt(position)
        if item is None:
            return

        if item not in self.tree.selectedItems():
            self.tree.clearSelection()
            item.setSelected(True)

        menu = QMenu(self)

        import_action = QAction("Importar...", self)
        import_action.triggered.connect(self.import_file)
        menu.addAction(import_action)

        insert_action = QAction("Insertar archivo...", self)
        insert_action.triggered.connect(self.insert_file)
        menu.addAction(insert_action)

        create_folder_action = QAction("Crear carpeta...", self)
        create_folder_action.triggered.connect(self.create_folder)
        menu.addAction(create_folder_action)

        delete_action = QAction("Borrar...", self)
        delete_action.triggered.connect(self.delete_selected)
        menu.addAction(delete_action)

        export_action = QAction("Exportar...", self)
        export_action.triggered.connect(self.export_selected_multiple)
        menu.addAction(export_action)

        entry = self.entries_by_path.get(item.data(0, Qt.UserRole))

        if entry and not entry.is_dir:
            # PACKFILE.BIN tiene una acción específica para futuras
            # implementaciones de recálculo de tamaño.
            if entry.name.upper() == "PACKFILE.BIN":
                menu.addSeparator()
                recalc_packfile_action = QAction("Recalcular tamaño", self)
                recalc_packfile_action.triggered.connect(
                    self.recalculate_packfile_size
                )
                menu.addAction(recalc_packfile_action)

            open_with_menu = QMenu("Abrir con", menu)
            self.populate_open_with_menu(
                open_with_menu,
                entry
            )

            if not open_with_menu.isEmpty():
                menu.addSeparator()
                menu.addMenu(open_with_menu)

            menu.addSeparator()

            edit_size_action = QAction("Editar tamaño...", self)
            edit_size_action.triggered.connect(self.edit_selected_size)
            menu.addAction(edit_size_action)

        menu.exec_(self.tree.viewport().mapToGlobal(position))

    def recalculate_packfile_size(self):
        """
        Recalcula el tamaño de PACKFILE.BIN.

        Importante:
        El tamaño registrado en ISO puede ser menor que los datos físicos
        que realmente existen en la ISO. En ese caso, _get_file_data()
        solamente devolvería hasta entry.size y se perdería la parte final
        del PACKFILE durante la reconstrucción.

        Por eso, cuando el nuevo tamaño calculado es mayor que la cantidad
        de datos actualmente disponibles en RAM/disco, se recuperan del
        archivo ISO original los bytes que faltan y se conservan en el
        almacenamiento de trabajo.
        """
        paths = self.get_selected_paths()
        if len(paths) != 1:
            return

        packfile_entry = self.entries_by_path.get(paths[0])
        if not packfile_entry or packfile_entry.is_dir:
            return

        if packfile_entry.name.upper() != "PACKFILE.BIN":
            return

        # ================================================================
        # DATOS DISPONIBLES PARA TU CÓDIGO
        # ================================================================
        packfile_size = int(packfile_entry.size)

        try:
            iso_size = Path(self.iso_path).stat().st_size
        except (OSError, TypeError):
            iso_size = 0

        packfile_offset = int(packfile_entry.extent) * SECTOR_SIZE

        # Lee el contenido disponible en el almacenamiento de trabajo.
        # Puede estar truncado al tamaño lógico original de la ISO.
        packfile_data = self._get_file_data(packfile_entry)
        packfile_data_size = len(packfile_data)

        # ---------------------------------------------------------------
        # CÓDIGO DE RECÁLCULO
        # ---------------------------------------------------------------
        if len(packfile_data) < 8:
            raise ValueError(
                "PACKFILE.BIN no contiene suficientes datos para leer "
                "su cabecera."
            )

        key_ttt = struct.unpack('<I', packfile_data[0:4])[0]
        num_files = struct.unpack('<I', packfile_data[4:8])[0]
        print(f"key ttt: {key_ttt} num files: {num_files}")

        offsets = []
        dc = DataConvert(None)

        for i in range(1, num_files + 1):
            record_offset = i * 0x10
            record_end = record_offset + 8

            if record_end > len(packfile_data):
                raise ValueError(
                    "El tamaño registrado de PACKFILE.BIN es demasiado "
                    "pequeño para contener toda la tabla de archivos."
                )

            offset = struct.unpack(
                '<I',
                packfile_data[record_offset:record_offset + 4]
            )[0]

            offset = dc.getOffsetConvert(
                val=offset,
                desincript_ttt=True,
                key=key_ttt,
                base_offset=(packfile_offset // 0x800) + 0x70
            )

            long = struct.unpack(
                '<I',
                packfile_data[record_offset + 4:record_offset + 8]
            )[0]

            long = dc.getSizeConvert(
                bitR=long,
                key=f"{i - 1}",
                desincript_ttt=True
            )

            offsets.append((offset * 0x800, long))

        if not offsets:
            raise ValueError(
                "PACKFILE.BIN no contiene archivos para calcular su tamaño."
            )

        offsets.sort(key=lambda x: x[0])
        offset_final = offsets[-1][0] + offsets[-1][1]

        if offset_final > iso_size:
            raise ValueError(
                f"No se pudo recalcular el tamaño del archivo: "
                f"{offset_final:X} > iso_size: {iso_size:X}"
            )

        packfile_long_new = offset_final - packfile_offset

        if packfile_long_new <= 0:
            raise ValueError(
                f"No fue posible recalcular el tamaño del archivo: "
                f"{packfile_long_new}"
            )

        # ================================================================
        # CONSERVAR LOS DATOS QUE QUEDAN FUERA DEL TAMAÑO LÓGICO ORIGINAL
        # ================================================================
        # Si el nuevo tamaño es mayor que los datos que actualmente tenemos,
        # recuperamos del ISO original únicamente la parte que falta.
        # Así se conservan posibles modificaciones hechas a los primeros
        # bytes del PACKFILE y además se recupera su cola física original.
        if packfile_long_new > len(packfile_data):
            missing_size = packfile_long_new - len(packfile_data)

            try:
                with open(self.iso_path, "rb") as iso_fp:
                    iso_fp.seek(packfile_offset + len(packfile_data))
                    extra_data = iso_fp.read(missing_size)
            except (OSError, TypeError) as exc:
                raise ValueError(
                    f"No se pudieron recuperar los datos faltantes de "
                    f"PACKFILE.BIN desde la ISO original: {exc}"
                ) from exc

            if len(extra_data) != missing_size:
                raise ValueError(
                    "La ISO original no contiene suficientes datos físicos "
                    "para recuperar el final de PACKFILE.BIN."
                )

            packfile_data += extra_data
            packfile_data_size = len(packfile_data)

            # Guardar la versión completa en el almacenamiento de trabajo.
            if self.mode == "ram":
                self.memory_files[packfile_entry.path] = packfile_data
            else:
                working_path = (
                    self.storage_root / packfile_entry.path.lstrip("/")
                )
                working_path.parent.mkdir(parents=True, exist_ok=True)
                working_path.write_bytes(packfile_data)

            print(
                f"Datos recuperados del PACKFILE: "
                f"0x{missing_size:X} bytes adicionales"
            )

        if packfile_long_new != packfile_size:
            old_size = int(packfile_entry.size)
            packfile_entry.size = packfile_long_new

            # Actualizar el tamaño del PACKFILE en la interfaz.
            item = self.tree.currentItem()
            if item:
                item.setText(2, self.format_size(packfile_long_new))

            # Marcar el PACKFILE como modificado para la reconstrucción.
            self.modified.add(packfile_entry.path)

            QMessageBox.information(
                self,
                "Tamaño recalculado",
                "El tamaño de PACKFILE.BIN fue recalculado correctamente.\n\n"
                f"Anterior: 0x{old_size:X} ({old_size} bytes)\n"
                f"Nuevo:    0x{packfile_long_new:X} "
                f"({packfile_long_new} bytes)\n\n"
                f"Datos disponibles: 0x{packfile_data_size:X} bytes"
            )

            self.status.showMessage(
                f"Tamaño recalculado: {paths[0]} | "
                f"0x{old_size:X} → 0x{packfile_long_new:X} "
                f"({packfile_long_new} bytes)"
            )

            print(f"Tamaño recalculado: {packfile_long_new:X}")
        else:
            self.status.showMessage(
                f"PACKFILE.BIN ya tiene el tamaño correcto: "
                f"0x{packfile_size:X}"
            )

    def populate_open_with_menu(self, menu, entry):
        """Populate 'Abrir con' from the extensible handler registry."""
        # PACKFILE.BIN tiene una acción especial independiente de la extensión.
        if (
            not entry.is_dir
            and entry.name.upper() == "PACKFILE.BIN"
        ):
            action = QAction("Explorar PackFile", self)
            action.triggered.connect(
                lambda checked=False, e=entry:
                    self.open_packfile_explorer(e)
            )
            menu.addAction(action)

        extension = Path(entry.name).suffix.lower()
        handlers = OPEN_WITH_HANDLERS.get(extension, [])

        for name, callback in handlers:
            action = QAction(name, self)
            action.triggered.connect(
                lambda checked=False, cb=callback, e=entry:
                    self.execute_open_with(cb, e)
            )
            menu.addAction(action)

    def open_packfile_explorer(self, entry):
        """
        Prepara PACKFILE.BIN para que una UI externa pueda editarlo.

        Este metodo NO crea ninguna UI de PackFile. El backend se guarda en:
            self.packfile_buffer

        La UI que implementes puede obtener:
            self.packfile_buffer.data
            self.packfile_buffer.get_bytes()
            self.packfile_buffer.packfile_offset
            self.packfile_buffer.iso_size

        Para aplicar los cambios al proyecto usa:
            self.apply_packfile_buffer()

        La ISO original nunca se modifica aquí.
        """
        if not entry or entry.is_dir or entry.name.upper() != "PACKFILE.BIN":
            return None

        status = get_iso_rebuild_status(
            self.original_entries_snapshot,
            self.entries,
            self.modified,
        )

        if status["required"]:
            QMessageBox.information(
                self,
                "Reconstruir ISO requerida",
                format_rebuild_message(status)
            )
            return None

        try:
            packfile_data = self._get_file_data(entry)
            iso_size = Path(self.iso_path).stat().st_size
            packfile_offset = int(entry.extent) * SECTOR_SIZE

            self.packfile_entry = entry
            self.packfile_buffer = PackFileBuffer(
                packfile_data,
                packfile_offset=packfile_offset,
                iso_size=iso_size,
                path=entry.path,
                contenedor=self
            )

            # Ejecutar el punto de entrada del backend.
            # Aquí se ejecuta el código que hayas colocado en
            # PackFileBuffer.run_custom_code().
            result = self.packfile_buffer.run_custom_code(
                self.original_entries_snapshot,
                self.entries,
                self.modified,
            )

            if result.get("rebuild_required"):
                # Esta comprobación normalmente ya se hizo arriba, pero
                # mantenemos el resultado del backend por seguridad.
                QMessageBox.information(
                    self,
                    "Reconstruir ISO requerida",
                    format_rebuild_message(result.get("status", status))
                )
                return None

            self.status.showMessage(
                f"PACKFILE.BIN preparado: 0x{self.packfile_buffer.packfile_size:X} "
                f"bytes | Offset 0x{packfile_offset:X} | ISO 0x{iso_size:X} | "
                f"código ejecutado"
            )

            return self.packfile_buffer

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Explorar PackFile",
                f"No se pudo preparar PACKFILE.BIN:\n\n{exc}",
            )
            return None

    def apply_packfile_buffer(self, buffer=None):
        """
        Aplica un buffer PACKFILE al proyecto sin cambiar la referencia
        al buffer original de edición.

        Si ``buffer`` es None se usa ``self.packfile_buffer`` (el buffer
        original que abrió el explorador). Cuando se pasa un buffer nuevo,
        ese buffer se usa únicamente como fuente para actualizar
        ``memory_files``/disco y posteriormente reconstruir la ISO.
        """
        if buffer is None:
            buffer = self.packfile_buffer

        if buffer is None:
            raise RuntimeError(
                "No hay PACKFILE.BIN preparado."
            )

        if self.packfile_entry is None:
            raise RuntimeError(
                "No existe la entrada PACKFILE.BIN."
            )

        data = buffer.get_bytes()

        # RAM
        if self.mode == "ram":
            self.memory_files[
                self.packfile_entry.path
            ] = data

        # DISCO
        else:
            path = (
                    self.storage_root
                    / self.packfile_entry.path.lstrip("/")
            )

            path.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            with open(path, "wb") as f:
                f.write(data)

        # Actualizar tamaño ISO
        self.packfile_entry.size = len(data)

        # Marcar modificación
        self.modified.add(
            self.packfile_entry.path
        )

        # El commit pertenece al buffer que realmente se aplicó.
        # Esto evita tocar el buffer original cuando se está usando
        # self.new_packfile_buffer.
        buffer.commit()

        return data

    def execute_open_with(self, callback, entry):
        """Extract an ISO file if necessary and execute its opener."""
        try:
            # Open-with applications require a physical file.
            if self.mode == "ram":
                temp_dir = Path(tempfile.mkdtemp(prefix="psp_iso_open_"))
                file_path = temp_dir / entry.name
                file_path.write_bytes(self._get_file_data(entry))
            else:
                file_path = self.storage_root / entry.path.lstrip("/")

                if not file_path.exists():
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    self.reader.extract_file_to(entry, file_path)

            callback(file_path)

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Abrir con",
                f"No se pudo abrir '{entry.name}':\n\n{exc}"
            )

    def get_selected_paths(self):
        """Return all selected paths in the tree."""
        paths = []

        for item in self.tree.selectedItems():
            path = item.data(0, Qt.UserRole)
            if path:
                paths.append(path)

        return paths

    def get_selected_path(self):
        """Return the first selected path for single-file operations."""
        paths = self.get_selected_paths()
        return paths[0] if paths else None

    def open_entry(self, item, column):
        path = item.data(0, Qt.UserRole)
        entry = self.entries_by_path.get(path)
        if not entry or entry.is_dir:
            return

        self.status.showMessage(
            f"{entry.path} | {self.format_size(entry.size)} | "
            f"Offset 0x{entry.extent * SECTOR_SIZE:X}"
        )

    def export_selected_multiple(self):
        """Export selected files and/or complete directories."""
        paths = self.get_selected_paths()

        if not paths:
            QMessageBox.information(
                self, "Exportar",
                "Selecciona uno o varios archivos o carpetas."
            )
            return

        target = QFileDialog.getExistingDirectory(
            self, "Selecciona la carpeta de destino"
        )
        if not target:
            return

        target = Path(target)

        # Determine all entries that belong to the selected items.
        selected_entries = []
        selected_prefixes = []

        for path in paths:
            entry = self.entries_by_path.get(path)
            if not entry:
                continue

            if entry.is_dir:
                prefix = entry.path.rstrip("/") + "/"
                selected_prefixes.append(prefix)
                selected_entries.extend(
                    e for e in self.entries_by_path.values()
                    if e.path.startswith(prefix)
                )
            else:
                selected_entries.append(entry)

        # Remove duplicates when a parent folder and one of its children
        # were selected simultaneously.
        unique = {}
        for entry in selected_entries:
            unique[entry.path] = entry

        entries = sorted(
            unique.values(),
            key=lambda e: e.path.lower()
        )

        if not entries:
            QMessageBox.information(
                self, "Exportar",
                "La selección no contiene archivos."
            )
            return

        try:
            # Create explicitly selected directories as well.
            for path in paths:
                entry = self.entries_by_path.get(path)
                if entry and entry.is_dir:
                    (target / entry.path.lstrip("/")).mkdir(
                        parents=True, exist_ok=True
                    )

            total = len(entries)

            for index, entry in enumerate(entries, 1):
                output = target / entry.path.lstrip("/")
                output.parent.mkdir(parents=True, exist_ok=True)

                if self.mode == "ram":
                    data = self._get_file_data(entry)
                    with open(output, "wb") as f:
                        f.write(data)
                else:
                    source = self.storage_root / entry.path.lstrip("/")

                    if not source.exists():
                        source.parent.mkdir(parents=True, exist_ok=True)
                        self.reader.extract_file_to(entry, source)

                    shutil.copyfile(source, output)

                self.status.showMessage(
                    f"Exportando {index}/{total}: {entry.path}"
                )

            self.status.showMessage(
                f"Exportación completada: {total} archivos."
            )

        except Exception as exc:
            QMessageBox.critical(self, "Error al exportar", str(exc))


    def export_all(self):
        if not self.reader:
            return

        target = QFileDialog.getExistingDirectory(
            self, "Selecciona la carpeta de destino"
        )
        if not target:
            return

        self.progress.setVisible(True)
        self.progress.setValue(0)

        if self.mode == "disk":
            # Already physically extracted; copy the complete tree.
            try:
                source = self.storage_root
                for item in source.rglob("*"):
                    relative = item.relative_to(source)
                    dest = Path(target) / relative
                    if item.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest)
                self.progress.setValue(100)
                self.progress.setVisible(False)
                self.status.showMessage("Exportación completada.")
            except Exception as exc:
                self.progress.setVisible(False)
                QMessageBox.critical(self, "Error", str(exc))
        else:
            # Extract directly from the ISO in a worker.
            self.worker = IsoWorker(
                self.reader,
                list(self.entries_by_path.values()),
                Path(target),
                "disk"
            )
            self.worker.progress.connect(self.progress.setValue)
            self.worker.progress.connect(
                lambda _, text: self.status.showMessage(text)
            )
            self.worker.finished_ok.connect(
                lambda _: (
                    self.progress.setVisible(False),
                    self.status.showMessage("Exportación completada.")
                )
            )
            self.worker.failed.connect(self.worker_error)
            self.worker.start()

    def _get_file_data(self, entry):
        """
        Obtiene los datos del archivo sin duplicar el archivo completo en RAM.

        En modo RAM, memory_files conserva el MISMO bytearray que fue
        cargado inicialmente. Para una entrada nueva, primero se reserva
        el bytearray y luego IsoReader.read_file_into() lo llena por bloques.

        Especialmente importante para PACKFILE.BIN: no se crea primero un
        bytes de cientos de MB para convertirlo después a bytearray.
        """
        if self.mode == "ram":
            if entry.path not in self.memory_files:
                if entry.is_dir:
                    self.memory_files[entry.path] = bytearray()
                else:
                    data = bytearray(int(entry.size))
                    self.reader.read_file_into(entry, data)
                    self.memory_files[entry.path] = data

            return self.memory_files[entry.path]

        source = self.storage_root / entry.path.lstrip("/")
        if not source.exists():
            self.reader.extract_file_to(entry, source)

        # También devolvemos bytearray para que el contrato de este metodo
        # sea consistente. En modo disco el archivo no permanece en RAM
        # salvo durante esta lectura.
        with open(source, "rb") as f:
            return bytearray(f.read())

    def _get_insert_parent(self):
        """Return the ISO directory where a new file/folder should go."""
        paths = self.get_selected_paths()

        if not paths:
            return "/"

        # Insertion only has a single destination.
        if len(paths) > 1:
            QMessageBox.information(
                self,
                "Insertar",
                "Selecciona un solo archivo o una sola carpeta."
            )
            return None

        entry = self.entries_by_path.get(paths[0])
        if not entry:
            return None

        if entry.is_dir:
            return entry.path.rstrip("/") or "/"

        # A selected file means insert next to it.
        parent = entry.path.rsplit("/", 1)[0]
        return parent if parent else "/"

    def insert_file(self):
        """Insert a new physical file into the ISO tree."""
        if not getattr(self, "reader", None):
            QMessageBox.information(
                self, "Insertar archivo",
                "Primero abre una ISO."
            )
            return

        parent = self._get_insert_parent()
        if parent is None:
            return

        source, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo para insertar"
        )
        if not source:
            return

        source = Path(source)
        name = source.name
        iso_path = parent.rstrip("/") + "/" + name if parent != "/" else "/" + name

        if iso_path in self.entries_by_path:
            QMessageBox.warning(
                self,
                "Insertar archivo",
                f"Ya existe un archivo o carpeta con el nombre:\n{iso_path}"
            )
            return

        try:
            data = source.read_bytes()

            # Keep the inserted file in the same storage mode selected
            # when the ISO was opened.
            if self.mode == "ram":
                self.memory_files[iso_path] = data
            else:
                destination = self.storage_root / iso_path.lstrip("/")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)

            entry = IsoEntry(
                name,
                iso_path,
                False,
                0,
                len(data)
            )

            self.entries.append(entry)
            self.entries_by_path[iso_path] = entry
            self.modified.add(iso_path)

            self._populate_tree(self.entries)

            # Try to select the inserted file.
            items = self.tree.findItems(
                name,
                Qt.MatchRecursive | Qt.MatchExactly,
                0
            )
            for item in items:
                if item.data(0, Qt.UserRole) == iso_path:
                    self.tree.clearSelection()
                    item.setSelected(True)
                    self.tree.scrollToItem(item)
                    break

            self.status.showMessage(
                f"Archivo insertado: {iso_path} ({len(data)} bytes)"
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error al insertar archivo",
                str(exc)
            )

    def create_folder(self):
        """Create a new directory in the ISO tree."""
        if not getattr(self, "reader", None):
            QMessageBox.information(
                self, "Crear carpeta",
                "Primero abre una ISO."
            )
            return

        parent = self._get_insert_parent()
        if parent is None:
            return

        name, ok = QInputDialog.getText(
            self,
            "Crear carpeta",
            "Nombre de la carpeta:"
        )

        if not ok:
            return

        name = name.strip()

        if not name:
            QMessageBox.warning(
                self,
                "Crear carpeta",
                "El nombre no puede estar vacío."
            )
            return

        if "/" in name or "\\" in name:
            QMessageBox.warning(
                self,
                "Crear carpeta",
                "El nombre no puede contener '/' ni '\\'."
            )
            return

        iso_path = parent.rstrip("/") + "/" + name if parent != "/" else "/" + name

        if iso_path in self.entries_by_path:
            QMessageBox.warning(
                self,
                "Crear carpeta",
                f"Ya existe:\n{iso_path}"
            )
            return

        try:
            if self.mode == "disk":
                directory = self.storage_root / iso_path.lstrip("/")
                directory.mkdir(parents=True, exist_ok=False)

            entry = IsoEntry(
                name,
                iso_path,
                True,
                0,
                0
            )

            self.entries.append(entry)
            self.entries_by_path[iso_path] = entry
            self.modified.add(iso_path)

            self._populate_tree(self.entries)

            items = self.tree.findItems(
                name,
                Qt.MatchRecursive | Qt.MatchExactly,
                0
            )
            for item in items:
                if item.data(0, Qt.UserRole) == iso_path:
                    self.tree.clearSelection()
                    item.setSelected(True)
                    self.tree.scrollToItem(item)
                    break

            self.status.showMessage(
                f"Carpeta creada: {iso_path}"
            )

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error al crear carpeta",
                str(exc)
            )

    def delete_selected(self):
        """Delete selected files/folders from the working ISO tree."""
        if not getattr(self, "reader", None):
            QMessageBox.information(
                self, "Borrar", "Primero abre una ISO."
            )
            return

        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(
                self, "Borrar", "Selecciona uno o varios archivos o carpetas."
            )
            return

        entries = []
        seen = set()
        for path in paths:
            entry = self.entries_by_path.get(path)
            if entry and path != "/" and path not in seen:
                entries.append(entry)
                seen.add(path)

        if not entries:
            QMessageBox.information(
                self, "Borrar", "No hay elementos válidos para borrar."
            )
            return

        # If a selected folder contains another selected item, deleting the
        # folder already deletes the child, so avoid duplicate work.
        selected_dirs = [e.path.rstrip("/") + "/" for e in entries if e.is_dir]
        effective = []
        for entry in entries:
            if any(entry.path.startswith(prefix) for prefix in selected_dirs):
                continue
            effective.append(entry)

        names = "\n".join(
            f"• {e.path}" for e in effective[:20]
        )
        extra = ""
        if len(effective) > 20:
            extra = f"\n... y {len(effective) - 20} más"

        answer = QMessageBox.question(
            self,
            "Confirmar borrado",
            "Se eliminarán del proyecto estos elementos:\n\n"
            f"{names}{extra}\n\n"
            "La ISO original no será modificada.\n"
            "Los cambios se aplicarán al crear una ISO reconstruida.\n\n"
            "¿Continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if answer != QMessageBox.Yes:
            return

        try:
            removed_files = 0
            removed_dirs = 0
            removed_paths = set()

            for entry in effective:
                prefix = entry.path.rstrip("/") + "/"

                if entry.is_dir:
                    child_entries = [
                        e for e in self.entries
                        if e.path == entry.path or e.path.startswith(prefix)
                    ]
                else:
                    child_entries = [entry]

                for child in child_entries:
                    removed_paths.add(child.path)
                    if child.is_dir:
                        removed_dirs += 1
                    else:
                        removed_files += 1

                if self.mode == "disk":
                    filesystem_path = self.storage_root / entry.path.lstrip("/")
                    if filesystem_path.exists():
                        if entry.is_dir:
                            shutil.rmtree(filesystem_path)
                        else:
                            filesystem_path.unlink()

            # Rebuild the in-memory index without deleted entries.
            self.entries = [
                e for e in self.entries if e.path not in removed_paths
            ]

            for path in removed_paths:
                self.entries_by_path.pop(path, None)
                self.memory_files.pop(path, None)
                self.modified.add(path)

            self.tree.clear()
            self._populate_tree(self.entries)

            self.status.showMessage(
                f"Borrado: {removed_files} archivos, {removed_dirs} carpetas."
            )

        except Exception as exc:
            QMessageBox.critical(
                self, "Error al borrar", str(exc)
            )

    def edit_selected_size(self):
        """Edit the logical size stored for the selected ISO9660 file."""
        paths = self.get_selected_paths()
        if not paths:
            QMessageBox.information(
                self, "Editar tamaño", "Selecciona un archivo."
            )
            return

        if len(paths) > 1:
            QMessageBox.information(
                self, "Editar tamaño",
                "Para editar el tamaño debes seleccionar un solo archivo."
            )
            return

        path = paths[0]
        entry = self.entries_by_path.get(path)
        if not entry or entry.is_dir:
            QMessageBox.information(
                self, "Editar tamaño",
                "Selecciona un archivo, no un directorio."
            )
            return

        # Use a text dialog instead of QInputDialog.getInt().
        # This also avoids the 32-bit integer limit of the Qt overload.
        from PyQt5.QtWidgets import QLineEdit

        current = str(int(entry.size))

        value_text, ok = QInputDialog.getText(
            self,
            "Editar tamaño del archivo",
            f"Tamaño de '{entry.name}' en bytes:\n"
            "También puedes usar hexadecimal (ej. 0x37110):",
            QLineEdit.Normal,
            current
        )

        if not ok:
            return

        value_text = value_text.strip()

        if not value_text:
            QMessageBox.warning(
                self, "Tamaño inválido",
                "Debes introducir un tamaño."
            )
            return

        try:
            if value_text.lower().startswith("0x"):
                new_size = int(value_text, 16)
            else:
                new_size = int(value_text, 10)

            if new_size < 0:
                raise ValueError

            # ISO9660 stores the file size as a 32-bit unsigned value.
            if new_size > 0xFFFFFFFF:
                raise ValueError

        except ValueError:
            QMessageBox.warning(
                self,
                "Tamaño inválido",
                "Introduce un número válido.\n\n"
                "Ejemplos:\n"
                "225456\n"
                "0x37110"
            )
            return

        old_size = int(entry.size)
        entry.size = new_size

        item = self.tree.currentItem()
        if item:
            item.setText(2, self.format_size(new_size))

        self.modified.add(path)

        self.status.showMessage(
            f"Tamaño modificado: {path} | "
            f"0x{old_size:X} → 0x{new_size:X} "
            f"({new_size} bytes)"
        )

    def import_file(self):
        path = self.get_selected_path()
        if not path:
            QMessageBox.information(
                self, "Importar", "Selecciona el archivo de la ISO que quieres reemplazar."
            )
            return

        entry = self.entries_by_path.get(path)
        if not entry or entry.is_dir:
            QMessageBox.information(
                self, "Importar", "Selecciona un archivo, no un directorio."
            )
            return

        source, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo para importar"
        )
        if not source:
            return

        try:
            new_size = os.path.getsize(source)

            if new_size > entry.size:
                answer = QMessageBox.question(
                    self,
                    "Tamaño mayor",
                    f"El archivo nuevo mide {self.format_size(new_size)} y "
                    f"el original {self.format_size(entry.size)}.\n\n"
                    "El archivo podrá reconstruirse como una nueva ISO, "
                    "pero no se conservará el espacio físico original.\n\n"
                    "¿Continuar?"
                )
                if answer != QMessageBox.Yes:
                    return

            if self.mode == "ram":
                with open(source, "rb") as f:
                    self.memory_files[path] = f.read()
            else:
                destination = self.storage_root / path.lstrip("/")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)

            entry.size = new_size
            self.modified.add(path)
            self.status.showMessage(
                f"Archivo reemplazado: {path} ({self.format_size(new_size)})"
            )

            QMessageBox.information(
                self, "Importar",
                "Archivo importado correctamente.\n\n"
                "Para obtener una ISO modificada usa ISO → Reconstruir ISO..."
            )

        except Exception as exc:
            QMessageBox.critical(self, "Error al importar", str(exc))

    def rebuild_iso(self):
        if not self.reader:
            QMessageBox.information(self, "Reconstruir", "Primero abre una ISO.")
            return

        try:
            import pycdlib
        except ImportError:
            QMessageBox.critical(
                self,
                "Falta dependencia",
                "Para reconstruir la ISO necesitas pycdlib.\n\n"
                "Instálalo con:\n\npip install pycdlib"
            )
            return

        target, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar ISO reconstruida",
            str(Path(self.iso_path).with_name(
                Path(self.iso_path).stem + "_mod.iso"
            )),
            "ISO (*.iso)"
        )
        if not target:
            return

        if Path(target) == Path(self.iso_path):
            QMessageBox.information(self, "Reconstruir", "No se puede rescribir la ISO base.")
            return

        try:
            iso = pycdlib.PyCdlib()
            iso.new(interchange_level=3)

            root_entries = [
                e for e in self.entries_by_path.values()
                if e.path != "/" and not e.is_dir
            ]

            # Add directories explicitly.
            dirs = sorted(
                [e for e in self.entries_by_path.values() if e.is_dir],
                key=lambda x: x.path.count("/")
            )

            for d in dirs:
                iso_path = self._to_iso_path(d.path)
                if iso_path != "/":
                    try:
                        iso.add_directory(iso_path)
                    except Exception:
                        pass

            for e in root_entries:
                iso_path = self._to_iso_path(e.path)

                if self.mode == "disk":
                    source = self.storage_root / e.path.lstrip("/")
                    if not source.exists():
                        source.parent.mkdir(parents=True, exist_ok=True)
                        self.reader.extract_file_to(e, source)
                    source_path = str(source)
                else:
                    # pycdlib add_fp works with file-like objects.
                    import io
                    source_path = None
                    fp = io.BytesIO(self._get_file_data(e))

                # The UI allows correcting the logical ISO file size.
                # pycdlib normally takes the physical host-file size, so when
                # the user changed entry.size we create a temporary stream
                # with exactly that many bytes (truncate or zero-pad).
                import io

                data = None
                if self.mode == "disk":
                    with open(source_path, "rb") as source_fp:
                        data = source_fp.read()
                else:
                    data = self._get_file_data(e)

                if len(data) != e.size:
                    if len(data) > e.size:
                        data = data[:e.size]
                    else:
                        data = data + (b"\x00" * (e.size - len(data)))

                fp = io.BytesIO(data)
                # pycdlib keeps the file-like object while building the ISO,
                # so it must remain open until iso.write() has completed.
                iso.add_fp(fp, e.size, iso_path=iso_path)

            iso.write(target)
            iso.close()

            QMessageBox.information(
                self,
                "ISO reconstruida",
                f"ISO creada correctamente:\n\n{target}\n\n"
                "Nota: esta operación crea una nueva ISO9660; "
                "no conserva necesariamente las posiciones físicas originales."
            )
            self.status.showMessage(f"ISO reconstruida: {target}")

        except Exception as exc:
            QMessageBox.critical(self, "Error al reconstruir", str(exc))

    @staticmethod
    def _to_iso_path(path):
        # ISO9660 path format expected by pycdlib.
        return "/" + "/".join(
            p.upper() for p in path.split("/") if p
        )

    def close_iso(self):
        if self.reader:
            self.reader.close()

        self.reader = None
        self.iso_path = None
        self.entries.clear()
        self.entries_by_path.clear()
        self.memory_files.clear()
        self.modified.clear()
        self.original_entries_snapshot.clear()
        self.packfile_buffer = None
        self.packfile_entry = None
        self.new_packfile_buffer = None
        self.tree.clear()

        if self.storage_root and self.storage_root.exists():
            try:
                shutil.rmtree(self.storage_root, ignore_errors=True)
            except Exception:
                pass

        self.storage_root = None
        self.setWindowTitle("PSP ISO Explorer")
        self.status.showMessage("ISO cerrada.")

        # liberar ram, de los objetos sin referencia
        gc.collect()

    def worker_error(self, text):
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Error", text)

    def show_about(self):
        QMessageBox.information(
            self,
            "PSP ISO Explorer",
            "Explorador ISO9660 para trabajar con ISOs de PSP.\n\n"
            "Permite modo RAM o disco, extracción, importación/reemplazo "
            "y reconstrucción de ISO."
        )

    def closeEvent(self, event):
        self.close_iso()
        event.accept()



# def main():
#     app = QApplication(sys.argv)
#     app.setApplicationName("PSP ISO Explorer")
#     app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
#     window = IsoExplorer()
#     window.show()
#     sys.exit(app.exec_())
#
#
# if __name__ == "__main__":
#     main()
