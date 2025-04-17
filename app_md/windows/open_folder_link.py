import os
from PyQt5.QtWidgets import QDialog, QLabel, QVBoxLayout, QPushButton
from PyQt5.QtCore import Qt

class Open_folder_link(QDialog):
    def __init__(self, parent_font=None, parent_icon=None, direc="", messag=""):
        super().__init__()
        self.direc = direc
        self.message = messag
        self.init_ui()

        
        if parent_font:
            self.setFont(parent_font)
        if parent_icon:
            self.setWindowIcon(parent_icon)

    def init_ui(self):
        label = QLabel(self.message)
        label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        label.setOpenExternalLinks(False)
        label.linkActivated.connect(self.open_folder)

        
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.on_ok_clicked)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(ok_button)
        self.setLayout(layout)

        self.setWindowTitle("Success")
        self.resize(350, 100)
        self.setWindowFlags(Qt.Window | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)

    def open_folder(self):
        folder_path = self.direc
        if os.path.isdir(folder_path):
            os.startfile(folder_path)
        else:
            ValueError(f"The path no exist: {folder_path}")

    def on_ok_clicked(self):
        self.close()
