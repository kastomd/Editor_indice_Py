#!/usr/bin/env python3
"""
PSPRecomp ELF Editor - PyQt5

Funciones:
- Abrir ELF32 little-endian.
- Mostrar información general del ELF.
- Mostrar todos los PT_LOAD.
- Seleccionar un PT_LOAD y ver sus datos.
- Exportar individualmente el FileSize del PT_LOAD como MIPS RAW (.txt o .raw).
- Importar un MIPS RAW (.txt o .raw) sobre un PT_LOAD existente.
- Guardar el ELF modificado conservando el resto del archivo intacto.

El RAW representa únicamente la zona respaldada por el archivo:
    [p_offset, p_offset + p_filesz)

La zona BSS (memsz > filesz) no se exporta porque no tiene bytes
correspondientes en el ELF.
"""
import os
import subprocess
import sys
import struct
import re
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget, QScrollArea,
    QFileDialog,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QGroupBox,
    QLineEdit,
    QCheckBox,
    QTextEdit,
    QSplitter,
    QInputDialog,
    QAction,
    QMenuBar,
    QStatusBar,
)

from app_md.elf_edit.elf.elf_loader import ElfLoader
from app_md.elf_edit.elf.elf_imports import Elf32, find_module_info, scan_imports
from app_md.elf_edit.mips_decoder import disassemble_mips, assemble_mips


def hex32(value):
    return f"0x{value:08X}"


def perms(flags):
    return (
        ("R" if flags & 4 else "-")
        + ("W" if flags & 2 else "-")
        + ("X" if flags & 1 else "-")
    )


class DropButton(QPushButton):
    """Botón que acepta archivos locales arrastrados y soltados."""
    filesDropped = pyqtSignal(list)

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            files = [u.toLocalFile() for u in event.mimeData().urls()
                     if u.isLocalFile()]
            if files:
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()
                 if u.isLocalFile()]
        if files:
            self.filesDropped.emit(files)
            event.acceptProposedAction()
        else:
            event.ignore()


