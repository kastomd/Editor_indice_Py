from pathlib import Path
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QPlainTextEdit, QPushButton
)

from app_md.base_app import QIcon

class ErrorDialog(QDialog):
    def __init__(self, mensaje, icon:Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Error")
        self.resize(500, 300)

        self.setWindowIcon(QIcon(str(icon)))

        layout = QVBoxLayout(self)

        self.text_area = QPlainTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.text_area.setPlainText(mensaje)

        self.text_area.setStyleSheet("color: red;")


        self.boton_cerrar = QPushButton("Cerrar")
        self.boton_cerrar.clicked.connect(self.accept)

        layout.addWidget(self.text_area)
        layout.addWidget(self.boton_cerrar)

# Ejemplo de uso:
#     dialogo = ErrorDialog(texto_largo)
#     dialogo.exec_()

