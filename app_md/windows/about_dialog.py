from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt

class AboutDialog(QDialog):
    def __init__(self, contenedor):
        super().__init__()

        self.contenedor = contenedor

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
       
        self.setWindowTitle("About")
        self.setWindowIcon(QIcon(str(self.contenedor.icon)))  

        # Crear el layout principal
        main_layout = QVBoxLayout()

        # Crear un layout horizontal para logo y texto
        logo_text_layout = QHBoxLayout()

        # Cargar el logo
        logo_pixmap = QPixmap(str(self.contenedor.icon))  
        logo_label = QLabel()
        logo_label.setPixmap(logo_pixmap)
        logo_label.setFixedHeight(200)  

        # Crear el texto
        text_label = QLabel()
        text_label.setText(
            "<b>Editor Indice Tag Team</b><br>"
            f"Version {self.contenedor.version}<br><br>"
            "This program aims to allow the user to modify<br>files within the PACKFILE.BIN of the ISO.<br><br>"
            "<a href='https://github.com/kastomd/Editor_indice_Py'>GitHub</a> | "
            "<a href='https://www.youtube.com/@KASTOMODDER15'>Kasto_md</a><br><br>"
            "Data or support:<br>"
            "<a href='https://www.youtube.com/@los-ijue30s'>Los ijue30s</a>"
        )
        text_label.setTextFormat(Qt.RichText)
        text_label.setTextInteractionFlags(Qt.TextBrowserInteraction)

        text_label.setOpenExternalLinks(True)

        # Agregar el logo y el texto al layout horizontal
        logo_text_layout.addWidget(logo_label)
        logo_text_layout.addWidget(text_label)

        # Agregar el layout horizontal al layout principal
        main_layout.addLayout(logo_text_layout)

        # Establecer el layout del diálogo
        self.setLayout(main_layout)

    def show_about(self):
        self.exec_()
