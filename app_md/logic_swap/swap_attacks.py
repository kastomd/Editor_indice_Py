import os

from PyQt5.QtWidgets import (
    QLabel, QPushButton, QFileDialog, QCheckBox,
    QVBoxLayout, QHBoxLayout, QComboBox, QMessageBox, QDialog, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent

from .swap_context import _resolver_ttt_ctx, _resolver_bt3_ctx
from .swap_logic import swap_habilidad, procesar_swap_ataques, procesar_swap_ataques_params_only


class VarHolder:
    def __init__(self, val):
        self.val = val
    def get(self): return self.val
    def set(self, val): self.val = val


class SelectPlatformDialog(QDialog):
    def __init__(self, parent=None, title="Select platform"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(340, 120)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.selected_mode = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 14, 20, 14)

        label = QLabel("What platform is the character from?")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_ttt = QPushButton("TTT")
        btn_ttt.setFixedHeight(32)
        btn_ttt.clicked.connect(lambda: self._select("TTT"))
        btn_bt3 = QPushButton("BT3")
        btn_bt3.setFixedHeight(32)
        btn_bt3.clicked.connect(lambda: self._select("BT3"))
        btn_layout.addWidget(btn_ttt)
        btn_layout.addWidget(btn_bt3)
        layout.addLayout(btn_layout)

    def _select(self, mode):
        self.selected_mode = mode
        self.accept()


def _sep():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


class CharDropPanel(QFrame):
    char_selected = pyqtSignal(str, str)

    _STYLE_IDLE   = "border: 2px dashed #555; border-radius: 6px; background: transparent;"
    _STYLE_HOVER  = "border: 2px dashed #5588cc; border-radius: 6px; background: transparent;"
    _STYLE_FILLED = "border: 2px solid #5588cc; border-radius: 6px; background: transparent;"

    def __init__(self, role: str, parent=None):
        super().__init__(parent)
        self.role      = role
        self._last_dir = ""
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self._STYLE_IDLE)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(10, 10, 10, 10)

        self._lbl_role = QLabel(role)
        self._lbl_role.setAlignment(Qt.AlignCenter)
        self._lbl_role.setStyleSheet("font-weight: bold; font-size: 12px; color: #aaa; border: none;")

        self._lbl_icon = QLabel("⬇")
        self._lbl_icon.setAlignment(Qt.AlignCenter)
        self._lbl_icon.setStyleSheet("font-size: 20px; color: #555; border: none;")

        self._lbl_name = QLabel("Drop or click to select")
        self._lbl_name.setAlignment(Qt.AlignCenter)
        self._lbl_name.setWordWrap(True)
        self._lbl_name.setStyleSheet("font-size: 12px; color: #777; border: none;")
        self._lbl_name.setMinimumHeight(30)

        layout.addWidget(self._lbl_role)
        layout.addWidget(self._lbl_icon)
        layout.addWidget(self._lbl_name)

    def set_char(self, path, mode):
        self._lbl_icon.setText("✓")
        self._lbl_icon.setStyleSheet("font-size: 20px; color: #5588cc; border: none;")
        self._lbl_name.setText(f"[{mode}]  {os.path.basename(path)}")
        self._lbl_name.setStyleSheet("font-size: 12px; border: none;")
        self.setStyleSheet(self._STYLE_FILLED)
        self._last_dir = os.path.dirname(path) if os.path.isfile(path) else path

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._open_dialog()

    def _try_resolve(self, path):
        if os.path.isdir(path):
            ctx = _resolver_ttt_ctx(path)
            if ctx: return ctx, "TTT", path
        if path.lower().endswith(".pak"):
            ctx = _resolver_bt3_ctx(path)
            if ctx: return ctx, "BT3", path
        return None, None, path

    def _open_dialog(self):
        parent = self.window()
        dialog = SelectPlatformDialog(parent, f"Select {self.role}")
        if dialog.exec_() != QDialog.Accepted:
            return
        mode = dialog.selected_mode
        if mode == "TTT":
            path = QFileDialog.getExistingDirectory(parent, f"{self.role} folder (TTT)", self._last_dir)
            if not path: return
            ctx = _resolver_ttt_ctx(path)
            if not ctx:
                QMessageBox.critical(parent, "Error", "The folder does not contain 1_p, 2_anims and 3_effects.")
                return
        else:
            path, _ = QFileDialog.getOpenFileName(parent, f"{self.role} .pak file (BT3)", self._last_dir, "PAK (*.pak)")
            if not path: return
            ctx = _resolver_bt3_ctx(path)
            if not ctx:
                QMessageBox.critical(parent, "Error", "Could not find '*_1p', '*_anm' and '*_eff' next to the .pak.")
                return
        self.set_char(path, mode)
        self.char_selected.emit(path, mode)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            self.setStyleSheet(self._STYLE_HOVER)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        filled = "✓" in self._lbl_icon.text()
        self.setStyleSheet(self._STYLE_FILLED if filled else self._STYLE_IDLE)

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls: return
        path = urls[0].toLocalFile()
        if not path: return
        parent = self.window()
        ctx, mode, resolved = self._try_resolve(path)
        if ctx is None:
            filled = "✓" in self._lbl_icon.text()
            self.setStyleSheet(self._STYLE_FILLED if filled else self._STYLE_IDLE)
            QMessageBox.critical(parent, "Error",
                "Drop a TTT character folder or a BT3 .pak file.\n"
                "TTT: folder containing 1_p, 2_anims and 3_effects.\n"
                "BT3: .pak file next to *_1p, *_anm and *_eff folders.")
            return
        self.set_char(resolved, mode)
        self.char_selected.emit(resolved, mode)


