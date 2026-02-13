from pprint import pprint
import sys
import traceback
import qdarkstyle
import winreg


from PyQt5.QtWidgets import QAction, QApplication, QCheckBox, QFileDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSplashScreen, QVBoxLayout, QWidget
from PyQt5.QtGui import QFont, QGuiApplication, QIcon, QKeySequence, QPixmap
from PyQt5.QtCore import QFile, Qt, QTimer, QThreadPool
from pathlib import Path

from app_md.windows.about_dialog import AboutDialog
from app_md.logic_iso.iso_reader import IsoReader
from app_md.windows.error_dialog import ErrorDialog
from app_md.logic_iso.data_convert import DataConvert
from app_md.logic_iso.worker import Worker
from app_md.logic_iso.data_file_manager import DataFileManager
from app_md.windows.open_folder_link import Open_folder_link
from app_md.windows.extract_tool import ExtractTool

import os
import shutil

class BaseApp:
    def __init__(self):
        self.path_iso = None
        self.version = "1.20260213"
        
        #icono de la app
        self.icon = Path(__file__).resolve().parent / "images" / "icon.ico"
        
        # Crear QApplication primero
        self.app = QApplication(sys.argv)

        # Aplicar tema oscuro de qdarkstyle
        if self.is_windows_dark_mode():
            self.app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
        else:
            self.app.setStyleSheet("")

        font = QFont("Cambria", 11)
        self.app.setFont(font)

        # Mostrar SplashScreen
        self.show_splash()

    def is_windows_dark_mode(self):
        try:
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            key = winreg.OpenKey(registry, key_path)

            # 0 = oscuro, 1 = claro
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)

            return value == 0  # True si es oscuro
        except FileNotFoundError:
            return False

    def show_splash(self):
        # Cargar imagen del splash
        splash_pix = QPixmap(str(Path(__file__).resolve().parent / "images" / "splash.png"))
        self.splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
        self.splash.showMessage("Loading...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)
        self.splash.show()

        # Esperar y luego lanzar la ventana principal
        QTimer.singleShot(620, self.start_main_window)

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
        #inciar windows class
        self.about = AboutDialog(self)
        self.extract_w = ExtractTool(window=self.window)

        # Menu principal
        menu_bar = self.window.menuBar()

        # Menu File
        file_menu = menu_bar.addMenu("File")
        openiso_action = QAction("Open iso", self.window)
        savebin_action = QAction("Save as BIN", self.window)
        closeiso_action = QAction("Close iso", self.window)
        exit_action = QAction("Exit", self.window)
        exit_action.setShortcut(QKeySequence("Ctrl+W"))

        openiso_action.setShortcut(QKeySequence("Ctrl+O"))
        openiso_action.triggered.connect(self.open_iso)
        savebin_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        savebin_action.triggered.connect(lambda: self.window.compress_task(packBin=True))
        closeiso_action.triggered.connect(lambda :self.close_iso(view= False))
        exit_action.triggered.connect(self.window.close)

        file_menu.addAction(openiso_action)
        file_menu.addAction(savebin_action)
        file_menu.addAction(closeiso_action)
        file_menu.addAction(exit_action)

        # Menu tool
        tool_menu = menu_bar.addMenu("Tool")
        extr_action = QAction("extract_tool", self.window)
        extr_action.triggered.connect(self.show_extract)
        extr_action.setShortcut(QKeySequence("Ctrl+U"))
        tool_menu.addAction(extr_action)

        add_m_action = QAction("Add/Remove _m_ to files", self.window)
        add_m_action.triggered.connect(self.select_and_rename_files_with_m)
        tool_menu.addAction(add_m_action)

        wav_at3_action = QAction("Convert WAV or AT3 audio files", self.window)
        wav_at3_action.triggered.connect(lambda: self.window.dropEvent(event=None))
        tool_menu.addAction(wav_at3_action)

        # Menu About
        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About", self.window)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def show_about(self):
        self.about.show_about()

    def show_extract(self):
        self.extract_w.show_extract()
        self.window.hide()

    def open_iso(self, file_path=None):
        # Verifica si se arrastro un archivo
        if not file_path:
            # Si no, abre el dialogo de archivos
            archivo, _ = QFileDialog.getOpenFileName(
                self.window,
                "Choose ISO file",
                "",
                "ISO files (*.iso);;All files (*.*)"
            )
            file_path = archivo  # Asigna lo seleccionado

        # Si se obtuvo un archivo valido (arrastrado o desde dialogo)
        if file_path:
            self.path_iso = Path(file_path)
            self.window.label.setPlainText(file_path)
            self.window.success_dialog(vaule=["File loaded"])

    def close_iso(self, view=True):
        if not self.path_iso:
            return
        # confirmacion para limpiar el path iso
        if self.path_iso and not view:
            answer = self.window.question_dialog("Are you sure you want to close the ISO path of the program?")

            if answer == QMessageBox.Cancel:
                return

        self.path_iso = None
        self.window.label.setPlainText("path iso")
        self.window.success_dialog(["path iso reseted"])

    
    def select_and_rename_files_with_m(self):
        files, _ = QFileDialog.getOpenFileNames(
            self.window,
            "Choose files",
            "",
            "All files (*.*)"
        )
        if not files:
            return

        renamed_files = []

        for f in files:
            path = Path(f)
            if not path.exists():
                continue

            if "_m_" in path.name.lower():
               new_name = path.name.replace("_m_", "")
            else:
                new_name = f"{path.stem}_m_{path.suffix}"

            new_path = path.with_name(new_name)

            if new_path.exists():
                os.remove(new_path)

            path.rename(new_path)
            renamed_files.append(new_path)

        self.window.success_dialog(vaule=[f"renamed files: {len(renamed_files)}"])

        
class MainWindow(QMainWindow):
    def __init__(self, contenedor):
        super().__init__()
        # clase baseapp
        self.contenedor = contenedor

        # version y icon del app
        self.version = self.contenedor.version
        self.icon_path = self.contenedor.icon

        self.is_bin = False
        self.name_compress_iso = None

        self.thread_pool = QThreadPool()

        self.setWindowTitle(f"Editor indice tag team - v:{self.version}")
        self.setFixedSize(550, 280)
        self.setWindowIcon(QIcon(str(self.icon_path)))

        # acepta drop
        self.setAcceptDrops(True)

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
        self.boton_compiso.clicked.connect(lambda: self.compress_task(packBin=False))

        self.label = QPlainTextEdit("path iso", self)
        self.label.setReadOnly(True)
        self.label.setLineWrapMode(QPlainTextEdit.NoWrap)

        # Checkboxes adicionales
        self.ischeckbox_wavs = False
        self.checkbox_wavs = QCheckBox("Process WAV files to AT3", self)
        self.checkbox_wavs.stateChanged.connect(self.on_state_checbox_wavs)
        # self.checkbox_opcion2 = QCheckBox("Usar compresión avanzada", self)

        layout = QVBoxLayout()
        layout.addWidget(self.edit_lb_pack)
        layout.addWidget(self.edit_lbl_files)
        layout.addWidget(self.edit_lbl_data_size)
        layout.addWidget(self.boton_extiso)
        layout.addWidget(self.boton_compiso)
        layout.addWidget(self.label)
        layout.addWidget(self.checkbox_wavs)
        # layout.addWidget(self.checkbox_opcion2)

        # Asignar el layout al widget central
        central_widget.setLayout(layout)

    def on_state_checbox_wavs(self, state):
        self.ischeckbox_wavs = (state == Qt.Checked)

    def dragEnterEvent(self, event):
        # verifica si lo arrastrado son archivos
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        url_local = True
        if event != None:
            urls = event.mimeData().urls()
        else:
            files, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose files",
            "",
            "All files (*.*)"
            )
            urls = files
            url_local = False

        if not urls:
            return

        # Agrupar archivos por extension
        iso_files = []
        wav_files = []
        at3_files = []
        unk_files = []

        for url in urls:
            filepath = url
            if url_local:
                filepath = url.toLocalFile()
            ext = filepath.split('.')[-1].lower()

            if ext == 'iso':
                iso_files.append(filepath)
            elif ext == 'wav':
                wav_files.append(Path(filepath))
            elif ext == 'at3':
                at3_files.append(Path(filepath))
            elif ext == 'unk':
                at3_files.append(Path(filepath))
            elif ext == 'bin':
                at3_files.append(Path(filepath))
            else:
                unk_files.append(filepath)

        if len(unk_files) > 0:
            self.manejar_error(f"Unsupported file type:\n{unk_files}")
            return

        # Validar que solo haya un ISO si existe alguno
        if len(iso_files) > 1:
            self.manejar_error("Only one ISO file is allowed at a time.")
            return

        # Procesar ISO
        if iso_files != []:
            reply = self.question_dialog(content="Detected file type: ISO\nAre you sure you want to open it?")
            if reply != QMessageBox.Cancel:
                self.contenedor.open_iso(file_path=iso_files[0])
                return

        if at3_files == [] and wav_files == []:
            return

        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        # Procesar audios
        self.open_audios(at3_path=at3_files, wav_path=wav_files)

    def closeEvent(self, event):
        reply = self.question_dialog(content="Are you sure you want to close the Editor application?", title="Confirm exit")

        if reply == QMessageBox.Ok:
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
            # self.contenedor.close_iso(False)
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
            # self.contenedor.close_iso(False)
            return

        #obtener los index verdaderos
        self.dataconvert = DataConvert(self)

        #crear una tarea asincrona
        worker = Worker(self.dataconvert.getDataIso)
        worker.signals.resultado.connect(self.resultado_indexs)
        worker.signals.error.connect(self.manejar_error)
        self.thread_pool.start(worker)

    @staticmethod
    def delete_content_folder(path_folder):
        for elemento in os.listdir(path_folder):
            ruta_elemento = os.path.join(path_folder, elemento)
            if os.path.isfile(ruta_elemento) or os.path.islink(ruta_elemento):
                os.remove(ruta_elemento)
            elif os.path.isdir(ruta_elemento):
                shutil.rmtree(ruta_elemento)
        return f"Deleted folder {path_folder}"

    def resultado_indexs(self, indexs):
        self.indexs = indexs

        #crear una carpeta
        file_iso = Path(self.contenedor.path_iso)
        self.new_folder = file_iso.parent / f"ext_PACKFILE_BIN_{file_iso.stem}"
        if self.new_folder.exists():
            respuesta = self.question_dialog("The folder exists; its content will be deleted.")
            if respuesta == QMessageBox.Cancel:
                self.success_dialog(["Extract_operation canceled by the user."])
                # self.contenedor.close_iso()
                return

        self.new_folder.mkdir(parents=True, exist_ok=True)
        # delete_content_folder(self.new_folder)

        #exportar los archivos a la carpeta
        self.datafilemanager = DataFileManager(self)
        self.datafilemanager.task_save()
        

    def compress_task(self, packBin:bool=False):
        if not self.contenedor.path_iso:
            self.success_dialog(["open a file first"], "Warning!")
            return

        self.is_bin = packBin

        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        
        # cargar paths del iso
        try:
            self.paths_iso = IsoReader.listar_archivos_iso(self.contenedor.path_iso)
        except Exception as e:
            error_msg = traceback.format_exc()  # Obtener la traza del error como texto
            self.manejar_error(f"Error attempting to read the ISO file.\n{error_msg}")
            return

        # obtener el path packfile
        self.index_Packfile = self.paths_iso.get(self.edit_lb_pack.text())

        if not self.index_Packfile:
            self.setEnabled(True)
            QApplication.restoreOverrideCursor()
            keys = "\n".join(self.paths_iso.keys())
            self.manejar_error(f"The path \"{self.edit_lb_pack.text()}\" was not found within the paths of the ISO file.\n\nPaths within the ISO file:\n{keys}")
            
            return

        # carpeta con los archivos
        file_iso = Path(self.contenedor.path_iso)
        self.new_folder = file_iso.parent / f"ext_PACKFILE_BIN_{file_iso.stem}"
        if not self.new_folder.exists():
            self.manejar_error(f"The folder \"{self.new_folder.name}\" does not exist in the file path.")
            return

        self.name_compress_iso = self.contenedor.path_iso.parent / f"compress_{self.contenedor.path_iso.name if not self.is_bin else 'PACKFILE.BIN'}"

        if QFile.exists(str(self.name_compress_iso)):
            respuesta = self.question_dialog(f"The {'iso' if not self.is_bin else 'BIN'} compress exists; its file will be deleted.")
            
            if respuesta == QMessageBox.Cancel:
                self.success_dialog(["Compress operation canceled by the user."])
                return

        # importar los archivos a la iso backup
        self.datafilemanager = DataFileManager(self)
        self.datafilemanager.task_import()

    def indexs_import(self, new_indexs):
        self.new_indexs = new_indexs[0]
        self.isleftover = new_indexs[1]

        self.dataconvert = DataConvert(self)

        #crear una tarea asincrona
        worker = Worker(self.dataconvert.setDataIso)
        worker.signals.resultado.connect(self.success_dialog)
        worker.signals.error.connect(self.manejar_error)
        self.thread_pool.start(worker)

    def manejar_error(self, error_msg):
        #mostrar una ventana con el error
        self.contenedor.extract_w.setEnabled(True)
        self.setEnabled(True)

        QApplication.restoreOverrideCursor()
        ErrorDialog(error_msg, self.icon_path).exec_()

    def success_dialog(self, vaule, title:str="Success"):
        self.contenedor.extract_w.setEnabled(True)
        self.setEnabled(True)

        QApplication.restoreOverrideCursor()

        if 'href' not in vaule[0]:
            # muestra el dialogo normal
            QMessageBox.information(self, title, vaule[0])
            return

        # muestra una ventana con texto clicked hacia una carpeta
        self.secundaria = Open_folder_link(parent_font=self.font(), parent_icon=self.windowIcon(), messag=vaule[0], direc=self.new_folder if not isinstance(vaule[-1], Path) else vaule[-1])
        self.secundaria.exec_()

    def question_dialog(self, content, title:str="Warning!"):
        answer = QMessageBox.question(
                            self,
                            title,
                            content,
                            QMessageBox.Ok | QMessageBox.Cancel,
                            QMessageBox.Cancel
                        )

        return answer

    def to_the_front(self):
        self.show()
        self.contenedor.extract_w.hide()

        # Si esta minimizada, la restauramos
        if self.windowState() & Qt.WindowMinimized:
            self.setWindowState(Qt.WindowNoState)
        self.raise_()
        self.activateWindow()

    def open_audios(self, at3_path, wav_path):
        # crea una tarea en un hilo secundario
        self.datafilemanagerw = DataFileManager(self)
        self.datafilemanagerw.wav_audios = wav_path
        self.datafilemanagerw.at3_audios = at3_path
        self.datafilemanagerw.task_audio_convert()
