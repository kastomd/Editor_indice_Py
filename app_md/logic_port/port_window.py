import os
import struct
import tempfile
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QCheckBox,
    QMessageBox, QFileDialog, QFrame, QApplication
)
from PyQt5.QtCore import Qt, QThreadPool, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent

from app_md.logic_iso.worker import Worker


_SIG_1P  = 0x000000FC
_SIG_ANM = 0x000001B8
_SIG_EFF = 0x00000006

_ROLE_SIGS = {"1p": _SIG_1P, "anm": _SIG_ANM, "eff": _SIG_EFF}
_ROLE_LABELS = {"1p": "1_p", "anm": "2_anm", "eff": "3_eff"}
_ROLE_HINTS  = {
    "1p":  "Drop or click · (name)_1p.pak",
    "anm": "Drop or click · (name)_2_anm.pak",
    "eff": "Drop or click · (name)_3_eff.pak",
}


def _read_sig(path: str) -> int:
    try:
        with open(path, "rb") as f:
            return struct.unpack_from("<I", f.read(4))[0]
    except Exception:
        return 0


def _char_name(path: str) -> str:
    stem = Path(path).stem
    for suffix in ("_2_1p", "_1p", "_2_anm", "_2_eff", "_3_eff", "_anm", "_eff"):
        if stem.lower().endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _sep():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


def _center_on(dialog, parent):
    if not parent:
        return
    pg = parent.geometry()
    dialog.adjustSize()
    x = pg.x() + (pg.width()  - dialog.width())  // 2
    y = pg.y() + (pg.height() - dialog.height()) // 2
    dialog.move(x, y)


class PakDropPanel(QFrame):
    file_selected = pyqtSignal(str)

    _IDLE  = "border: 2px dashed #555; border-radius: 6px; background: transparent;"
    _HOVER = "border: 2px dashed #5588cc; border-radius: 6px; background: transparent;"
    _OK    = "border: 2px solid #55aa55; border-radius: 6px; background: transparent;"
    _ERR   = "border: 2px solid #aa3333; border-radius: 6px; background: transparent;"

    def __init__(self, role: str, parent=None):
        super().__init__(parent)
        self.role = role
        self._last_dir = ""
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self._IDLE)

        layout = QVBoxLayout(self)
        layout.setSpacing(3)
        layout.setContentsMargins(10, 8, 10, 8)

        self._lbl_role = QLabel(_ROLE_LABELS[role])
        self._lbl_role.setAlignment(Qt.AlignCenter)
        self._lbl_role.setStyleSheet("font-weight: bold; font-size: 11px; color: #888; border: none;")

        self._lbl_icon = QLabel("⬇")
        self._lbl_icon.setAlignment(Qt.AlignCenter)
        self._lbl_icon.setStyleSheet("font-size: 18px; color: #555; border: none;")

        self._lbl_name = QLabel(_ROLE_HINTS[role])
        self._lbl_name.setAlignment(Qt.AlignCenter)
        self._lbl_name.setWordWrap(True)
        self._lbl_name.setStyleSheet("font-size: 11px; color: #666; border: none;")
        self._lbl_name.setMinimumHeight(28)

        layout.addWidget(self._lbl_role)
        layout.addWidget(self._lbl_icon)
        layout.addWidget(self._lbl_name)

    def set_file(self, path: str, ok: bool):
        icon  = "✓" if ok else "✗"
        color = "#55aa55" if ok else "#aa3333"
        self._lbl_icon.setText(icon)
        self._lbl_icon.setStyleSheet(f"font-size: 18px; color: {color}; border: none;")
        self._lbl_name.setText(Path(path).name)
        self._lbl_name.setStyleSheet(f"font-size: 11px; color: {color if not ok else ''}; border: none;")
        self.setStyleSheet(self._OK if ok else self._ERR)
        self._last_dir = str(Path(path).parent)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            path, _ = QFileDialog.getOpenFileName(
                self.window(), f"Open {_ROLE_LABELS[self.role]}",
                self._last_dir, "PAK files (*.pak *.unk);;All files (*)"
            )
            if path:
                self.file_selected.emit(path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            self.setStyleSheet(self._HOVER)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._OK if "✓" in self._lbl_icon.text() else self._IDLE)

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            self.file_selected.emit(urls[0].toLocalFile())



