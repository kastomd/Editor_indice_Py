from pprint import pprint
import sys
import traceback
import qdarkstyle


from PyQt5.QtWidgets import QAction, QApplication, QFileDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSplashScreen, QVBoxLayout, QWidget
from PyQt5.QtGui import QFont, QGuiApplication, QIcon, QPixmap
from PyQt5.QtCore import QFile, Qt, QTimer, QThreadPool
from pathlib import Path
from app_md.windows.about_dialog import AboutDialog

from app_md.logic_iso.iso_reader import IsoReader
from app_md.windows.error_dialog import ErrorDialog
from app_md.logic_iso.data_convert import DataConvert
from app_md.logic_iso.worker import Worker
from app_md.logic_iso.data_file_manager import DataFileManager

import os
import shutil

class BaseApp:
    def __init__(self):
        self.path_iso = None
        self.version = "1.20250408"
        
        #icono de la app
        self.icon = Path(__file__).resolve().parent / "images" / "icon.ico"
        
        # Crear QApplication primero
        self.app = QApplication(sys.argv)

        # Aplicar tema oscuro de qdarkstyle
        self.app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())

        font = QFont("Cambria", 11)
        self.app.setFont(font)

        # Mostrar SplashScreen
        self.show_splash()

    def show_splash(self):
        # Cargar imagen del splash
        splash_pix = QPixmap(str(Path(__file__).resolve().parent / "images" / "splash.png"))
        self.splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        self.splash.showMessage("Cargando...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        self.splash.show()

        # Esperar 2 segundos y luego lanzar la ventana principal
        QTimer.singleShot(2000, self.start_main_window)

    def start_main_window(self):
        # Crear y mostrar ventana principal
        self.window = MainWindow(self)
        self.center_on_screen()
        
        
        self.init_menu()

        self.window.show()

        # Finalizar el splash
        self.splash.finish(self.window)

    def center_on_screen(self):
        screen = QGuiApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        window_geometry = self.window.frameGeometry()
        center_point = screen_geometry.center()
        window_geometry.moveCenter(center_point)
        self.window.move(window_geometry.topLeft())

    def run(self):
        sys.exit(self.app.exec_())

    def init_menu(self):
        # Menu principal
        menu_bar = self.window.menuBar()

        # Menu File
        file_menu = menu_bar.addMenu("File")
        openiso_action = QAction("Open iso", self.window)
        closeiso_action = QAction("Close iso", self.window)
        exit_action = QAction("Exit", self.window)

        openiso_action.triggered.connect(self.open_iso)
        closeiso_action.triggered.connect(self.close_iso)
        exit_action.triggered.connect(self.window.close)

        file_menu.addAction(openiso_action)
        file_menu.addAction(closeiso_action)
        file_menu.addAction(exit_action)

        # Menu About
        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About", self.window)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def show_about(self):
        self.about = AboutDialog(self)
        self.about.show_about()

    def open_iso(self):
        archivo, _ = QFileDialog.getOpenFileName(self.window, "Choose file iso", "", 
                                                 "All files (*);;iso file (*.iso)")
        if archivo:
            self.path_iso = archivo
            self.window.label.setPlainText(archivo)

    def close_iso(self):
        self.path_iso = None
        self.window.label.setPlainText("path iso")
        self.window.success_dialog(["path iso reseted"])

class MainWindow(QMainWindow):
    def __init__(self, contenedor):
        super().__init__()
        self.contenedor = contenedor
        self.version = self.contenedor.version
        self.icon_path = self.contenedor.icon

        self.thread_pool = QThreadPool()

        self.setWindowTitle(f"Editor indice tag team - v:{self.version}")
        self.setFixedSize(550, 255)
        self.setWindowIcon(QIcon(str(self.icon_path)))

        # Crear el widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        self.edit_lb_pack = QLineEdit(self)
        self.edit_lb_pack.setText("/PSP_GAME/USRDIR/PACKFILE.BIN")
        self.edit_lb_pack.setPlaceholderText("path PACKFILE.BIN")

        self.edit_lbl_data_size = QLineEdit(self)
        self.edit_lbl_data_size.setText("0x38000")
        self.edit_lbl_data_size.setPlaceholderText("index size")

        self.edit_lbl_files = QLineEdit(self)
        self.edit_lbl_files.setText("0x3711")
        self.edit_lbl_files.setPlaceholderText("number of files")

        self.boton_extiso = QPushButton("extract iso", self)
        self.boton_extiso.clicked.connect(self.extract_task)
        self.boton_compiso = QPushButton("compress iso", self)
        self.boton_compiso.clicked.connect(self.compress_task)

        self.label = QPlainTextEdit("path iso", self)
        self.label.setReadOnly(True)
        self.label.setLineWrapMode(QPlainTextEdit.NoWrap)

        layout = QVBoxLayout()
        layout.addWidget(self.edit_lb_pack)
        layout.addWidget(self.edit_lbl_files)
        layout.addWidget(self.edit_lbl_data_size)
        layout.addWidget(self.boton_extiso)
        layout.addWidget(self.boton_compiso)
        layout.addWidget(self.label)

        # Asignar el layout al widget central
        central_widget.setLayout(layout)


    def closeEvent(self, event):
        reply = QMessageBox.question(
            self,
            "Confirm exit",
            "Are you sure you want to close the application?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

    def extract_task(self):
        if not self.contenedor.path_iso:
            self.success_dialog(["open a file first"], "Warning!")
            return
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        #cargar paths del iso
        try:
            self.paths_iso = IsoReader.listar_archivos_iso(self.contenedor.path_iso)
        except Exception as e:
            error_msg = traceback.format_exc()  # Obtener la traza del error como texto
            self.manejar_error(f"Error attempting to read the ISO file.\n{error_msg}")
            #resetear todo
            self.contenedor.close_iso()
            return

        #obtener el path packfile
        self.index_Packfile = self.paths_iso.get(self.edit_lb_pack.text())

        if not self.index_Packfile:
            self.setEnabled(True)
            QApplication.restoreOverrideCursor()
            keys = "\n".join(self.paths_iso.keys())
            ErrorDialog(f"The path \"{self.edit_lb_pack.text()}\" was not found within the paths of the ISO file.\n\nPaths within the ISO file:\n{keys}", self.icon_path).exec_()
            # self.paths_iso = None
            #resetear todo
            self.contenedor.close_iso()
            return

        #obtener los index verdaderos
        self.dataconvert = DataConvert(self)

        #crear una tarea asincrona
        worker = Worker(self.dataconvert.getDataIso)
        worker.signals.resultado.connect(self.resultado_indexs)
        worker.signals.error.connect(self.manejar_error)
        self.thread_pool.start(worker)

    def resultado_indexs(self, indexs):
        self.indexs = indexs
        def delete_content_folder(path_folder):
            for elemento in os.listdir(path_folder):
                ruta_elemento = os.path.join(path_folder, elemento)
                if os.path.isfile(ruta_elemento) or os.path.islink(ruta_elemento):
                    os.remove(ruta_elemento)
                elif os.path.isdir(ruta_elemento):
                    shutil.rmtree(ruta_elemento)
        #metodo para exportar archivos de la iso
        # self.setEnabled(True)
        # QApplication.restoreOverrideCursor()
        # print(f"data recibida {indexs[-1]}")

        #crear una carpeta
        file_iso = Path(self.contenedor.path_iso)
        self.new_folder = file_iso.parent / f"ext_PACKFILE_BIN_{file_iso.stem}"
        if self.new_folder.exists():
            respuesta = self.question_dialog("The folder exists; its content will be deleted.")
            # respuesta = QMessageBox.question(
            #                 self,
            #                 "Warning!",
            #                 "The folder exists; its content will be deleted.",
            #                 QMessageBox.Ok | QMessageBox.Cancel,
            #                 QMessageBox.Cancel
            #             )
            if respuesta == QMessageBox.Cancel:
                self.success_dialog(["Extract_operation canceled by the user."])
                # self.contenedor.close_iso()
                return

        self.new_folder.mkdir(parents=True, exist_ok=True)
        delete_content_folder(self.new_folder)

        #exportar los archivos a la carpeta
        self.datafilemanager = DataFileManager(self)
        self.datafilemanager.task_save()
        

    def compress_task(self):
        if not self.contenedor.path_iso:
            self.success_dialog(["open a file first"], "Warning!")
            return

        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        #cargar paths del iso
        try:
            self.paths_iso = IsoReader.listar_archivos_iso(self.contenedor.path_iso)
        except Exception as e:
            error_msg = traceback.format_exc()  # Obtener la traza del error como texto
            self.manejar_error(f"Error attempting to read the ISO file.\n{error_msg}")
            #resetear todo
            self.contenedor.close_iso()
            return

        #obtener el path packfile
        self.index_Packfile = self.paths_iso.get(self.edit_lb_pack.text())

        if not self.index_Packfile:
            self.setEnabled(True)
            QApplication.restoreOverrideCursor()
            keys = "\n".join(self.paths_iso.keys())
            ErrorDialog(f"The path \"{self.edit_lb_pack.text()}\" was not found within the paths of the ISO file.\n\nPaths within the ISO file:\n{keys}", self.icon_path).exec_()
            # self.paths_iso = None
            #resetear todo
            self.contenedor.close_iso()
            return

        #carpeta con los archivos
        file_iso = Path(self.contenedor.path_iso)
        self.new_folder = file_iso.parent / f"ext_PACKFILE_BIN_{file_iso.stem}"
        if not self.new_folder.exists():
            self.success_dialog(f"The folder \"{self.new_folder.parent}\" does not exist in the file path.", "Warning!")
            return

        if QFile.exists(self.contenedor.path_iso+".compress"):
            respuesta = self.question_dialog("The iso.compress exists; its file will be deleted.")
            # respuesta = QMessageBox.question(
            #                 self,
            #                 "Warning!",
            #                 "The iso.compress exists; its file will be deleted.",
            #                 QMessageBox.Ok | QMessageBox.Cancel,
            #                 QMessageBox.Cancel
            #             )
            if respuesta == QMessageBox.Cancel:
                self.success_dialog(["Compress operation canceled by the user."])
                # self.contenedor.contenedor.close_iso()
                return

        #importar los archivos a la iso backup
        self.datafilemanager = DataFileManager(self)
        self.datafilemanager.task_import()

    def indexs_import(self, new_indexs):
        self.new_indexs = new_indexs

        self.dataconvert = DataConvert(self)

        #crear una tarea asincrona
        worker = Worker(self.dataconvert.setDataIso)
        worker.signals.resultado.connect(self.success_dialog)
        worker.signals.error.connect(self.manejar_error)
        self.thread_pool.start(worker)

    def manejar_error(self, error_msg):
        #mostrar una ventana con el error
        self.setEnabled(True)
        QApplication.restoreOverrideCursor()
        ErrorDialog(error_msg, self.icon_path).exec_()

    def success_dialog(self, vaule, title:str="Success"):
        self.setEnabled(True)
        QApplication.restoreOverrideCursor()
        QMessageBox.information(self, title, vaule[0])

    def question_dialog(self, content, title:str="Warning!"):
        respuesta = QMessageBox.question(
                            self,
                            title,
                            content,
                            QMessageBox.Ok | QMessageBox.Cancel,
                            QMessageBox.Cancel
                        )

        return respuesta
