﻿from pathlib import Path
import sys
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from app_md.logic_extr.ex_renamer import ExRenamer
from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QMessageBox, QWidget, QPushButton, QHBoxLayout,
    QVBoxLayout, QTabWidget, QGridLayout, QLineEdit, QScrollArea, QComboBox,
    QDialog
)

class NameListEditor(QDialog):
    def __init__(self, contenedor):
        super().__init__()
        self.exRem = ExRenamer(self)

        self.contenedor = contenedor

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.setWindowTitle("Name List Editor")
        self.setWindowIcon(QIcon(str(self.contenedor.icon)))

        # Layout principal
        main_layout = QVBoxLayout()

        # self.listpack = Path(__file__).resolve().parent / "scr"
        self.listpack = self.get_base_path() / "scr"
        self.listpack.mkdir(parents=True, exist_ok=True)
        self.copy_files(path_folder=self.listpack)

        # Parte superior: 3 botones horizontales
        top_button_layout = QHBoxLayout()
        save_button = QPushButton("Save as")
        save_button.clicked.connect(self.save_as)
        top_button_layout.addWidget(save_button)
        
        self.combo_box = QComboBox()
        self.combo_box.setMaximumWidth(150)
        self.combo_box.setMinimumWidth(100)

        # agrega las opciones
        optionsCombobox = [archivo.stem for archivo in self.listpack.glob("*.txt")]
        for i in optionsCombobox:
            self.combo_box.addItem(i)

        self.combo_box.currentTextChanged.connect(self.on_combo_text_changed)

        top_button_layout.addWidget(self.combo_box)

        main_layout.addLayout(top_button_layout)

        # Tabs
        self.tabs = QTabWidget()
        categorias = self.extract_dynamic_categories(self.listpack / f"{optionsCombobox[0]}.txt")
        for cat, items in categorias.items():
            self.tabs.addTab(self.create_scrollable_grid_tab(rows=items), f"{cat}")

        

        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)
        self.resize(600, 350)

    def get_base_path(self):
        if getattr(sys, 'frozen', False):
            # Ejecutable generado (e.g., PyInstaller)
            return Path(sys.executable).parent
        else:
            # Script .py normal
            return Path(__file__).resolve().parent

    def copy_files(self, path_folder: Path):
        folder_rename = Path(__file__).resolve().parent / "scr"

        name_files = [archivo.name for archivo in folder_rename.glob("*") if archivo.is_file()]
        
        for name in name_files:
            file_path = path_folder / name
            if not file_path.is_file():
                with open(folder_rename / name, "rb") as f_r:
                    with open(file_path, "wb") as f_w:
                        f_w.write(f_r.read())

    def on_combo_text_changed(self, text):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        # Limpiar las tabs existentes
        self.tabs.clear()

        # Volver a llenar con nuevas categorias
        categorias = self.extract_dynamic_categories(self.listpack / f"{text}.txt")
        for cat, items in categorias.items():
            self.tabs.addTab(self.create_scrollable_grid_tab(rows=items), f"{cat}")

        QApplication.restoreOverrideCursor()

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

        with open(ruta_txt, "r", encoding="utf-8-sig") as f:
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

    def save_as(self):
        name_file = f"{self.combo_box.currentText()}.txt"
        # print(self.get_dynamic_categories())
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save as",
            name_file,  # Nombre sugerido
            "All files (*)"
        )

        if not filepath:
            return

        try:
            with open(filepath, 'w', encoding='utf-8-sig') as f:
                total_tabs = self.tabs.count()

                for i in range(total_tabs):
                    categoria = self.tabs.tabText(i)
                    f.write(f"{categoria}:\n")

                    tab_widget = self.tabs.widget(i)
                    scroll_area = tab_widget.layout().itemAt(0).widget()
                    grid_container = scroll_area.widget()
                    grid_layout = grid_container.layout()

                    for row in range(grid_layout.rowCount()):
                        index_widget = grid_layout.itemAtPosition(row, 0).widget()
                        name_widget = grid_layout.itemAtPosition(row, 1).widget()

                        if index_widget and name_widget:
                            index = index_widget.text()
                            name = name_widget.text()
                            f.write(f"{index}: {name}\n")

                    # Solo agregar salto de linea entre categorias, excepto en la ultima
                    if i < total_tabs - 1:
                        f.write("\n")
        except Exception as e:
            QMessageBox.information(self, "Error", f"{e}")

        QMessageBox.information(self, "Success", "Saved.")

    def show_exr(self):
        self.combo_box.currentTextChanged.disconnect(self.on_combo_text_changed)

        # agrega las opciones
        optionsCombobox = [archivo.stem for archivo in self.listpack.glob("*.txt")]
        self.combo_box.clear()
        for i in optionsCombobox:
            self.combo_box.addItem(i)

        self.on_combo_text_changed(text=optionsCombobox[0])

        self.combo_box.currentTextChanged.connect(self.on_combo_text_changed)
        self.exec_()
