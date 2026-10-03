import struct
import sys
import os
import json
import re
import shutil
import tempfile
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal, QEvent, QPoint, QTimer
from PyQt5.QtGui import QIcon, QCursor, QColor, QBrush
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QListWidget, QListWidgetItem,
    QAbstractItemView,
    QSplitter, QPushButton, QLabel, QLineEdit, QMenu, QAction,
    QFileDialog, QMessageBox, QInputDialog, QHeaderView,
    QDialog, QFormLayout, QDialogButtonBox, QCheckBox, QTextEdit, QSpinBox
)

from app_md.logic_extr.vag_header import VAGHeader
from app_md.logic_iso.data_convert import DataConvert
from app_md.wav.wav_header import AT3HeaderBuilder
from app_md.logic_iso.data_file_manager import DataFileManager
from app_md.logic_explorer_ram.packfile_explorer import PackFileBuffer

# ============================================================
# MODELO DE DATOS VIRTUAL
# ============================================================

def make_ram_file_name(num_file):
    """
    Nombre interno para un archivo RAM:
        num_decimal-num_hex.unk

    Ejemplos:
        1  -> 1-1.unk
        15 -> 15-F.unk
        26 -> 26-1A.unk
    """
    number = int(num_file)
    return f"{number}-{number:X}.unk"


def natural_sort_key(text):
    """
    Clave de ordenamiento tipo Explorador de Windows:
    los grupos numericos se comparan como numeros y no como texto.

    Ejemplo:
        1-1.unk
        2-2.unk
        3-3.unk
        15-F.unk
    """
    parts = re.split(r"(\d+)", str(text))
    key = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.casefold()))
    return key


def normalize_ram_file_entry(entry):
    """
    Normaliza una entrada de la lista:
        (offset, length, num_file)
    """
    if not isinstance(entry, (tuple, list)) or len(entry) != 3:
        raise ValueError(
            "Cada archivo RAM debe tener el formato "
            "(offset, length, num_file)."
        )

    offset, length, num_file = entry
    return int(offset), int(length), int(num_file)


def normalize_packfile_list_folder(folder_path):
    """
    Normaliza una ruta de carpeta del LISTA_PACKFILE.

    El formato observado usa '\\' como separador, por ejemplo:
        Main\Data
        Menus\Free_Battle
        General_Audios\SFX
    """
    if folder_path is None:
        return []

    folder_path = str(folder_path).strip()
    folder_path = folder_path.rstrip(":").strip()

    return [
        part.strip()
        for part in re.split(r"[\\/]+", folder_path)
        if part.strip()
    ]


def parse_packfile_internal_name(internal_name):
    """
    Extrae el número decimal de nombres como:
        1_1.unk
        15_F.unk
        13934_366E.unk

    Devuelve None si el nombre no cumple ese patrón.
    """
    match = re.match(
        r"^(\d+)_([0-9A-Fa-f]+)\.unk$",
        str(internal_name).strip(),
    )

    if match is None:
        return None

    return int(match.group(1))


class ExplorerItem:
    def __init__(
        self,
        name,
        item_type="folder",
        path=None,
        parent=None,
        internal_name=None,
        offset=None,
        length=None,
        num_file=None,
    ):
        self.name = name
        self.item_type = item_type
        self.path = Path(path) if path else None
        self.parent = parent

        # Referencia permanente. Renombrar self.name NO la modifica.
        self.internal_name = (
            internal_name if internal_name is not None else name
        )

        # Metadatos del archivo dentro de la RAM.
        self.offset = offset
        self.length = length
        self.num_file = num_file

        self.children = []
        self._child_name_set = set()

    def is_folder(self):
        return self.item_type == "folder"

    def add_child(self, item):
        item.parent = self
        self.children.append(item)
        self._child_name_set.add(item.name.casefold())

    def remove_child(self, item):
        if item in self.children:
            self.children.remove(item)
            self._child_name_set.discard(item.name.casefold())

    def row(self):
        if self.parent is None:
            return 0
        try:
            return self.parent.children.index(self)
        except ValueError:
            return 0


# ============================================================
# TABLA CON DRAG & DROP CONTROLADO
# ============================================================

class ExplorerTableWidget(QTableWidget):
    """
    Arrastre manual controlado con indicador visual.

    El drag se inicia sobre una fila de la tabla y se captura mediante
    eventFilter para poder salir de la tabla sin perder el release.
    Mientras se arrastra se muestra una pequeña "etiqueta flotante"
    con el icono y nombre del elemento siguiendo al cursor.
    """

    itemDropped = pyqtSignal(object, int)
    favoriteDropped = pyqtSignal(object, object)

    def __init__(self, parent=None):
        super().__init__(0, 3, parent)

        self._pressed_row = -1
        self._press_pos = None

        # IDs de la selección existente antes del click.
        self._selection_before_press_ids = []
        self._preserve_selection_on_press = False

        self._dragging = False
        self._drag_item_ids = []
        self._drag_item_names = []

        self._drop_row = -1
        self._favorite_target = None

        # Fila/item actualmente resaltados como destino del drop.
        self._highlighted_table_row = -1
        self._highlighted_favorite_item = None

        self._favorite_list = None
        self._explorer_owner = None
        self._event_filter_installed = False

        # Vista flotante que acompaña al cursor durante el drag.
        self._drag_preview = None
        self._drag_preview_icon = None

    def setFavoriteList(self, favorite_list):
        self._favorite_list = favorite_list

    def setExplorerOwner(self, owner):
        self._explorer_owner = owner

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            index = self.indexAt(event.pos())

            # Guardar la selección ANTES de que Qt pueda modificarla.
            self._selection_before_press_ids = []

            for selected_index in self.selectionModel().selectedRows():
                selected_item = self.item(
                    selected_index.row(),
                    0
                )

                if selected_item is not None:
                    item_id = selected_item.data(Qt.UserRole)

                    if item_id is not None:
                        self._selection_before_press_ids.append(
                            item_id
                        )

            self._preserve_selection_on_press = False

            # Click en espacio vacío: deseleccionar _todo.
            if not index.isValid():
                self.clearSelection()
                self.setCurrentCell(-1, -1)

            self._pressed_row = (
                index.row()
                if index.isValid()
                else -1
            )

            self._press_pos = event.pos()
            self._dragging = False
            self._drag_item_ids = []
            self._drag_item_names = []
            self._drop_row = -1
            self._favorite_target = None

            if index.isValid():
                clicked_row = index.row()

                selected_rows = {
                    selected_index.row()
                    for selected_index
                    in self.selectionModel().selectedRows()
                }

                no_modifier = not (
                    event.modifiers()
                    & (
                        Qt.ControlModifier |
                        Qt.ShiftModifier
                    )
                )

                # Ya estaba seleccionado y no se está usando Ctrl/Shift:
                # NO permitir que Qt reduzca la selección a una sola fila.
                if clicked_row in selected_rows and no_modifier:
                    self._preserve_selection_on_press = True
                    return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return

        if self._pressed_row < 0 or self._press_pos is None:
            super().mouseMoveEvent(event)
            return

        if not self._dragging:
            distance = (
                event.pos() - self._press_pos
            ).manhattanLength()

            if distance < QApplication.startDragDistance():
                super().mouseMoveEvent(event)
                return

            source_item = self.item(
                self._pressed_row,
                0
            )

            if source_item is None:
                return

            # Si el usuario hizo click sobre un elemento que ya estaba
            # seleccionado, usar la selección que existía ANTES del click.
            if self._preserve_selection_on_press:
                selected_ids = list(
                    self._selection_before_press_ids
                )
            else:
                selected_ids = []

                for index in self.selectionModel().selectedRows():
                    table_item = self.item(
                        index.row(),
                        0
                    )

                    if table_item is not None:
                        item_id = table_item.data(Qt.UserRole)

                        if item_id is not None:
                            selected_ids.append(item_id)

                # Por seguridad, incluir al menos el elemento pulsado.
                source_id_pressed = self.item(
                    self._pressed_row,
                    0
                ).data(Qt.UserRole)

                if (
                    source_id_pressed is not None
                    and source_id_pressed not in selected_ids
                ):
                    selected_ids = [source_id_pressed]

            drag_ids = []
            drag_names = []
            drag_items = []

            owner = self._explorer_owner
            row_map = getattr(owner, "_row_by_id", None) if owner is not None else None

            for item_id in selected_ids:
                row = row_map.get(item_id, -1) if row_map is not None else -1

                if row < 0:
                    # Compatibilidad si la tabla todavía no fue indexada.
                    for candidate_row in range(self.rowCount()):
                        candidate = self.item(candidate_row, 0)
                        if (
                            candidate is not None
                            and candidate.data(Qt.UserRole) == item_id
                        ):
                            row = candidate_row
                            break

                if row < 0:
                    continue
                table_item = self.item(row, 0)
                if table_item is None:
                    continue

                drag_ids.append(item_id)
                drag_names.append(table_item.text())
                drag_items.append(table_item)

            if not drag_ids:
                return

            self._drag_item_ids = drag_ids
            self._drag_item_names = drag_names
            self._dragging = True

            # Cursor de arrastre mientras se mantiene el botón.
            QApplication.setOverrideCursor(
                Qt.ClosedHandCursor
            )

            self._create_drag_preview(
                drag_items,
                event.globalPos()
            )

            if not self._event_filter_installed:
                QApplication.instance().installEventFilter(self)
                self._event_filter_installed = True

        self._update_drop_target(event.globalPos())
        self._move_drag_preview(event.globalPos())

    def _create_drag_preview(self, source_items, global_pos):
        """
        Muestra una representación visual del arrastre.
        Para varios elementos muestra el número de elementos seleccionados.
        """
        self._destroy_drag_preview()

        self._drag_preview = QLabel()
        self._drag_preview.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True
        )
        self._drag_preview.setWindowFlags(
            Qt.Tool |
            Qt.FramelessWindowHint |
            Qt.NoDropShadowWindowHint
        )
        self._drag_preview.setStyleSheet(
            """
            QLabel {
                background: rgba(245, 245, 245, 230);
                border: 1px solid #8a8a8a;
                border-radius: 4px;
                color: #202020;
                padding: 4px 8px 4px 4px;
            }
            """
        )

        count = len(source_items)

        if count == 1:
            icon = source_items[0].icon()

            if not icon.isNull():
                self._drag_preview.setPixmap(
                    icon.pixmap(24, 24)
                )

            self._drag_preview.setText(
                ("   " if not icon.isNull() else "") +
                source_items[0].text()
            )

        else:
            # Usar el icono del primer elemento y mostrar cantidad.
            icon = source_items[0].icon()

            if not icon.isNull():
                self._drag_preview.setPixmap(
                    icon.pixmap(24, 24)
                )

            self._drag_preview.setText(
                ("   " if not icon.isNull() else "") +
                f"{count} elementos"
            )

            self._drag_preview.setToolTip(
                "\n".join(self._drag_item_names)
            )

        self._drag_preview.adjustSize()

        max_width = 320

        if self._drag_preview.width() > max_width:
            self._drag_preview.setFixedWidth(max_width)

        self._move_drag_preview(global_pos)
        self._drag_preview.show()
        self._drag_preview.raise_()

    def _move_drag_preview(self, global_pos):
        if self._drag_preview is None:
            return

        # Desplazamiento para que la vista no quede exactamente
        # debajo del puntero.
        self._drag_preview.move(
            global_pos.x() + 14,
            global_pos.y() + 14
        )
        self._drag_preview.raise_()

    def _destroy_drag_preview(self):
        if self._drag_preview is not None:
            self._drag_preview.hide()
            self._drag_preview.deleteLater()
            self._drag_preview = None

    def eventFilter(self, watched, event):
        if not self._dragging:
            return False

        event_type = event.type()

        if event_type == QEvent.MouseMove:
            if event.buttons() & Qt.LeftButton:
                global_pos = event.globalPos()
                self._update_drop_target(global_pos)
                self._move_drag_preview(global_pos)
                return True
            return False

        if event_type == QEvent.MouseButtonRelease:
            if event.button() == Qt.LeftButton:
                global_pos = event.globalPos()
                self._update_drop_target(global_pos)
                self._finish_drop()
                return True

        return False

    def _update_drop_target(self, global_pos):
        """
        Detecta el destino y lo marca visualmente.

        La selección real NO se modifica. El color se aplica únicamente
        al elemento/carpeta que recibiría el drop.
        """
        self._drop_row = -1
        self._favorite_target = None
        self._clear_drop_highlight()

        # ----------------------------------------------------------
        # FAVORITOS
        # ----------------------------------------------------------
        if self._favorite_list is not None:
            favorite_viewport = self._favorite_list.viewport()
            local_pos = favorite_viewport.mapFromGlobal(global_pos)

            if favorite_viewport.rect().contains(local_pos):
                favorite_item = self._favorite_list.itemAt(local_pos)

                if favorite_item is not None:
                    item_id = favorite_item.data(Qt.UserRole)

                    if item_id is not None:
                        target = self._find_virtual_item(item_id)

                        # Solo una carpeta puede ser destino.
                        if target is not None and target.is_folder():
                            self._favorite_target = favorite_item
                            self._highlight_favorite_item(
                                favorite_item
                            )

                return

        # ----------------------------------------------------------
        # TABLA
        # ----------------------------------------------------------
        table_viewport = self.viewport()
        table_pos = table_viewport.mapFromGlobal(global_pos)

        if table_viewport.rect().contains(table_pos):
            index = self.indexAt(table_pos)

            if index.isValid():
                row = index.row()

                # La fila destino solo es válida si representa carpeta.
                type_item = self.item(row, 1)

                if (
                    type_item is not None
                    and type_item.text() == "Carpeta"
                ):
                    self._drop_row = row
                    self._highlight_table_row(row)

    def _find_virtual_item(self, item_id):
        """
        Busca un ExplorerItem por su ID sin depender de la selección visual.
        """
        owner = getattr(
            self,
            "_explorer_owner",
            None
        )

        if owner is not None:
            index = getattr(owner, "_item_by_id", None)
            if index is not None:
                return index.get(item_id)
            if hasattr(owner, "root"):
                return self._find_by_id_recursive(owner.root, item_id)

        return None

    @staticmethod
    def _find_by_id_recursive(item, item_id):
        if id(item) == item_id:
            return item

        for child in item.children:
            result = ExplorerTableWidget._find_by_id_recursive(
                child,
                item_id
            )

            if result is not None:
                return result

        return None

    def _highlight_table_row(self, row):
        if row < 0 or row >= self.rowCount():
            return

        # El color se aplica a las tres columnas, pero no se usa
        # selectRow(), por lo que no altera la multi-selección.
        brush = QBrush(
            QColor(198, 230, 255)
        )

        for column in range(self.columnCount()):
            item = self.item(row, column)
            if item is not None:
                item.setBackground(brush)

        self._highlighted_table_row = row

    def _highlight_favorite_item(self, favorite_item):
        favorite_item.setBackground(
            QBrush(
                QColor(198, 255, 210)
            )
        )

        self._highlighted_favorite_item = favorite_item

    def _clear_drop_highlight(self):
        if self._highlighted_table_row >= 0:
            row = self._highlighted_table_row

            if row < self.rowCount():
                for column in range(self.columnCount()):
                    item = self.item(row, column)

                    if item is not None:
                        # QBrush() devuelve el control visual a la
                        # selección/estilo normal del QTableWidget.
                        item.setBackground(QBrush())

        self._highlighted_table_row = -1

        if self._highlighted_favorite_item is not None:
            self._highlighted_favorite_item.setBackground(
                QBrush()
            )

        self._highlighted_favorite_item = None

    def mouseReleaseEvent(self, event):
        # Si se está haciendo drag, el eventFilter captura el release.
        if self._dragging:
            return

        preserve = self._preserve_selection_on_press

        self._reset_drag_state()

        # En un click sobre una fila ya seleccionada sin Ctrl/Shift,
        # conservar la multi-selección también al soltar.
        if preserve:
            return

        super().mouseReleaseEvent(event)

    def _finish_drop(self):
        try:
            source_ids = list(self._drag_item_ids)

            if source_ids:
                if self._favorite_target is not None:
                    self.favoriteDropped.emit(
                        source_ids,
                        self._favorite_target
                    )
                elif self._drop_row >= 0:
                    self.itemDropped.emit(
                        source_ids,
                        int(self._drop_row)
                    )
        finally:
            self._reset_drag_state()

    def _reset_drag_state(self):
        if self._event_filter_installed:
            try:
                QApplication.instance().removeEventFilter(self)
            except Exception:
                pass

        self._destroy_drag_preview()
        self._clear_drop_highlight()

        self._event_filter_installed = False

        # Restaurar cursor normal después del arrastre.
        try:
            QApplication.restoreOverrideCursor()
        except Exception:
            pass

        self._pressed_row = -1
        self._press_pos = None
        self._dragging = False
        self._drag_item_ids = []
        self._drag_item_names = []
        self._selection_before_press_ids = []
        self._preserve_selection_on_press = False
        self._drop_row = -1
        self._favorite_target = None

        if self._favorite_list is not None:
            self._favorite_list.clearSelection()

