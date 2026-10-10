from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QWidget,
    QFrame,
    QAbstractItemView,
)
from PyQt5.QtCore import Qt


class PathOrderDialog(QDialog):

    def __init__(self, paths, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Ordenar archivos")
        self.resize(850, 600)

        self.paths = list(paths)

        # ==================================================
        # LAYOUT PRINCIPAL
        # ==================================================

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Orden de los archivos")
        title.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
            }
        """)

        layout.addWidget(title)

        info = QLabel(
            "Arrastra los archivos para cambiar su orden."
        )

        info.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 12px;
            }
        """)

        layout.addWidget(info)

        # ==================================================
        # LISTA
        # ==================================================

        self.list_widget = ReorderListWidget()

        # Permitir seleccionar varios elementos con Ctrl/Shift
        self.list_widget.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )

        self.list_widget.setDragDropMode(
            QListWidget.InternalMove
        )

        self.list_widget.setDefaultDropAction(
            Qt.MoveAction
        )

        self.list_widget.setSpacing(4)

        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 6px;
                background: #202020;
            }

            QListWidget::item {
                border: none;
                padding: 0px;
            }

            QListWidget::item:selected {
                background: #3a6ea5;
                border-radius: 5px;
            }
        """)

        layout.addWidget(self.list_widget)

        # ==================================================
        # BOTONES
        # ==================================================

        buttons_layout = QHBoxLayout()

        self.btn_up = QPushButton("↑ Subir")
        self.btn_down = QPushButton("↓ Bajar")

        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Cancelar")

        self.btn_up.setMinimumWidth(100)
        self.btn_down.setMinimumWidth(100)

        self.btn_ok.setMinimumWidth(100)
        self.btn_cancel.setMinimumWidth(100)

        buttons_layout.addWidget(self.btn_up)
        buttons_layout.addWidget(self.btn_down)

        buttons_layout.addStretch()

        buttons_layout.addWidget(self.btn_cancel)
        buttons_layout.addWidget(self.btn_ok)

        layout.addLayout(buttons_layout)

        # ==================================================
        # CARGAR PATHS
        # ==================================================

        self.load_paths()

        # ==================================================
        # EVENTOS
        # ==================================================

        self.btn_up.clicked.connect(self.move_up)
        self.btn_down.clicked.connect(self.move_down)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        self.list_widget.model().rowsMoved.connect(
            self.update_positions
        )

        self.list_widget.itemSelectionChanged.connect(
            self.update_selection_style
        )

    def update_selection_style(self):

        selected_items = self.list_widget.selectedItems()

        selected_ids = {
            id(item)
            for item in selected_items
        }

        for i in range(self.list_widget.count()):

            item = self.list_widget.item(i)

            widget = self.list_widget.itemWidget(item)

            if widget is None:
                continue

            if id(item) in selected_ids:

                widget.setStyleSheet("""
                    QWidget#pathItem {
                        background-color: #3a6ea5;
                        border-radius: 5px;
                    }

                    QWidget#pathItem QLabel {
                        background-color: transparent;
                    }
                """)

            else:

                widget.setStyleSheet("""
                    QWidget#pathItem {
                        background-color: transparent;
                    }

                    QWidget#pathItem QLabel {
                        background-color: transparent;
                    }
                """)

    # ======================================================
    # CREAR ELEMENTO
    # ======================================================

    def create_item_widget(self, position, path):

        widget = QWidget()

        widget.setObjectName("pathItem")

        layout = QHBoxLayout(widget)

        layout.setContentsMargins(
            8, 7, 8, 7
        )

        layout.setSpacing(10)

        # ----------------------------------------------
        # POSICIÓN
        # ----------------------------------------------

        position_label = QLabel(
            f"{position:02d}"
        )

        position_label.setObjectName("positionLabel")
        position_label.setFixedWidth(35)

        position_label.setAlignment(
            Qt.AlignCenter
        )

        position_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: bold;
                color: #aaaaaa;
            }
        """)

        layout.addWidget(position_label)

        # ----------------------------------------------
        # INFORMACIÓN
        # ----------------------------------------------

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        filename = Path(path).name

        name_label = QLabel(filename)

        name_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #ffffff;
            }
        """)

        path_label = QLabel(str(path))

        path_label.setStyleSheet("""
            QLabel {
                font-size: 11px;
                color: #999999;
            }
        """)

        path_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        info_layout.addWidget(name_label)
        info_layout.addWidget(path_label)

        layout.addLayout(info_layout)

        # ----------------------------------------------
        # SEPARADOR
        # ----------------------------------------------

        line = QFrame()

        line.setFrameShape(
            QFrame.VLine
        )

        line.setStyleSheet("""
            QFrame {
                color: #444444;
            }
        """)

        layout.addWidget(line)

        return widget

    # ======================================================
    # CARGAR PATHS
    # ======================================================

    def load_paths(self):

        self.list_widget.clear()

        for i, path in enumerate(self.paths):

            item = QListWidgetItem()

            widget = self.create_item_widget(
                i + 1,
                path
            )

            item.setSizeHint(widget.sizeHint())

            item.setData(
                Qt.UserRole,
                path
            )

            self.list_widget.addItem(item)

            self.list_widget.setItemWidget(
                item,
                widget
            )

    # ======================================================
    # ACTUALIZAR POSICIONES
    # ======================================================

    def update_position_label(self, row):

        if row < 0 or row >= self.list_widget.count():
            return

        item = self.list_widget.item(row)
        widget = self.list_widget.itemWidget(item)

        if widget is None:
            return

        position_label = widget.findChild(
            QLabel,
            "positionLabel"
        )

        if position_label is not None:
            position_label.setText(
                f"{row + 1:02d}"
            )

    def update_positions(self, *args):

        # Se mantiene este metodo para el arrastrar y soltar.
        # Solo se actualizan las etiquetas de posición;
        # no se reconstruyen los widgets.
        for i in range(self.list_widget.count()):
            self.update_position_label(i)

        self.update_selection_style()

    # ======================================================
    # MOVER ELEMENTOS SELECCIONADOS
    # ======================================================

    def _move_selected(self, direction):

        selected = self.list_widget.selectedItems()

        if not selected:
            return

        # QListWidgetItem no es hashable en PyQt5.
        # Guardamos sus identificadores para comprobar pertenencia.
        selected_ids = {
            id(item)
            for item in selected
        }

        if direction < 0:
            # Al subir, procesamos de arriba hacia abajo.
            ordered = sorted(
                selected,
                key=lambda item: self.list_widget.row(item)
            )

            for item in ordered:

                row = self.list_widget.row(item)

                if row <= 0:
                    continue

                previous_item = self.list_widget.item(row - 1)

                # Si el elemento anterior también está seleccionado,
                # este elemento ya se moverá junto con él.
                if id(previous_item) in selected_ids:
                    continue

                self.list_widget.takeItem(row)

                self.list_widget.insertItem(
                    row - 1,
                    item
                )

        else:
            # Al bajar, procesamos de abajo hacia arriba.
            ordered = sorted(
                selected,
                key=lambda item: self.list_widget.row(item),
                reverse=True
            )

            last_row = self.list_widget.count() - 1

            for item in ordered:

                row = self.list_widget.row(item)

                if row >= last_row:
                    continue

                next_item = self.list_widget.item(row + 1)

                # Si el elemento siguiente también está seleccionado,
                # este elemento ya se moverá junto con él.
                if id(next_item) in selected_ids:
                    continue

                self.list_widget.takeItem(row)

                self.list_widget.insertItem(
                    row + 1,
                    item
                )

        # Actualizar únicamente las etiquetas de posición.
        # El ordenamiento ya terminó, por lo que no se reconstruyen
        # los widgets visuales.
        for i in range(self.list_widget.count()):
            self.update_position_label(i)

        # Mantener todos los elementos seleccionados.
        self.list_widget.clearSelection()

        for item in selected:
            item.setSelected(True)

        self.update_selection_style()

    # ======================================================
    # SUBIR
    # ======================================================

    def move_up(self):
        self._move_selected(-1)

    # ======================================================
    # BAJAR
    # ======================================================

    def move_down(self):
        self._move_selected(1)

    # ======================================================
    # OBTENER PATHS
    # ======================================================

    def get_paths(self):

        paths = []

        for i in range(
            self.list_widget.count()
        ):

            item = self.list_widget.item(i)

            path = item.data(
                Qt.UserRole
            )

            paths.append(path)

        return paths

class ReorderListWidget(QListWidget):

    def dropEvent(self, event):

        source_row = self.currentRow()

        if source_row < 0:
            event.ignore()
            return

        # Posición donde se está intentando soltar
        target_item = self.itemAt(event.position().toPoint())

        if target_item is None:
            event.ignore()
            return

        target_row = self.row(target_item)

        # Determinar si se está soltando arriba o abajo
        rect = self.visualItemRect(target_item)
        mouse_y = event.position().toPoint().y()

        if mouse_y < rect.center().y():
            drop_row = target_row
        else:
            drop_row = target_row + 1

        # ---------------------------------------------
        # Evitar moverlo a su propia posición
        # ---------------------------------------------

        if drop_row == source_row or drop_row == source_row + 1:
            event.ignore()
            return

        # ---------------------------------------------
        # Movimiento normal
        # ---------------------------------------------

        super().dropEvent(event)