_FACE_SLOTS = [
    (3,  "Damage",   True),
    (4,  "Talk 1",   False),
    (5,  "Talk 2",   False),
    (6,  "Talk 3",   False),
    (7,  "Face 1",   True),
    (8,  "Face 2",   True),
    (9,  "Face 3",   True),
    (10, "Unused",   False),
]
_FACE_SLOT_IDX = {s: (s-3) for s, _, _ in _FACE_SLOTS}


class FaceSelectDialog(QDialog):
    def __init__(self, parent, detected: dict):
        super().__init__(parent)
        self.setWindowTitle("Select faces to port")
        self.setModal(True)
        self.setFixedWidth(260)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        if parent:
            self.setWindowIcon(parent.windowIcon())
            self.setFont(parent.font())

        self._checks = {}
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(16, 14, 16, 14)

        lbl = QLabel("Detected faces — select which to include:")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 11px; color: #aaa;")
        layout.addWidget(lbl)

        for slot, label, default in _FACE_SLOTS:
            if slot not in detected:
                continue
            chk = QCheckBox(label)
            chk.setChecked(default)
            chk.setFocusPolicy(Qt.NoFocus)
            layout.addWidget(chk)
            self._checks[slot] = chk

        btn = QPushButton("Continue")
        btn.setFixedHeight(30)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

        _center_on(self, parent)

    def selected(self) -> set:
        return {slot for slot, chk in self._checks.items() if chk.isChecked()}


