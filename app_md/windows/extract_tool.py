from collections import defaultdict
import os
from pathlib import Path
import re
import shutil
import tempfile
from PyQt5.QtGui import QCursor, QKeySequence
from PyQt5.QtWidgets import QAction, QApplication, QCheckBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QMenuBar, QMessageBox, QPushButton, QVBoxLayout
from PyQt5.QtCore import QThreadPool, Qt, pyqtSignal

from app_md.logic_extr.data_file_manager import DataFileManager
from app_md.logic_extr.data_convert import DataConvert
from app_md.logic_iso.worker import Worker
from app_md.windows.name_list_editor import NameListEditor

class ExtractTool(QDialog):
    def __init__(self, window=None):
        super().__init__()
        self.exRenamer = None
        self.path_file = None
        self.contenedor = window
        self.setAcceptDrops(True)

        self.datafilemanager = DataFileManager()
        self.dataconvert = DataConvert(self)
        self.thread_pool = QThreadPool()
        self.exRenamer = NameListEditor(self.contenedor.contenedor)

        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint |
                            Qt.WindowCloseButtonHint | Qt.WindowMinimizeButtonHint)

        self.setWindowIcon(self.contenedor.windowIcon())
        self.setFont(self.contenedor.font())
        self.setWindowTitle(f"Extract tool - v:{self.contenedor.version}")
        self.setFixedSize(430, 350)

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

        # tool menu
        tool_menu = QMenu("Tool", self)
        action_edit = QAction("Editor indice", self)
        action_edit.triggered.connect(self.contenedor.to_the_front)
        action_edit.setShortcut(QKeySequence("Ctrl+E"))
        
        action_edit_exr = QAction("Name List Editor", self)
        action_edit_exr.triggered.connect(lambda: self.exRenamer.show_exr())

        action_anm_tanm = QAction("Convert anm or tanm", self)
        action_anm_tanm.triggered.connect(self.process_anm)

        file_menu.addAction(action_close_fil)
        file_menu.addAction(action_salir)
        tool_menu.addAction(action_edit)
        tool_menu.addAction(action_edit_exr)
        tool_menu.addAction(action_anm_tanm)
        self.menu_bar.addMenu(file_menu)
        self.menu_bar.addMenu(tool_menu)

        layout.setMenuBar(self.menu_bar)

        # Contenedor de arrastrar y soltar
        drop_frame = ClickableFrame()
        drop_frame.clicked.connect(self.open_file_choose)

        drop_frame.setStyleSheet("""
            QFrame {
                border: 2px dashed #808080;
                border-radius: 10px;
            }
        """)
        drop_frame.setMinimumSize(400, 180)

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

        self.ischeckbox = True
        self.ischeckbox_wav = True
        self.ischeckbox_subdirec = False
        self.ischeckbox_narut = False
        self.ischeckbox_anims = False

         # Layout para los checkboxes en 2 filas y 2 columnas
        checkboxes_layout = QGridLayout()

        self.pad_to_16_checkbox = QCheckBox("Padding to 16")
        self.pad_to_16_checkbox.setChecked(True)
        self.pad_to_16_checkbox.stateChanged.connect(self.on_pad_checkbox_changed)

        self.proces_wav_checkbox = QCheckBox("Process wav")
        self.proces_wav_checkbox.setChecked(True)
        self.proces_wav_checkbox.stateChanged.connect(self.on_pad_checkbox_changed_wav)

        self.sub_directorios_checkbox = QCheckBox("No subfolders")
        self.sub_directorios_checkbox.stateChanged.connect(self.on_pad_checkbox_changed_subdirec)

        self.pphd_narut_checkbox = QCheckBox("PPHD narut")
        self.pphd_narut_checkbox.stateChanged.connect(self.on_pad_checkbox_changed_narut)

        self.proccess_anims_checkbox = QCheckBox("Process anims")
        self.proccess_anims_checkbox.stateChanged.connect(self.on_pad_checkbox_changed_anims)

        checkboxes_layout.addWidget(self.pad_to_16_checkbox, 0, 0)
        checkboxes_layout.addWidget(self.proces_wav_checkbox, 0, 1)
        checkboxes_layout.addWidget(self.sub_directorios_checkbox, 1, 0)
        checkboxes_layout.addWidget(self.pphd_narut_checkbox, 1, 1)
        checkboxes_layout.addWidget(self.proccess_anims_checkbox,2, 0)

        layout.addLayout(checkboxes_layout)

        self.setLayout(layout)

    def on_pad_checkbox_changed(self, state):
        self.ischeckbox = (state == Qt.Checked)
        # print(state == Qt.Checked)
        
    def on_pad_checkbox_changed_wav(self, state):
        self.ischeckbox_wav = (state == Qt.Checked)
        # print(state == Qt.Checked)
        
    def on_pad_checkbox_changed_narut(self, state):
        self.ischeckbox_narut = (state == Qt.Checked)
        # print(state == Qt.Checked)      
          
    def on_pad_checkbox_changed_subdirec(self, state):
        self.ischeckbox_subdirec = (state == Qt.Checked)
        # print(state == Qt.Checked)
        
    def on_pad_checkbox_changed_anims(self, state):
        self.ischeckbox_anims = (state == Qt.Checked)

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

        # crear una tarea asincrona
        if self.ischeckbox_subdirec:
            worker = Worker(self.dataconvert.import_config)
            worker.signals.resultado.connect(self.contenedor.success_dialog)
            worker.signals.error.connect(self.contenedor.manejar_error)
            self.thread_pool.start(worker)
            return

        # procesar todo el directorio
        worker = Worker(self.process_subdirect)
        worker.signals.resultado.connect(self.contenedor.success_dialog)
        worker.signals.error.connect(self.contenedor.manejar_error)
        self.thread_pool.start(worker)

    def process_subdirect(self):
        def extraer_num(p: Path):
            nombre = p.stem
            m = re.match(r"(\d+)-(\w+)", nombre)
            if m:
                parte1 = int(m.group(1))
                try:
                    parte2 = int(m.group(2), 16)
                except ValueError:
                    parte2 = 0
                return (parte1, parte2)
            return (float('inf'), float('inf'))

        def get_paths(ruta_base):
            for elemento in ruta_base.rglob('*'):
                if elemento.is_file() and ".unk" in elemento.name:
                    paths.append(elemento)

        self.path_parent = Path(self.path_file)
        paths = []
        folder_root = self.path_parent.parent / f"compress_{self.path_parent.name}"
        if folder_root.exists():
            raise ValueError(f"The \"{folder_root.name}\" file already exists and cannot be overwritten.")

        base_folder = self.path_file.parent / self.path_file.stem
        get_paths(base_folder)

        # Ordenar paths por numero y profundidad
        sort_paths = sorted(paths, key=lambda p: (len(p.parts), extraer_num(p)))

        # Crear directorio temporal
        self.temp_dir = Path(tempfile.gettempdir()) / self.path_file.stem
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir) # eliminar directoria en temp

        # crear una copia del directorio en temp
        origen_folder = self.path_parent.parent / self.path_parent.stem
        shutil.copytree(origen_folder, self.temp_dir)

        # Crear archivo temporal de backup
        file_temp = self.temp_dir.parent / self.path_parent.name
        if file_temp.exists():
            os.remove(file_temp)

        if self.path_parent.is_file():
            with open(self.path_parent, "rb") as rf, open(file_temp, "wb") as wf:
                wf.write(rf.read())
        else:
            with open(file_temp, "wb") as wf:
                wf.write()

        # Invertir orden de paths
        sort_paths.reverse()

        # Generar rutas relativas y absolutas dentro del directorio temporal
        relative_paths = [
            os.path.relpath(str(p), str(base_folder)) for p in sort_paths
        ]
        sort_paths = [self.temp_dir / rel for rel in relative_paths]

        # Agregar archivo padre al final
        sort_paths.append(file_temp)

        print(sort_paths, "\n")

        # Procesar archivos
        self.send_path_for_processing(sort_paths)

        # Guardar archivo final
        with open(file_temp, 'rb') as rf, open(folder_root, 'wb') as wf:
            wf.write(rf.read())

        # print("\nfinish\n", bytes_dict)

        self.path_file = self.path_parent

        # eliminar los archivos temp
        os.remove(file_temp)
        shutil.rmtree(self.temp_dir) # eliminar directoria en temp

        # return [f"The entire directory has been processed.\nName file:{folder_root.name}"]
        return [f'The entire directory has been processed<br>Name file: <a href="#">{folder_root.name}</a>', folder_root.parent]

    def send_path_for_processing(self, rutas, resultado=None):
        if resultado is None:
            resultado = {}

        if isinstance(rutas, list):
            for ruta in rutas:
                self.send_path_for_processing(ruta, resultado)
        elif isinstance(rutas, Path):
            ruta_actual = rutas
            if ruta_actual not in resultado:
                # comprobar si tiene folder
                folder_is = ruta_actual.parent / ruta_actual.stem
                if not folder_is.exists():
                    resultado.update({ruta_actual : True})
                else:
                    # comprimir el archivo
                    self.path_file = ruta_actual
                    resultado.update(self.dataconvert.import_config())
        else:
            raise TypeError("Invalid path type. It must be Path or list")

        return resultado


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

    def process_anm(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose files",
            "",
            "anims files (*.anm);;tanms files (*.tanm);;All files (*.*)"
        )

        if not files:
            return

        worker = Worker(lambda: self.task_anm(files=files))
        worker.signals.resultado.connect(self.contenedor.success_dialog)
        worker.signals.error.connect(self.contenedor.manejar_error)
        self.thread_pool.start(worker)


    def task_anm(self, files):
        files_list = defaultdict(list)
        for archivo in files:
            archivo = Path(archivo)
            ext = archivo.suffix.lower()
            files_list[ext].append(archivo)

        self.dataconvert.Tanm.batch_convert_tanm_anm(paths_anm=files_list.get(".anm"),
                                                    paths_tanm=files_list.get(".tanm"))

        return ["successfully converted"]


class ClickableFrame(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def mousePressEvent(self, event):
        self.clicked.emit()