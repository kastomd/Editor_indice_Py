import os
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton,
    QFileDialog, QLabel, QMessageBox
)
from PyQt5.QtCore import Qt

BASE_SCR = Path(__file__).parent / "scr"
ANIM_LIST_FILE = BASE_SCR / "anim0.txt"


class Anims0(QWidget):
    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowMinimizeButtonHint
        )
        self.setWindowTitle("Anims0 - Vaciar animaciones")
        self.setFixedSize(360, 180)

        self.anim_folder = None

        layout = QVBoxLayout()
        layout.setSpacing(14)

        self.label = QLabel("No se ha seleccionado ninguna carpeta")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        btn_select = QPushButton("Seleccionar carpeta de Animaciones")
        btn_select.setFixedHeight(36)
        btn_select.clicked.connect(self.select_folder)
        layout.addWidget(btn_select)

        btn_process = QPushButton("Procesar")
        btn_process.setFixedHeight(36)
        btn_process.clicked.connect(self.process_anims)
        layout.addWidget(btn_process)

        self.setLayout(layout)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Selecciona la carpeta de animaciones"
        )
        if not folder:
            return

        self.anim_folder = Path(folder)
        self.label.setText(f"Carpeta seleccionada:\n{folder}")

    def process_anims(self):
        if not self.anim_folder:
            QMessageBox.warning(self, "Aviso", "Selecciona primero una carpeta de animaciones.")
            return

        if not ANIM_LIST_FILE.exists():
            QMessageBox.critical(
                self,
                "Error",
                f"No se encontró el archivo:\n{ANIM_LIST_FILE}"
            )
            return

        # Leer lista de animaciones
        with open(ANIM_LIST_FILE, "r", encoding="utf-8", errors="ignore") as f:
            names = [line.strip() for line in f if line.strip()]

        if not names:
            QMessageBox.warning(self, "Aviso", "La lista anim0.txt está vacía.")
            return

        processed = 0

        for base_name in names:
            for ext in (".anm", ".tanm", ".canm"):
                anim_path = self.anim_folder / (base_name + ext)
                if anim_path.exists() and anim_path.is_file():
                    # Vaciar archivo → 0 bytes
                    open(anim_path, "wb").close()
                    processed += 1
                    break

        QMessageBox.information(
            self,
            "Completado",
            f"Proceso finalizado.\nAnimaciones procesadas: {processed}"
        )