class SwapApp(QDialog):
    def __init__(self, parent_tool=None):
        super().__init__(parent_tool)
        self._parent_tool = parent_tool

        self.setWindowTitle("Swap Attacks")
        self.setFixedWidth(430)
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint |
                            Qt.WindowCloseButtonHint)

        if parent_tool:
            self.setWindowIcon(parent_tool.windowIcon())
            self.setFont(parent_tool.font())

        self._ctx_donor    = {}
        self._ctx_receptor = {}

        self._donor_var        = VarHolder("Habilidad 1")
        self._receptor_var     = VarHolder("Habilidad 1")
        self._atk_donor_var    = VarHolder("Ataque 1")
        self._atk_receptor_var = VarHolder("Ataque 1")

        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 12, 14, 14)

        # ── Character panels ─────────────────────────────────────────────────
        char_row = QHBoxLayout()
        char_row.setSpacing(0)

        self._panel_receptor = CharDropPanel("RECEPTOR")
        self._panel_receptor.char_selected.connect(self._on_receptor_selected)

        arrow_col = QVBoxLayout()
        arrow_col.setAlignment(Qt.AlignCenter)
        arrow_lbl = QLabel("←")
        arrow_lbl.setFixedWidth(36)
        arrow_lbl.setAlignment(Qt.AlignCenter)
        arrow_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #5588cc;")
        arrow_sub = QLabel("receives")
        arrow_sub.setFixedWidth(36)
        arrow_sub.setAlignment(Qt.AlignCenter)
        arrow_sub.setStyleSheet("font-size: 9px; color: #555;")
        arrow_col.addStretch()
        arrow_col.addWidget(arrow_lbl)
        arrow_col.addWidget(arrow_sub)
        arrow_col.addStretch()

        self._panel_donor = CharDropPanel("DONOR")
        self._panel_donor.char_selected.connect(self._on_donor_selected)

        char_row.addWidget(self._panel_receptor, 5)
        char_row.addLayout(arrow_col, 0)
        char_row.addWidget(self._panel_donor, 5)
        root.addLayout(char_row)

        # ── Options ──────────────────────────────────────────────────────────
        opts_row = QHBoxLayout()
        opts_row.setSpacing(16)
        opts_row.setContentsMargins(4, 0, 4, 0)

        self.chk_effect = QCheckBox("Include effect")
        self.chk_effect.setChecked(True)
        self.chk_effect.setFocusPolicy(Qt.NoFocus)

        self.chk_cman = QCheckBox("Include cman")
        self.chk_cman.setChecked(True)
        self.chk_cman.setFocusPolicy(Qt.NoFocus)

        opts_row.addStretch()
        opts_row.addWidget(self.chk_effect)
        opts_row.addWidget(self.chk_cman)
        opts_row.addStretch()
        root.addLayout(opts_row)

        root.addWidget(_sep())

        # ── Skills ───────────────────────────────────────────────────────────
        lbl_skill = QLabel("Skills")
        lbl_skill.setStyleSheet("font-weight: bold;")
        root.addWidget(lbl_skill)

        skill_row = QHBoxLayout()
        skill_row.setSpacing(6)

        self.combo_receptor = QComboBox()
        self.combo_receptor.addItems(["Skill 1", "Skill 2"])
        self.combo_receptor.currentTextChanged.connect(lambda v: self._receptor_var.set(
            "Habilidad 1" if v == "Skill 1" else "Habilidad 2"))

        arr_skill = QLabel("←")
        arr_skill.setFixedWidth(24)
        arr_skill.setAlignment(Qt.AlignCenter)
        arr_skill.setStyleSheet("font-size: 14px; color: #5588cc;")

        self.combo_donor = QComboBox()
        self.combo_donor.addItems(["Skill 1", "Skill 2"])
        self.combo_donor.currentTextChanged.connect(lambda v: self._donor_var.set(
            "Habilidad 1" if v == "Skill 1" else "Habilidad 2"))

        skill_row.addWidget(self.combo_receptor, 5)
        skill_row.addWidget(arr_skill, 0)
        skill_row.addWidget(self.combo_donor, 5)
        root.addLayout(skill_row)

        skill_btns = QHBoxLayout()
        skill_btns.setSpacing(6)
        self.btn_swap_skill = QPushButton("Swap Skill")
        self.btn_swap_skill.setFixedHeight(28)
        self.btn_swap_skill.clicked.connect(lambda: self._run_swap_skill(False))
        self.btn_skill_params = QPushButton("Params only")
        self.btn_skill_params.setFixedHeight(28)
        self.btn_skill_params.clicked.connect(lambda: self._run_swap_skill(True))
        skill_btns.addWidget(self.btn_swap_skill, 3)
        skill_btns.addWidget(self.btn_skill_params, 2)
        root.addLayout(skill_btns)

        root.addWidget(_sep())

        # ── Attacks ──────────────────────────────────────────────────────────
        lbl_atk = QLabel("Attacks")
        lbl_atk.setStyleSheet("font-weight: bold;")
        root.addWidget(lbl_atk)

        atk_row = QHBoxLayout()
        atk_row.setSpacing(6)

        self.combo_atk_receptor = QComboBox()
        self.combo_atk_receptor.addItems(["Attack 1", "Attack 2", "Attack 3"])
        self.combo_atk_receptor.currentTextChanged.connect(lambda v: self._atk_receptor_var.set(
            {"Attack 1": "Ataque 1", "Attack 2": "Ataque 2", "Attack 3": "Ataque 3"}[v]))

        arr_atk = QLabel("←")
        arr_atk.setFixedWidth(24)
        arr_atk.setAlignment(Qt.AlignCenter)
        arr_atk.setStyleSheet("font-size: 14px; color: #5588cc;")

        self.combo_atk_donor = QComboBox()
        self.combo_atk_donor.addItems(["Attack 1", "Attack 2", "Attack 3"])
        self.combo_atk_donor.currentTextChanged.connect(lambda v: self._atk_donor_var.set(
            {"Attack 1": "Ataque 1", "Attack 2": "Ataque 2", "Attack 3": "Ataque 3"}[v]))

        atk_row.addWidget(self.combo_atk_receptor, 5)
        atk_row.addWidget(arr_atk, 0)
        atk_row.addWidget(self.combo_atk_donor, 5)
        root.addLayout(atk_row)

        atk_btns = QHBoxLayout()
        atk_btns.setSpacing(6)
        self.btn_swap_atk = QPushButton("Swap Attack")
        self.btn_swap_atk.setFixedHeight(28)
        self.btn_swap_atk.clicked.connect(self._run_swap_attack)
        self.btn_atk_params = QPushButton("Params only")
        self.btn_atk_params.setFixedHeight(28)
        self.btn_atk_params.clicked.connect(self._run_swap_attack_params)
        atk_btns.addWidget(self.btn_swap_atk, 3)
        atk_btns.addWidget(self.btn_atk_params, 2)
        root.addLayout(atk_btns)

    # ── context slots ────────────────────────────────────────────────────────

    def _on_donor_selected(self, path, mode):
        self._ctx_donor = _resolver_ttt_ctx(path) if mode == "TTT" else _resolver_bt3_ctx(path)

    def _on_receptor_selected(self, path, mode):
        self._ctx_receptor = _resolver_ttt_ctx(path) if mode == "TTT" else _resolver_bt3_ctx(path)

    # ── dialogs ──────────────────────────────────────────────────────────────

    def _ok(self, text):
        QMessageBox.information(self, "Done", text)

    def _err(self, text):
        QMessageBox.critical(self, "Error", text)

    # ── swap runners ─────────────────────────────────────────────────────────

    def _run_swap_skill(self, params_only):
        if not self._ctx_donor or not self._ctx_receptor:
            self._err("Select donor and receptor first.")
            return
        try:
            result = swap_habilidad(
                params_only, self._donor_var, self._receptor_var,
                self._ctx_donor, self._ctx_receptor,
                include_effect=self.chk_effect.isChecked()
            )
            if result: self._ok(result)
        except Exception as e:
            self._err(str(e))

    def _run_swap_attack(self):
        if not self._ctx_donor or not self._ctx_receptor:
            self._err("Select donor and receptor first.")
            return
        try:
            result = procesar_swap_ataques(
                self._atk_donor_var.get(), self._atk_receptor_var.get(),
                self._ctx_donor, self._ctx_receptor,
                include_effect=self.chk_effect.isChecked(),
                include_cman=self.chk_cman.isChecked()
            )
            if result: self._ok(result)
        except Exception as e:
            self._err(str(e))

    def _run_swap_attack_params(self):
        if not self._ctx_donor or not self._ctx_receptor:
            self._err("Select donor and receptor first.")
            return
        try:
            result = procesar_swap_ataques_params_only(
                self._atk_donor_var.get(), self._atk_receptor_var.get(),
                self._ctx_donor, self._ctx_receptor
            )
            if result: self._ok(result)
        except Exception as e:
            self._err(str(e))

    def closeEvent(self, event):
        if self._parent_tool:
            self._parent_tool.setEnabled(True)
        event.accept()