# ============================================================
# EXPLORADOR
# ============================================================

class ExplorerWindow(QMainWindow):
    """
    Explorador virtual.

    A diferencia de un QTreeView tradicional, el panel principal
    solo muestra los hijos directos de la carpeta actualmente abierta.
    Las carpetas se abren con doble clic, como en un explorador normal.
    """
    closed = pyqtSignal()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def __init__(self, files_list=None, ram_source=None):
        super().__init__()

        # Objeto padre que contiene los bytes del packfile/RAM.
        # Debe permitir slicing, por ejemplo: parent[offset:end].
        self.ram_source = ram_source

        # Tamaño configurable del header de PACKFILE.
        # Valor inicial: 0x38000.
        self.packfile_header_size = 0x38000

        # Ajustar automáticamente la velocidad de los audios AT3 al importar.
        self.adjust_at3_audio_speed = True

        # Archivo LISTA_PACKFILE actualmente cargado, si existe.
        self.packfile_list_path = None

        # Bytes importados que reemplazan temporalmente archivos RAM.
        # La clave SIEMPRE es internal_name para que renombrar el archivo
        # en la UI no rompa la referencia al archivo original.
        self.imported_files = {}

        # Archivos nuevos insertados desde archivos físicos.
        # La clave es el nombre interno y cada entrada conserva los bytes
        # y la información del archivo nuevo.
        self.new_files = {}

        # Estructura de paddings definida desde Tools -> Paddings.
        # La clave es el nombre del archivo y el valor son las unidades.
        # Cada unidad equivale a 0x800 bytes.
        self.paddings = {}

        self.setWindowTitle("PyQt5 Explorer")
        self.resize(850, 500)

        self.root = ExplorerItem("ROOT", "folder")
        self.current_folder = self.root
        self.favorites = []
        self.history = []

        # Índices en memoria para evitar búsquedas recursivas sobre los
        # ~14.000 elementos cada vez que se selecciona, mueve o abre algo.
        self._item_by_id = {}
        self._row_by_id = {}

        # Índices de archivos de la UI.
        # _file_by_internal_name permite localizar un archivo por su nombre
        # interno sin recorrer los ~14.000 elementos del árbol.
        self._file_by_internal_name = {}
        self._ui_file_count = 0

        self._rebuild_item_index()
        self.history_index = -1

        self.setup_ui()

        # ROOT siempre está presente en favoritos y no se puede eliminar.
        self.favorites = [self.root]
        self.update_favorites()

        if files_list is not None:
            self.set_ram_files(files_list, refresh=False)

        self.open_folder(self.root, add_history=False)

    # ========================================================
    # UI
    # ========================================================

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # ---------------- Navegacion ----------------
        nav = QHBoxLayout()

        self.btn_back = QPushButton("◀")
        self.btn_back.setToolTip("Atrás")
        self.btn_back.setFixedWidth(42)

        self.btn_forward = QPushButton("▶")
        self.btn_forward.setToolTip("Adelante")
        self.btn_forward.setFixedWidth(42)

        self.btn_up = QPushButton("⬆")
        self.btn_up.setToolTip("Subir a la carpeta padre")
        self.btn_up.setFixedWidth(42)

        self.btn_home = QPushButton("⌂")
        self.btn_home.setToolTip("Ir a ROOT")
        self.btn_home.setFixedWidth(42)

        self.path_label = QLineEdit()
        self.path_label.setReadOnly(True)
        self.path_label.setPlaceholderText("Ruta")

        nav.addWidget(self.btn_back)
        nav.addWidget(self.btn_forward)
        nav.addWidget(self.btn_up)
        nav.addWidget(self.btn_home)
        nav.addWidget(self.path_label, 1)

        main_layout.addLayout(nav)

        # ---------------- Acciones ----------------
        actions = QHBoxLayout()

        self.btn_add_folder = QPushButton("＋ Carpeta")
        self.btn_favorite = QPushButton("⭐ Favorito")
        self.btn_refresh = QPushButton("↻ Actualizar")
        self.btn_save = QPushButton("💾 Guardar")
        self.btn_insert_file = QPushButton("＋ Insertar archivo")
        self.btn_open_packfile_list = QPushButton("📄 Abrir LISTA_PACKFILE")
        self.btn_import = QPushButton("📥 Importar estructura")
        self.btn_export = QPushButton("📤 Exportar estructura")

        for button in (
            self.btn_add_folder,
            self.btn_favorite,
            self.btn_refresh,
            self.btn_save,
            self.btn_insert_file,
            self.btn_open_packfile_list,
            self.btn_import,
            self.btn_export,
        ):
            actions.addWidget(button)

        actions.addStretch()
        main_layout.addLayout(actions)

        # ---------------- Busqueda ----------------
        search = QHBoxLayout()
        search.addWidget(QLabel("Buscar:"))

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Nombre de archivo o carpeta...")
        search.addWidget(self.search_edit, 1)

        # Por defecto la búsqueda se hace en _TODO ROOT.
        # Al desactivarlo vuelve a buscar únicamente en la carpeta actual.
        self.search_root_checkbox = QCheckBox("Todo ROOT")
        self.search_root_checkbox.setChecked(True)
        self.search_root_checkbox.setToolTip(
            "Buscar en todas las carpetas y archivos de ROOT"
        )
        search.addWidget(self.search_root_checkbox)

        main_layout.addLayout(search)

        # ---------------- Splitter ----------------
        splitter = QSplitter(Qt.Horizontal)

        favorites_widget = QWidget()
        favorites_layout = QVBoxLayout(favorites_widget)
        favorites_layout.setContentsMargins(0, 0, 0, 0)
        favorites_layout.addWidget(QLabel("⭐ FAVORITOS"))

        self.favorite_list = QListWidget()
        self.favorite_list.setContextMenuPolicy(Qt.CustomContextMenu)
        favorites_layout.addWidget(self.favorite_list)

        splitter.addWidget(favorites_widget)

        # ---------------- Contenido de la carpeta actual ----------------
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)

        self.table = ExplorerTableWidget()
        self.table.setFavoriteList(self.favorite_list)
        self.table.setExplorerOwner(self)
        self.table.setHorizontalHeaderLabels(["Nombre", "Tipo", "Tamaño"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        # Selección múltiple estilo explorador:
        # Ctrl + click = seleccionar/deseleccionar elementos individuales.
        # Shift + click = seleccionar un rango.
        self.table.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )

        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.setSortingEnabled(False)
        # El drag se inicia manualmente en ExplorerTableWidget.
        # Qt solo se usa para recibir el drop.
        self.table.setDragEnabled(False)
        self.table.setAcceptDrops(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, 300)

        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.resizeSection(1, 100)

        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 100)

        # Los iconos estándar se crean una sola vez.
        style = QApplication.style()
        self._folder_icon = style.standardIcon(style.SP_DirIcon)
        self._file_icon = style.standardIcon(style.SP_FileIcon)

        content_layout.addWidget(self.table)
        splitter.addWidget(content_widget)
        splitter.setSizes([250, 850])

        main_layout.addWidget(splitter, 1)

        # ---------------- Estado ----------------
        self.status_label = QLabel("ROOT")
        main_layout.addWidget(self.status_label)

        # ---------------- Señales ----------------
        self.btn_back.clicked.connect(self.go_back)
        self.btn_forward.clicked.connect(self.go_forward)
        self.btn_up.clicked.connect(self.go_up)
        self.btn_home.clicked.connect(lambda: self.open_folder(self.root))

        self.btn_add_folder.clicked.connect(self.create_folder)
        self.btn_favorite.clicked.connect(self.add_favorite)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_save.clicked.connect(self.guardar)
        self.btn_insert_file.clicked.connect(self.insert_new_file)
        self.btn_open_packfile_list.clicked.connect(
            self.open_packfile_list
        )
        self.btn_import.clicked.connect(self.import_structure)
        self.btn_export.clicked.connect(self.export_structure)

        # Con miles de archivos, no reconstruir la tabla en cada tecla.
        # Esperamos un momento para agrupar las pulsaciones.
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(120)
        self.search_timer.timeout.connect(self.refresh_current_folder)
        self.search_edit.textChanged.connect(
            lambda _text: self.search_timer.start()
        )
        self.search_root_checkbox.stateChanged.connect(
            lambda _state: self.search_timer.start()
        )
        self.table.cellDoubleClicked.connect(self.on_double_click)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.itemDropped.connect(self.handle_item_drop)
        self.table.favoriteDropped.connect(self.handle_favorite_drop)
        self.favorite_list.itemDoubleClicked.connect(self.open_favorite)
        self.favorite_list.customContextMenuRequested.connect(self.favorite_context_menu)

        self.update_navigation_buttons()

        # ---------------- Menu superior ----------------
        self._create_menu()

    def _create_menu(self):
        menubar = self.menuBar()

        tools_menu = menubar.addMenu("Tools")

        config_action = QAction("Config", self)
        config_action.triggered.connect(self.open_config_dialog)
        tools_menu.addAction(config_action)

        paddings_action = QAction("Paddings", self)
        paddings_action.triggered.connect(self.open_paddings_dialog)
        tools_menu.addAction(paddings_action)

    def open_paddings_dialog(self):
        """
        Editor visual de la estructura de paddings.

        self.paddings:
            {
                "1-1.unk": 1,
                "2-2.unk": 3
            }

        El JSON utiliza exactamente esta misma estructura.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("Paddings")
        dialog.setModal(True)
        dialog.resize(650, 420)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            "Cada unidad equivale a 0x800 bytes. "
        ))

        table = QTableWidget(0, 4, dialog)
        table.setHorizontalHeaderLabels(["Archivo", "Unidades", "Bytes", ""])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.SelectedClicked
        )

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.resizeSection(1, 110)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, 180)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.resizeSection(3, 85)
        layout.addWidget(table, 1)

        def rebuild_table():
            table.setRowCount(0)

            for name, units in self.paddings.items():
                row = table.rowCount()
                table.insertRow(row)

                table.setItem(row, 0, QTableWidgetItem(str(name)))

                spin = QSpinBox(table)
                spin.setRange(0, 0x7FFFFFFF)
                spin.setValue(int(units))
                spin.setSingleStep(1)
                table.setCellWidget(row, 1, spin)

                bytes_value = int(units) * 0x800
                bytes_item = QTableWidgetItem(
                    f"0x{bytes_value:X} ({bytes_value:,} bytes)"
                )
                bytes_item.setFlags(
                    bytes_item.flags() & ~Qt.ItemIsEditable
                )
                table.setItem(row, 2, bytes_item)

                button = QPushButton("Eliminar", table)
                button.clicked.connect(
                    lambda _checked=False, b=button:
                    remove_row(b)
                )
                table.setCellWidget(row, 3, button)

                spin.valueChanged.connect(
                    lambda value, s=spin:
                    self._update_padding_widget(table, s, value)
                )

        def remove_row(button):
            row = next(
                (
                    r for r in range(table.rowCount())
                    if table.cellWidget(r, 3) is button
                ),
                -1,
            )

            if row < 0:
                return

            item = table.item(row, 0)
            if item is not None:
                self.paddings.pop(item.text().strip(), None)

            table.removeRow(row)

        def add_row(name=None, units=1):
            # Al añadir desde la UI se genera automáticamente:
            # 1-1.unk, 2-2.unk, 3-3.unk, ...
            if name is None:
                i = 1
                while True:
                    generated_name = f"{i}-{i:X}.unk"
                    if generated_name not in self.paddings:
                        name = generated_name
                        break
                    i += 1
            else:
                name = str(name).strip()

            if not name:
                QMessageBox.warning(
                    dialog,
                    "Paddings",
                    "El nombre no puede estar vacío.",
                )
                return

            if name in self.paddings:
                QMessageBox.warning(
                    dialog,
                    "Paddings",
                    f"Ya existe un padding para '{name}'.",
                )
                return

            self.paddings[name] = int(units)
            rebuild_table()

        def sync_table():
            result = {}

            for row in range(table.rowCount()):
                item = table.item(row, 0)
                spin = table.cellWidget(row, 1)

                if item is None or not isinstance(spin, QSpinBox):
                    continue

                name = item.text().strip()
                if not name:
                    continue

                result[name] = spin.value()

            self.paddings.clear()
            self.paddings.update(result)

        rebuild_table()

        controls = QHBoxLayout()

        add_button = QPushButton("＋ Añadir padding")
        add_button.clicked.connect(lambda: add_row())
        controls.addWidget(add_button)

        clear_button = QPushButton("🗑 Limpiar todo")
        def clear_paddings():
            if not self.paddings:
                return

            reply = QMessageBox.question(
                dialog,
                "Limpiar paddings",
                "¿Quieres eliminar todos los paddings?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                self.paddings.clear()
                table.setRowCount(0)

        clear_button.clicked.connect(clear_paddings)
        controls.addWidget(clear_button)

        controls.addStretch()

        import_button = QPushButton("📥 Importar")
        import_button.clicked.connect(
            lambda: self.import_paddings(dialog)
        )
        controls.addWidget(import_button)

        export_button = QPushButton("📤 Exportar")
        export_button.clicked.connect(
            lambda: self.export_paddings(dialog, table)
        )
        controls.addWidget(export_button)

        layout.addLayout(controls)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(sync_table)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec_()

    def _update_padding_widget(self, table, spin, units):
        row = next(
            (
                r for r in range(table.rowCount())
                if table.cellWidget(r, 1) is spin
            ),
            -1,
        )

        if row < 0:
            return

        bytes_value = int(units) * 0x800
        bytes_item = table.item(row, 2)

        if bytes_item is not None:
            bytes_item.setText(
                f"0x{bytes_value:X} ({bytes_value:,} bytes)"
            )

    def export_paddings(self, parent_dialog=None, table=None):
        """Exporta self.paddings directamente como JSON."""
        if table is not None:
            result = {}

            for row in range(table.rowCount()):
                item = table.item(row, 0)
                spin = table.cellWidget(row, 1)

                if item is None or not isinstance(spin, QSpinBox):
                    continue

                name = item.text().strip()
                if name:
                    result[name] = spin.value()

            self.paddings.clear()
            self.paddings.update(result)

        filename, _ = QFileDialog.getSaveFileName(
            parent_dialog or self,
            "Exportar paddings",
            "paddings.json",
            "JSON (*.json)",
        )

        if not filename:
            return

        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(
                    self.paddings,
                    f,
                    indent=4,
                    ensure_ascii=False,
                )

            QMessageBox.information(
                parent_dialog or self,
                "Paddings",
                "La estructura de paddings se exportó correctamente.",
            )

        except Exception as exc:
            QMessageBox.critical(
                parent_dialog or self,
                "Error",
                f"No se pudo exportar la estructura:\n{exc}",
            )

    def import_paddings(self, parent_dialog=None):
        """Importa directamente un diccionario de paddings desde JSON."""
        filename, _ = QFileDialog.getOpenFileName(
            parent_dialog or self,
            "Importar paddings",
            "",
            "JSON (*.json)",
        )

        if not filename:
            return

        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError(
                    "El JSON debe ser un objeto con el formato:\n"
                    '{"1-1.unk": 1, "2-2.unk": 3}'
                )

            imported = {}

            for name, units in data.items():
                name = str(name).strip()

                if not name:
                    raise ValueError(
                        "Existe un elemento con nombre vacío."
                    )

                units = int(units)

                if units < 0:
                    raise ValueError(
                        f"El padding de '{name}' no puede ser negativo."
                    )

                imported[name] = units

            self.paddings.clear()
            self.paddings.update(imported)

            QMessageBox.information(
                parent_dialog or self,
                "Paddings",
                f"Se importaron {len(imported)} elemento(s).",
            )

            # Actualizar la ventana actualmente abierta.
            if parent_dialog is not None:
                parent_dialog.close()
                self.open_paddings_dialog()

        except Exception as exc:
            QMessageBox.critical(
                parent_dialog or self,
                "Error",
                f"No se pudo importar la estructura:\n{exc}",
            )

    def open_config_dialog(self):
        """Muestra la configuración del tamaño del header PACKFILE."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Config")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        label = QLabel("Tamaño del header packfile:")
        layout.addWidget(label)

        entry = QLineEdit()
        entry.setText(f"0x{self.packfile_header_size:X}")
        entry.setPlaceholderText("Ejemplo: 0x38000")
        layout.addWidget(entry)

        adjust_at3_checkbox = QCheckBox("Ajustar velocidad de audios AT3")
        adjust_at3_checkbox.setChecked(self.adjust_at3_audio_speed)
        adjust_at3_checkbox.setToolTip(
            "Si está activo, permite ajustar la velocidad de los audios AT3 durante la importación."
        )
        layout.addWidget(adjust_at3_checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec_() == QDialog.Accepted:
            try:
                self.set_packfile_header_size(entry.text())
                self.ram_source.psp_iso_explorer.set_packfile_header_size(entry.text())
                self.adjust_at3_audio_speed = adjust_at3_checkbox.isChecked()
            except (TypeError, ValueError):
                QMessageBox.warning(
                    self,
                    "Config",
                    "El tamaño del header no es válido.\n"
                    "Use un valor hexadecimal como 0x38000 "
                    "o un valor decimal."
                )

    def set_packfile_header_size(self, value):
        """
        Actualiza el tamaño del header PACKFILE.

        Acepta:
            0x38000
            "0x38000"
            229376
            "229376"
        """
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("El valor está vacío.")
            value = int(value, 0)

        value = int(value)

        if value < 0:
            raise ValueError("El tamaño no puede ser negativo.")

        self.packfile_header_size = value

        self.status_label.setText(
            f"STATUS | PACKFILE.BIN header actualizado | "
            f"0x{self.packfile_header_size:X}, {self.packfile_header_size}"
        )
        return self.packfile_header_size

    def get_packfile_header_size(self):
        """Devuelve el tamaño actual del header PACKFILE."""
        return self.packfile_header_size

    def get_adjust_at3_audio_speed(self):
        """Devuelve True si está activo el ajuste de velocidad de audios AT3."""
        return self.adjust_at3_audio_speed

    # ========================================================
    # LISTA_PACKFILE.TXT
    # ========================================================

    def open_packfile_list(self):
        """
        Abre un archivo de texto con el formato de LISTA_PACKFILE.

        Ejemplo:
            Main:
            1_1.unk: 1_system_jp.pak

            Main\Data:
            7_7.unk: 7_7.elf

        Las líneas terminadas en ':' definen la carpeta actual.
        Las líneas '<interno>: <visible>' definen archivos.
        """
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir LISTA_PACKFILE",
            "",
            "Listas PACKFILE (*.txt);;Todos los archivos (*)",
        )

        if not filename:
            return

        try:
            self.load_packfile_list(filename)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error al abrir LISTA_PACKFILE",
                f"No se pudo procesar el archivo:\n\n{exc}",
            )

    def load_packfile_list(self, filename, refresh=True):
        """
        Aplica una LISTA_PACKFILE sobre los archivos que YA existen en la UI.

        Importante:
            - NO se crean ExplorerItem de tipo archivo.
            - NO se reemplaza ``self.root``.
            - NO se borran archivos existentes.
            - Los objetos de archivo existentes conservan todos sus metadatos:
              ``path``, ``offset``, ``length``, ``num_file``,
              ``internal_name`` e información importada.
            - Únicamente se cambia ``name`` (nombre visible) y ``parent``
              (la carpeta donde queda el archivo).
            - Las carpetas indicadas por la lista sí se crean cuando no
              existen.

        El archivo de la izquierda de LISTA_PACKFILE, por ejemplo
        ``123_7B.unk``, se utiliza únicamente para identificar el archivo
        existente mediante su número decimal (``123``).
        """
        filename = str(filename)

        with open(
            filename,
            "r",
            encoding="utf-8-sig",
            errors="replace",
        ) as f:
            lines = f.readlines()

        # ----------------------------------------------------
        # 1) Parsear la lista SIN tocar todavía la estructura de la UI.
        # ----------------------------------------------------
        entries = []
        folder_paths = []
        current_folder_parts = []
        ignored_lines = []

        for line_number, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()

            if not line:
                continue

            # ---------------- Línea de carpeta ----------------
            if line.endswith(":"):
                folder_text = line[:-1].strip()

                if not folder_text:
                    current_folder_parts = []
                    continue

                current_folder_parts = normalize_packfile_list_folder(
                    folder_text
                )

                if current_folder_parts:
                    folder_paths.append(tuple(current_folder_parts))
                continue

            # ---------------- Línea de archivo ----------------
            if ":" not in line:
                ignored_lines.append((line_number, line))
                continue

            internal_name, visible_name = line.split(":", 1)
            internal_name = internal_name.strip()
            visible_name = visible_name.strip()

            if not internal_name or not visible_name:
                ignored_lines.append((line_number, line))
                continue

            num_file = parse_packfile_internal_name(internal_name)
            if num_file is None:
                ignored_lines.append((line_number, line))
                continue

            entries.append({
                "line": line_number,
                "folder_parts": tuple(current_folder_parts),
                "internal_name": internal_name,
                "visible_name": visible_name,
                "num_file": num_file,
            })

        # ----------------------------------------------------
        # 2) Indexar los archivos QUE YA ESTAN CARGADOS en la UI.
        # ----------------------------------------------------
        existing_files_by_num = {}
        duplicate_loaded_nums = set()

        stack = [self.root]
        while stack:
            parent = stack.pop()

            for child in parent.children:
                if child.is_folder():
                    stack.append(child)
                    continue

                # El número del archivo existente es el dato estable para
                # relacionarlo con la LISTA_PACKFILE. No se modifica.
                if child.num_file is None:
                    continue

                try:
                    num = int(child.num_file)
                except (TypeError, ValueError):
                    continue

                if num in existing_files_by_num:
                    duplicate_loaded_nums.add(num)
                else:
                    existing_files_by_num[num] = child

        # Si una lista apunta a un número duplicado en la UI no podemos saber
        # de forma segura cuál de los objetos existentes corresponde.
        for num in duplicate_loaded_nums:
            existing_files_by_num.pop(num, None)

        # ----------------------------------------------------
        # 3) Crear/reutilizar SOLO carpetas.
        # ----------------------------------------------------
        folder_cache = {"": self.root}

        def cache_existing_folders(parent, prefix=()):
            for child in parent.children:
                if not child.is_folder():
                    continue

                key = tuple(prefix) + (child.name.casefold(),)
                folder_cache["\\".join(key)] = child
                cache_existing_folders(child, tuple(prefix) + (child.name.casefold(),))

        cache_existing_folders(self.root)

        created_folders = 0

        def get_or_create_folder(parts):
            nonlocal created_folders

            parent = self.root
            normalized_parts = []

            for part in parts:
                part = str(part).strip()
                if not part:
                    continue

                normalized_parts.append(part.casefold())
                key = "\\".join(normalized_parts)

                folder = folder_cache.get(key)
                if folder is None:
                    # Buscar en el padre actual por si la caché no contiene
                    # una carpeta creada/renombrada por el usuario.
                    folder = next(
                        (
                            child for child in parent.children
                            if child.is_folder()
                            and child.name.casefold() == part.casefold()
                        ),
                        None,
                    )

                if folder is None:
                    folder = ExplorerItem(
                        name=part,
                        item_type="folder",
                        parent=parent,
                        internal_name=part,
                    )
                    parent.add_child(folder)
                    created_folders += 1

                folder_cache[key] = folder
                parent = folder

            return parent

        # Crear las carpetas de la lista incluso si alguno de sus archivos
        # todavía no está cargado en la UI.
        for folder_parts in folder_paths:
            get_or_create_folder(folder_parts)

        # ----------------------------------------------------
        # 4) Resolver las referencias de la lista contra objetos existentes.
        # ----------------------------------------------------
        resolved = []
        missing_entries = []
        duplicate_reference_lines = []
        used_loaded_items = set()

        for entry in entries:
            item = existing_files_by_num.get(entry["num_file"])

            if item is None:
                missing_entries.append(entry)
                continue

            if item in used_loaded_items:
                duplicate_reference_lines.append(entry)
                continue

            target_folder = get_or_create_folder(entry["folder_parts"])

            resolved.append((item, target_folder, entry["visible_name"], entry))
            used_loaded_items.add(item)

        # ----------------------------------------------------
        # 5) Validar nombres antes de mover/renombrar.
        # ----------------------------------------------------
        conflicts = []

        # Nombres que ya existen en cada carpeta, excluyendo archivos que
        # nosotros mismos vamos a mover.
        moving_items = {item for item, _folder, _name, _entry in resolved}
        destination_names = {}

        for item, target_folder, visible_name, entry in resolved:
            key = id(target_folder)

            if key not in destination_names:
                destination_names[key] = {
                    child.name.casefold()
                    for child in target_folder.children
                    if child not in moving_items
                }

            name_key = visible_name.casefold()

            if name_key in destination_names[key]:
                conflicts.append(
                    (
                        entry["line"],
                        visible_name,
                        self.item_path(target_folder),
                    )
                )
                continue

            destination_names[key].add(name_key)

        conflict_ids = {
            (line, name, path)
            for line, name, path in conflicts
        }

        # ----------------------------------------------------
        # 6) Aplicar cambios sobre LOS MISMOS objetos de archivo.
        # ----------------------------------------------------
        applied = 0
        moved = 0
        renamed = 0

        for item, target_folder, visible_name, entry in resolved:
            if (
                entry["line"],
                visible_name,
                self.item_path(target_folder),
            ) in conflict_ids:
                continue

            old_parent = item.parent
            old_name = item.name

            same_parent = old_parent is target_folder
            same_name = old_name == visible_name

            if same_parent and same_name:
                applied += 1
                continue

            # Sacar del conjunto de nombres del padre actual antes de
            # modificar ``name``.
            if old_parent is not None:
                old_parent.remove_child(item)

            # Cambia SOLO el nombre visible.
            item.name = visible_name

            # Y cambia SOLO su ubicación dentro de la estructura virtual.
            target_folder.add_child(item)

            if not same_parent:
                moved += 1
            if not same_name:
                renamed += 1

            applied += 1

        # ----------------------------------------------------
        # 7) Mantener todos los índices/estado existentes.
        # ----------------------------------------------------
        self.packfile_list_path = filename
        self._rebuild_item_index()

        if self.current_folder is None:
            self.current_folder = self.root

        if refresh and hasattr(self, "table"):
            self.refresh_current_folder()
            self.update_favorites()
            self.path_label.setText(self.item_path(self.current_folder))
            self.update_navigation_buttons()

        # ----------------------------------------------------
        # 8) Estado y resultado.
        # ----------------------------------------------------
        ignored_count = len(ignored_lines)
        missing_count = len(missing_entries)
        conflict_count = len(conflicts)
        unresolved_count = (
            missing_count
            + len(duplicate_reference_lines)
            + conflict_count
        )

        status = (
            "LISTA_PACKFILE aplicada | "
            f"{created_folders} carpetas nuevas | "
            f"{len(entries)} referencias | "
            f"{applied} archivos aplicados | "
            f"{moved} movidos | "
            f"{renamed} renombrados | "
            f"{unresolved_count} sin aplicar"
        )

        if ignored_count:
            status += f" | {ignored_count} líneas ignoradas"

        self.status_label.setText(status)

        return {
            "path": filename,
            "folders_created": created_folders,
            "references": len(entries),
            "files_applied": applied,
            "moved": moved,
            "renamed": renamed,
            "missing": missing_entries,
            "duplicate_loaded_nums": sorted(duplicate_loaded_nums),
            "duplicate_references": duplicate_reference_lines,
            "conflicts": conflicts,
            "ignored_lines": ignored_lines,
            "root": self.root,
        }

    # ========================================================
    # ARCHIVOS EN RAM
    # ========================================================

    def set_ram_files(self, files_list, refresh=True):
        """
        Carga/reemplaza los archivos de ROOT usando:

            [(offset, length, num_file), ...]

        El nombre interno se genera como:
            num_decimal-num_hex.unk

        self.name es el nombre visible y puede ser renombrado.
        self.internal_name nunca cambia al renombrar.
        """
        if files_list is None:
            files_list = []

        new_items = []

        for entry in files_list:
            offset, length, num_file = normalize_ram_file_entry(entry)
            internal_name = make_ram_file_name(num_file)

            new_items.append(
                ExplorerItem(
                    name=internal_name,
                    item_type="file",
                    parent=self.root,
                    internal_name=internal_name,
                    offset=offset,
                    length=length,
                    num_file=num_file,
                )
            )

        self.root.children = new_items
        self.root._child_name_set = {
            item.name.casefold() for item in new_items
        }

        # La lista de archivos representa una nueva fuente RAM/packfile;
        # los reemplazos anteriores ya no deben afectar esta nueva lista.
        self.imported_files.clear()
        self.new_files.clear()
        self.packfile_list_path = None

        for item in self.root.children:
            item.parent = self.root

        self._rebuild_item_index()

        # Al reemplazar la lista RAM, los favoritos antiguos pueden
        # apuntar a objetos que ya no existen.
        self.favorites = [self.root]
        self.history = [self.root]
        self.history_index = 0
        self.current_folder = self.root

        if refresh and hasattr(self, "table"):
            self.refresh_current_folder()
            self.update_favorites()
            self.path_label.setText(self.item_path(self.root))
            self.update_navigation_buttons()

    def add_ram_file(self, offset, length, num_file, parent=None):
        """
        Añade un único archivo RAM a una carpeta.
        """
        if parent is None:
            parent = self.current_folder

        offset = int(offset)
        length = int(length)
        num_file = int(num_file)

        internal_name = make_ram_file_name(num_file)

        if any(
            child.internal_name.lower() == internal_name.lower()
            for child in parent.children
        ):
            raise ValueError(
                f"Ya existe el archivo RAM '{internal_name}' "
                f"en '{parent.name}'."
            )

        item = ExplorerItem(
            name=internal_name,
            item_type="file",
            parent=parent,
            internal_name=internal_name,
            offset=offset,
            length=length,
            num_file=num_file,
        )

        parent.add_child(item)
        self._item_by_id[id(item)] = item

        # Insertar solo una fila evita reconstruir 14.000+ filas.
        if parent is self.current_folder:
            self._insert_item_into_current_view(item)
        return item

    def get_ram_file_reference(self, item):
        """
        Obtiene la referencia interna del archivo RAM.
        """
        if item is None or item.item_type != "file":
            return None

        return {
            "name": item.internal_name,
            "offset": item.offset,
            "length": item.length,
            "num_file": item.num_file,
        }

    # ========================================================
    # NAVEGACION
    # ========================================================

    def open_folder(self, folder, add_history=True):
        if folder is None or not folder.is_folder():
            return

        if folder is not self.root and id(folder) not in self._item_by_id:
            return

        if add_history and folder is not self.current_folder:
            if self.history_index < len(self.history) - 1:
                self.history = self.history[:self.history_index + 1]

            self.history.append(folder)
            self.history_index = len(self.history) - 1

        self.current_folder = folder
        self.refresh_current_folder()
        self.path_label.setText(self.item_path(folder))
        self.status_label.setText(
            f"{self.item_path(folder)}   |   {len(folder.children)} elemento(s)"
        )
        self.update_navigation_buttons()

    def go_back(self):
        if self.history_index <= 0:
            return

        self.history_index -= 1
        self.current_folder = self.history[self.history_index]
        self.refresh_current_folder()
        self.path_label.setText(self.item_path(self.current_folder))
        self.update_status()
        self.update_navigation_buttons()

    def go_forward(self):
        if self.history_index >= len(self.history) - 1:
            return

        self.history_index += 1
        self.current_folder = self.history[self.history_index]
        self.refresh_current_folder()
        self.path_label.setText(self.item_path(self.current_folder))
        self.update_status()
        self.update_navigation_buttons()

    def go_up(self):
        if self.current_folder.parent is not None:
            self.open_folder(self.current_folder.parent)

    def update_navigation_buttons(self):
        self.btn_back.setEnabled(self.history_index > 0)
        self.btn_forward.setEnabled(
            self.history_index >= 0 and
            self.history_index < len(self.history) - 1
        )
        self.btn_up.setEnabled(self.current_folder.parent is not None)

    # ========================================================
    # MOSTRAR SOLO EL CONTENIDO ACTUAL
    # ========================================================

    def _is_global_search_active(self):
        """Indica si la búsqueda está configurada para recorrer _todo ROOT."""
        return bool(
            hasattr(self, "search_root_checkbox")
            and self.search_root_checkbox.isChecked()
            and self.search_edit.text().strip()
        )

    def _get_visible_children(self, folder=None):
        """
        Devuelve los elementos visibles ya filtrados y ordenados.

        - Sin búsqueda global: solo hijos directos de ``folder``.
        - Con ``_Todo ROOT`` activo y texto: busca recursivamente en _todo ROOT.
        """
        if folder is None:
            folder = self.current_folder

        filter_text = self.search_edit.text().strip().casefold()

        if filter_text and hasattr(self, "search_root_checkbox") and self.search_root_checkbox.isChecked():
            # El índice en memoria evita recorrer recursivamente el árbol
            # desde cero. Solo filtramos los objetos ya indexados.
            children = [
                item for item in self._item_by_id.values()
                if item is not self.root
                and filter_text in item.name.casefold()
            ]
        else:
            children = folder.children
            if filter_text:
                children = [
                    child for child in children
                    if filter_text in child.name.casefold()
                ]
            else:
                children = list(children)

        # Carpetas primero y luego archivos, con orden natural tipo Windows.
        children.sort(
            key=lambda x: (not x.is_folder(), natural_sort_key(x.name))
        )
        return children

    def _populate_table_row(self, row, item):
        """Rellena una sola fila sin hacer ninguna búsqueda en el árbol."""
        name_item = QTableWidgetItem(item.name)
        type_item = QTableWidgetItem(
            "Carpeta" if item.is_folder() else "Archivo"
        )
        size_item = QTableWidgetItem(self.item_size(item))

        name_item.setIcon(
            self._folder_icon if item.is_folder() else self._file_icon
        )
        name_item.setData(Qt.UserRole, id(item))

        self.table.setItem(row, 0, name_item)
        self.table.setItem(row, 1, type_item)
        self.table.setItem(row, 2, size_item)

    def _rebuild_row_index(self):
        """Reconstruye solo el índice fila -> objeto visible."""
        self._row_by_id.clear()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                item_id = item.data(Qt.UserRole)
                if item_id is not None:
                    self._row_by_id[item_id] = row

    def _rebuild_item_index(self):
        """
        Indexa todos los ExplorerItem una sola vez.

        Además de ``_item_by_id``, mantiene:
            - ``_file_by_internal_name``: búsqueda O(1) por nombre interno.
            - ``_ui_file_count``: cantidad total de archivos que existen
              actualmente en la estructura de la UI.
        """
        self._item_by_id.clear()
        self._file_by_internal_name.clear()
        self._ui_file_count = 0

        stack = [self.root]

        while stack:
            item = stack.pop()
            self._item_by_id[id(item)] = item

            if item.is_folder():
                if item.children:
                    stack.extend(reversed(item.children))
                continue

            self._ui_file_count += 1

            internal_name = str(item.internal_name).strip()
            if internal_name:
                # En condiciones normales cada nombre interno es único.
                # Si hubiera un duplicado, conservamos el primero para que
                # la búsqueda siga siendo determinista.
                key = internal_name.casefold()
                if key not in self._file_by_internal_name:
                    self._file_by_internal_name[key] = item

    def _insert_item_into_current_view(self, item):
        """Inserta una sola fila en su posición natural."""
        global_search = self._is_global_search_active()

        if not global_search and item.parent is not self.current_folder:
            return

        filter_text = self.search_edit.text().strip().casefold()
        if filter_text and filter_text not in item.name.casefold():
            return

        visible = self._get_visible_children(self.current_folder)
        try:
            row = visible.index(item)
        except ValueError:
            return

        self.table.insertRow(row)
        self._populate_table_row(row, item)
        self._rebuild_row_index()
        self.update_status()

    def _remove_items_from_current_view(self, items):
        """Elimina únicamente las filas visibles correspondientes a items."""
        rows = sorted(
            {
                self._row_by_id.get(id(item), -1)
                for item in items
            },
            reverse=True,
        )
        rows = [row for row in rows if row >= 0]

        if not rows:
            return

        self.table.setUpdatesEnabled(False)
        try:
            for row in rows:
                if row < self.table.rowCount():
                    self.table.removeRow(row)
        finally:
            self.table.setUpdatesEnabled(True)

        self._rebuild_row_index()
        self.update_status()

    def _reposition_item_in_current_view(self, item):
        """Actualiza la posición de un elemento renombrado sin reconstruir toda la tabla."""
        old_row = self._row_by_id.get(id(item), -1)
        if old_row >= 0:
            self.table.removeRow(old_row)
            self._rebuild_row_index()

        self._insert_item_into_current_view(item)

    def refresh_current_folder(self):
        if self.current_folder is None:
            return

        if hasattr(self, "search_timer"):
            self.search_timer.stop()

        if hasattr(self.table, "_clear_drop_highlight"):
            self.table._clear_drop_highlight()

        children = self._get_visible_children(self.current_folder)

        # setRowCount() de una sola vez es considerablemente más rápido que
        # insertRow() repetidamente cuando hay miles de archivos.
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(children))

            for row, item in enumerate(children):
                self._populate_table_row(row, item)
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

        self._rebuild_row_index()
        self.update_status()

    def update_status(self):
        if self._is_global_search_active():
            results = self.table.rowCount()
            self.status_label.setText(
                f"Búsqueda en ROOT   |   {results} resultado(s)"
            )
            return

        self.status_label.setText(
            f"{self.item_path(self.current_folder)}   |   "
            f"{len(self.current_folder.children)} elemento(s)"
        )

    def selected_items(self):
        """Devuelve los ExplorerItem seleccionados usando el índice en memoria."""
        selected_rows = sorted(
            index.row()
            for index in self.table.selectionModel().selectedRows()
        )

        result = []
        for row in selected_rows:
            table_item = self.table.item(row, 0)
            if table_item is None:
                continue

            item_id = table_item.data(Qt.UserRole)
            obj = self._item_by_id.get(item_id)
            if obj is not None:
                result.append(obj)

        return result

    def current_selected_item(self):
        row = self.table.currentRow()
        if row < 0:
            return None

        table_item = self.table.item(row, 0)
        if table_item is None:
            return None

        item_id = table_item.data(Qt.UserRole)
        return self._item_by_id.get(item_id)

    def on_double_click(self, row, column):
        item = self.current_selected_item()
        if item is None:
            return

        if item.is_folder():
            self.open_folder(item)
        else:
            self.open_file(item)

    # ========================================================
    # DRAG & DROP
    # ========================================================

    def handle_item_drop(self, source_ids, target_row):
        """
        Mueve uno o varios elementos seleccionados a la carpeta destino.
        """
        sources = self.items_from_ids(source_ids)

        if not sources:
            return

        if target_row < 0 or target_row >= self.table.rowCount():
            return

        target_table_item = self.table.item(target_row, 0)
        if target_table_item is None:
            return

        target_id = target_table_item.data(Qt.UserRole)
        target = self.find_by_id(self.root, target_id)

        if target is None or not target.is_folder():
            self.refresh_current_folder()
            self.select_items(sources)
            return

        self.move_items_to_folder(sources, target)

    def handle_favorite_drop(self, source_ids, favorite_item):
        """
        Mueve uno o varios elementos seleccionados hacia la carpeta
        representada por el favorito.
        """
        sources = self.items_from_ids(source_ids)

        if not sources:
            return

        if favorite_item is None:
            return

        target_id = favorite_item.data(Qt.UserRole)

        if target_id is None:
            return

        target_folder = self.find_by_id(
            self.root,
            target_id
        )

        if target_folder is None:
            return

        if not target_folder.is_folder():
            self.refresh_current_folder()
            self.select_items(sources)
            return

        self.move_items_to_folder(
            sources,
            target_folder
        )

    def items_from_ids(self, source_ids):
        """Convierte IDs a objetos usando búsqueda O(1)."""
        if source_ids is None:
            return []

        if not isinstance(source_ids, (list, tuple, set)):
            source_ids = [source_ids]

        result = []
        for source_id in source_ids:
            source = self._item_by_id.get(source_id)
            if source is not None and source is not self.root:
                result.append(source)
        return result

    def select_items(self, items):
        """Selecciona visualmente elementos visibles sin buscar en _todo el árbol."""
        wanted = {id(item) for item in items}

        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.clearSelection()

            for item_id in wanted:
                row = self._row_by_id.get(item_id, -1)
                if row >= 0:
                    self.table.selectRow(row)
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

    def move_items_to_folder(self, sources, target_folder):
        """
        Mueve varios elementos a una carpeta realizando las validaciones
        antes de modificar la estructura.
        """
        unique_sources = []

        for source in sources:
            if source not in unique_sources:
                unique_sources.append(source)

        sources = unique_sources

        if not sources or target_folder is None:
            return

        # ROOT no se puede mover.
        sources = [
            source for source in sources
            if source is not self.root
        ]

        if not sources:
            return

        # Si ya están en la carpeta destino no hay ningún cambio que hacer.
        if all(source.parent is target_folder for source in sources):
            return

        # No permitir mover una carpeta dentro de sí misma o un descendiente.
        # Se construye el conjunto de ancestros del destino una sola vez.
        target_ancestors = set()
        current = target_folder
        while current is not None:
            target_ancestors.add(current)
            current = current.parent

        for source in sources:
            if source in target_ancestors:
                QMessageBox.warning(
                    self,
                    "Movimiento no válido",
                    f"No puedes mover '{source.name}' dentro de sí misma "
                    "o de una subcarpeta."
                )
                self.refresh_current_folder()
                self.select_items(sources)
                return

        # Si una carpeta padre y uno de sus hijos están seleccionados,
        # recorrer solo la cadena de padres de cada seleccionado.
        source_set = set(sources)
        for source in sources:
            current = source.parent
            while current is not None:
                if current in source_set:
                    QMessageBox.warning(
                        self,
                        "Movimiento no válido",
                        "No puedes mover al mismo tiempo una carpeta "
                        "y un elemento que está dentro de ella."
                    )
                    self.refresh_current_folder()
                    self.select_items(sources)
                    return
                current = current.parent

        # Comprobar nombres duplicados en destino.
        source_set = set(sources)

        destination_names = {
            child.name.lower()
            for child in target_folder.children
            if child not in source_set
        }

        for source in sources:
            if source.name.lower() in destination_names:
                QMessageBox.warning(
                    self,
                    "Movimiento no realizado",
                    f"La carpeta '{target_folder.name}' ya contiene "
                    f"un elemento llamado '{source.name}'."
                )
                self.refresh_current_folder()
                self.select_items(sources)
                return

            destination_names.add(source.name.lower())

        old_current = self.current_folder

        # Mover todos.
        for source in sources:
            if source.parent is not None:
                source.parent.remove_child(source)

        for source in sources:
            target_folder.add_child(source)

        # La carpeta de destino normalmente no está abierta; en ese caso
        # basta con quitar las filas de origen visibles. No reconstruimos
        # las 14.000 filas de ROOT.
        if old_current is self.current_folder:
            self._remove_items_from_current_view(sources)
        else:
            self.refresh_current_folder()

        # IMPORTANTE:
        # Si el destino fue un favorito (por ejemplo ROOT), el objeto
        # QListWidgetItem que está resaltado como destino pertenece a
        # favorite_list. ``update_favorites()`` hace clear() sobre esa
        # lista y destruye esos QListWidgetItem. Si dejamos la referencia
        # guardada en ExplorerTableWidget, ``_reset_drag_state()`` intentará
        # usar un QListWidgetItem que ya fue destruido y Qt puede cerrar el
        # proceso directamente.
        #
        # Limpiamos el resaltado ANTES de reconstruir la lista de favoritos.
        if hasattr(self, "table") and hasattr(
            self.table, "_clear_drop_highlight"
        ):
            self.table._clear_drop_highlight()

        self.update_favorites()
        self.update_status()

    def move_item_to_folder(self, source, target_folder):
        """Compatibilidad para mover un solo elemento."""
        self.move_items_to_folder(
            [source],
            target_folder
        )

    # ========================================================
    # CARPETAS / ARCHIVOS
    # ========================================================

    def create_folder(self):
        name, ok = QInputDialog.getText(self, "Nueva carpeta", "Nombre:")
        if not ok or not name.strip():
            return

        name = name.strip()
        if self.name_exists(self.current_folder, name):
            QMessageBox.warning(self, "Error", "Ya existe un elemento con ese nombre.")
            return

        item = ExplorerItem(name, "folder", parent=self.current_folder)
        self.current_folder.add_child(item)
        self._item_by_id[id(item)] = item
        self._insert_item_into_current_view(item)

    def add_file(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Seleccionar archivos")
        if not files:
            return

        added = []
        for filename in files:
            source = Path(filename)
            if self.name_exists(self.current_folder, source.name):
                continue

            item = ExplorerItem(
                source.name,
                "file",
                source,
                self.current_folder,
            )
            self.current_folder.add_child(item)
            self._item_by_id[id(item)] = item
            added.append(item)

        if not added:
            return

        # Para pocos archivos, insertar solo esas filas es mucho más rápido.
        # Para una importación grande usamos una sola reconstrucción.
        if len(added) <= 32:
            for item in added:
                self._insert_item_into_current_view(item)
        else:
            self.refresh_current_folder()

    def _get_next_ui_file_num(self):
        """
        Devuelve el siguiente número interno disponible.

        Se toma el número num_file más alto de todos los archivos que
        existen actualmente en la UI y se suma 1.

        Ejemplo:
            último = 15-F.unk (num_file=15)
            siguiente = 16-10.unk
        """
        max_num = 0

        for item in self.get_ui_files():
            try:
                num = int(item.num_file)
            except (TypeError, ValueError):
                continue

            if num > max_num:
                max_num = num

        return max_num + 1

    def insert_new_file(self):
        """
        Inserta un archivo físico NUEVO en ROOT.

        El archivo físico no modifica ningún archivo existente:
            - nombre visible = nombre físico
            - nombre interno = siguiente <decimal>-<hex>.unk
            - offset = "(por definir)"
            - length = tamaño real del archivo
            - num_file = siguiente número disponible
            - path = ruta física del archivo

        Además, los bytes quedan almacenados en ``self.new_files``.
        La estructura de cada entrada es:

            self.new_files[internal_name] = {
                "bytes": <bytes>,
                "info": {
                    "visible_name": ...,
                    "internal_name": ...,
                    "offset": "(por definir)",
                    "length": ...,
                    "size": ...,
                    "num_file": ...,
                    "physical_path": ...,
                    "virtual_path": ...,
                    "item": <ExplorerItem>,
                },
            }

        Siempre se inserta en ROOT, independientemente de la carpeta
        actualmente abierta.
        """
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Insertar archivo nuevo",
            "",
            "Todos los archivos (*)",
        )

        if not filename:
            return

        source = Path(filename)

        try:
            if not source.is_file():
                QMessageBox.warning(
                    self,
                    "Insertar archivo",
                    f"El archivo no existe o no es válido:\n{source}",
                )
                return

            data = source.read_bytes()
            size = len(data)
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Error al insertar archivo",
                f"No se pudo leer el archivo:\n\n{source}\n\n{exc}",
            )
            return

        visible_name = source.name

        # Se inserta en ROOT, por lo que comprobamos solamente los nombres
        # visibles que ya están directamente dentro de ROOT.
        if self.name_exists(self.root, visible_name):
            QMessageBox.warning(
                self,
                "Archivo ya existente",
                f"Ya existe un elemento llamado:\n\n{visible_name}\n\nen ROOT.",
            )
            return

        num_file = self._get_next_ui_file_num()
        internal_name = make_ram_file_name(num_file)

        # Seguridad adicional: nunca sobrescribir una entrada del diccionario.
        while internal_name.casefold() in {
            str(key).casefold() for key in self.new_files.keys()
        }:
            num_file += 1
            internal_name = make_ram_file_name(num_file)

        item = ExplorerItem(
            name=visible_name,
            item_type="file",
            path=source,
            parent=self.root,
            internal_name=internal_name,
            offset="(por definir)",
            length=size,
            num_file=num_file,
        )

        self.root.add_child(item)

        virtual_path = self.item_path(item)

        self.new_files[internal_name] = {
            "bytes": data,
            "info": {
                "visible_name": visible_name,
                "name": visible_name,
                "internal_name": internal_name,
                "offset": "(por definir)",
                "length": size,
                "size": size,
                "num_file": num_file,
                "physical_path": str(source),
                "virtual_path": virtual_path,
                "path": virtual_path,
                "parent_path": self.item_path(self.root),
                "item": item,
                "is_new": True,
            },
        }

        self._rebuild_item_index()

        if self.current_folder is self.root:
            self._insert_item_into_current_view(item)
        else:
            # La estructura cambió, pero la carpeta actual no.
            # Solo necesitamos actualizar el estado de cantidad.
            self.update_status()

        self.status_label.setText(
            f"Archivo nuevo insertado | {internal_name} | "
            f"{self.format_size(size)}"
        )

    def get_new_files(self):
        """
        Devuelve el diccionario de archivos nuevos insertados.

        Las entradas contienen:

            {
                "bytes": bytes,
                "info": {
                    "visible_name": ...,
                    "internal_name": ...,
                    "offset": "(por definir)",
                    "length": ...,
                    "size": ...,
                    "num_file": ...,
                    "physical_path": ...,
                    "virtual_path": ...,
                    "item": <ExplorerItem>,
                },
            }

        Se devuelve el mismo diccionario interno, sin copiar los bytes.
        """
        return self.new_files

    def open_file(self, item):
        if not item.path or not item.path.exists():
            QMessageBox.information(self, "Archivo", f"Archivo virtual:\n{item.name}")
            return

        try:
            if os.name == "nt":
                os.startfile(str(item.path))
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(item.path)])
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    # ========================================================
    # FAVORITOS
    # ========================================================

    def add_favorite(self):
        item = self.current_selected_item()
        target = item if item is not None else self.current_folder

        if target is self.root:
            return

        if target not in self.favorites:
            self.favorites.append(target)
            self.update_favorites()

    def update_favorites(self):
        # Evitar referencias a QListWidgetItem que serán destruidos por
        # favorite_list.clear(). Esto protege también cualquier otra llamada
        # a update_favorites() durante un drag & drop.
        if hasattr(self, "table") and hasattr(
            self.table, "_clear_drop_highlight"
        ):
            self.table._clear_drop_highlight()

        # ROOT es siempre el primer favorito y nunca se elimina.
        normalized = [self.root]

        for item in self.favorites:
            if item is not self.root and item not in normalized:
                normalized.append(item)

        self.favorites = normalized

        self.favorite_list.clear()

        for item in self.favorites:
            list_item = QListWidgetItem()
            icon = (
                QApplication.style().standardIcon(QApplication.style().SP_DirIcon)
                if item.is_folder()
                else QApplication.style().standardIcon(QApplication.style().SP_FileIcon)
            )
            list_item.setIcon(icon)
            list_item.setText(item.name)
            list_item.setToolTip(self.item_path(item))
            list_item.setData(Qt.UserRole, id(item))
            self.favorite_list.addItem(list_item)

    def open_favorite(self, list_item):
        item_id = list_item.data(Qt.UserRole)
        item = self.find_by_id(self.root, item_id)
        if item is None:
            return

        if item.is_folder():
            self.open_folder(item)
        elif item.parent is not None:
            self.open_folder(item.parent)
            self.select_item(item)

    def select_item(self, target):
        row = self._row_by_id.get(id(target), -1)
        if row < 0:
            return

        item = self.table.item(row, 0)
        if item is not None:
            self.table.selectRow(row)
            self.table.scrollToItem(item)

    def favorite_context_menu(self, position):
        item = self.favorite_list.itemAt(position)
        if item is None:
            return

        item_id = item.data(Qt.UserRole)
        favorite_obj = self.find_by_id(self.root, item_id)

        menu = QMenu(self)

        # ROOT es un favorito permanente.
        if favorite_obj is self.root:
            protected = QAction("ROOT (favorito permanente)", self)
            protected.setEnabled(False)
            menu.addAction(protected)
            menu.exec_(self.favorite_list.mapToGlobal(position))
            return

        remove = QAction("Quitar de favoritos", self)
        menu.addAction(remove)

        action = menu.exec_(self.favorite_list.mapToGlobal(position))
        if action == remove:
            self.favorites = [
                x for x in self.favorites
                if x is not self.root and id(x) != item_id
            ]

            # Garantizar que ROOT nunca desaparezca.
            if self.root not in self.favorites:
                self.favorites.insert(0, self.root)

            self.update_favorites()

    # ========================================================
    # MENU CONTEXTUAL
    # ========================================================


    def show_context_menu(self, position):
        """
        Menú contextual para el elemento sobre el que se hizo click derecho.

        Cuando existe una selección múltiple, las operaciones de I/O trabajan
        sobre toda la selección siempre que todos los elementos sean del mismo
        tipo (solo archivos o solo carpetas).
        """
        index = self.table.indexAt(position)

        item = None
        clicked_row = -1

        if index.isValid():
            clicked_row = index.row()
            table_item = self.table.item(clicked_row, 0)

            if table_item is not None:
                item_id = table_item.data(Qt.UserRole)
                item = self._item_by_id.get(item_id)

        if item is None:
            item = self.current_selected_item()

        # Click derecho sobre un elemento que no estaba seleccionado:
        # convertirlo en la única selección. Si ya pertenecía a la selección,
        # conservar la multi-selección existente.
        if item is not None and clicked_row >= 0:
            selected_rows = {
                selected_index.row()
                for selected_index in self.table.selectionModel().selectedRows()
            }

            if clicked_row not in selected_rows:
                self.table.clearSelection()
                self.table.selectRow(clicked_row)

        context_selection = self.selected_items()

        # Garantizar que al menos el elemento pulsado forme parte del contexto.
        if item is not None and item not in context_selection:
            context_selection = [item]

        selected_folders = [
            x for x in context_selection
            if x is not None and x.is_folder()
        ]
        selected_files = [
            x for x in context_selection
            if x is not None and not x.is_folder()
        ]

        menu = QMenu(self)

        new_folder = QAction("＋ Nueva carpeta", self)
        menu.addAction(new_folder)

        if item is not None:
            menu.addSeparator()

            open_action = QAction("Abrir", self)
            info_action = QAction("Información", self)
            rename_action = QAction("Renombrar", self)
            favorite_action = QAction("⭐ Agregar a favoritos", self)

            menu.addAction(open_action)
            menu.addAction(info_action)
            menu.addAction(rename_action)
            menu.addAction(favorite_action)

            # ----------------------------------------------------
            # OPERACIONES SOBRE CARPETAS
            # ----------------------------------------------------
            export_folder_action = None
            import_folder_action = None
            export_file_action = None
            import_file_action = None

            if item.is_folder():
                menu.addSeparator()

                if selected_folders and not selected_files:
                    export_folder_action = QAction(
                        (
                            f"📤 Exportar {len(selected_folders)} carpetas"
                            if len(selected_folders) > 1
                            else "📤 Exportar carpeta"
                        ),
                        self,
                    )
                    import_folder_action = QAction(
                        "📥 Importar carpeta",
                        self,
                    )

                    menu.addAction(export_folder_action)
                    menu.addAction(import_folder_action)

            # ----------------------------------------------------
            # OPERACIONES SOBRE ARCHIVOS
            # ----------------------------------------------------
            else:
                menu.addSeparator()

                if selected_files and not selected_folders:
                    export_file_action = QAction(
                        (
                            f"📤 Exportar {len(selected_files)} archivos"
                            if len(selected_files) > 1
                            else "📤 Exportar archivo"
                        ),
                        self,
                    )
                    import_file_action = QAction(
                        (
                            f"📥 Importar {len(selected_files)} archivos"
                            if len(selected_files) > 1
                            else "📥 Importar archivo"
                        ),
                        self,
                    )

                    menu.addAction(export_file_action)
                    menu.addAction(import_file_action)

            menu.addSeparator()

            # ============================================================
            # ABRIR CON
            # ============================================================
            # Por ahora solo se agrega Play.
            # Se muestra únicamente cuando hay exactamente un archivo
            # seleccionado.
            open_with_menu = QMenu("Abrir con", self)
            play_action = None

            if len(selected_files) == 1 and not selected_folders:
                play_action = QAction("Play", self)
                # La acción se procesa más abajo mediante:
                #     action == play_action
                # No conectar triggered aquí porque produciría una
                # segunda ejecución de play_selected_file().
                open_with_menu.addAction(play_action)
                menu.addMenu(open_with_menu)

            delete_action = QAction("🗑 Eliminar", self)
            menu.addAction(delete_action)
        else:
            open_action = None
            info_action = None
            rename_action = None
            favorite_action = None
            export_folder_action = None
            import_folder_action = None
            export_file_action = None
            import_file_action = None
            delete_action = None

        action = menu.exec_(
            self.table.viewport().mapToGlobal(position)
        )

        if action == new_folder:
            self.create_folder()

        elif item is not None and action == open_action:
            if item.is_folder():
                self.open_folder(item)
            else:
                self.open_file(item)

        elif item is not None and action == info_action:
            self.show_item_information(item)

        elif item is not None and action == rename_action:
            # Renombrar sigue siendo individual.
            self.rename_item(item)

        elif item is not None and action == favorite_action:
            self.add_specific_favorite(item)

        elif (
            item is not None
            and item.is_folder()
            and export_folder_action is not None
            and action == export_folder_action
        ):
            folders = self.selected_items()

            if any(not x.is_folder() for x in folders):
                QMessageBox.warning(
                    self,
                    "Exportar carpetas",
                    "Para exportar carpetas seleccionadas, "
                    "todos los elementos seleccionados deben ser carpetas.",
                )
            elif not folders:
                QMessageBox.information(
                    self,
                    "Exportar carpetas",
                    "Selecciona al menos una carpeta.",
                )
            else:
                self.export_selected_folders(folders)

        elif (
            item is not None
            and item.is_folder()
            and import_folder_action is not None
            and action == import_folder_action
        ):
            context_selection = self.selected_items()

            if len(context_selection) > 1:
                QMessageBox.warning(
                    self,
                    "Importar carpeta",
                    "Solo se puede importar una carpeta a la vez.\n\n"
                    f"Actualmente hay {len(context_selection)} elementos seleccionados.",
                )
            elif (
                len(context_selection) == 1
                and context_selection[0].is_folder()
            ):
                self.import_folder(context_selection[0])
            else:
                QMessageBox.information(
                    self,
                    "Importar carpeta",
                    "Selecciona una sola carpeta para importar.",
                )

        elif (
            item is not None
            and not item.is_folder()
            and export_file_action is not None
            and action == export_file_action
        ):
            files = self.selected_items()

            if any(x.is_folder() for x in files):
                QMessageBox.warning(
                    self,
                    "Exportar archivos",
                    "Para exportar archivos seleccionados, "
                    "todos los elementos seleccionados deben ser archivos.",
                )
            elif not files:
                QMessageBox.information(
                    self,
                    "Exportar archivos",
                    "Selecciona al menos un archivo.",
                )
            elif len(files) == 1:
                self.export_file_bytes(files[0])
            else:
                self.export_selected_files(files)

        elif (
            item is not None
            and not item.is_folder()
            and import_file_action is not None
            and action == import_file_action
        ):
            files = self.selected_items()

            if any(x.is_folder() for x in files):
                QMessageBox.warning(
                    self,
                    "Importar archivos",
                    "Para importar archivos seleccionados, "
                    "todos los elementos seleccionados deben ser archivos.",
                )
            elif not files:
                QMessageBox.information(
                    self,
                    "Importar archivos",
                    "Selecciona al menos un archivo.",
                )
            else:
                self.import_file_bytes(files)

        elif (
            item is not None
            and play_action is not None
            and action == play_action
        ):
            self.play_selected_file(item)

        elif item is not None and action == delete_action:
            self.delete_item(item)
    def play_selected_file(self, item):
        """
        Obtiene los bytes del único archivo seleccionado y toda su
        información para que play_file() pueda procesarlo.

        No modifica ni mueve el archivo.
        """
        if item is None or item.is_folder():
            return

        # Play solo acepta exactamente un archivo.
        selected = [
            x for x in self.selected_items()
            if x is not None and not x.is_folder()
        ]

        if len(selected) != 1:
            QMessageBox.information(
                self,
                "Play",
                "Play solo puede utilizarse con un archivo seleccionado."
            )
            return

        item = selected[0]

        try:
            # Usa el metodo existente para respetar:
            # - archivos importados
            # - archivos nuevos
            # - archivos contenidos en ram_source
            # - archivos físicos
            data = self.get_file_bytes(item)

            file_info = {
                "nombre_visible": item.name,
                "nombre_interno": item.internal_name,
                "ruta": self.item_path(item),
                "offset": item.offset,
                "long": item.length,
                "item": item,
            }

            self.play_file(data, file_info)

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Play",
                f"No se pudieron obtener los datos del archivo "
                f"'{item.name}':\n\n{exc}"
            )

    def play_file(self, data, file_info):
        """
        Punto de entrada para tu código de conversión/reproducción.

        data:
            Datos del archivo seleccionado.

        file_info:
            {
                "nombre_visible": nombre mostrado en la UI,
                "nombre_interno": nombre interno,
                "ruta": ruta virtual dentro del explorador,
                "offset": offset original,
                "long": longitud original,
                "item": ExplorerItem
            }

        Agrega aquí tu código AT3 -> WAV.
        """

        # ============================================================
        # TU CÓDIGO AT3 -> WAV VA AQUÍ
        # ============================================================


        at3_Builder = AT3HeaderBuilder(data_size=len(data))
        audio_at3 = at3_Builder.build_header() + data


        temp_dir = tempfile.gettempdir()

        at3_path = Path(
            temp_dir,
            file_info["nombre_visible"]
        )
        at3_path = at3_path.with_suffix(".wav")

        with open(at3_path, "wb") as f:
            f.write(audio_at3)

        force_name = "_m_" in file_info["nombre_visible"].lower()

        if force_name:
            result, at3_path = DataFileManager.add_block2(path_audio_at3=at3_path)

        # convertir a wav si se requiere
        wav_path = at3_path.parent / f"{at3_path.stem}_converted.wav"
        VAGHeader().convert_vag_to_wav(is_vag=False, vag_path=at3_path, wav_path=wav_path, force_speed=self.get_adjust_at3_audio_speed() and force_name)

        os.startfile(wav_path)

        print("=== PLAY ===")
        print("Nombre visible:", file_info["nombre_visible"])
        print("Nombre interno:", file_info["nombre_interno"])
        print("Ruta:", file_info["ruta"])
        print("Offset:", file_info["offset"])
        print("Long:", file_info["long"])
        print("Tipo de datos:", type(data).__name__)
        print("Cantidad de bytes:", wav_path.stat().st_size)

    def show_item_information(self, item):
        """Muestra la información detallada del elemento seleccionado."""
        if item is None:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Información - {item.name}")
        dialog.setMinimumWidth(440)

        layout = QFormLayout(dialog)
        layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        def add_field(label, value):
            field = QLineEdit(str(value))
            field.setReadOnly(True)
            field.setCursorPosition(0)
            layout.addRow(label, field)

        add_field("Nombre:", item.name)
        add_field("Nombre interno:", item.internal_name)
        add_field("Tipo:", "Carpeta" if item.is_folder() else "Archivo")

        # Offset puede ser numérico en archivos RAM o texto en archivos
        # nuevos, por ejemplo: "(por definir)". Nunca asumir que se puede
        # convertir directamente a int().
        if item.offset is None:
            add_field("Offset:", "-")
        elif isinstance(item.offset, bool):
            add_field("Offset:", str(item.offset))
        else:
            try:
                offset = int(item.offset)
            except (TypeError, ValueError):
                add_field("Offset:", item.offset)
            else:
                add_field("Offset:", f"0x{offset:X} ({offset})")

        # La longitud normalmente es numérica, pero también la manejamos de
        # forma segura para que Información nunca se caiga por un metadato
        # especial o personalizado.
        if item.length is not None:
            try:
                length = int(item.length)
            except (TypeError, ValueError):
                add_field("Longitud:", item.length)
            else:
                add_field("Longitud:", f"0x{length:X} ({length} bytes)")
        elif not item.is_folder() and item.path and item.path.exists():
            try:
                length = item.path.stat().st_size
                add_field("Longitud:", f"0x{length:X} ({length} bytes)")
            except OSError:
                add_field("Longitud:", "-")
        else:
            add_field("Longitud:", "-")

        if item.num_file is not None:
            number = int(item.num_file)
            add_field("Número de archivo:", f"{number} (0x{number:X})")
        else:
            add_field("Número de archivo:", "-")

        add_field("Ruta:", self.item_path(item))

        if item.path is not None:
            add_field("Ruta física:", item.path)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addRow(buttons)

        dialog.exec_()

    # ========================================================
    # I/O DE ARCHIVOS DEL PACKFILE / RAM
    # ========================================================

    def _read_ram_bytes(self, item):
        """
        Lee los bytes originales de un archivo RAM desde el objeto padre.

        El offset almacenado en ExplorerItem es el offset del packfile.
        SOLO para acceder al buffer del padre se aplica:

            real_offset = item.offset - parent.packfile_offset

        No se modifica item.offset, por lo que la información de la UI
        continúa mostrando el offset original.
        """
        if item is None or item.is_folder():
            raise ValueError("El elemento seleccionado no es un archivo.")

        if item.offset is None or item.length is None:
            raise ValueError("El archivo no tiene offset/longitud de RAM.")

        parent = self.ram_source
        if parent is None:
            raise RuntimeError(
                "No se configuró el objeto padre que contiene los bytes del packfile."
            )

        if not hasattr(parent, "packfile_offset"):
            raise AttributeError(
                "El objeto padre no tiene el atributo 'packfile_offset'."
            )

        try:
            packfile_offset = int(parent.packfile_offset)
            offset = int(item.offset)
            length = int(item.length)
        except (TypeError, ValueError) as exc:
            raise ValueError("Offset, longitud o packfile_offset no son válidos.") from exc

        real_offset = offset - packfile_offset
        if real_offset < 0:
            raise ValueError(
                f"Offset inválido: 0x{offset:X} - 0x{packfile_offset:X} = "
                f"0x{real_offset:X}."
            )

        if length < 0:
            raise ValueError("La longitud del archivo no puede ser negativa.")

        try:
            # El PACKFILE permanece una sola vez en ``ram_source``.
            # Esta copia se crea SOLO cuando una operación realmente necesita
            # los bytes del archivo (exportar, abrir con, editor, etc.).
            if hasattr(parent, "read_bytes"):
                data = parent.read_bytes(real_offset, length)
            else:
                data = bytes(parent[real_offset:real_offset + length])
        except Exception as exc:
            raise RuntimeError(
                f"No se pudieron leer los bytes en 0x{real_offset:X}: {exc}"
            ) from exc

        if len(data) != length:
            raise ValueError(
                f"Se esperaban {length} bytes, pero el padre devolvió {len(data)} bytes."
            )

        return data

    def get_file_span(self, item):
        """
        Devuelve solo la referencia lógica al rango del archivo dentro del
        PACKFILE, sin copiar sus bytes.

        Retorna ``(ram_source, real_offset, length)``.
        """
        if item is None or item.is_folder():
            raise ValueError("El elemento seleccionado no es un archivo.")
        if item.offset is None or item.length is None:
            raise ValueError("El archivo no tiene offset/longitud.")
        if self.ram_source is None:
            raise RuntimeError("No existe ram_source.")

        real_offset = int(item.offset) - int(self.ram_source.packfile_offset)
        length = int(item.length)
        if real_offset < 0 or length < 0:
            raise ValueError("Offset/longitud inválidos.")
        return self.ram_source, real_offset, length

    def get_file_bytes(self, item):
        """
        Devuelve los bytes efectivos del archivo.

        Si el archivo fue importado/reemplazado, se usan primero los bytes
        guardados en ``self.imported_files``. De lo contrario se leen del
        packfile/RAM o del archivo físico.
        """
        if item is None or item.is_folder():
            raise ValueError("El elemento seleccionado no es un archivo.")

        # Los archivos nuevos tienen sus bytes almacenados directamente
        # en self.new_files.
        new_entry = self.new_files.get(item.internal_name)
        if new_entry is not None:
            return new_entry["bytes"]

        imported = self.imported_files.get(item.internal_name)
        if imported is not None:
            return imported

        # Los archivos RAM normales usan offset/length numéricos.
        # Un archivo nuevo tiene offset="(por definir)", por lo que NO
        # debe intentarse leer desde ram_source.
        if (
            item.offset is not None
            and item.length is not None
            and self.ram_source is not None
            and isinstance(item.offset, (int, float))
            and not isinstance(item.offset, bool)
        ):
            return self._read_ram_bytes(item)

        if item.path is not None and item.path.exists():
            return item.path.read_bytes()

        raise RuntimeError(f"No hay una fuente de bytes para '{item.name}'.")

    def _update_item_size_in_ui(self, item):
        """Actualiza solamente la celda Tamaño del archivo modificado."""
        row = self._row_by_id.get(id(item), -1)
        if row < 0 or row >= self.table.rowCount():
            return

        size_item = self.table.item(row, 2)
        if size_item is None:
            size_item = QTableWidgetItem()
            self.table.setItem(row, 2, size_item)

        size_item.setText(self.item_size(item))


    def export_file_bytes(self, item=None):
        """Exporta el contenido efectivo de un único archivo a un archivo físico."""
        if item is None:
            selected = self.selected_items()
            if len(selected) == 1 and not selected[0].is_folder():
                item = selected[0]
            else:
                item = self.current_selected_item()

        if item is None or item.is_folder():
            return

        try:
            data = self.get_file_bytes(item)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Exportar archivo",
                f"No se pudieron obtener los bytes de '{item.name}':\n{exc}"
            )
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar archivo",
            item.name,
            "Todos los archivos (*.*)"
        )
        if not filename:
            return

        try:
            with open(filename, "wb") as f:
                f.write(data)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error al exportar",
                f"No se pudo guardar el archivo:\n{exc}"
            )
            return

        QMessageBox.information(
            self,
            "Exportado",
            f"Archivo exportado correctamente.\n\n"
            f"Nombre: {item.name}\n"
            f"Bytes: {len(data)}"
        )

    def export_selected_files(self, files):
        """
        Exporta varios archivos seleccionados a un mismo directorio.

        Cada archivo se crea usando su NOMBRE VISIBLE en la UI.
        No se usa el nombre interno para el nombre físico.
        """
        if files is None:
            files = []

        unique = []
        seen = set()

        for item in files:
            if item is None or item.is_folder():
                continue

            item_id = id(item)
            if item_id in seen:
                continue

            seen.add(item_id)
            unique.append(item)

        files = unique

        if not files:
            QMessageBox.information(
                self,
                "Exportar archivos",
                "No hay archivos seleccionados para exportar.",
            )
            return

        parent_dir = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta destino",
        )
        if not parent_dir:
            return

        parent_dir = Path(parent_dir)

        # Validar todos los nombres visibles y leer todos los bytes antes
        # de crear cualquier archivo.
        names_seen = {}
        prepared = []

        try:
            for item in files:
                visible_name = str(item.name).strip()

                if not visible_name:
                    raise ValueError(
                        f"El archivo '{item.internal_name}' no tiene "
                        "nombre visible."
                    )

                key = visible_name.casefold()

                if key in names_seen:
                    raise ValueError(
                        "Hay archivos seleccionados con el mismo nombre "
                        f"visible: '{names_seen[key]}' y '{visible_name}'."
                    )

                names_seen[key] = visible_name

                destination = parent_dir / visible_name

                if destination.exists():
                    raise FileExistsError(
                        f"Ya existe en el destino: {destination}"
                    )

                data = self.get_file_bytes(item)
                prepared.append((item, destination, data))

        except Exception as exc:
            QMessageBox.warning(
                self,
                "Exportar archivos",
                "No se pudo preparar la exportación.\n\n"
                f"{exc}\n\n"
                "No se creó ningún archivo.",
            )
            return

        created = []

        try:
            for _item, destination, data in prepared:
                destination.write_bytes(data)
                created.append(destination)

        except Exception as exc:
            for destination in reversed(created):
                try:
                    if destination.exists():
                        destination.unlink()
                except Exception:
                    pass

            QMessageBox.critical(
                self,
                "Error al exportar archivos",
                "No se pudieron exportar todos los archivos.\n\n"
                "Se eliminaron los archivos creados durante la operación.\n\n"
                f"{exc}",
            )
            return

        total_bytes = sum(len(data) for _item, _destination, data in prepared)

        self.status_label.setText(
            f"{len(prepared)} archivo(s) exportado(s) | "
            f"{total_bytes} bytes"
        )

        QMessageBox.information(
            self,
            "Archivos exportados",
            "Los archivos se exportaron correctamente.\n\n"
            f"Archivos: {len(prepared)}\n"
            f"Destino: {parent_dir}\n"
            f"Bytes totales: {total_bytes}",
        )

    def convert_wav_to_at3(self, wav_path):
        """
        Punto de entrada para tu código WAV -> AT3.

        wav_path:
            Ruta física exacta del WAV seleccionado.

        Debe devolver los bytes completos del AT3.
        Si el archivo NO termina en .wav, este metodo no se utiliza.
        """
        wav_path = Path(wav_path)
        speed_f:bool = "_m_" in wav_path.name.lower()

        at3_header = AT3HeaderBuilder(parent=None)
        temp_dir = Path(tempfile.gettempdir())
        at3_path = temp_dir / f"{wav_path.stem}.unk"
        at3_header.convert_wav_to_at3(wav_path=wav_path, output_at3_path=at3_path, force_speed=self.get_adjust_at3_audio_speed() and speed_f)

        data_audio = None
        if speed_f:
            DataFileManager.remove_block2(path_audio_at3=at3_path)

        with open(at3_path, "rb") as f:
            data = f.read()
            offset_data = data.find(b'data')
            if offset_data == -1:
                raise ValueError(f"No audio data found, file: {at3_path.name}")

            long_audio = int.from_bytes(data[offset_data + 4:offset_data + 8], byteorder='little')
            data_audio = data[offset_data + 8:offset_data + 8 + long_audio]

        return data_audio


    def _read_import_file(self, filename):
        """
        Lee un archivo físico para importación.

        Si el nombre termina exactamente en .wav (ignorando mayúsculas/minúsculas),
        NO se importan directamente sus bytes: se pasan por convert_wav_to_at3().

        Para cualquier otra extensión, devuelve los bytes originales.

        Retorna:
            bytes, was_wav
        """
        filename = Path(filename)

        # La detección se hace únicamente por la extensión final del nombre.
        # No se inspecciona el contenido/MIME del archivo.
        if filename.name.lower().endswith(".wav"):
            data = self.convert_wav_to_at3(filename)
            if not isinstance(data, (bytes, bytearray, memoryview)):
                raise TypeError(
                    "convert_wav_to_at3() debe devolver bytes del AT3."
                )
            return bytes(data), True

        return filename.read_bytes(), False

    def import_file_bytes(self, item=None):
        """
        Importa bytes desde uno o varios archivos físicos.

        Reglas:
            - 1 archivo seleccionado en la UI:
                se selecciona 1 archivo físico y su nombre NO importa.
            - varios archivos seleccionados en la UI:
                se deben seleccionar EXACTAMENTE la misma cantidad de
                archivos físicos y cada archivo físico debe tener el mismo
                nombre que el NOMBRE VISIBLE correspondiente de la UI.

        La correspondencia múltiple se realiza por nombre visible
        (case-insensitive), nunca por nombre interno.
        """
        if item is not None:
            if isinstance(item, (list, tuple, set)):
                selected = list(item)
            else:
                selected = [item]
        else:
            selected = self.selected_items()
            if not selected:
                current = self.current_selected_item()
                if current is not None:
                    selected = [current]

        # Deduplicar y conservar solo archivos.
        unique_selected = []
        seen_ids = set()

        for target in selected:
            if target is None or target.is_folder():
                continue

            target_id = id(target)
            if target_id in seen_ids:
                continue

            seen_ids.add(target_id)
            unique_selected.append(target)

        selected = unique_selected

        if not selected:
            QMessageBox.information(
                self,
                "Importar archivo",
                "Selecciona al menos un archivo."
            )
            return

        # ============================================================
        # UN SOLO ARCHIVO
        # ============================================================
        if len(selected) == 1:
            filename, _ = QFileDialog.getOpenFileName(
                self,
                "Importar archivo",
            )
            if not filename:
                return

            try:
                data, was_wav = self._read_import_file(filename)
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Error al importar",
                    f"No se pudo leer el archivo seleccionado:\n{exc}"
                )
                return

            try:
                self._replace_imported_bytes_for_item(
                    selected[0],
                    data,
                )
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Error al importar",
                    f"No se pudieron reemplazar los bytes:\n{exc}"
                )
                return

            self._update_item_size_in_ui(selected[0])

            self.status_label.setText(
                f"1 archivo reemplazado en memoria | "
                f"{len(data)} bytes importados"
                + (" | WAV convertido a AT3" if was_wav else "")
            )
            return

        # ============================================================
        # VARIOS ARCHIVOS
        # ============================================================
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Importar archivos",
            "",
            "Todos los archivos (*.*)",
        )

        if not filenames:
            return

        # Debe coincidir exactamente la cantidad UI <-> físico.
        if len(filenames) != len(selected):
            QMessageBox.warning(
                self,
                "Importar archivos",
                "La cantidad de archivos físicos no coincide con "
                "la cantidad de archivos seleccionados en la UI.\n\n"
                f"UI: {len(selected)} archivo(s)\n"
                f"Almacenamiento: {len(filenames)} archivo(s)\n\n"
                "No se reemplazó ningún byte.",
            )
            return

        # ============================================================
        # MAPEAR POR NOMBRE VISIBLE
        # ============================================================
        ui_by_name = {}
        duplicate_ui_names = []

        for target in selected:
            key = str(target.name).casefold()

            if key in ui_by_name:
                duplicate_ui_names.append(
                    f"'{ui_by_name[key].name}' / '{target.name}'"
                )
            else:
                ui_by_name[key] = target

        if duplicate_ui_names:
            QMessageBox.warning(
                self,
                "Importar archivos",
                "No se puede realizar la importación múltiple porque "
                "hay nombres visibles duplicados en la selección de la UI.\n\n"
                + "\n".join(
                    f"• {name}"
                    for name in duplicate_ui_names
                )
                + "\n\n"
                "La correspondencia por nombre sería ambigua. "
                "No se reemplazó ningún byte.",
            )
            return

        physical_by_name = {}

        for filename in filenames:
            physical_name = Path(filename).name
            key = physical_name.casefold()

            if key in physical_by_name:
                QMessageBox.warning(
                    self,
                    "Importar archivos",
                    "Hay nombres físicos duplicados entre los archivos "
                    f"seleccionados:\n\n"
                    f"• {Path(physical_by_name[key]).name}\n"
                    f"• {physical_name}\n\n"
                    "No se reemplazó ningún byte.",
                )
                return

            physical_by_name[key] = filename

        # Deben existir exactamente los nombres visibles de la UI.
        missing_in_storage = [
            target.name
            for target in selected
            if str(target.name).casefold() not in physical_by_name
        ]

        extra_in_storage = [
            Path(filename).name
            for key, filename in physical_by_name.items()
            if key not in ui_by_name
        ]

        if missing_in_storage or extra_in_storage:
            messages = [
                "Los nombres de los archivos del almacenamiento deben "
                "coincidir exactamente con los nombres visibles de la UI "
                "(sin distinguir mayúsculas/minúsculas).",
                "",
                "No se reemplazó ningún byte.",
            ]

            if missing_in_storage:
                messages.extend([
                    "",
                    f"FALTAN EN EL ALMACENAMIENTO ({len(missing_in_storage)}):",
                ])
                messages.extend(
                    f"• {name}"
                    for name in missing_in_storage
                )

            if extra_in_storage:
                messages.extend([
                    "",
                    f"NO CORRESPONDEN CON LA UI ({len(extra_in_storage)}):",
                ])
                messages.extend(
                    f"• {name}"
                    for name in extra_in_storage
                )

            QMessageBox.warning(
                self,
                "Importar archivos",
                "\n".join(messages),
            )
            return

        # Leer todos los archivos antes de modificar cualquier entrada.
        import_data = []

        try:
            for target in selected:
                filename = physical_by_name[str(target.name).casefold()]
                data, was_wav = self._read_import_file(filename)
                import_data.append((target, data, filename, was_wav))
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error al importar archivos",
                "No se pudieron leer todos los archivos.\n\n"
                "No se reemplazó ningún byte.\n\n"
                f"{exc}",
            )
            return

        details = "\n".join(
            f"• {target.name} ← {Path(filename).name} ({len(data)} bytes)"
            + (" [WAV → AT3]" if was_wav else "")
            for target, data, filename, was_wav in import_data
        )

        answer = QMessageBox.question(
            self,
            "Importar archivos",
            f"Se reemplazarán {len(import_data)} archivos en memoria.\n\n"
            f"{details}\n\n"
            "La correspondencia se hizo por nombre visible.\n\n"
            "¿Continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if answer != QMessageBox.Yes:
            return

        # Aplicar todos los reemplazos solamente después de superar todas
        # las validaciones.
        try:
            for target, data, _filename, _was_wav in import_data:
                self._replace_imported_bytes_for_item(
                    target,
                    data,
                )
                self._update_item_size_in_ui(target)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Error al importar archivos",
                "Ocurrió un error al guardar los reemplazos en memoria.\n\n"
                f"{exc}",
            )
            return

        total_bytes = sum(
            len(data)
            for _target, data, _filename, _was_wav in import_data
        )

        self.status_label.setText(
            f"{len(import_data)} archivo(s) reemplazado(s) en memoria | "
            f"{total_bytes} bytes importados"
        )

        QMessageBox.information(
            self,
            "Archivos importados",
            "Los archivos se importaron correctamente.\n\n"
            f"Archivos: {len(import_data)}\n"
            f"Bytes totales: {total_bytes}",
        )
    def get_imported_files(self):
        """Devuelve el diccionario de reemplazos RAM almacenados en memoria."""
        return self.imported_files

    def _get_folder_manifest(self, folder):
        """
        Construye la estructura esperada de una carpeta virtual.

        Devuelve:
            {
                "folders": {relative_path_tuple: ExplorerItem},
                "files": {relative_path_tuple: ExplorerItem},
            }

        Las rutas relativas usan EXCLUSIVAMENTE los nombres visibles de la UI.
        El nombre interno no participa en la comparación física; se conserva
        en el ExplorerItem y se utiliza después para guardar los bytes.
        """
        if folder is None or not folder.is_folder():
            raise ValueError("El elemento seleccionado no es una carpeta.")

        manifest = {
            "folders": {},
            "files": {},
        }

        stack = [(folder, ())]
        while stack:
            current_folder, relative_parent = stack.pop()

            for child in current_folder.children:
                relative_path = relative_parent + (child.name,)

                if child.is_folder():
                    manifest["folders"][relative_path] = child
                    stack.append((child, relative_path))
                else:
                    manifest["files"][relative_path] = child

        return manifest

    @staticmethod
    def _physical_folder_manifest(folder_path):
        """
        Construye la estructura de una carpeta física usando rutas relativas.

        Devuelve dos diccionarios:
            folders: set de tuplas con nombres de carpetas.
            files:   set de tuplas con nombres de archivos.

        También distingue automáticamente los casos en que en físico existe
        un archivo donde la UI espera una carpeta, o viceversa.
        """
        root = Path(folder_path)
        if not root.is_dir():
            raise ValueError(f"La ruta no es una carpeta válida: {root}")

        folders = set()
        files = set()

        for current_root, dirnames, filenames in os.walk(root):
            current_root = Path(current_root)
            rel_root = current_root.relative_to(root)
            rel_prefix = tuple(rel_root.parts) if rel_root.parts else ()

            for dirname in dirnames:
                folders.add(rel_prefix + (dirname,))

            for filename in filenames:
                files.add(rel_prefix + (filename,))

        return folders, files

    @staticmethod
    def _format_relative_entry(relative_path):
        """Convierte ('A', 'B', 'file.bin') en 'A\\B\\file.bin'."""
        if not relative_path:
            return "ROOT"
        return "\\".join(str(part) for part in relative_path)

    def _replace_imported_bytes_for_item(self, item, data):
        """
        Reemplaza los bytes efectivos de un archivo ya existente en la UI.

        Archivos insertados recientemente se actualizan en ``new_files``.
        Los demás utilizan ``imported_files``, que es el mecanismo de
        reemplazo temporal de los archivos provenientes de RAM/packfile.
        """
        if item is None or item.is_folder():
            raise ValueError("El elemento seleccionado no es un archivo.")

        data = bytes(data)
        key = item.internal_name

        if key in self.new_files:
            entry = self.new_files.get(key)
            if isinstance(entry, dict):
                entry["bytes"] = data
                item.length = len(data)

                # Mantener sincronizada la información expuesta por
                # get_new_files()/get_file_info_by_internal_name().
                self.get_file_info_by_internal_name(
                    key,
                    include_bytes=False,
                )
                return "new_files"

        self.imported_files[key] = data
        item.length = len(data)
        return "imported_files"

    def export_selected_folders(self, folders):
        """
        Exporta varias carpetas virtuales seleccionadas a un mismo directorio.

        Cada carpeta seleccionada se crea directamente dentro del directorio
        destino usando su nombre visible y conserva toda su estructura interna.
        Los bytes exportados son los bytes efectivos actuales de la UI.

        Antes de comenzar se validan todos los destinos para evitar dejar una
        exportación parcial por colisiones de nombres.
        """
        if folders is None:
            folders = []

        # Eliminar duplicados conservando el orden de la selección.
        unique = []
        seen = set()
        for folder in folders:
            if folder is None or not folder.is_folder():
                continue
            key = id(folder)
            if key not in seen:
                seen.add(key)
                unique.append(folder)

        folders = unique

        if not folders:
            QMessageBox.information(
                self,
                "Exportar carpetas",
                "No hay carpetas seleccionadas para exportar.",
            )
            return

        parent_dir = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta destino",
        )
        if not parent_dir:
            return

        parent_dir = Path(parent_dir)

        # No iniciar nada si alguna carpeta de destino ya existe.
        destinations = []
        duplicate_names = set()
        destination_names = set()

        for folder in folders:
            name_key = folder.name.casefold()
            if name_key in destination_names:
                duplicate_names.add(folder.name)
            destination_names.add(name_key)

            destination = parent_dir / folder.name
            destinations.append((folder, destination))

        if duplicate_names:
            QMessageBox.warning(
                self,
                "Exportar carpetas",
                "Hay carpetas seleccionadas con el mismo nombre visible, "
                "por lo que no se pueden exportar juntas al mismo destino:\n\n"
                + "\n".join(f"• {name}" for name in sorted(duplicate_names)),
            )
            return

        existing = [destination for _folder, destination in destinations if destination.exists()]
        if existing:
            QMessageBox.warning(
                self,
                "Exportar carpetas",
                "Ya existe una o más carpetas en el destino.\n\n"
                + "\n".join(f"• {path}" for path in existing)
                + "\n\nPor seguridad, no se sobrescribirá ninguna.",
            )
            return

        # Construir todos los manifiestos antes de crear nada.
        manifests = []
        try:
            for folder, destination in destinations:
                manifest = self._get_folder_manifest(folder)
                manifests.append((folder, destination, manifest))
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Exportar carpetas",
                f"No se pudo analizar la estructura virtual:\n\n{exc}",
            )
            return

        created_destinations = []
        total_files = 0
        total_folders = 0

        try:
            for folder, destination, manifest in manifests:
                destination.mkdir(parents=True, exist_ok=False)
                created_destinations.append(destination)

                for relative_folder in sorted(manifest["folders"]):
                    (destination / Path(*relative_folder)).mkdir(
                        parents=True,
                        exist_ok=True,
                    )
                    total_folders += 1

                for relative_file, item in sorted(manifest["files"].items()):
                    target_file = destination / Path(*relative_file)
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    target_file.write_bytes(self.get_file_bytes(item))
                    total_files += 1

        except Exception as exc:
            # Si falla la exportación de cualquiera, limpiar las carpetas que
            # creó este proceso para no dejar resultados incompletos.
            for destination in reversed(created_destinations):
                try:
                    if destination.exists():
                        shutil.rmtree(destination)
                except Exception:
                    pass

            QMessageBox.critical(
                self,
                "Error al exportar carpetas",
                "No se pudieron exportar todas las carpetas.\n\n"
                f"No se dejó una exportación parcial.\n\n{exc}",
            )
            return

        self.status_label.setText(
            f"{len(folders)} carpeta(s) exportada(s) | "
            f"{total_files} archivo(s)"
        )

        QMessageBox.information(
            self,
            "Carpetas exportadas",
            "Las carpetas se exportaron correctamente.\n\n"
            f"Carpetas exportadas: {len(folders)}\n"
            f"Archivos exportados: {total_files}\n"
            f"Subcarpetas: {total_folders}\n"
            f"Destino: {parent_dir}",
        )

    def export_folder(self, folder=None):
        """
        Exporta una carpeta virtual completa a una carpeta física.

        Se conserva exactamente la estructura visible de la UI y se escriben
        los bytes EFECTIVOS de cada archivo, es decir, respeta también los
        reemplazos existentes en ``self.imported_files``/``self.new_files``.

        El usuario selecciona el directorio PADRE y se crea dentro de él una
        carpeta con el mismo nombre visible de la carpeta virtual.
        """
        if folder is None:
            folder = self.current_selected_item()

        if folder is None or not folder.is_folder():
            QMessageBox.information(
                self,
                "Exportar carpeta",
                "Selecciona una carpeta para exportar.",
            )
            return

        parent_dir = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta destino",
        )
        if not parent_dir:
            return

        destination = Path(parent_dir) / folder.name

        if destination.exists():
            QMessageBox.warning(
                self,
                "Exportar carpeta",
                "Ya existe una carpeta con ese nombre en el destino:\n\n"
                f"{destination}\n\n"
                "Por seguridad, no se sobrescribirá.",
            )
            return

        try:
            manifest = self._get_folder_manifest(folder)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Exportar carpeta",
                f"No se pudo analizar la carpeta virtual:\n\n{exc}",
            )
            return

        try:
            destination.mkdir(parents=True, exist_ok=False)

            # Crear primero toda la estructura de carpetas.
            for relative_folder in sorted(manifest["folders"]):
                (destination / Path(*relative_folder)).mkdir(
                    parents=True,
                    exist_ok=True,
                )

            exported_files = 0

            # Escribir los bytes efectivos de cada archivo.
            for relative_file, item in sorted(manifest["files"].items()):
                target_file = destination / Path(*relative_file)
                target_file.parent.mkdir(parents=True, exist_ok=True)

                data = self.get_file_bytes(item)
                target_file.write_bytes(data)
                exported_files += 1

        except Exception as exc:
            # La carpeta de destino fue creada por este metodo; limpiarla
            # evita dejar una exportación incompleta.
            try:
                if destination.exists():
                    shutil.rmtree(destination)
            except Exception:
                pass

            QMessageBox.critical(
                self,
                "Error al exportar carpeta",
                f"No se pudo exportar la carpeta.\n\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Carpeta exportada",
            "La carpeta se exportó correctamente.\n\n"
            f"Origen virtual: {self.item_path(folder)}\n"
            f"Destino físico: {destination}\n"
            f"Carpetas: {len(manifest['folders'])}\n"
            f"Archivos: {exported_files}",
        )

    def import_folder(self, folder=None):
        """
        Importa los bytes de una carpeta física sobre una carpeta virtual.

        IMPORTANTE: primero se valida TODA la estructura. Solo cuando la
        estructura física coincide con la UI se leen/aplican los bytes.

        La comparación utiliza:
            - nombre visible
            - ubicación relativa
            - tipo (carpeta/archivo)

        NO se modifica el nombre visible, nombre interno, offset ni la ruta
        del archivo en la UI. Solo se reemplazan sus bytes y, por tanto,
        ``length`` pasa a reflejar el nuevo tamaño.

        Si falta un archivo físico, se informa exactamente en qué ubicación
        relativa falta y NO se importa ningún byte.
        """
        if folder is None:
            folder = self.current_selected_item()

        if folder is None or not folder.is_folder():
            QMessageBox.information(
                self,
                "Importar carpeta",
                "Selecciona una carpeta para importar.",
            )
            return

        physical_root = QFileDialog.getExistingDirectory(
            self,
            f"Seleccionar carpeta física para '{folder.name}'",
        )
        if not physical_root:
            return

        physical_root = Path(physical_root)

        try:
            virtual_manifest = self._get_folder_manifest(folder)
            physical_folders, physical_files = self._physical_folder_manifest(
                physical_root
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Importar carpeta",
                f"No se pudo analizar la estructura:\n\n{exc}",
            )
            return

        expected_folders = set(virtual_manifest["folders"].keys())
        expected_files = set(virtual_manifest["files"].keys())
        physical_all = physical_folders | physical_files
        expected_all = expected_folders | expected_files

        # Un mismo path no puede ser simultáneamente carpeta y archivo.
        type_conflicts = []
        for relative_path in sorted(expected_all | physical_all):
            expected_is_folder = relative_path in expected_folders
            expected_is_file = relative_path in expected_files
            physical_is_folder = relative_path in physical_folders
            physical_is_file = relative_path in physical_files

            if expected_is_folder and physical_is_file:
                type_conflicts.append(("UI carpeta / físico archivo", relative_path))
            elif expected_is_file and physical_is_folder:
                type_conflicts.append(("UI archivo / físico carpeta", relative_path))

        missing_files = sorted(expected_files - physical_files)
        missing_folders = sorted(expected_folders - physical_folders)
        extra_files = sorted(physical_files - expected_files)
        extra_folders = sorted(physical_folders - expected_folders)

        # Si existe un conflicto de tipo, quitar esa ruta de missing/extra evita
        # mostrarla dos veces y hace más claro el diagnóstico.
        conflict_paths = {path for _kind, path in type_conflicts}
        missing_files = [path for path in missing_files if path not in conflict_paths]
        missing_folders = [path for path in missing_folders if path not in conflict_paths]
        extra_files = [path for path in extra_files if path not in conflict_paths]
        extra_folders = [path for path in extra_folders if path not in conflict_paths]

        has_structure_mismatch = bool(
            type_conflicts
            or missing_files
            or missing_folders
            or extra_files
            or extra_folders
        )

        if has_structure_mismatch:
            lines = [
                "La estructura física NO coincide con la estructura de la UI.",
                "",
                "No se reemplazó ningún byte.",
            ]

            if missing_files:
                lines.extend([
                    "",
                    f"ARCHIVOS QUE FALTAN EN FÍSICO ({len(missing_files)}):",
                ])
                lines.extend(
                    f"  • {self._format_relative_entry(path)}"
                    for path in missing_files
                )

            if missing_folders:
                lines.extend([
                    "",
                    f"CARPETAS QUE FALTAN EN FÍSICO ({len(missing_folders)}):",
                ])
                lines.extend(
                    f"  • {self._format_relative_entry(path)}"
                    for path in missing_folders
                )

            if type_conflicts:
                lines.extend([
                    "",
                    f"TIPOS O UBICACIONES INCORRECTAS ({len(type_conflicts)}):",
                ])
                lines.extend(
                    f"  • {kind}: {self._format_relative_entry(path)}"
                    for kind, path in type_conflicts
                )

            if extra_files:
                lines.extend([
                    "",
                    f"ARCHIVOS SOBRANTES EN FÍSICO ({len(extra_files)}):",
                ])
                lines.extend(
                    f"  • {self._format_relative_entry(path)}"
                    for path in extra_files
                )

            if extra_folders:
                lines.extend([
                    "",
                    f"CARPETAS SOBRANTES EN FÍSICO ({len(extra_folders)}):",
                ])
                lines.extend(
                    f"  • {self._format_relative_entry(path)}"
                    for path in extra_folders
                )

            QMessageBox.warning(
                self,
                "Estructura diferente",
                "\n".join(lines),
            )
            return

        # La estructura ya está validada. Ahora leemos todos los bytes antes
        # de tocar ``imported_files``/``new_files``. Si un archivo falla al
        # leerse, el estado en memoria permanece sin cambios.
        pending = []

        try:
            for relative_file, item in sorted(virtual_manifest["files"].items()):
                physical_file = physical_root / Path(*relative_file)
                data, was_wav = self._read_import_file(physical_file)
                pending.append((item, data, was_wav, physical_file))
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Importar carpeta",
                "La estructura coincide, pero no se pudieron leer todos los "
                f"archivos físicos.\n\nNo se modificó ningún byte.\n\n{exc}",
            )
            return

        imported_count = 0
        imported_total = 0

        try:
            for item, data, _was_wav, _physical_file in pending:
                self._replace_imported_bytes_for_item(item, data)
                imported_count += 1
                imported_total += len(data)
        except Exception as exc:
            # En teoría no debería fallar aquí después de validar y leer todos
            # los datos. Si ocurre, avisamos para que el usuario no interprete
            # el proceso como completamente terminado.
            QMessageBox.critical(
                self,
                "Importar carpeta",
                "Ocurrió un error al aplicar los bytes en memoria.\n\n"
                f"Archivos aplicados antes del error: {imported_count}\n"
                f"Error: {exc}",
            )
            self.refresh_current_folder()
            return

        for item, _data, _was_wav, _physical_file in pending:
            self._update_item_size_in_ui(item)

        wav_count = sum(1 for _item, _data, was_wav, _physical_file in pending if was_wav)

        self.status_label.setText(
            f"Carpeta importada | {imported_count} archivo(s) | "
            f"{self.format_size(imported_total)} en memoria"
            + (f" | {wav_count} WAV → AT3" if wav_count else "")
        )

        QMessageBox.information(
            self,
            "Carpeta importada",
            "La estructura coincide correctamente con la UI.\n\n"
            f"Carpeta: {self.item_path(folder)}\n"
            f"Archivos reemplazados: {imported_count}\n"
            f"Bytes importados: {imported_total}",
        )

    def add_specific_favorite(self, item):
        if item is self.root:
            return

        if item not in self.favorites:
            self.favorites.append(item)

        # ROOT debe permanecer siempre.
        if self.root not in self.favorites:
            self.favorites.insert(0, self.root)

        self.update_favorites()

    def rename_item(self, item):
        name, ok = QInputDialog.getText(self, "Renombrar", "Nuevo nombre:", text=item.name)
        if not ok or not name.strip():
            return

        name = name.strip()
        if any(x is not item and x.name.lower() == name.lower() for x in item.parent.children):
            QMessageBox.warning(self, "Error", "Ya existe un elemento con ese nombre.")
            return

        old_name_key = item.name.casefold()
        item.name = name
        if item.parent is not None:
            item.parent._child_name_set.discard(old_name_key)
            item.parent._child_name_set.add(item.name.casefold())
        self._reposition_item_in_current_view(item)
        self.update_favorites()
        self.path_label.setText(self.item_path(self.current_folder))

    def delete_item(self, item):
        if item is self.root:
            return

        answer = QMessageBox.question(
            self,
            "Eliminar",
            f"¿Eliminar '{item.name}' de la estructura virtual?",
            QMessageBox.Yes | QMessageBox.No
        )
        if answer != QMessageBox.Yes:
            return

        parent = item.parent

        # Quitar del índice y de self.new_files a todos los descendientes.
        stack = [item]
        while stack:
            current = stack.pop()
            self._item_by_id.pop(id(current), None)

            if not current.is_folder():
                self.new_files.pop(current.internal_name, None)

            stack.extend(current.children)

        parent.remove_child(item)
        self._rebuild_item_index()
        self.remove_favorite_recursive(item)

        if self._is_global_search_active():
            # Al eliminar una carpeta también desaparecen sus descendientes
            # de los resultados globales.
            self.refresh_current_folder()
        elif parent is self.current_folder:
            self._remove_items_from_current_view([item])
        else:
            self.refresh_current_folder()

        self.update_favorites()

    def remove_favorite_recursive(self, item):
        to_remove = set()
        for favorite in self.favorites:
            current = favorite
            while current is not None:
                if current is item:
                    to_remove.add(favorite)
                    break
                current = current.parent
        self.favorites = [x for x in self.favorites if x not in to_remove]

    # ========================================================
    # GUARDAR / ACCESO A LOS ARCHIVOS DE LA UI
    # ========================================================

    def get_ui_file_count(self):
        """
        Devuelve la cantidad TOTAL de archivos que existen actualmente
        en la estructura virtual de la UI.

        Las carpetas no se cuentan.
        """
        # Mantener el contador sincronizado incluso después de una
        # inserción que todavía no haya provocado una reconstrucción completa.
        if self._ui_file_count != len(self._file_by_internal_name):
            self._rebuild_item_index()

        return self._ui_file_count

    def get_ui_files(self):
        """
        Devuelve una lista con los objetos ``ExplorerItem`` de TODOS los
        archivos que existen actualmente en la UI.

        No crea copias de los archivos ni copia sus bytes.
        Cada objeto conserva sus datos originales:
            ``name``, ``internal_name``, ``path``, ``offset``,
            ``length``, ``num_file``, ``parent``, etc.
        """
        result = []

        stack = [self.root]
        while stack:
            current = stack.pop()

            for child in current.children:
                if child.is_folder():
                    stack.append(child)
                else:
                    result.append(child)

        return result

    def get_file_info_by_internal_name(self, internal_name, include_bytes=False):
        """
        Busca un archivo de la UI por ``internal_name`` y devuelve toda
        la información útil del objeto.

        Ejemplo:
            info = self.get_file_info_by_internal_name("123-7B.unk")

        Resultado:
            {
                "visible_name": ...,
                "internal_name": ...,
                "offset": ...,
                "length": ...,
                "size": ...,
                "num_file": ...,
                "path": ...,
                "virtual_path": ...,
                "physical_path": ...,
                "parent": ...,
                "item": ...,
                "is_imported": ...
            }

        ``path`` y ``virtual_path`` son la ruta dentro de la UI.
        ``physical_path`` es la ruta física original, cuando existe.

        Por defecto NO se leen los bytes para evitar cargar archivos grandes
        innecesariamente. Con ``include_bytes=True`` se añade ``"data"``.
        """
        if internal_name is None:
            return None

        key = str(internal_name).strip().casefold()
        if not key:
            return None

        item = self._file_by_internal_name.get(key)
        if item is None:
            return None

        new_entry = self.new_files.get(item.internal_name)
        new_data = (
            new_entry.get("bytes")
            if isinstance(new_entry, dict)
            else None
        )

        imported_data = self.imported_files.get(item.internal_name)

        # Tamaño efectivo del archivo.
        if new_data is not None:
            size = len(new_data)
        elif imported_data is not None:
            size = len(imported_data)
        elif item.length is not None:
            try:
                size = int(item.length)
            except (TypeError, ValueError):
                size = None
        elif item.path is not None:
            try:
                size = item.path.stat().st_size if item.path.exists() else None
            except OSError:
                size = None
        else:
            size = None

        virtual_path = self.item_path(item)

        info = {
            "visible_name": item.name,
            "name": item.name,
            "internal_name": item.internal_name,
            "offset": item.offset,
            "length": item.length,
            "size": size,
            "num_file": item.num_file,

            # Ruta/ubicación dentro de la UI.
            "path": virtual_path,
            "virtual_path": virtual_path,
            "parent_path": (
                self.item_path(item.parent)
                if item.parent is not None
                else None
            ),

            # Ruta física original, si el archivo la tiene.
            "physical_path": (
                str(item.path)
                if item.path is not None
                else None
            ),

            "parent": item.parent,
            "item": item,
            "is_imported": imported_data is not None,
            "is_new": new_entry is not None,
        }

        # Mantener actualizada la información del diccionario de archivos
        # nuevos, especialmente la ruta virtual si el archivo fue movido.
        if new_entry is not None and isinstance(new_entry, dict):
            new_entry["info"] = {
                **new_entry.get("info", {}),
                "visible_name": item.name,
                "name": item.name,
                "internal_name": item.internal_name,
                "offset": item.offset,
                "length": item.length,
                "size": size,
                "num_file": item.num_file,
                "physical_path": (
                    str(item.path) if item.path is not None else None
                ),
                "virtual_path": virtual_path,
                "path": virtual_path,
                "parent_path": (
                    self.item_path(item.parent)
                    if item.parent is not None
                    else None
                ),
                "item": item,
                "is_new": True,
            }

        if include_bytes:
            if new_data is not None:
                info["data"] = new_data
            elif imported_data is not None:
                info["data"] = imported_data
            else:
                try:
                    info["data"] = self.get_file_bytes(item)
                except Exception:
                    info["data"] = None

        return info

    def get_all_ui_file_info(self, include_bytes=False):
        """
        Devuelve la información de TODOS los archivos de la UI.

        Cada elemento de la lista usa el mismo formato que
        ``get_file_info_by_internal_name()``.
        """
        result = []

        for item in self.get_ui_files():
            info = self.get_file_info_by_internal_name(
                item.internal_name,
                include_bytes=include_bytes,
            )
            if info is not None:
                result.append(info)

        return result

    def guardar(self):
        """
        Punto de entrada del botón "💾 Guardar".

        Este metodo está preparado para que puedas colocar aquí tu lógica
        de guardado/reconstrucción. NO reconstruye ni escribe la ISO por sí
        mismo.

        Dentro del metodo tienes acceso directo a:

            self.ram_source
                -> objeto original que contiene los datos de la RAM/packfile.

            self.imported_files
                -> diccionario de reemplazos en memoria.
                   La clave es ``internal_name`` y el valor son los bytes.

            ui_files
                -> lista de todos los archivos actualmente presentes en la UI.

            file_count
                -> cantidad total de archivos actualmente presentes.

        Para buscar un archivo concreto:

            info = self.get_file_info_by_internal_name("1-1.unk")

        Y ``info`` contiene nombre visible, nombre interno, offset, tamaño,
        ruta virtual, ruta física, num_file, ExplorerItem, etc.
        """

        # ----------------------------------------------------
        # Variables disponibles directamente para tu código.
        # ----------------------------------------------------
        ram_source = self.ram_source
        imported_files = self.imported_files
        new_files = self.new_files
        ui_files = self.get_ui_files()
        paddings = self.paddings

        # Actualizar la información de los archivos nuevos antes de que tu
        # lógica de guardado la utilice. Esto mantiene al día, por ejemplo,
        # la ruta virtual si el archivo fue movido después de insertarlo.
        for new_item in ui_files:
            if new_item.internal_name in new_files:
                self.get_file_info_by_internal_name(
                    new_item.internal_name,
                    include_bytes=False,
                )

        file_count = self.get_ui_file_count()

        # ``new_files`` contiene directamente los bytes y la información
        # de cada archivo insertado.
        #
        # Ejemplo:
        #     for internal_name, entry in new_files.items():
        #         data = entry["bytes"]
        #         info = entry["info"]
        #
        #     info["visible_name"]
        #     info["internal_name"]
        #     info["offset"]
        #     info["length"]
        #     info["num_file"]
        #     info["physical_path"]
        #     info["virtual_path"]
        #
        # Ejemplo de búsqueda por nombre interno:
        #
        # info = self.get_file_info_by_internal_name("1-1.unk")
        #
        # Ejemplo de acceso a un dato concreto:
        #
        # if info is not None:
        #     visible_name = info["visible_name"]
        #     internal_name = info["internal_name"]
        #     offset = info["offset"]
        #     size = info["size"]
        #     route = info["path"]
        #
        # ----------------------------------------------------
        # COLOCA AQUÍ TU CÓDIGO DE GUARDADO.
        # ----------------------------------------------------
        QMessageBox.information(self, "Reconstruir-PackFile", "Asegurate de no tener la ISO orginal abierta en otro software,\nmientras se termina esta tarea")

        iso_explorer = ram_source.psp_iso_explorer

        source_new = bytearray()
        address_files = []
        nt_fd_files = []
        offset_actual = 0
        # with open(iso_explorer.iso_path, "rb") as f:
        for i in range(1, file_count+1):
            name = f"{i}-{i:X}.unk"

            # Buscar en new_files
            data = new_files.get(name)

            if data is not None:
                data_file = data["bytes"]

            else:
                # Buscar en imported_files
                data_file = imported_files.get(name)

                if data_file is None:
                    # Buscar en los archivos originales
                    info = self.get_file_info_by_internal_name(name)

                    if info is not None:
                        offset:int = info["offset"]
                        offset -= ram_source.packfile_offset
                        size:int = info["size"]
                        data_file = ram_source[offset:offset + size]
                        #leer el iso fisico, evita recalcular los offset, en caso de reconstruir iso
                        # f.seek(offset)
                        # data_file = f.read(size)
                    else:
                        nt_fd_files.append(name)
                        continue

            # Agregar archivo
            size = len(data_file)
            source_new += bytearray(data_file)

            # Padding hasta múltiplo de 0x800
            padding = (-size) % 0x800
            source_new += b"\x00" * padding

            # agregar padding extra
            add_padding:int = paddings.get(name, 0)
            if add_padding is not None and add_padding > 0:
                add_padding*=0x800
                source_new += b"\x00" * add_padding

            # Registrar información
            address_files.append((offset_actual, size, name))
            offset_actual += size + padding + add_padding

        # header
        data_indices = bytearray()
        key_ttt = struct.unpack("<I", ram_source[0:4])[0]
        num_files_validos = len(address_files)
        data_indices.extend(struct.pack("<I", key_ttt))
        data_indices.extend(struct.pack("<I", num_files_validos))
        data_indices.extend(b"\x00" * 8)

        #indices
        size_indices = num_files_validos*0x10
        size_indices+=0x10
        remainder = size_indices % 0x800
        if remainder != 0:
            padding = 0x800 - remainder
            size_indices += padding

        # minimo 38000 bytes para 0x3711 archivos
        if size_indices < 0x38000: size_indices = 0x38000
        self.set_packfile_header_size(size_indices)
        iso_explorer.set_packfile_header_size(size_indices)

        d_c = DataConvert(None)
        for i in range(num_files_validos):
            offset = d_c.getOffsetConvert(
                encript_ttt=True,
                val=(address_files[i][0] + ram_source.packfile_offset + size_indices)//0x800,
                key=key_ttt,
                base_offset=(ram_source.packfile_offset + size_indices)//0x800
            )

            long = d_c.getSizeConvert(
                desincript_ttt=True,
                key=f"{i}",
                bitR=address_files[i][1]
            )

            data_indices.extend(struct.pack("<I", offset))
            data_indices.extend(struct.pack("<I", long))
            data_indices.extend(struct.pack("<I", key_ttt))
            data_indices.extend(b"\x00" * 4)

        # padding para header de indices
        padding = size_indices-len(data_indices)
        if padding < 0:
            raise ValueError(f"Valor negativo: size_indices - data_indices\n{size_indices:X} - {len(data_indices):X} = {padding}")
        if padding > 0:
            data_indices.extend(b"\x00" * padding)
        source_new = data_indices + source_new

        # ------------------------------------------------------------
        # Crear un NUEVO buffer para el resultado reconstruido.
        #
        # ram_source es el buffer ORIGINAL y NO se modifica.
        # El nuevo buffer se entrega al IsoExplorer únicamente para que
        # sea usado como fuente del PACKFILE que se reconstruirá en la ISO.
        # ------------------------------------------------------------
        if iso_explorer is None:
            raise RuntimeError(
                "No existe el IsoExplorer asociado."
            )

        new_packfile_buffer = PackFileBuffer(
            bytearray(source_new),
            packfile_offset=ram_source.packfile_offset,
            iso_size=ram_source.iso_size,
            path=ram_source.path,
            contenedor=iso_explorer,
        )

        # NO hacer: ram_source.data[:] = source_new
        # ram_source continúa conteniendo el PACKFILE original.
        #
        # El nuevo buffer se conserva en IsoExplorer separado del
        # buffer original (self.packfile_buffer).
        iso_explorer.new_packfile_buffer = new_packfile_buffer
        iso_explorer.apply_packfile_buffer(new_packfile_buffer)

        self.status_label.setText(
            f"Guardar | PACKFILE.BIN actualizado | "
            f"{len(source_new):,} bytes"
        )

        if nt_fd_files:
            self.mostrar_lista(nt_fd_files)

        # build iso
        iso_explorer.rebuild_iso()

    def mostrar_lista(self, lista):
        dialog = QDialog(self)
        dialog.setWindowTitle("Reconstruir-PackFile")
        dialog.resize(700, 500)

        layout = QVBoxLayout(dialog)

        text = QTextEdit()
        text.setReadOnly(True)

        contenido = (
                f"Archivos eliminados por el usuario: {len(lista)}\n\n"
                + "\n".join(map(str, lista))
        )

        text.setPlainText(contenido)

        layout.addWidget(text)

        button = QPushButton("Cerrar")
        button.clicked.connect(dialog.accept)
        layout.addWidget(button)

        dialog.exec_()

    # ========================================================
    # REFRESCAR
    # ========================================================

    def refresh(self):
        self.refresh_current_folder()
        self.update_favorites()
        self.path_label.setText(self.item_path(self.current_folder))

    # ========================================================
    # JSON
    # ========================================================

    def serialize_item(self, item):
        data = {
            "name": item.name,
            "type": item.item_type,
        }

        if item.item_type == "file":
            data["path"] = str(item.path) if item.path else None

            data["internal_name"] = item.internal_name
            data["offset"] = item.offset
            data["length"] = item.length
            data["num_file"] = item.num_file

        if item.is_folder():
            data["children"] = [self.serialize_item(c) for c in item.children]

        return data

    def export_structure(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar estructura",
            "explorer_structure.json",
            "JSON (*.json)"
        )
        if not filename:
            return

        data = {
            "version": 2,
            "root": self.serialize_item(self.root),
            "favorites": [self.item_path(x) for x in self.favorites],
        }

        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "Exportado", "Estructura exportada correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def import_structure(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Abrir estructura",
            "",
            "JSON (*.json)"
        )
        if not filename:
            return

        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.root = self.deserialize_item(data["root"], None)
            self.new_files.clear()
            self._rebuild_item_index()
            self.packfile_list_path = None
            self.favorites = [self.root]

            for path in data.get("favorites", []):
                item = self.find_by_virtual_path(path)
                if item:
                    self.favorites.append(item)

            self.history = [self.root]
            self.history_index = 0
            self.current_folder = self.root
            self.refresh_current_folder()
            self.update_favorites()
            self.path_label.setText(self.item_path(self.root))
            self.update_navigation_buttons()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo importar:\n{e}")

    def deserialize_item(self, data, parent):
        item = ExplorerItem(
            data["name"],
            data["type"],
            data.get("path"),
            parent,
            internal_name=data.get(
                "internal_name",
                data["name"]
            ),
            offset=data.get("offset"),
            length=data.get("length"),
            num_file=data.get("num_file"),
        )

        for child_data in data.get("children", []):
            child = self.deserialize_item(child_data, item)
            item.add_child(child)

        return item

    # ========================================================
    # UTILIDADES
    # ========================================================

    @staticmethod
    def name_exists(parent, name):
        name_key = str(name).casefold()
        name_set = getattr(parent, "_child_name_set", None)
        if name_set is not None:
            return name_key in name_set

        return any(c.name.casefold() == name_key for c in parent.children)

    @staticmethod
    def item_size(item):
        """
        Devuelve el tamaño que se muestra en la columna "Tamaño".

        Para archivos RAM usa ``item.length``, que corresponde al segundo
        valor de la entrada ``(offset, length, num_file)``.
        Para archivos físicos usa el tamaño real del archivo.
        Las carpetas no muestran tamaño.
        """
        if item.is_folder():
            return ""

        # Archivos definidos desde RAM:
        # (offset, length, num_file) -> length es el tamaño del archivo.
        if item.length is not None:
            try:
                return ExplorerWindow.format_size(int(item.length))
            except (TypeError, ValueError):
                pass

        # Archivos físicos normales.
        if item.path and item.path.exists():
            try:
                return ExplorerWindow.format_size(item.path.stat().st_size)
            except OSError:
                pass

        return ""

    @staticmethod
    def format_size(size):
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.2f} KB"
        if size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        return f"{size / (1024 * 1024 * 1024):.2f} GB"

    @staticmethod
    def all_items(item):
        result = []
        for child in item.children:
            result.append(child)
            if child.is_folder():
                result.extend(ExplorerWindow.all_items(child))
        return result

    def find_by_id(self, item, item_id):
        # ``item`` se conserva por compatibilidad con el código existente.
        # La búsqueda real usa el índice O(1).
        return self._item_by_id.get(item_id)

    def item_path(self, item):
        parts = []
        current = item
        while current is not None and current is not self.root:
            parts.append(current.name)
            current = current.parent
        parts.reverse()
        return "ROOT" if not parts else "ROOT / " + " / ".join(parts)

    def find_by_virtual_path(self, path):
        normalized = str(path).replace("\\", "/")
        parts = [p for p in normalized.split("/") if p and p != "ROOT"]

        current = self.root
        for part in parts:
            found = next((c for c in current.children if c.name == part), None)
            if found is None:
                return None
            current = found
        return current


# ============================================================
# MAIN
# ============================================================

def mostrar_explorador(files_list=None, app=None, ram_source=None):
    """
    Abre el explorador usando una lista de archivos RAM y, opcionalmente,
    un objeto padre que contiene los bytes reales del packfile.

    ``ram_source`` debe exponer ``packfile_offset`` y permitir slicing,
    por ejemplo ``ram_source[offset:end]``.

    Ejemplo:

        lista_archivos = [
            (0x1000, 0x40, 1),
            (0x1040, 0x80, 2),
            (0x10C0, 0x20, 15),
        ]

        window = mostrar_explorador(
            lista_archivos,
            ram_source=self,
        )

    ``ram_source`` es el objeto padre que contiene el buffer del packfile.
    Se usa únicamente para leer bytes y debe tener ``packfile_offset`` y
    soportar slicing.

    La lista es convertida a ExplorerItem y cada archivo conserva:
        offset, length, num_file, internal_name
    """
    if app is None:
        app = QApplication.instance()

        if app is None:
            app = QApplication(sys.argv)
            app.setStyle("Fusion")

    window = ExplorerWindow(
        files_list=files_list,
        ram_source=ram_source,
    )
    window.show()

    return window


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = mostrar_explorador(app=app)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