class PortWindow(QDialog):
    def __init__(self, parent_tool=None):
        super().__init__(parent_tool)
        self._parent_tool = parent_tool
        self.setWindowTitle("BT3 → TTT Character Port")
        self.setFixedWidth(430)
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint |
                            Qt.WindowCloseButtonHint)

        if parent_tool:
            self.setWindowIcon(parent_tool.windowIcon())
            self.setFont(parent_tool.font())

        self._paths     = {"1p": None, "anm": None, "eff": None}
        self._names     = {"1p": None, "anm": None, "eff": None}
        self._bt3_parts = None
        self._bt3_blob  = None
        self._thread_pool = QThreadPool()

        self._build_ui()
        _center_on(self, parent_tool)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 12, 14, 14)

        self._lbl_status = QLabel("Open the 3 BT3 pak files with the same character name.")
        self._lbl_status.setAlignment(Qt.AlignCenter)
        self._lbl_status.setWordWrap(True)
        self._lbl_status.setStyleSheet("font-size: 11px; color: #888;")
        root.addWidget(self._lbl_status)

        self._panels = {}
        for role in ("1p", "anm", "eff"):
            panel = PakDropPanel(role)
            panel.file_selected.connect(lambda p, r=role: self._on_file(r, p))
            self._panels[role] = panel
            root.addWidget(panel)

        root.addWidget(_sep())

        self._btn_process = QPushButton("Process")
        self._btn_process.setFixedHeight(32)
        self._btn_process.setEnabled(False)
        self._btn_process.clicked.connect(self._on_process)
        root.addWidget(self._btn_process)

    def _on_file(self, role: str, path: str):
        sig      = _read_sig(path)
        expected = _ROLE_SIGS[role]
        ok       = (sig == expected)
        self._panels[role].set_file(path, ok)

        if ok:
            self._paths[role] = path
            self._names[role] = _char_name(path)
        else:
            self._paths[role] = None
            self._names[role] = None
            QMessageBox.critical(self, "Invalid file",
                f"Wrong signature for {_ROLE_LABELS[role]}.\n"
                f"Expected: 0x{expected:08X}  Got: 0x{sig:08X}")
        self._update_state()

    def _update_state(self):
        paths_ok = all(self._paths[r] for r in ("1p", "anm", "eff"))
        names_ok = paths_ok and len({self._names[r] for r in ("1p", "anm", "eff")}) == 1
        if not paths_ok:
            self._lbl_status.setText("Open the 3 BT3 pak files with the same character name.")
        elif not names_ok:
            ns = ", ".join(f"{_ROLE_LABELS[r]}: {self._names[r]}" for r in ("1p","anm","eff"))
            self._lbl_status.setText(f"Name mismatch — {ns}")
        else:
            self._lbl_status.setText(f"Ready · {self._names['1p']}")
        self._btn_process.setEnabled(paths_ok and names_ok)

    def _on_process(self):
        print(f"[port] Starting BT3→TTT port for: {self._names['1p']}")
        self._load_bt3_and_open_packer()

    def _load_bt3_and_open_packer(self):
        from app_md.logic_swap.pmdl.parser import parse_bt3
        from app_md.logic_swap.pmdl.bt3_tex_reader import load_dbt, map_dbt_to_tex_ids
        from app_md.logic_swap.swap_vfx import parse_pak

        print("[port] Reading 1_p pak...")
        with open(self._paths["1p"], "rb") as f:
            data_1p = f.read()

        entries_1p = parse_pak(data_1p)
        e_map = {idx: raw for idx, _, _, raw in entries_1p}

        pmdl_blob = e_map.get(2, b'')
        dbt_blob  = e_map.get(11, b'')

        if not pmdl_blob:
            QMessageBox.critical(self, "Error", "Could not find pmdl (slot 2) in 1_p.")
            return
        if not dbt_blob:
            QMessageBox.critical(self, "Error", "Could not find dbt (slot 11) in 1_p.")
            return

        print("[port] Parsing BT3 pmdl...")
        try:
            _, parts = parse_bt3(pmdl_blob)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error parsing pmdl:\n{e}")
            return
        print(f"[port] pmdl parsed: {len(parts)} parts")

        tex_ids = []
        seen = set()
        for p in parts:
            for m in p.get("meshes", []):
                tid = m.get("tex_id", "")
                if tid and tid not in seen:
                    seen.add(tid); tex_ids.append(tid)
        print(f"[port] Found {len(tex_ids)} unique tex_ids")

        print("[port] Loading DBT textures...")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dbt")
        try:
            tmp.write(dbt_blob); tmp.flush(); tmp.close()
            entries_dbt, raw_data, tbl_offset = load_dbt(tmp.name)
        finally:
            try: os.unlink(tmp.name)
            except: pass

        mapped = map_dbt_to_tex_ids(entries_dbt, tex_ids,
                                    raw_data=raw_data, table_offset=tbl_offset)
        tex_map = {tid: img for tid, img in (mapped or {}).items() if img is not None}
        print(f"[port] Mapped {len(tex_map)}/{len(tex_ids)} textures from DBT")

        if not tex_map:
            QMessageBox.critical(self, "Error", "Could not map any texture from the DBT.")
            return

        self._bt3_blob  = pmdl_blob
        self._bt3_parts = parts

        # detect face blobs (slots 3-10 in pak index)
        _FACE_OFFSETS = {3:0x10,4:0x14,5:0x18,6:0x1C,7:0x20,8:0x24,9:0x28,10:0x2C}
        self._face_blobs = {}
        self._face_dbt_tex = {}
        for slot, off in _FACE_OFFSETS.items():
            raw = e_map.get(slot, b'')
            if len(raw) >= 0x60 + 48:
                self._face_blobs[slot] = raw
        print(f"[port] Detected faces: {list(self._face_blobs.keys())}")

        if self._face_blobs:
            dlg = FaceSelectDialog(self, self._face_blobs)
            if dlg.exec_() != QDialog.Accepted:
                return
            self._face_selected = dlg.selected()
        else:
            self._face_selected = set()

        # load face extra DBTs only for selected faces
        self._face_dbt_tex = {}
        if self._face_selected:
            from app_md.logic_swap.pmdl.bt3_tex_reader import load_dbt
            from app_md.logic_swap.pmdl.bt3_face_parser import parse_bt3_face as _pf
            _FACE_DBT_PAIR = {7: 13, 8: 14, 9: 15}
            for face_slot, dbt_slot in _FACE_DBT_PAIR.items():
                if face_slot not in self._face_selected:
                    continue
                raw_dbt = e_map.get(dbt_slot, b'')
                if len(raw_dbt) < 256:
                    continue
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dbt")
                try:
                    tmp.write(raw_dbt); tmp.flush(); tmp.close()
                    entries_dbt, _, _ = load_dbt(tmp.name)
                    valid = [e for e in entries_dbt if e.get("image") is not None]
                    if not valid:
                        continue
                    img = valid[0]["image"]
                    subparts = _pf(self._face_blobs[face_slot])
                    vert_count = {}
                    for sp in subparts:
                        t = sp['tex_id']
                        vert_count[t] = vert_count.get(t, 0) + len(sp['verts'])
                    if not vert_count:
                        continue
                    face_tid = max(vert_count, key=vert_count.get)
                    unique_tid = f"FACE{face_slot:02d}_{face_tid}"
                    tex_map[unique_tid] = img
                    self._face_dbt_tex[face_slot] = (face_tid, unique_tid)
                    print(f"[port] Face slot {face_slot}: override {face_tid} → {unique_tid}")
                except Exception as ex:
                    print(f"[port] Face slot {face_slot}: dbt load failed ({ex})")
                finally:
                    try: os.unlink(tmp.name)
                    except: pass

        self._open_packer(tex_map)

    def _open_packer(self, tex_map: dict):
        from app_md.logic_port.tex_compress import TexturePackerWindow
        print("[port] Opening texture packer...")
        packer = TexturePackerWindow(self, tex_map, self._run_port)
        packer.exec_()

    def _run_port(self, atlas_image, pack_result, tex_id_order):
        char_name = self._names["1p"]
        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save PCK1", f"{char_name}.PCK1", "PCK1 files (*.PCK1);;All files (*)"
        )
        if not out_path:
            return
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        def task():
            from app_md.logic_port.char_port import port_character

            print(f"[port] === Starting full port: {char_name} ===")

            print("[port] Reading pak files...")
            with open(self._paths["1p"],  "rb") as f: d1p  = f.read()
            with open(self._paths["anm"], "rb") as f: danm = f.read()
            with open(self._paths["eff"], "rb") as f: deff = f.read()

            face_blobs = {s: b for s, b in self._face_blobs.items()
                          if s in self._face_selected}
            face_tex_override = {s: v for s, v in self._face_dbt_tex.items()
                                  if s in self._face_selected}
            pck1 = port_character(
                d1p, danm, deff,
                atlas_image, pack_result, tex_id_order,
                self._bt3_parts, face_blobs=face_blobs,
                face_tex_override=face_tex_override
            )

            print(f"[port] Writing {Path(out_path).name} ({len(pck1):,} bytes)...")
            Path(out_path).write_bytes(pck1)

            print(f"[port] === Done: {char_name} ===")
            return [f'Port complete · <a href="#">{char_name}</a>', Path(out_path).parent]

        worker = Worker(task)
        worker.signals.resultado.connect(self._on_done)
        worker.signals.error.connect(self._on_error)
        self._thread_pool.start(worker)

    def _on_done(self, result):
        self.setEnabled(True)
        QApplication.restoreOverrideCursor()
        if self._parent_tool:
            self._parent_tool.contenedor.success_dialog(result)

    def _on_error(self, msg):
        self.setEnabled(True)
        QApplication.restoreOverrideCursor()
        if self._parent_tool:
            self._parent_tool.contenedor.manejar_error(msg)

    def closeEvent(self, event):
        if self._parent_tool:
            self._parent_tool.setEnabled(True)
        event.accept()