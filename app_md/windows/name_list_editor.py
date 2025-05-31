from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QWidget, QPushButton, QHBoxLayout,
    QVBoxLayout, QTabWidget, QGridLayout, QLineEdit, QScrollArea, QComboBox,
    QDialog
)

class NameListEditor(QDialog):
    def __init__(self, contenedor):
        super().__init__()

        self.contenedor = contenedor

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.setWindowTitle("Name List Editor")
        self.setWindowIcon(QIcon(str(self.contenedor.icon)))

        # Layout principal
        main_layout = QVBoxLayout()

        self.listpack = Path(__file__).resolve().parent / "scr"

        # Parte superior: 3 botones horizontales
        top_button_layout = QHBoxLayout()
        top_button_layout.addWidget(QPushButton("Save"))
        top_button_layout.addWidget(QPushButton("Import"))
        
        combo_box = QComboBox()
        combo_box.setMaximumWidth(150)
        combo_box.setMinimumWidth(100)

        # agrega las opciones
        optionsCombobox = [archivo.stem for archivo in self.listpack.glob("*.txt")]
        for i in optionsCombobox:
            combo_box.addItem(i)

        combo_box.currentTextChanged.connect(self.on_combo_text_changed)

        top_button_layout.addWidget(combo_box)

        main_layout.addLayout(top_button_layout)

        # Tabs
        self.tabs = QTabWidget()
        categorias = self.extract_dynamic_categories(self.listpack / f"{optionsCombobox[0]}.txt")
        for cat, items in categorias.items():
            self.tabs.addTab(self.create_scrollable_grid_tab(rows=items), f"{cat}")

        

        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)
        self.resize(500, 300)

    def on_combo_text_changed(self, text):
        # Limpiar las tabs existentes
        self.tabs.clear()

        # Volver a llenar con nuevas categorias
        categorias = self.extract_dynamic_categories(self.listpack / f"{text}.txt")
        for cat, items in categorias.items():
            self.tabs.addTab(self.create_scrollable_grid_tab(rows=items), f"{cat}")

    def create_scrollable_grid_tab(self, rows):
        # Widget principal del tab
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)

        # Crear contenedor para la grilla
        grid_container = QWidget()
        grid_layout = QGridLayout(grid_container)

        # Crear grilla con 2 columnas y 'rows' filas
        for row in range(len(rows)):
            for col in range(2):
                line_edit = QLineEdit(rows[row][col])
                grid_layout.addWidget(line_edit, row, col)

        # ScrollArea que contiene el widget con grilla
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(grid_container)

        layout.addWidget(scroll_area)
        return tab_widget

    def extract_dynamic_categories(self, ruta_txt):
        categorias = {}
        categoria_actual = None

        with open(ruta_txt, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue  # Saltar lineas vacias

                # Detectar nueva categoria (termina con ":" y es una palabra)
                if linea.endswith(":"):
                    categoria_actual = linea[:-1]
                    if categoria_actual not in categorias:
                        categorias[categoria_actual] = []
                    continue

                # Si estamos dentro de una categoría, extraer pares clave-valor
                if categoria_actual and ":" in linea:
                    clave, valor = map(str.strip, linea.split(":", 1))
                    categorias[categoria_actual].append((clave, valor))

        return categorias


    def show_exr(self):
            self.exec_()