class ElfEditor(QMainWindow):
    def __init__(self):
        super().__init__()

        self.loader = None
        self.elf_data = None
        self.elf_path = None
        self.dirty = False
        self.module_info = None
        self.imports = []

        self.setWindowTitle("ELF Editor")
        self.resize(1150, 760)

        self._build_ui()
        self._build_menu()
        self._update_ui()

    @staticmethod
    def _get_resources_path(rel_path: Path) -> Path:
        # Retorna la ruta absoluta del recurso, compatible con PyInstaller
        if hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS) / rel_path
        return Path(__file__).resolve().parent / rel_path

    @staticmethod
    def _run_subprocess(command: list, cwd=None) -> subprocess.CompletedProcess:
        # Ejecuta un comando en subprocess y evita ventana emergente en Windows
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        return subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
            cwd=cwd
        )

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        central = QWidget()
        scroll.setWidget(central)
        self.setCentralWidget(scroll)

        root = QVBoxLayout(central)

        # Top buttons
        buttons = QHBoxLayout()

        self.open_button = DropButton("Abrir ELF")
        self.save_button = QPushButton("Guardar ELF")
        self.save_as_button = QPushButton("Guardar como...")

        self.open_button.clicked.connect(self.open_elf)
        self.save_button.clicked.connect(self.save_elf)
        self.save_as_button.clicked.connect(self.save_elf_as)

        buttons.addWidget(self.open_button)
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.save_as_button)
        buttons.addStretch()

        self.path_label = QLabel("Ningún ELF abierto")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        buttons.addWidget(self.path_label)

        root.addLayout(buttons)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        # --------------------------------------------------------------
        # Left: ELF + PT_LOAD tree
        # --------------------------------------------------------------

        left = QWidget()
        left_layout = QVBoxLayout(left)

        self.elf_info_group = QGroupBox("ELF")
        elf_grid = QGridLayout(self.elf_info_group)

        self.lbl_format = QLabel("-")
        self.lbl_machine = QLabel("-")
        self.lbl_module = QLabel("-")
        self.lbl_entry = QLabel("-")
        self.lbl_size = QLabel("-")
        self.lbl_segments = QLabel("-")

        elf_grid.addWidget(QLabel("Formato:"), 0, 0)
        elf_grid.addWidget(self.lbl_format, 0, 1)

        elf_grid.addWidget(QLabel("Machine:"), 1, 0)
        elf_grid.addWidget(self.lbl_machine, 1, 1)

        elf_grid.addWidget(QLabel("Module:"), 2, 0)
        elf_grid.addWidget(self.lbl_module, 2, 1)

        elf_grid.addWidget(QLabel("Entry:"), 3, 0)
        elf_grid.addWidget(self.lbl_entry, 3, 1)

        elf_grid.addWidget(QLabel("Tamaño:"), 4, 0)
        elf_grid.addWidget(self.lbl_size, 4, 1)

        elf_grid.addWidget(QLabel("PT_LOAD:"), 5, 0)
        elf_grid.addWidget(self.lbl_segments, 5, 1)

        left_layout.addWidget(self.elf_info_group)

        self.segment_tree = QTreeWidget()
        self.segment_tree.setColumnCount(7)
        self.segment_tree.setHeaderLabels([
            "#",
            "Flags",
            "Offset",
            "VAddr",
            "FileSize",
            "MemSize",
            "Align",
        ])
        self.segment_tree.setAlternatingRowColors(True)
        self.segment_tree.itemSelectionChanged.connect(
            self.segment_selected
        )

        left_layout.addWidget(QLabel("Program Headers / PT_LOAD"))
        left_layout.addWidget(self.segment_tree)

        splitter.addWidget(left)

        # --------------------------------------------------------------
        # Right: selected segment
        # --------------------------------------------------------------

        right = QWidget()
        right_layout = QVBoxLayout(right)

        self.segment_group = QGroupBox("PT_LOAD seleccionado")
        grid = QGridLayout(self.segment_group)

        self.fields = {}

        field_names = [
            ("Índice PHDR", "index"),
            ("Offset ELF", "offset"),
            ("Virtual Address", "vaddr"),
            ("Physical Address", "paddr"),
            ("File Size", "filesz"),
            ("Memory Size", "memsz"),
            ("Flags", "flags"),
            ("Permisos", "perms"),
            ("Alignment", "align"),
            ("File End", "file_end"),
            ("Memory End", "mem_end"),
            ("BSS Size", "bss"),
        ]

        for row, (title, key) in enumerate(field_names):
            grid.addWidget(QLabel(title + ":"), row, 0)

            value = QLineEdit()
            value.setReadOnly(True)
            value.setText("-")

            self.fields[key] = value
            grid.addWidget(value, row, 1)

        right_layout.addWidget(self.segment_group)

        # --------------------------------------------------------------
        # Edit selected PT_LOAD
        # --------------------------------------------------------------
        edit_group = QGroupBox("Editar PT_LOAD seleccionado")
        edit_grid = QGridLayout(edit_group)

        self.edit_vaddr = QLineEdit()
        self.edit_paddr = QLineEdit()
        self.edit_memsz = QLineEdit()
        self.edit_align = QLineEdit()

        edit_grid.addWidget(QLabel("Virtual Address:"), 0, 0)
        edit_grid.addWidget(self.edit_vaddr, 0, 1)
        edit_grid.addWidget(QLabel("Physical Address:"), 1, 0)
        edit_grid.addWidget(self.edit_paddr, 1, 1)
        edit_grid.addWidget(QLabel("Memory Size:"), 2, 0)
        edit_grid.addWidget(self.edit_memsz, 2, 1)
        edit_grid.addWidget(QLabel("Alignment:"), 3, 0)
        edit_grid.addWidget(self.edit_align, 3, 1)

        edit_perm = QHBoxLayout()
        edit_perm.addWidget(QLabel("Permisos:"))
        self.edit_read_check = QCheckBox("R")
        self.edit_write_check = QCheckBox("W")
        self.edit_exec_check = QCheckBox("X")
        edit_perm.addWidget(self.edit_read_check)
        edit_perm.addWidget(self.edit_write_check)
        edit_perm.addWidget(self.edit_exec_check)
        edit_perm.addStretch()
        edit_grid.addLayout(edit_perm, 4, 0, 1, 2)

        edit_buttons = QHBoxLayout()
        self.apply_segment_button = QPushButton("Aplicar cambios")
        self.delete_segment_button = QPushButton("Eliminar PT_LOAD")
        self.apply_segment_button.clicked.connect(self.apply_segment_changes)
        self.delete_segment_button.clicked.connect(self.delete_selected_segment)
        edit_buttons.addWidget(self.apply_segment_button)
        edit_buttons.addWidget(self.delete_segment_button)
        edit_grid.addLayout(edit_buttons, 5, 0, 1, 2)

        right_layout.addWidget(edit_group)

        # Buttons
        actions_group = QGroupBox("MIPS RAW")
        actions = QVBoxLayout(actions_group)

        self.export_button = QPushButton(
            "Exportar PT_LOAD seleccionado → MIPS RAW"
        )
        self.import_button = DropButton(
            "Importar MIPS RAW → PT_LOAD seleccionado"
        )
        self.raw_to_code_button = DropButton(
            "Convertir MIPS RAW → MIPS Code"
        )
        self.code_to_raw_button = DropButton(
            "Convertir MIPS Code → MIPS RAW"
        )
        self.add_pt_load_button = DropButton(
            "Añadir PT_LOAD desde MIPS RAW"
        )

        # Permisos del nuevo PT_LOAD.
        # Por defecto: R-X, apropiado para código MIPS ejecutable.
        permissions_layout = QHBoxLayout()
        permissions_layout.addWidget(QLabel("Permisos del nuevo PT_LOAD:"))

        self.add_read_check = QCheckBox("R (Read)")
        self.add_write_check = QCheckBox("W (Write)")
        self.add_exec_check = QCheckBox("X (Execute)")

        self.add_read_check.setChecked(True)
        self.add_exec_check.setChecked(True)

        permissions_layout.addWidget(self.add_read_check)
        permissions_layout.addWidget(self.add_write_check)
        permissions_layout.addWidget(self.add_exec_check)
        permissions_layout.addStretch()

        self.export_button.clicked.connect(
            self.export_selected_segment
        )
        self.import_button.clicked.connect(
            lambda :self.import_selected_segment()
        )
        self.raw_to_code_button.clicked.connect(
            lambda :self.convert_raw_to_code()
        )
        self.code_to_raw_button.clicked.connect(
            lambda :self.convert_code_to_raw()
        )
        self.add_pt_load_button.clicked.connect(
            lambda :self.add_pt_load_from_raw()
        )

        self.open_button.filesDropped.connect(self._drop_open_elf)
        self.import_button.filesDropped.connect(self._drop_import_raw)
        self.raw_to_code_button.filesDropped.connect(self._drop_raw_to_code)
        self.code_to_raw_button.filesDropped.connect(self._drop_code_to_raw)
        self.add_pt_load_button.filesDropped.connect(self._drop_add_pt_load)

        actions.addWidget(self.export_button)
        actions.addWidget(self.import_button)
        actions.addWidget(self.raw_to_code_button)
        actions.addWidget(self.code_to_raw_button)
        actions.addLayout(permissions_layout)
        actions.addWidget(self.add_pt_load_button)

        right_layout.addWidget(actions_group)

        # Log
        right_layout.addWidget(QLabel("Información"))

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QTextEdit.NoWrap)
        right_layout.addWidget(self.log)

        splitter.addWidget(right)
        splitter.setSizes([650, 500])

        self.status = QStatusBar()
        self.setStatusBar(self.status)

    def _build_menu(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("Archivo")

        open_action = QAction("Abrir ELF", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_elf)

        save_action = QAction("Guardar", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_elf)

        save_as_action = QAction("Guardar como...", self)
        save_as_action.triggered.connect(self.save_elf_as)

        exit_action = QAction("Salir", self)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

    # ------------------------------------------------------------------
    # Drag & Drop
    # ------------------------------------------------------------------

    @staticmethod
    def _first_dropped(files):
        return Path(files[0]) if files else None

    def _drop_open_elf(self, files):
        path = self._first_dropped(files)
        if path is not None:
            self.load_elf(path)

    def _drop_import_raw(self, files):
        path = self._first_dropped(files)
        if path is not None:
            self.import_selected_segment(str(path))

    def _drop_raw_to_code(self, files):
        path = self._first_dropped(files)
        if path is not None:
            self.convert_raw_to_code(str(path))

    def _drop_code_to_raw(self, files):
        path = self._first_dropped(files)
        if path is not None:
            self.convert_code_to_raw(str(path))

    def _drop_add_pt_load(self, files):
        path = self._first_dropped(files)
        if path is not None:
            self.add_pt_load_from_raw(str(path))


    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _update_ui(self):
        enabled = self.loader is not None

        self.save_button.setEnabled(enabled and self.dirty)
        self.save_as_button.setEnabled(enabled)

        self.export_button.setEnabled(
            enabled and self.selected_segment() is not None
        )
        self.import_button.setEnabled(
            enabled and self.selected_segment() is not None
        )
        self.raw_to_code_button.setEnabled(
            enabled and self.selected_segment() is not None
        )
        self.code_to_raw_button.setEnabled(
            enabled and self.selected_segment() is not None
        )
        self.add_pt_load_button.setEnabled(enabled)
        has_segment = enabled and self.selected_segment() is not None
        self.apply_segment_button.setEnabled(has_segment)
        self.delete_segment_button.setEnabled(has_segment)

        if not enabled:
            self.path_label.setText("Ningún ELF abierto")
            self.lbl_format.setText("-")
            self.lbl_machine.setText("-")
            self.lbl_module.setText("-")
            self.lbl_entry.setText("-")
            self.lbl_size.setText("-")
            self.lbl_segments.setText("-")

    def selected_segment(self):
        item = self.segment_tree.currentItem()

        if item is None:
            return None

        index = item.data(0, Qt.UserRole)

        if index is None:
            return None

        try:
            return self.loader.segments[int(index)]
        except (IndexError, TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Open
    # ------------------------------------------------------------------

    def open_elf(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir ELF",
            "",
            "ELF (*.elf *.ELF);;Todos los archivos (*)",
        )

        if not filename:
            return

        self.load_elf(Path(filename))

    def load_elf(self, path: Path):
        try:
            data = path.read_bytes()
            loader = ElfLoader(data)
            module_info = None
            imports = []
            try:
                parsed_elf = Elf32(data)
                module_info = find_module_info(parsed_elf)
                if module_info:
                    imports = scan_imports(parsed_elf, module_info)
            except (ValueError, RuntimeError):
                # Algunos ELF pueden no tener ModuleInfo; no impedir la carga.
                module_info = None

            if not loader.segments:
                raise ValueError(
                    "El ELF no contiene segmentos PT_LOAD."
                )

            self.elf_data = bytearray(data)
            self.loader = loader
            self.module_info = module_info
            self.imports = imports
            self.elf_path = path
            self.dirty = False

            self.populate_elf_info()
            self.populate_segments()

            self.log.clear()
            self.log_message(
                f"ELF abierto: {path}"
            )
            self.log_message(
                f"PT_LOAD encontrados: "
                f"{len(loader.segments)}"
            )
            self.log_message(
                f"Librerías importadas: {len(self.imports)}"
            )

            self.status.showMessage(
                f"Abierto: {path.name}"
            )

            self._update_ui()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error al abrir ELF",
                str(exc),
            )

    def populate_elf_info(self):
        data = self.elf_data

        elf_class = data[4]
        endian = data[5]

        machine = struct.unpack_from(
            "<H",
            data,
            18,
        )[0]

        self.lbl_format.setText(
            f"ELF{32 if elf_class == 1 else '?'} / "
            f"{'Little Endian' if endian == 1 else 'Big Endian'}"
        )

        machine_name = {
            8: "MIPS",
            0x28: "ARM",
            0x3E: "x86-64",
        }.get(machine, f"0x{machine:04X}")

        self.lbl_machine.setText(machine_name)
        self.lbl_module.setText(
            self.module_info["name"] if self.module_info else "No encontrado"
        )
        self.lbl_entry.setText(
            hex32(self.loader.entry)
        )
        self.lbl_size.setText(
            f"{len(data):,} bytes "
            f"({hex32(len(data))})"
        )
        self.lbl_segments.setText(
            str(len(self.loader.segments))
        )

        self.path_label.setText(
            str(self.elf_path)
        )

    def populate_segments(self):
        self.segment_tree.clear()

        for number, seg in enumerate(self.loader.segments):
            item = QTreeWidgetItem([
                str(number),
                perms(seg.flags),
                hex32(seg.offset),
                hex32(seg.vaddr),
                hex32(seg.filesz),
                hex32(seg.memsz),
                hex32(seg.align),
            ])

            item.setData(
                0,
                Qt.UserRole,
                number,
            )

            self.segment_tree.addTopLevelItem(item)

        if self.loader.segments:
            self.segment_tree.setCurrentItem(
                self.segment_tree.topLevelItem(0)
            )

    # ------------------------------------------------------------------
    # Segment selection
    # ------------------------------------------------------------------

    def segment_selected(self):
        seg = self.selected_segment()

        if seg is None:
            self.clear_segment_info()
            self._update_ui()
            return

        values = {
            "index": str(seg.index),
            "offset": hex32(seg.offset),
            "vaddr": hex32(seg.vaddr),
            "paddr": hex32(seg.paddr),
            "filesz": hex32(seg.filesz),
            "memsz": hex32(seg.memsz),
            "flags": f"0x{seg.flags:X}",
            "perms": perms(seg.flags),
            "align": hex32(seg.align),
            "file_end": hex32(seg.file_end),
            "mem_end": hex32(seg.mem_end),
            "bss": hex32(seg.bss_size),
        }

        for key, value in values.items():
            self.fields[key].setText(value)

        self.edit_vaddr.setText(hex32(seg.vaddr))
        self.edit_paddr.setText(hex32(seg.paddr))
        self.edit_memsz.setText(hex32(seg.memsz))
        self.edit_align.setText(hex32(seg.align))
        self.edit_read_check.setChecked(bool(seg.flags & 4))
        self.edit_write_check.setChecked(bool(seg.flags & 2))
        self.edit_exec_check.setChecked(bool(seg.flags & 1))

        self.segment_group.setTitle(
            f"PT_LOAD #{self.segment_tree.currentItem().text(0)}"
        )

        self.log_message(
            f"Seleccionado PT_LOAD "
            f"#{self.segment_tree.currentItem().text(0)}: "
            f"VAddr={hex32(seg.vaddr)}, "
            f"FileSize={hex32(seg.filesz)}, "
            f"MemSize={hex32(seg.memsz)}"
        )

        self._update_ui()

    def refresh_segment_ui(self, index):
        """Actualiza la UI después de modificar un PT_LOAD en memoria."""
        if self.loader is None or not (0 <= index < len(self.loader.segments)):
            return

        seg = self.loader.segments[index]
        item = self.segment_tree.topLevelItem(index)

        if item is not None:
            item.setText(0, str(index))
            item.setText(1, perms(seg.flags))
            item.setText(2, hex32(seg.offset))
            item.setText(3, hex32(seg.vaddr))
            item.setText(4, hex32(seg.filesz))
            item.setText(5, hex32(seg.memsz))
            item.setText(6, hex32(seg.align))
            item.setData(0, Qt.UserRole, index)
            self.segment_tree.setCurrentItem(item)

        # Actualizar todos los campos del PT_LOAD seleccionado sin depender
        # del objeto Segment anterior al refresco del ElfLoader.
        values = {
            "index": str(seg.index),
            "offset": hex32(seg.offset),
            "vaddr": hex32(seg.vaddr),
            "paddr": hex32(seg.paddr),
            "filesz": hex32(seg.filesz),
            "memsz": hex32(seg.memsz),
            "flags": f"0x{seg.flags:X}",
            "perms": perms(seg.flags),
            "align": hex32(seg.align),
            "file_end": hex32(seg.file_end),
            "mem_end": hex32(seg.mem_end),
            "bss": hex32(seg.bss_size),
        }
        for key, value in values.items():
            self.fields[key].setText(value)

        self.edit_vaddr.setText(hex32(seg.vaddr))
        self.edit_paddr.setText(hex32(seg.paddr))
        self.edit_memsz.setText(hex32(seg.memsz))
        self.edit_align.setText(hex32(seg.align))
        self.edit_read_check.setChecked(bool(seg.flags & 4))
        self.edit_write_check.setChecked(bool(seg.flags & 2))
        self.edit_exec_check.setChecked(bool(seg.flags & 1))

        self.lbl_size.setText(
            f"{len(self.elf_data):,} bytes ({hex32(len(self.elf_data))})"
        )
        self.lbl_segments.setText(str(len(self.loader.segments)))

    def clear_segment_info(self):
        for field in self.fields.values():
            field.setText("-")
        self.edit_vaddr.clear()
        self.edit_paddr.clear()
        self.edit_memsz.clear()
        self.edit_align.clear()
        self.edit_read_check.setChecked(False)
        self.edit_write_check.setChecked(False)
        self.edit_exec_check.setChecked(False)

    # ------------------------------------------------------------------
    # Edit / delete PT_LOAD
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_hex_int(text, field_name):
        text = text.strip()
        if not text:
            raise ValueError(f"{field_name} no puede estar vacío.")
        try:
            return int(text, 0)
        except ValueError as exc:
            raise ValueError(
                f"{field_name} inválido: {text!r}. Usa, por ejemplo, 0x08900000."
            ) from exc

    def _validate_segment_edit(self, seg, vaddr, paddr, memsz, flags, align):
        if not (0 <= vaddr <= 0xFFFFFFFF):
            raise ValueError("Virtual Address debe ser un valor ELF32.")
        if not (0 <= paddr <= 0xFFFFFFFF):
            raise ValueError("Physical Address debe ser un valor ELF32.")
        if not (0 <= memsz <= 0xFFFFFFFF):
            raise ValueError("Memory Size debe ser un valor ELF32.")
        if not (0 <= flags <= 7):
            raise ValueError("Los permisos deben estar entre 0 y 7.")
        if align not in (0, 1) and (align & (align - 1)) != 0:
            raise ValueError("Alignment debe ser 0, 1 o una potencia de 2.")
        if memsz < seg.filesz:
            raise ValueError(
                f"Memory Size ({hex32(memsz)}) no puede ser menor que "
                f"File Size ({hex32(seg.filesz)})."
            )
        if vaddr + memsz > 0x100000000:
            raise ValueError("El rango de memoria excede ELF32.")

        if align > 1 and (seg.offset % align) != (vaddr % align):
            raise ValueError(
                "El nuevo Virtual Address no cumple la regla ELF "
                "p_offset % p_align == p_vaddr % p_align.\n"
                f"Offset={hex32(seg.offset)}, Align={hex32(align)}, "
                f"VAddr={hex32(vaddr)}"
            )

        new_start, new_end = vaddr, vaddr + memsz
        for other in self.loader.segments:
            if other.index == seg.index:
                continue
            start, end = other.vaddr, other.vaddr + other.memsz
            if new_start < end and new_end > start:
                raise ValueError(
                    f"El PT_LOAD se solaparía con PT_LOAD #{other.index}:\n"
                    f"nuevo = {hex32(new_start)} - {hex32(new_end)}\n"
                    f"otro  = {hex32(start)} - {hex32(end)}"
                )

    def apply_segment_changes(self):
        seg = self.selected_segment()
        if seg is None:
            return

        try:
            vaddr = self._parse_hex_int(self.edit_vaddr.text(), "Virtual Address")
            paddr = self._parse_hex_int(self.edit_paddr.text(), "Physical Address")
            memsz = self._parse_hex_int(self.edit_memsz.text(), "Memory Size")
            align = self._parse_hex_int(self.edit_align.text(), "Alignment")

            flags = 0
            if self.edit_read_check.isChecked():
                flags |= 4
            if self.edit_write_check.isChecked():
                flags |= 2
            if self.edit_exec_check.isChecked():
                flags |= 1

            self._validate_segment_edit(seg, vaddr, paddr, memsz, flags, align)

            data = bytearray(self.elf_data)
            phoff = struct.unpack_from("<I", data, 28)[0]
            phentsize = struct.unpack_from("<H", data, 42)[0]
            phnum = struct.unpack_from("<H", data, 44)[0]

            if phentsize < 32 or seg.index >= phnum:
                raise ValueError("Program Header seleccionado no es válido.")

            off = phoff + seg.index * phentsize
            p_type = struct.unpack_from("<I", data, off)[0]
            if p_type != 1:
                raise ValueError("El header seleccionado ya no es PT_LOAD.")

            # Solo editamos los campos solicitados; offset/filesz permanecen intactos.
            struct.pack_into("<I", data, off + 8, vaddr)
            struct.pack_into("<I", data, off + 12, paddr)
            struct.pack_into("<I", data, off + 20, memsz)
            struct.pack_into("<I", data, off + 24, flags)
            struct.pack_into("<I", data, off + 28, align)

            rebuilt = ElfLoader(bytes(data))
            self.elf_data = data
            self.loader = rebuilt
            self.dirty = True
            self.populate_segments()
            self.log_message(
                f"PT_LOAD #{seg.index} actualizado: "
                f"VAddr={hex32(vaddr)}, PAddr={hex32(paddr)}, "
                f"MemSize={hex32(memsz)}, Permisos={perms(flags)}, "
                f"Align={hex32(align)}"
            )
            self.status.showMessage("PT_LOAD actualizado")

        except Exception as exc:
            QMessageBox.warning(self, "No se pudo modificar el PT_LOAD", str(exc))

    def delete_selected_segment(self):
        seg = self.selected_segment()
        if seg is None:
            return

        reply = QMessageBox.question(
            self,
            "Eliminar PT_LOAD",
            f"¿Eliminar PT_LOAD #{seg.index}?\n\n"
            "Se eliminará su Program Header. Los bytes que ocupaba en el "
            "archivo se conservarán para no cambiar los offsets de los "
            "demás segmentos.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            data = bytearray(self.elf_data)
            phoff = struct.unpack_from("<I", data, 28)[0]
            phentsize = struct.unpack_from("<H", data, 42)[0]
            phnum = struct.unpack_from("<H", data, 44)[0]

            if phentsize < 32 or seg.index >= phnum:
                raise ValueError("Program Header seleccionado no es válido.")

            # Compactar la tabla para que e_phnum siga describiendo exactamente
            # los headers válidos. Los datos del archivo no se mueven.
            for i in range(seg.index, phnum - 1):
                src = phoff + (i + 1) * phentsize
                dst = phoff + i * phentsize
                data[dst:dst + phentsize] = data[src:src + phentsize]

            last = phoff + (phnum - 1) * phentsize
            data[last:last + phentsize] = b"\x00" * phentsize
            struct.pack_into("<H", data, 44, phnum - 1)

            rebuilt = ElfLoader(bytes(data))
            self.elf_data = data
            self.loader = rebuilt
            self.dirty = True
            self.populate_segments()
            self.log_message(
                f"Eliminado PT_LOAD #{seg.index}. "
                "Los bytes del archivo fueron conservados."
            )
            self.status.showMessage("PT_LOAD eliminado")

        except Exception as exc:
            QMessageBox.warning(self, "No se pudo eliminar el PT_LOAD", str(exc))

    # ------------------------------------------------------------------
    # RAW file helpers
    # ------------------------------------------------------------------

    def _read_mips_raw_binary(self, filename):
        """Lee un .raw binario sin interpretar su contenido."""
        return Path(filename).read_bytes()

    # ------------------------------------------------------------------
    # Export MIPS RAW
    # ------------------------------------------------------------------

    def export_selected_segment(self):
        seg = self.selected_segment()

        if seg is None:
            return

        number = self.segment_tree.currentItem().text(0)

        default_name = (
            f"{self.elf_path.stem}_"
            f"pt_load_{number}_"
            f"{seg.vaddr:08X}_mips.txt"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar PT_LOAD como MIPS RAW",
            str(self.elf_path.parent / default_name),
            "MIPS RAW (*.txt *.raw) *.bin);;Todos los archivos (*)",
        )

        if not filename:
            return

        try:
            start = seg.offset
            end = seg.offset + seg.filesz
            raw = bytes(self.elf_data[start:end])

            if Path(filename).suffix.lower() in [".raw", ".bin"]:
                # .raw es binario: se escriben exactamente los bytes del PT_LOAD.
                Path(filename).write_bytes(raw)
                lines_count = len(raw) // 4
                trailing = len(raw) % 4
            else:
                # .txt conserva el formato textual existente.
                lines = []
                for offset in range(0, len(raw) - 3, 4):
                    instruction = int.from_bytes(
                        raw[offset:offset + 4],
                        byteorder="little",
                        signed=False,
                    )
                    address = seg.vaddr + offset
                    lines.append(
                        f"0x{address:08X}: 0x{instruction:08X}\n"
                    )
                Path(filename).write_text(
                    "".join(lines),
                    encoding="utf-8",
                )
                lines_count = len(lines)
                trailing = len(raw) % 4

            self.log_message(
                f"Exportado PT_LOAD #{number}: {filename}"
            )
            self.log_message(
                f"Dirección inicial: {hex32(seg.vaddr)}"
            )
            self.log_message(
                f"Instrucciones: {lines_count}"
            )
            if trailing:
                self.log_message(
                    f"Bytes finales sin palabra MIPS: {trailing}"
                )

            QMessageBox.information(
                self,
                "Exportación completada",
                (
                    "MIPS RAW exportado correctamente.\n\n"
                    f"Bytes exportados: {len(raw)}"
                    f"\nPalabras MIPS: {lines_count}"
                ),
            )

        except OSError as exc:
            QMessageBox.critical(
                self,
                "Error",
                str(exc),
            )

    # ------------------------------------------------------------------
    # Import MIPS RAW
    # ------------------------------------------------------------------

    def import_selected_segment(self, filename=None):
        seg = self.selected_segment()

        if seg is None:
            return

        number = self.segment_tree.currentItem().text(0)

        if filename is None:
            filename, _ = QFileDialog.getOpenFileName(
                self,
                "Importar MIPS RAW",
                "",
                "MIPS RAW (*.txt *.raw *.bin);;Todos los archivos (*)",
            )
            if not filename:
                return

        try:
            binary_raw = None

            if Path(filename).suffix.lower() == ".asm":
                exe_path = self._get_resources_path(Path("tools/armips.exe"))
                command = [str(exe_path), str(filename)]
                result = self._run_subprocess(command, cwd=str(Path(filename).parent))

                if result.returncode != 0:
                    error = result.stdout.strip()
                    raise ValueError(f"Ocurrio un error al convertir el .asm:\n{error}")

                name_file_bin = None

                with Path(filename).open("r", encoding="utf-8") as f:
                    for linea in f:
                        if linea.strip().startswith(".create"):
                            match = re.search(r'\.create\s+"([^"]+)"', linea)

                            if match:
                                name_file_bin = match.group(1)
                            break

                if not name_file_bin:
                    raise ValueError("No se encontro '.create' en el .asm")

                filename = Path(filename).parent / name_file_bin


            if Path(filename).suffix.lower() in [".raw", ".bin"]:
                binary_raw = self._read_mips_raw_binary(filename)

                if not binary_raw:
                    QMessageBox.warning(
                        self, "RAW vacío", "El archivo RAW está vacío."
                    )
                    return

                # El tamaño del .raw puede ser menor, igual o mayor que el
                # FileSize actual. En todos los casos se permite la importación.
                #
                # Si antes FileSize == MemorySize, ambos representan una región
                # completamente respaldada por el archivo, por lo que al cambiar
                # el tamaño del RAW también actualizamos MemorySize. Si eran
                # diferentes (por ejemplo, había BSS), conservamos MemorySize y
                # solo cambiamos FileSize.

                # Un .raw no contiene direcciones: sus bytes se copian desde
                # el inicio del PT_LOAD seleccionado.
                changes = []
                errors = []

            else:
                text = Path(filename).read_text(encoding="utf-8")

                changes = []
                errors = []

                for line_number, raw_line in enumerate(text.splitlines(), 1):
                    line = raw_line.strip()

                    if not line or line.startswith("#"):
                        continue

                    if ":" not in line:
                        errors.append(f"Línea {line_number}: falta ':'")
                        continue

                    address_text, instruction_text = line.split(":", 1)

                    try:
                        address = int(address_text.strip(), 0)
                        instruction = int(instruction_text.strip(), 0)
                    except ValueError:
                        errors.append(
                            f"Línea {line_number}: dirección/instrucción inválida"
                        )
                        continue

                    if not 0 <= instruction <= 0xFFFFFFFF:
                        errors.append(
                            f"Línea {line_number}: instrucción fuera de rango"
                        )
                        continue

                    if not (seg.vaddr <= address < seg.vaddr + seg.filesz):
                        errors.append(
                            f"Línea {line_number}: dirección {hex32(address)} "
                            f"fuera del PT_LOAD seleccionado"
                        )
                        continue

                    if (address - seg.vaddr) % 4 != 0:
                        errors.append(
                            f"Línea {line_number}: dirección {hex32(address)} "
                            "no está alineada a 4 bytes"
                        )
                        continue

                    if address + 4 > seg.vaddr + seg.filesz:
                        errors.append(
                            f"Línea {line_number}: instrucción fuera del FileSize"
                        )
                        continue

                    file_offset = seg.offset + (address - seg.vaddr)
                    changes.append((file_offset, instruction))

            if errors:
                preview = "\n".join(errors[:12])
                if len(errors) > 12:
                    preview += f"\n... y {len(errors) - 12} errores más."

                QMessageBox.warning(
                    self,
                    "RAW inválido",
                    preview + "\n\nNo se modificó el ELF.",
                )
                return

            # Para .raw binario, `changes` queda vacío a propósito: los bytes
            # se copian directamente al comienzo del PT_LOAD.
            if binary_raw is None and not changes:
                QMessageBox.warning(
                    self,
                    "RAW vacío",
                    "No se encontraron instrucciones válidas.",
                )
                return

            if binary_raw is not None:
                start = seg.offset
                old_filesz = seg.filesz
                old_memsz = seg.memsz
                new_filesz = len(binary_raw)

                # bytearray permite ampliar el ELF automáticamente si el RAW
                # nuevo supera el tamaño que tenía el PT_LOAD.
                end = start + new_filesz
                if end > len(self.elf_data):
                    self.elf_data.extend(b"\x00" * (end - len(self.elf_data)))
                self.elf_data[start:end] = binary_raw

                # Actualizar el Program Header del PT_LOAD seleccionado.
                # p_filesz siempre pasa a ser el tamaño real del RAW importado.
                # p_memsz solo se actualiza si antes era exactamente igual a
                # p_filesz; si existía BSS, se conserva tal cual estaba.
                data = self.elf_data
                phoff = struct.unpack_from("<I", data, 28)[0]
                phentsize = struct.unpack_from("<H", data, 42)[0]
                phnum = struct.unpack_from("<H", data, 44)[0]

                if phentsize < 32 or seg.index >= phnum:
                    raise ValueError("Program Header seleccionado no es válido.")

                phdr_off = phoff + seg.index * phentsize
                if phdr_off + 32 > len(data):
                    raise ValueError("Program Header seleccionado está truncado.")

                if struct.unpack_from("<I", data, phdr_off)[0] != 1:
                    raise ValueError("El header seleccionado ya no es PT_LOAD.")

                struct.pack_into("<I", data, phdr_off + 16, new_filesz)
                if old_filesz == old_memsz:
                    struct.pack_into("<I", data, phdr_off + 20, new_filesz)

                changed_count = len(binary_raw)
            else:
                for file_offset, instruction in changes:
                    self.elf_data[file_offset:file_offset + 4] = instruction.to_bytes(
                        4,
                        byteorder="little",
                        signed=False,
                    )
                changed_count = len(changes)

            self.loader = ElfLoader(bytes(self.elf_data))
            self.dirty = True

            # El PT_LOAD ya cambió en memoria. Refrescar inmediatamente la
            # tabla y los campos del panel derecho para que FileSize,
            # MemorySize, File End, Memory End y BSS muestren los nuevos
            # valores sin tener que volver a seleccionar el segmento.
            self.refresh_segment_ui(seg.index)

            self.log_message(
                f"Importado MIPS RAW en PT_LOAD #{number}: {filename}"
            )
            self.log_message(
                f"Bytes modificados: {changed_count}"
            )

            self.status.showMessage(
                f"PT_LOAD #{number} modificado"
            )

            self._update_ui()

        except (OSError, UnicodeDecodeError) as exc:
            QMessageBox.critical(
                self,
                "Error al importar RAW",
                str(exc),
            )
        except ValueError as exc:
            QMessageBox.critical(
                self,
                "ELF inválido",
                str(exc),
            )

    # ------------------------------------------------------------------
    # MIPS RAW <-> MIPS Code
    # ------------------------------------------------------------------

    def convert_raw_to_code(self, filename=None):
        """Convierte MIPS RAW a MIPS Code e inserta referencias a imports PSP."""
        seg = self.selected_segment()
        if seg is None:
            return

        if filename is None:
            filename, _ = QFileDialog.getOpenFileName(
                self,
                "Abrir MIPS RAW",
                "",
                "MIPS RAW (*.txt *.raw);;Todos los archivos (*)",
            )
            if not filename:
                return

        default_name = f"{Path(filename).stem}_code.txt"
        output, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar MIPS Code",
            str(Path(filename).parent / default_name),
            "MIPS Code (*.txt);;Todos los archivos (*)",
        )
        if not output:
            return

        try:
            text = Path(filename).read_text(encoding="utf-8")
            raw_entries = []
            errors = []

            for line_number, raw_line in enumerate(text.splitlines(), 1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                if ":" not in line:
                    errors.append(f"Línea {line_number}: falta ':'")
                    continue

                address_text, instruction_text = line.split(":", 1)
                try:
                    address = int(address_text.strip(), 0)
                    raw_instruction = int(instruction_text.strip(), 0)
                except ValueError:
                    errors.append(
                        f"Línea {line_number}: dirección/instrucción inválida"
                    )
                    continue

                if not 0 <= raw_instruction <= 0xFFFFFFFF:
                    errors.append(
                        f"Línea {line_number}: instrucción fuera de rango"
                    )
                    continue

                if not (seg.vaddr <= address < seg.vaddr + seg.filesz):
                    errors.append(
                        f"Línea {line_number}: dirección {hex32(address)} fuera del PT_LOAD"
                    )
                    continue

                if (address - seg.vaddr) % 4 != 0:
                    errors.append(
                        f"Línea {line_number}: dirección {hex32(address)} no está alineada"
                    )
                    continue

                raw_entries.append((address, raw_instruction))

            if errors:
                preview = "\n".join(errors[:12])
                if len(errors) > 12:
                    preview += f"\n... y {len(errors) - 12} errores más."
                QMessageBox.warning(
                    self,
                    "RAW inválido",
                    preview + "\n\nNo se creó el MIPS Code.",
                )
                return

            # stub_address -> (library, nid). El stub apunta a la primera
            # instrucción del stub; la referencia de import se escribe en
            # la siguiente instrucción, que en un stub PSP normalmente es nop.
            imports_by_stub = {
                imp.stub_address: imp
                for imp in self.imports
                if seg.vaddr <= imp.stub_address < seg.vaddr + seg.filesz
            }

            entries_by_address = dict(raw_entries)
            lines_out = []
            converted = 0
            references = 0

            for address, raw_instruction in raw_entries:
                converted_text = disassemble_mips(
                    raw_instruction,
                    address=address,
                )
                lines_out.append(
                    f"0x{address:08X}: {converted_text}\n"
                )
                converted += 1

                imp = imports_by_stub.get(address - 4)
                if imp is not None:
                    # Solo escribimos la referencia si el siguiente RAW
                    # realmente existe. Su contenido original se reemplaza
                    # visualmente por la referencia.
                    next_address = address
                    if next_address in entries_by_address:
                        lines_out[-1] = (
                            f"0x{address:08X}: "
                            f"{imp.library}: NID=0x{imp.nid:08X}\n"
                        )
                        references += 1

            # El algoritmo anterior necesita conservar la instrucción del stub
            # y sustituir la línea siguiente. Reconstruimos la salida para que
            # el formato sea exactamente:
            #   stub: jr $ra
            #   stub+4: Library: NID=...
            lines_out = []
            reference_addresses = {
                imp.stub_address + 4: imp
                for imp in self.imports
                if seg.vaddr <= imp.stub_address + 4 < seg.vaddr + seg.filesz
            }

            for address, raw_instruction in raw_entries:
                imp = reference_addresses.get(address)
                if imp is not None:
                    lines_out.append(
                        f"0x{address:08X}: "
                        f"{imp.library}: NID=0x{imp.nid:08X}\n"
                    )
                    references += 1
                    continue

                converted_text = disassemble_mips(
                    raw_instruction,
                    address=address,
                )
                lines_out.append(
                    f"0x{address:08X}: {converted_text}\n"
                )

            Path(output).write_text("".join(lines_out), encoding="utf-8")
            self.log_message(f"MIPS RAW → MIPS Code: {output}")
            self.log_message(f"Instrucciones convertidas: {converted}")
            self.log_message(f"Referencias a librerías: {references}")

            QMessageBox.information(
                self,
                "Conversión completada",
                (
                    "MIPS Code creado correctamente.\n\n"
                    f"Instrucciones: {converted}\n"
                    f"Referencias a librerías: {references}"
                ),
            )

        except (OSError, UnicodeDecodeError) as exc:
            QMessageBox.critical(self, "Error al convertir RAW", str(exc))

    def convert_code_to_raw(self, filename=None):
        """Convierte MIPS Code a RAW; referencias de imports se convierten en NOP."""
        seg = self.selected_segment()
        if seg is None:
            return

        if filename is None:
            filename, _ = QFileDialog.getOpenFileName(
                self,
                "Abrir MIPS Code",
                "",
                "MIPS Code (*.txt);;Todos los archivos (*)",
            )
            if not filename:
                return

        default_name = f"{Path(filename).stem}_raw.txt"
        output, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar MIPS RAW",
            str(Path(filename).parent / default_name),
            "MIPS RAW (*.txt *.raw);;Todos los archivos (*)",
        )
        if not output:
            return

        try:
            text = Path(filename).read_text(encoding="utf-8")
            lines_out = []
            errors = []
            converted = 0
            references = 0

            # Formato generado por RAW -> Code:
            # 0x08804000: jr $ra
            # 0x08804004: SysMemUserForUser: NID=0x1B4217BC
            import_reference_re = re.compile(
                r"^[^:]+:\s*NID=0x[0-9A-Fa-f]{1,8}\s*$"
            )

            for line_number, raw_line in enumerate(text.splitlines(), 1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                if ":" not in line:
                    errors.append(f"Línea {line_number}: falta ':'")
                    continue

                address_text, code_text = line.split(":", 1)
                try:
                    address = int(address_text.strip(), 0)
                except ValueError:
                    errors.append(f"Línea {line_number}: dirección inválida")
                    continue

                code_text = code_text.strip()
                if not code_text:
                    errors.append(f"Línea {line_number}: instrucción vacía")
                    continue

                if not (seg.vaddr <= address < seg.vaddr + seg.filesz):
                    errors.append(
                        f"Línea {line_number}: dirección {hex32(address)} fuera del PT_LOAD"
                    )
                    continue

                if (address - seg.vaddr) % 4 != 0:
                    errors.append(
                        f"Línea {line_number}: dirección {hex32(address)} no está alineada"
                    )
                    continue

                if address + 4 > seg.vaddr + seg.filesz:
                    errors.append(
                        f"Línea {line_number}: instrucción fuera del FileSize"
                    )
                    continue

                # Una referencia de import no es una instrucción MIPS real.
                # Al reconstruir RAW ocupa exactamente 4 bytes y equivale a NOP.
                if import_reference_re.match(code_text):
                    instruction = 0
                    references += 1
                else:
                    try:
                        instruction = assemble_mips(
                            code_text,
                            address=address,
                        )
                    except ValueError as exc:
                        errors.append(f"Línea {line_number}: {exc}")
                        continue

                lines_out.append(
                    f"0x{address:08X}: 0x{instruction:08X}\n"
                )
                converted += 1

            if errors:
                preview = "\n".join(errors[:12])
                if len(errors) > 12:
                    preview += f"\n... y {len(errors) - 12} errores más."
                QMessageBox.warning(
                    self,
                    "MIPS Code inválido",
                    preview + "\n\nNo se creó el MIPS RAW.",
                )
                return

            Path(output).write_text("".join(lines_out), encoding="utf-8")
            self.log_message(f"MIPS Code → MIPS RAW: {output}")
            self.log_message(f"Instrucciones convertidas: {converted}")
            self.log_message(f"Referencias convertidas a NOP: {references}")

            QMessageBox.information(
                self,
                "Conversión completada",
                (
                    "MIPS RAW creado correctamente.\n\n"
                    f"Instrucciones: {converted}\n"
                    f"Referencias → NOP: {references}"
                ),
            )

        except (OSError, UnicodeDecodeError) as exc:
            QMessageBox.critical(self, "Error al convertir MIPS Code", str(exc))

    # ------------------------------------------------------------------
    # Add PT_LOAD from MIPS RAW
    # ------------------------------------------------------------------

    @staticmethod
    def _align_up(value, alignment):
        if alignment <= 1:
            return value
        return (value + alignment - 1) & ~(alignment - 1)

    def add_pt_load_from_raw(self, filename=None):
        """
        Añade un PT_LOAD nuevo sin modificar los PT_LOAD existentes.

        El MIPS RAW debe tener el formato:
            0x08900000: 0x3C1C0000
            0x08900004: 0x279C1234
            ...

        La primera dirección es el Virtual Address del nuevo PT_LOAD.
        El contenido de cada línea se almacena como una palabra MIPS
        little-endian consecutiva.
        """
        if self.loader is None or self.elf_data is None:
            return

        if filename is None:
            filename, _ = QFileDialog.getOpenFileName(
                self,
                "Añadir PT_LOAD desde MIPS RAW",
                "",
                "MIPS RAW (*.txt *.raw *.bin *.asm);;Todos los archivos (*)",
            )
            if not filename:
                return

        try:
            if Path(filename).suffix.lower() == ".asm":
                exe_path = self._get_resources_path(Path("tools/armips.exe"))
                command = [str(exe_path), str(filename)]
                result = self._run_subprocess(command, cwd=str(Path(filename).parent))

                if result.returncode != 0:
                    error = result.stdout.strip()
                    raise ValueError(f"Ocurrio un error al convertir el .asm:\n{error}")

                name_file_bin = None

                with Path(filename).open("r", encoding="utf-8") as f:
                    for linea in f:
                        if linea.strip().startswith(".create"):
                            match = re.search(r'\.create\s+"([^"]+)"', linea)

                            if match:
                                name_file_bin = match.group(1)
                            break

                if not name_file_bin:
                    raise ValueError(f"No se encontro '.create' en \n{filename}")

                filename = Path(filename).parent / name_file_bin

            # .raw es binario: no contiene direcciones, por lo que el usuario
            # debe indicar la dirección de memoria donde se cargará el código.
            is_binary_raw = Path(filename).suffix.lower() in [".raw", ".bin"]

            if is_binary_raw:
                raw_data = Path(filename).read_bytes()

                if not raw_data:
                    QMessageBox.warning(
                        self,
                        "RAW vacío",
                        "El archivo RAW está vacío.",
                    )
                    return

                address_text, ok = QInputDialog.getText(
                    self,
                    "Dirección de memoria",
                    "¿En qué dirección de memoria se debe cargar el código?\n\n"
                    "Puedes usar hexadecimal (ej. 0x08900000) o decimal:",
                    text="0x08900000",
                )

                if not ok:
                    return

                try:
                    vaddr = self._parse_hex_int(
                        address_text,
                        "Dirección de memoria",
                    )
                except ValueError as exc:
                    QMessageBox.warning(
                        self,
                        "Dirección inválida",
                        str(exc),
                    )
                    return

                if not 0 <= vaddr <= 0xFFFFFFFF:
                    raise ValueError(
                        "La dirección de memoria debe ser un valor ELF32."
                    )

                if vaddr & 3:
                    raise ValueError(
                        f"La dirección de memoria {hex32(vaddr)} "
                        "no está alineada a 4 bytes."
                    )

                filesz = len(raw_data)
                memsz = filesz

            else:
                text = Path(filename).read_text(encoding="utf-8")
                entries = []
                errors = []

                for line_number, raw_line in enumerate(text.splitlines(), 1):
                    line = raw_line.strip()

                    if not line or line.startswith("#"):
                        continue

                    if ":" not in line:
                        errors.append(
                                f"Línea {line_number}: falta ':'"
                        )
                        continue

                    address_text, instruction_text = line.split(":", 1)

                    try:
                        address = int(address_text.strip(), 0)
                    except ValueError:
                        errors.append(
                                f"Línea {line_number}: dirección inválida"
                        )
                        continue

                    try:
                        instruction = int(
                                instruction_text.strip(),
                                0,
                        )
                    except ValueError:
                        errors.append(
                                f"Línea {line_number}: instrucción inválida"
                        )
                        continue

                    if not 0 <= address <= 0xFFFFFFFF:
                        errors.append(
                                f"Línea {line_number}: dirección fuera de rango"
                        )
                        continue

                    if not 0 <= instruction <= 0xFFFFFFFF:
                        errors.append(
                                f"Línea {line_number}: instrucción fuera de rango"
                        )
                        continue

                    if address & 3:
                        errors.append(
                                f"Línea {line_number}: dirección "
                                f"{hex32(address)} no está alineada a 4 bytes"
                        )
                        continue

                    entries.append((address, instruction))

                if errors:
                    preview = "\n".join(errors[:12])
                    if len(errors) > 12:
                        preview += (
                                f"\n... y {len(errors) - 12} errores más."
                        )

                    QMessageBox.warning(
                        self,
                        "MIPS RAW inválido",
                        preview,
                    )
                    return

                if not entries:
                    QMessageBox.warning(
                        self,
                        "MIPS RAW vacío",
                        "No se encontraron instrucciones.",
                    )
                    return

                # La primera dirección define el VAddr del nuevo PT_LOAD.
                vaddr = entries[0][0]

                # Un PT_LOAD representa una región continua del archivo.
                # Por eso exigimos direcciones consecutivas.
                for i in range(1, len(entries)):
                    expected = entries[i - 1][0] + 4

                    if entries[i][0] != expected:
                        raise ValueError(
                                "El MIPS RAW no es continuo:\n"
                                f"se esperaba {hex32(expected)}, "
                                f"pero se encontró {hex32(entries[i][0])}."
                        )

                raw_data = b"".join(
                    instruction.to_bytes(
                        4,
                        byteorder="little",
                        signed=False,
                    )
                    for _, instruction in entries
                )

            filesz = len(raw_data)
            memsz = filesz

            # Permisos elegidos en la interfaz.
            # ELF: PF_X=1, PF_W=2, PF_R=4.
            flags = 0
            if self.add_read_check.isChecked():
                flags |= 4
            if self.add_write_check.isChecked():
                flags |= 2
            if self.add_exec_check.isChecked():
                flags |= 1

            if flags == 0:
                raise ValueError(
                    "Debes seleccionar al menos un permiso (R, W o X)."
                )

            align = 0x1000

            # No permitir que el nuevo PT_LOAD se superponga a uno existente.
            new_mem_end = vaddr + memsz

            if new_mem_end > 0x100000000:
                raise ValueError(
                    "El nuevo PT_LOAD excede el espacio de direcciones ELF32."
                )

            for seg in self.loader.segments:
                seg_start = seg.vaddr
                seg_end = seg.vaddr + seg.memsz

                if vaddr < seg_end and new_mem_end > seg_start:
                    raise ValueError(
                        "El nuevo PT_LOAD se superpone con "
                        f"PT_LOAD #{seg.index}:\n"
                        f"nuevo = {hex32(vaddr)} - {hex32(new_mem_end)}\n"
                        f"existente = {hex32(seg_start)} - "
                        f"{hex32(seg_end)}"
                    )

            # ----------------------------------------------------------
            # Añadimos el nuevo Program Header en la tabla ORIGINAL.
            #
            # Es importante para PSP: conservamos e_phoff y todos los
            # offsets existentes. Solamente ocupamos los 32 bytes que
            # siguen a la tabla original. Si no hay espacio suficiente
            # antes del primer segmento, no modificamos el ELF.
            # ----------------------------------------------------------

            data = bytearray(self.elf_data)

            old_phoff = struct.unpack_from("<I", data, 28)[0]
            old_phentsize = struct.unpack_from("<H", data, 42)[0]
            old_phnum = struct.unpack_from("<H", data, 44)[0]

            if old_phentsize != 32:
                raise ValueError(
                    "Para añadir PT_LOAD se requiere e_phentsize = 32."
                )

            old_table_end = old_phoff + old_phentsize * old_phnum

            if old_table_end > len(data):
                raise ValueError(
                    "La Program Header Table está fuera del ELF."
                )

            new_phdr_offset = old_table_end
            new_table_end = new_phdr_offset + 32

            # Buscar el primer byte de archivo utilizado por un Program
            # Header. No debemos sobrescribir ningún dato existente.
            first_file_offset = len(data)

            for i in range(old_phnum):
                phoff = old_phoff + i * old_phentsize
                (
                    p_type,
                    p_offset,
                    p_vaddr,
                    p_paddr,
                    p_filesz,
                    p_memsz,
                    p_flags,
                    p_align,
                ) = struct.unpack_from("<IIIIIIII", data, phoff)

                if p_type != 0 and p_filesz:
                    if p_offset < first_file_offset:
                        first_file_offset = p_offset

            # Hay que tener 32 bytes libres entre la tabla actual y el
            # primer dato del ELF. En el EBOOT.OLD probado existe ese
            # espacio, por lo que e_phoff permanece exactamente igual.
            if new_table_end > first_file_offset:
                raise ValueError(
                    "No hay espacio libre para otro Program Header sin "
                    "mover los datos existentes del ELF.\n\n"
                    f"Fin de PHDR actual: {hex32(old_table_end)}\n"
                    f"Primer dato ELF:      {hex32(first_file_offset)}\n"
                    f"Se necesitan:         0x20 bytes\n\n"
                    "No se modificó el ELF."
                )

            # p_offset % p_align debe coincidir con p_vaddr % p_align.
            raw_base = self._align_up(len(data), align)
            vaddr_mod = vaddr % align
            raw_offset = raw_base + (
                (vaddr_mod - raw_base % align) % align
            )

            if raw_offset > len(data):
                data.extend(b"\x00" * (raw_offset - len(data)))

            # Nuevo Program Header ELF32.
            new_header = struct.pack(
                "<IIIIIIII",
                1,              # p_type = PT_LOAD
                raw_offset,     # p_offset
                vaddr,          # p_vaddr
                vaddr,          # p_paddr
                filesz,         # p_filesz
                memsz,          # p_memsz
                flags,          # p_flags
                align,          # p_align
            )

            # Escribimos solamente el nuevo PHDR en la tabla original.
            data[new_phdr_offset:new_table_end] = new_header

            new_phnum = old_phnum + 1

            # e_phoff NO cambia. e_phentsize tampoco cambia.
            struct.pack_into("<H", data, 44, new_phnum)

            # Escribimos el MIPS RAW al final del ELF.
            data[raw_offset:raw_offset + filesz] = raw_data

            # ----------------------------------------------------------
            # Validación
            # ----------------------------------------------------------

            rebuilt_loader = ElfLoader(bytes(data))

            new_segment = None

            for segment in rebuilt_loader.segments:
                if (
                    segment.vaddr == vaddr
                    and
                    segment.offset == raw_offset
                    and
                    segment.filesz == filesz
                ):
                    new_segment = segment
                    break

            if new_segment is None:
                raise ValueError(
                    "El PT_LOAD nuevo no pudo ser validado."
                )

            # Sustituimos el ELF actual solamente después de validar.
            self.elf_data = data
            self.loader = rebuilt_loader
            self.dirty = True

            # Volver a calcular imports/module sobre el ELF nuevo.
            self.module_info = None
            self.imports = []

            try:
                parsed_elf = Elf32(bytes(data))
                self.module_info = find_module_info(
                    parsed_elf
                )

                if self.module_info:
                    self.imports = scan_imports(
                        parsed_elf,
                        self.module_info,
                    )
            except (ValueError, RuntimeError):
                pass

            self.populate_elf_info()
            self.populate_segments()

            # Seleccionar el segmento nuevo.
            for row in range(self.segment_tree.topLevelItemCount()):
                item = self.segment_tree.topLevelItem(row)

                if item.data(0, Qt.UserRole) == (
                    len(self.loader.segments) - 1
                ):
                    self.segment_tree.setCurrentItem(item)
                    break

            self.log_message(
                "Nuevo PT_LOAD añadido."
            )
            self.log_message(
                f"VAddr: {hex32(vaddr)}"
            )
            self.log_message(
                f"Offset ELF: {hex32(raw_offset)}"
            )
            self.log_message(
                f"FileSize: {hex32(filesz)}"
            )
            self.log_message(
                f"MemSize: {hex32(memsz)}"
            )
            self.log_message(
                f"Flags: {perms(flags)}"
            )
            self.log_message(
                f"Alignment: {hex32(align)}"
            )
            self.log_message(
                f"Program Headers: {new_phnum}"
            )
            self.log_message(
                f"RAW importado desde: {filename}"
            )

            self.status.showMessage(
                "Nuevo PT_LOAD añadido"
            )

            QMessageBox.information(
                self,
                "PT_LOAD añadido",
                (
                    "Se añadió correctamente un nuevo PT_LOAD.\n\n"
                    f"Virtual Address: {hex32(vaddr)}\n"
                    f"File Size: {hex32(filesz)}\n"
                    f"File Offset: {hex32(raw_offset)}\n"
                    f"Flags: {perms(flags)}\n"
                    f"Alignment: {hex32(align)}"
                ),
            )

            self._update_ui()

        except (
            OSError,
            UnicodeDecodeError,
            ValueError,
            struct.error,
        ) as exc:
            QMessageBox.critical(
                self,
                "Error al añadir PT_LOAD",
                str(exc),
            )

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_elf(self):
        if self.loader is None:
            return

        if self.elf_path is None:
            return self.save_elf_as()

        self.write_elf(self.elf_path)

    def save_elf_as(self):
        if self.loader is None:
            return

        default = (
            self.elf_path.name
            if self.elf_path
            else "recomp.ELF"
        )

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar ELF",
            str(
                self.elf_path.parent / default
                if self.elf_path
                else Path.cwd() / default
            ),
            "ELF (*.elf *.ELF);;Todos los archivos (*)",
        )

        if not filename:
            return

        self.write_elf(Path(filename))

    def write_elf(self, path: Path):
        try:
            path.write_bytes(bytes(self.elf_data))

            self.elf_path = path
            self.dirty = False

            self.path_label.setText(
                str(self.elf_path)
            )

            self.status.showMessage(
                f"Guardado: {path.name}"
            )

            self.log_message(
                f"ELF guardado: {path}"
            )

            self._update_ui()

        except OSError as exc:
            QMessageBox.critical(
                self,
                "Error al guardar ELF",
                str(exc),
            )

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def log_message(self, text):
        self.log.append(text)

    def closeEvent(self, event):
        if not self.dirty:
            event.accept()
            return

        answer = QMessageBox.question(
            self,
            "Cambios sin guardar",
            "El ELF tiene cambios sin guardar. ¿Guardar?",
            QMessageBox.Save
            | QMessageBox.Discard
            | QMessageBox.Cancel,
            QMessageBox.Save,
        )

        if answer == QMessageBox.Save:
            self.save_elf()

            if self.dirty:
                event.ignore()
            else:
                event.accept()

        elif answer == QMessageBox.Discard:
            event.accept()
        else:
            event.ignore()


# def main():
#     app = QApplication(sys.argv)
#
#     app.setApplicationName("PSPRecomp ELF Editor")
#
#     window = ElfEditor()
#     window.show()
#
#     return app.exec_()
#
#
# if __name__ == "__main__":
#     raise SystemExit(main())
