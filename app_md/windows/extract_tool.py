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
        self.setFixedSize(430, 370)

        layout = QVBoxLayout()

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
        
        action_edit_exr = QAction("Name List Editor", self)
        action_edit_exr.triggered.connect(lambda: self.exRenamer.show_exr())

        action_anm_tanm = QAction("Convert anm or tanm", self)
        action_anm_tanm.triggered.connect(self.process_anm)

        action_swap = QAction("Swap Attacks (TTT)", self)
        action_swap.setShortcut(QKeySequence("Ctrl+T"))
        action_swap.triggered.connect(self.open_swap_attacks)

        action_anim0 = QAction("Anims0 (vaciar animaciones)", self)
        action_anim0.setShortcut(QKeySequence("Ctrl+0"))
        action_anim0.triggered.connect(self.open_anims0)

        action_port = QAction("BT3 → TTT Port", self)
        action_port.setShortcut(QKeySequence("Ctrl+P"))
        action_port.triggered.connect(self.open_port)

        file_menu.addAction(action_close_fil)
        file_menu.addAction(action_salir)
        tool_menu.addAction(action_edit)
        tool_menu.addAction(action_edit_exr)
        tool_menu.addAction(action_anm_tanm)
        tool_menu.addAction(action_swap)
        tool_menu.addAction(action_anim0)
        tool_menu.addAction(action_port)
        self.menu_bar.addMenu(file_menu)
        self.menu_bar.addMenu(tool_menu)

        layout.setMenuBar(self.menu_bar)

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
        self.ischeckbox_cascade = False

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

        self.cascade_checkbox = QCheckBox("Cascade process")
        self.cascade_checkbox.stateChanged.connect(self.on_pad_checkbox_changed_cascade)

        checkboxes_layout.addWidget(self.pad_to_16_checkbox, 0, 0)
        checkboxes_layout.addWidget(self.proces_wav_checkbox, 0, 1)
        checkboxes_layout.addWidget(self.sub_directorios_checkbox, 1, 0)
        checkboxes_layout.addWidget(self.pphd_narut_checkbox, 1, 1)
        checkboxes_layout.addWidget(self.proccess_anims_checkbox, 2, 0)
        checkboxes_layout.addWidget(self.cascade_checkbox, 2, 1)

        layout.addLayout(checkboxes_layout)

        self.setLayout(layout)

    def on_pad_checkbox_changed(self, state):
        self.ischeckbox = (state == Qt.Checked)
        
    def on_pad_checkbox_changed_wav(self, state):
        self.ischeckbox_wav = (state == Qt.Checked)
        
    def on_pad_checkbox_changed_narut(self, state):
        self.ischeckbox_narut = (state == Qt.Checked)
          
    def on_pad_checkbox_changed_subdirec(self, state):
        self.ischeckbox_subdirec = (state == Qt.Checked)
        
    def on_pad_checkbox_changed_anims(self, state):
        self.ischeckbox_anims = (state == Qt.Checked)

    def on_pad_checkbox_changed_cascade(self, state):
        self.ischeckbox_cascade = (state == Qt.Checked)

    def extract_file(self):
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        
        if not self.path_file:
            self.contenedor.success_dialog(vaule=["open a file first"],title="Warning!")
            return
        
        worker = Worker(self._extract_task)
        worker.signals.resultado.connect(self.contenedor.success_dialog)
        worker.signals.error.connect(self.contenedor.manejar_error)
        self.thread_pool.start(worker)

    def _extract_task(self):
        result = self.dataconvert.load_offsets()
        if self.ischeckbox_cascade:
            char_output = self.path_file.parent / self.path_file.stem
            self._cascade_extract(char_output=char_output)
        return result


    def compress_file(self):
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        if not self.path_file:
            self.contenedor.success_dialog(vaule=["open a file first"],title="Warning!")
            return

        if self.ischeckbox_subdirec:
            worker = Worker(self.dataconvert.import_config)
            worker.signals.resultado.connect(self.contenedor.success_dialog)
            worker.signals.error.connect(self.contenedor.manejar_error)
            self.thread_pool.start(worker)
            return

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

        sort_paths = sorted(paths, key=lambda p: (len(p.parts), extraer_num(p)))

        self.temp_dir = Path(tempfile.gettempdir()) / self.path_file.stem
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

        origen_folder = self.path_parent.parent / self.path_parent.stem
        shutil.copytree(origen_folder, self.temp_dir)

        file_temp = self.temp_dir.parent / self.path_parent.name
        if file_temp.exists():
            os.remove(file_temp)

        if self.path_parent.is_file():
            with open(self.path_parent, "rb") as rf, open(file_temp, "wb") as wf:
                wf.write(rf.read())
        else:
            with open(file_temp, "wb") as wf:
                wf.write()

        sort_paths.reverse()

        relative_paths = [
            os.path.relpath(str(p), str(base_folder)) for p in sort_paths
        ]
        temp_paths = [self.temp_dir / rel for rel in relative_paths]

        print(temp_paths, "\n")

        self.send_path_for_processing(temp_paths)

        if self.ischeckbox_cascade:
            self._cascade_compress_in_temp()
            self._copy_cascade_paks_to_origin(origen_folder)

        self.send_path_for_processing(file_temp)

        with open(file_temp, 'rb') as rf, open(folder_root, 'wb') as wf:
            wf.write(rf.read())

        self.path_file = self.path_parent

        os.remove(file_temp)
        shutil.rmtree(self.temp_dir)

        return [f'The entire directory has been processed<br>Name file: <a href="#">{folder_root.name}</a>', folder_root.parent]

    def _cascade_compress_in_temp(self):
        try:
            cam = None
            for patt in ["07_skill_cameras.pak", "07_skill_cameras.*", "*skill_cameras*.pak", "*skill_cameras*.*"]:
                cam = next((p for p in self.temp_dir.rglob(patt) if p.is_file()), None)
                if cam:
                    break

            if cam:
                cam_folder = cam.parent / cam.stem
                if cam_folder.exists():
                    old_path = self.path_file
                    try:
                        self.path_file = cam
                        self.dataconvert.import_config()
                    finally:
                        self.path_file = old_path

            common = None
            for patt in ["05_effect_common.pak", "05_effect_common.*"]:
                common = next((p for p in self.temp_dir.rglob(patt) if p.is_file()), None)
                if common:
                    break

            if common:
                common_folder = common.parent / common.stem
                if common_folder.exists():
                    old_path = self.path_file
                    try:
                        self.path_file = common
                        self.dataconvert.import_config()
                    finally:
                        self.path_file = old_path

        except Exception:
            pass

    def _copy_cascade_paks_to_origin(self, origin_root: Path):
        try:
            cam = None
            for patt in ["07_skill_cameras.pak", "07_skill_cameras.*", "*skill_cameras*.pak", "*skill_cameras*.*"]:
                cam = next((p for p in self.temp_dir.rglob(patt) if p.is_file()), None)
                if cam:
                    break
            if cam:
                rel = cam.relative_to(self.temp_dir)
                dst = origin_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cam, dst)

            common = None
            for patt in ["05_effect_common.pak", "05_effect_common.*"]:
                common = next((p for p in self.temp_dir.rglob(patt) if p.is_file()), None)
                if common:
                    break
            if common:
                rel = common.relative_to(self.temp_dir)
                dst = origin_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(common, dst)

        except Exception:
            pass


    def send_path_for_processing(self, rutas, resultado=None):
        if resultado is None:
            resultado = {}

        if isinstance(rutas, list):
            for ruta in rutas:
                self.send_path_for_processing(ruta, resultado)
        elif isinstance(rutas, Path):
            ruta_actual = rutas
            if ruta_actual not in resultado:
                folder_is = ruta_actual.parent / ruta_actual.stem
                if not folder_is.exists():
                    resultado.update({ruta_actual : True})
                else:
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

        if self.windowState() & Qt.WindowMinimized:
            self.setWindowState(Qt.WindowNoState)
        self.raise_()
        self.activateWindow()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
    
        if len(urls) != 1:
            self.contenedor.manejar_error("Only one file is allowed.")
            return

        reply = self.contenedor.question_dialog(content="Are you sure you want to open the file?")
        if reply == QMessageBox.Cancel:
            return

        filepath = urls[0].toLocalFile()
        self.open_file_choose(view=False,file_path=filepath)

    def open_port(self):
        try:
            from app_md.logic_port.port_window import PortWindow
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load Port tool: {e}")
            return
        self.setEnabled(False)
        port = PortWindow(parent_tool=self)
        port.exec_()

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

        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        worker = Worker(lambda: self.task_anm(files=files))
        worker.signals.resultado.connect(self.contenedor.success_dialog)
        worker.signals.error.connect(self.contenedor.manejar_error)
        self.thread_pool.start(worker)


    def open_swap_attacks(self):
        try:
            from app_md.logic_swap.swap_attacks import SwapApp
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo importar Swap_Attacks: {e}")
            return

        self.setEnabled(False)
        swap = SwapApp(parent_tool=self)
        swap.exec_()

    def open_anims0(self):
        try:
            from app_md.windows.anim0 import Anims0
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo abrir Anims0:\n{e}")
            return

        if hasattr(self, "anims0_window") and self.anims0_window is not None:
            try:
                self.anims0_window.close()
            except:
                pass

        self.anims0_window = Anims0()
        self.anims0_window.setWindowIcon(self.windowIcon())
        self.anims0_window.setFont(self.font())
        self.anims0_window.show()
        self.anims0_window.raise_()
        self.anims0_window.activateWindow()

    def task_anm(self, files):
        files_list = defaultdict(list)
        for archivo in files:
            archivo = Path(archivo)
            ext = archivo.suffix.lower()
            files_list[ext].append(archivo)

        self.dataconvert.Tanm.batch_convert_tanm_anm(paths_anm=files_list.get(".anm"),
                                                    paths_tanm=files_list.get(".tanm"))

        return ["successfully converted"]


    def _cascade_extract(self, char_output: Path):
        effects_folder = char_output / "3_effects"
        if not effects_folder.is_dir():
            return

        effect_common_pak = effects_folder / "05_effect_common.pak"
        if not effect_common_pak.exists():
            return

        saved_path = self.path_file

        self.path_file = effect_common_pak
        self.dataconvert.load_offsets()

        effect_common_folder = effects_folder / "05_effect_common" / "1_effect_common"
        if not effect_common_folder.is_dir():
            self.path_file = saved_path
            return

        skill_cameras_pak = effect_common_folder / "07_skill_cameras.pak"
        if not skill_cameras_pak.exists():
            self.path_file = saved_path
            return

        self.path_file = skill_cameras_pak
        self.dataconvert.load_offsets()

        self.path_file = saved_path


class ClickableFrame(QFrame):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def mousePressEvent(self, event):
        self.clicked.emit()