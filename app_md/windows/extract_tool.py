from pathlib import Path
from PyQt5.QtGui import QCursor, QKeySequence
from PyQt5.QtWidgets import QAction, QApplication, QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMenuBar, QMessageBox, QPushButton, QVBoxLayout
from PyQt5.QtCore import QThreadPool, Qt, pyqtSignal

from app_md.logic_extr.data_file_manager import DataFileManager
from app_md.logic_extr.data_convert import DataConvert
from app_md.logic_iso.worker import Worker

class ExtractTool(QDialog):
    def __init__(self, window=None):
        super().__init__()
        self.path_file = None
        self.contenedor = window
        self.setAcceptDrops(True)

        self.datafilemanager = DataFileManager()
        self.dataconvert = DataConvert(self)
        self.thread_pool = QThreadPool()

        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint |
                            Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)

        self.setWindowIcon(self.contenedor.windowIcon())
        self.setFont(self.contenedor.font())
        self.setWindowTitle("Extract tool")
        self.setFixedSize(420, 300)

        # Layout principal
        layout = QVBoxLayout()

        # Menu
        self.menu_bar = QMenuBar(self)
        file_menu = QMenu("File", self)
        action_salir = QAction("Exit", self)
        action_salir.triggered.connect(self.close)
        action_salir.setShortcut(QKeySequence("Ctrl+W"))

        action_close_fil = QAction("Close file", self)
        action_close_fil.triggered.connect(self.close_file)

        tool_menu = QMenu("Tool", self)
        action_edit = QAction("Editor indice", self)
        action_edit.triggered.connect(self.contenedor.to_the_front)
        action_edit.setShortcut(QKeySequence("Ctrl+E"))

        file_menu.addAction(action_close_fil)
        file_menu.addAction(action_salir)
        tool_menu.addAction(action_edit)
        self.menu_bar.addMenu(file_menu)
        self.menu_bar.addMenu(tool_menu)

        layout.setMenuBar(self.menu_bar)

        # Contenedor de arrastrar y soltar
        drop_frame = ClickableFrame()
        drop_frame.clicked.connect(self.open_file_choose)

        drop_frame.setStyleSheet("""
            QFrame {
                border: 2px dashed #eeefef;
                border-radius: 10px;
            }
        """)
        drop_frame.setMinimumSize(400, 200)

        drop_layout = QVBoxLayout()
        self.drop_label = QLabel("Drop a file here or click to open")
        self.drop_label.setAlignment(Qt.AlignCenter)
        self.drop_label.setWordWrap(True)

        drop_layout.addWidget(self.drop_label)

        # Botones
        buttons_layout = QHBoxLayout()
        btn_extraer = QPushButton("Extract")
        btn_extraer.clicked.connect(self.extract_file)
        btn_comprimir = QPushButton("Compress")
        btn_comprimir.clicked.connect(self.compress_file)

        buttons_layout.addWidget(btn_extraer)
        buttons_layout.addWidget(btn_comprimir)
        drop_layout.addLayout(buttons_layout)
        drop_frame.setLayout(drop_layout)

        layout.addWidget(drop_frame)

        self.ischeckbox = False
        self.pad_to_16_checkbox = QCheckBox("Padding to 16")
        self.pad_to_16_checkbox.stateChanged.connect(self.on_pad_checkbox_changed)
        layout.addWidget(self.pad_to_16_checkbox, alignment=Qt.AlignBottom | Qt.AlignLeft)

        self.setLayout(layout)

    def on_pad_checkbox_changed(self, state):
        self.ischeckbox = (state == Qt.Checked)
        # print(state == Qt.Checked)

    def extract_file(self):
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        
        if not self.path_file:
            self.contenedor.success_dialog(vaule=["open a file first"],title="Warning!")
            return
        
        #crear una tarea asincrona
        worker = Worker(self.dataconvert.load_offsets)
        worker.signals.resultado.connect(self.contenedor.success_dialog)
        worker.signals.error.connect(self.contenedor.manejar_error)
        self.thread_pool.start(worker)


    def compress_file(self):
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        if not self.path_file:
            self.contenedor.success_dialog(vaule=["open a file first"],title="Warning!")
            return

        # self.dataconvert.import_config()
        #crear una tarea asincrona
        worker = Worker(self.dataconvert.import_config)
        worker.signals.resultado.connect(self.contenedor.success_dialog)
        worker.signals.error.connect(self.contenedor.manejar_error)
        self.thread_pool.start(worker)

    def open_file_choose(self, view=True, file_path=None):
        if view: file_path, _ = QFileDialog.getOpenFileName(self, "Choose a file", "", "All files (*)")
        if file_path:
            self.path_file = Path(file_path)
            f_der = "folder" if self.path_file.is_dir() else "file"
            self.drop_label.setText(f"{f_der}: {file_path}")
            self.contenedor.success_dialog([f"{f_der} opened"])

    def show_extract(self):
        self.show()

        # Si esta minimizada, la restauramos
        if self.windowState() & Qt.WindowMinimized:
            self.setWindowState(Qt.WindowNoState)
        self.raise_()
        self.activateWindow()

    def dragEnterEvent(self, event):
        #verifica si lo arrastrado son archivos
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        #verifica y asigna un solo archivo arrastrado
        urls = event.mimeData().urls()
    
        if len(urls) != 1:
            self.contenedor.manejar_error("Only one file is allowed.")
            return  # Ignora si hay mas de uno

        reply = self.contenedor.question_dialog(content="Are you sure you want to open the file?")
        if reply == QMessageBox.Cancel:
            return

        #asginar path del archivo
        filepath = urls[0].toLocalFile()
        self.open_file_choose(view=False,file_path=filepath)

    def closeEvent(self, event):
        reply = self.contenedor.question_dialog(content="Are you sure you want to close the Extract application?",title="Confirm exit")

        if reply == QMessageBox.Ok:
            event.accept()
        else:
            event.ignore()

    def close_file(self):
        if not self.path_file:
            return

        reply = self.contenedor.question_dialog(content="Are you sure you want to close the file?")

        if reply == QMessageBox.Cancel:
            return

        self.drop_label.setText("Drop a file here")
        self.path_file = None

        self.contenedor.success_dialog(["path file reset"])




class ClickableFrame(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def mousePressEvent(self, event):
        self.clicked.emit()