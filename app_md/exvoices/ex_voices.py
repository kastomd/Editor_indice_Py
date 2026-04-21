import os
import shutil
import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QFileDialog, QMessageBox,
    QVBoxLayout, QHBoxLayout, QCheckBox, QScrollArea, QComboBox, QFrame,
    QMenuBar, QMenu, QAction, QDialog
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
import qdarkstyle

from pathlib import Path

BASE_DICC = Path(__file__).parent


# RANGOS: (inicio, fin, nombre de carpeta)
RANGOS_VOZ = [
    (4442, 4567, "01_Goku_Base"),
    (4568, 4693, "02_Goku_SSJ"),
    (4694, 4819, "03_Goku_SSJ2"),
    (4820, 4945, "04_Goku_SSJ3"),
    (4946, 5071, "05_Gohan_Niño"),
    (5072, 5197, "06_Gohan_Joven_Base"),
    (5198, 5323, "07_Gohan_Joven_SSJ"),
    (5324, 5449, "08_Gohan_Joven_SSJ2"),
    (5450, 5575, "09_Gohan_Base"),
    (5576, 5701, "10_Gohan_SSJ"),
    (5702, 5827, "11_Gohan_SSJ2"),
    (5828, 5953, "12_Gohan_Definitivo"),
    (5954, 6079, "13_Picoro"),
    (6080, 6205, "14_Krilin"),
    (6206, 6331, "15_Yamcha"),
    (6332, 6457, "16_Tenshinhan"),
    (6458, 6583, "17_Chaos"),
    (6584, 6709, "18_Vegeta_Rastreador"),
    (6710, 6835, "19_Vegeta_Base"),
    (6836, 6961, "20_Vegeta_SSJ"),
    (6962, 7087, "21_Vegeta_SSJ2"),
    (7088, 7213, "22_Vegeta_Majin"),
    (7214, 7339, "23_Trunks_Niño_Base"),
    (7340, 7465, "24_Trunks_Niño_SSJ"),
    (7466, 7591, "25_Trunks_Espada_Base"),
    (7592, 7717, "26_Trunks_Espada_SSJ"),
    (7718, 7843, "27_Trunks_Base"),
    (7844, 7969, "28_Trunks_SSJ"),
    (7970, 8095, "29_Videl"),
    (8096, 8221, "30_Goten_Base"),
    (8222, 8347, "31_Goten_SSJ"),
    (8348, 8473, "32_Gotenks_SSJ"),
    (8474, 8599, "33_Gotenks_SSJ3"),
    (8600, 8725, "34_Super_Gogeta"),
    (8726, 8851, "35_Super_Vegito"),
    (8852, 8977, "36_Bardock"),
    (8978, 9103, "37_Raditz"),
    (9104, 9229, "38_Saibaiman"),
    (9230, 9355, "39_Nappa"),
    (9356, 9481, "40_Cui"),
    (9482, 9607, "41_Zarbon"),
    (9608, 9733, "42_Zarbon_Transformado"),
    (9734, 9859, "43_Dodoria"),
    (9860, 9985, "44_Capitan_Ginyu"),
    (9986, 10111, "45_Recome"),
    (10112, 10237, "46_Guldo"),
    (10238, 10363, "47_Jeice"),
    (10364, 10489, "48_Burter"),
    (10490, 10615, "49_Freezer_Forma_1"),
    (10616, 10741, "50_Freezer_Forma_2"),
    (10742, 10867, "51_Freezer_Forma_3"),
    (10868, 10993, "52_Freezer_Forma_Final"),
    (10994, 11119, "53_Freezer_Full_Power"),
    (11120, 11245, "54_Androide_16"),
    (11246, 11371, "55_Androide_17"),
    (11372, 11497, "56_Androide_18"),
    (11498, 11623, "57_Androide_19"),
    (11624, 11749, "58_Dr_Gero"),
    (11750, 11875, "59_Cell_Jr"),
    (11876, 12001, "60_Cell_Forma_1"),
    (12002, 12127, "61_Cell_Forma_2"),
    (12128, 12253, "62_Cell_Forma_Perfecta"),
    (12254, 12379, "63_Cell_Perfecto"),
    (12380, 12505, "64_Dabura"),
    (12506, 12631, "65_Majin_Bu"),
    (12632, 12757, "66_Super_Bu"),
    (12758, 12883, "67_Super_Bu_Gohan"),
    (12884, 13009, "68_Kid_Bu"),
    (13010, 13135, "69_Broly_SSJL"),
    (13136, 13261, "70_Soldado_de_Freezer"),
]

def procesar_carpeta(origen, combo_donador, combo_receptor):
    destino_base = os.path.join(origen, "Character_Voices")
    os.makedirs(destino_base, exist_ok=True)

    # Crear diccionario: clave = número decimal, valor = nombre del archivo real (ej: 4442_115A.unk)
    archivos_disponibles = {}
    for f in os.listdir(origen):
        if f.endswith(".unk") and "_" in f:
            nombre_sin_ext = f[:-4]  # quitar .unk
            parte_decimal = nombre_sin_ext.split("_")[0]
            if parte_decimal.isdigit():
                archivos_disponibles[int(parte_decimal)] = f

    for (inicio, fin, nombre), chk_var in zip(RANGOS_VOZ, check_vars):
        if not chk_var.isChecked():
            continue  # si no está seleccionado, lo saltamos

        carpeta_personaje = os.path.join(destino_base, nombre)
        os.makedirs(carpeta_personaje, exist_ok=True)
        for i, numero in enumerate(range(inicio, fin + 1), 1):
            if numero in archivos_disponibles:
                nuevo_nombre = f"{i}-{format(i, 'X').upper()}.unk"
                origen_path = os.path.join(origen, archivos_disponibles[numero])
                destino_path = os.path.join(carpeta_personaje, nuevo_nombre)
                shutil.move(origen_path, destino_path)

    aplicar_renombrado_voces(destino_base)
    QMessageBox.information(None, "Extracción completada", "Las voces fueron extraídas correctamente.")
    # if combo_donador and combo_receptor:
    #     actualizar_lista_personajes(origen, combo_donador, combo_receptor)
    actualizar_lista_personajes(origen, combo_donador, combo_receptor)

# ----------------- RENOMBRADO -----------------
def aplicar_renombrado_voces(carpeta_base):
    """
    Aplica los nombres descriptivos de 'LISTA VO TTT.txt' a los audios en cada subcarpeta.
    """
    lista_path = BASE_DICC / "LISTA_VO_TTT.txt"
    if not lista_path.exists():
        QMessageBox.critical(None, "Error", "No se encontró 'LISTA VO TTT.txt'")
        return

    equivalencias = {}
    with open(lista_path, "r", encoding="utf-8") as f:
        for linea in f:
            if ".unk:" in linea:
                partes = linea.strip().split(":")
                if len(partes) == 2:
                    clave = partes[0].strip()
                    valor = partes[1].strip()
                    equivalencias[clave] = valor

    errores = []

    for carpeta_personaje in os.listdir(carpeta_base):
        ruta_completa = os.path.join(carpeta_base, carpeta_personaje)
        if not os.path.isdir(ruta_completa):
            continue

        for archivo in os.listdir(ruta_completa):
            if archivo.endswith(".unk"):
                nuevo_nombre = equivalencias.get(archivo)
                if nuevo_nombre:
                    origen = os.path.join(ruta_completa, archivo)
                    destino = os.path.join(ruta_completa, nuevo_nombre)
                    try:
                        os.rename(origen, destino)
                    except Exception as e:
                        errores.append(f"{archivo}: {e}")


    if errores:
        QMessageBox.warning(None, "Renombrado incompleto", "\n".join(errores))

def restaurar_archivos_a_original(ruta_unk):
    origen_base = os.path.join(ruta_unk, "Character_Voices")
    errores = []

    # Paso 1: revertir nombre descriptivo → 1-1.unk, 2-2.unk, etc.
    ruta_lista = BASE_DICC / "LISTA_VO_TTT.txt"
    if not ruta_lista.exists():
        QMessageBox.critical(None, "Error", "No se encontró LISTA_VO_TTT.txt")
        return

    mapa_descriptivo_a_basico = {}
    with open(ruta_lista, "r", encoding="utf-8") as f:
        for linea in f:
            if ".unk:" in linea:
                partes = linea.strip().split(":")
                if len(partes) == 2:
                    original = partes[0].strip()  # 1-1.unk
                    descriptivo = partes[1].strip()  # 001_intro_1_m_.unk
                    mapa_descriptivo_a_basico[descriptivo] = original

    for inicio, fin, nombre in RANGOS_VOZ:
        carpeta = os.path.join(origen_base, nombre)
        if not os.path.isdir(carpeta):
            continue

        for archivo in os.listdir(carpeta):
            if archivo.endswith(".unk") and archivo in mapa_descriptivo_a_basico:
                nuevo = mapa_descriptivo_a_basico[archivo]
                origen = os.path.join(carpeta, archivo)
                destino = os.path.join(carpeta, nuevo)
                try:
                    os.rename(origen, destino)
                except Exception as e:
                    errores.append(f"Renombrando {archivo}: {e}")

    # Paso 2: mover de 1-1.unk, 2-2.unk... a 4442_115A.unk, etc.
    for inicio, fin, nombre in RANGOS_VOZ:
        carpeta = os.path.join(origen_base, nombre)
        if not os.path.isdir(carpeta):
            continue

        for i, numero in enumerate(range(inicio, fin + 1), 1):
            nombre_1_1 = f"{i}-{format(i, 'X').upper()}.unk"
            nombre_original = f"{numero}_{format(numero, 'X').upper()}.unk"
            ruta_actual = os.path.join(carpeta, nombre_1_1)
            ruta_destino = os.path.join(ruta_unk, nombre_original)
            if os.path.exists(ruta_actual):
                try:
                    shutil.move(ruta_actual, ruta_destino)
                except Exception as e:
                    errores.append(f"{nombre_1_1}: {e}")
            else:
                errores.append(f"No encontrado: {nombre_1_1}")

    # Eliminar carpetas vacías
    for _, _, nombre in RANGOS_VOZ:
        carpeta = os.path.join(origen_base, nombre)
        if os.path.isdir(carpeta) and not os.listdir(carpeta):
            os.rmdir(carpeta)

    if os.path.isdir(origen_base) and not os.listdir(origen_base):
        os.rmdir(origen_base)

    if errores:
        QMessageBox.warning(None, "Restaurado con errores", "\n".join(errores))
    else:
        QMessageBox.information(None, "Restaurado", "Todos los audios fueron restaurados correctamente.")

# ================= INTERFAZ ==================


class ExVoicesApp(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool)

        # Crear barra de menú
        menu_bar = QMenuBar(self)
        file_menu = QMenu("File", self)
        tools_menu = QMenu("Tools", self)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        menu_bar.addMenu(file_menu)
        menu_bar.addMenu(tools_menu)

        # Establecer la barra como menú de la ventana
        self.setWindowTitle("ExVoices")
        self.setMinimumSize(600, 750)
        self.resize(600, 750)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        container = QWidget()
        self.layout = QVBoxLayout(container)
        self.layout.setAlignment(Qt.AlignTop)

        scroll_area.setWidget(container)

        # Layout principal
        main_layout = QVBoxLayout(self)
        main_layout.setMenuBar(menu_bar)
        main_layout.addWidget(scroll_area)

        self.ruta_unk = None
        self.check_vars = []
        self.checkboxes = []

        self.init_ui()

    def init_ui(self):
        # Texto principal
        label = QLabel("Extraer Voces de Personajes desde ISO Descomprimido")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.layout.addWidget(label)

        # Botón seleccionar carpeta
        self.add_button("📁 Seleccionar carpeta ext_PACKFILE", self.seleccionar_carpeta)

        # Scroll para checkboxes
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setFixedHeight(310)  # ← altura definida y cerrada

        # Check global
        self.var_todos = QCheckBox("Seleccionar/Deseleccionar todos")
        self.var_todos.setChecked(True)
        self.var_todos.stateChanged.connect(self.alternar_todos)
        scroll_layout.addWidget(self.var_todos)

        # Checks por personaje
        for _, _, nombre in RANGOS_VOZ:
            var = QCheckBox(nombre)
            var.setChecked(True)
            scroll_layout.addWidget(var)
            self.check_vars.append(var)

        # Agregar el scroll al layout principal
        self.layout.addWidget(scroll_area)

        # ==== SECCIÓN FIJA: botones debajo del scroll ====
        self.layout.addSpacing(15)  # separador visual
        h_layout = QHBoxLayout()

        btn_extraer = QPushButton("📤 Iniciar extracción de voces")
        btn_extraer.setMinimumWidth(200)
        btn_extraer.clicked.connect(self.iniciar_extraccion)
        h_layout.addWidget(btn_extraer)

        btn_restaurar = QPushButton("♻️ Restaurar audios para comprimir")
        btn_restaurar.setMinimumWidth(200)
        btn_restaurar.clicked.connect(self.restaurar_a_original)
        h_layout.addWidget(btn_restaurar)

        self.layout.addLayout(h_layout)

        self.setup_swap_section()

    def add_button(self, text, func):
        btn = QPushButton(text)
        btn.setFixedSize(280, 38)
        btn.clicked.connect(func)
        self.layout.addWidget(btn, alignment=Qt.AlignCenter)

    def alternar_todos(self):
        estado = self.var_todos.isChecked()
        for v in self.check_vars:
            v.setChecked(estado)

    def seleccionar_carpeta(self):
        ruta = QFileDialog.getExistingDirectory(self, "Selecciona carpeta con .unk")
        if ruta:
            self.ruta_unk = ruta
            QMessageBox.information(self, "Ruta seleccionada", f"Carpeta seleccionada:\n{ruta}")
            actualizar_lista_personajes(ruta, self.combo_donador, self.combo_receptor)

    def iniciar_extraccion(self):
        if self.ruta_unk:
            global check_vars
            check_vars = self.check_vars
            procesar_carpeta(self.ruta_unk, self.combo_donador, self.combo_receptor)
        else:
            QMessageBox.critical(self, "Error", "Primero selecciona una carpeta")

    def restaurar_a_original(self):
        if not self.ruta_unk:
            QMessageBox.critical(self, "Error", "Primero selecciona una carpeta para restaurar.")
            return
        restaurar_archivos_a_original(self.ruta_unk)

    def setup_swap_section(self):
        self.layout.addSpacing(15)

        swap_label = QLabel("Intercambiar audios entre personajes")
        swap_label.setAlignment(Qt.AlignCenter)
        swap_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.layout.addWidget(swap_label)

        combo_layout = QHBoxLayout()
        self.combo_donador = QComboBox()
        self.combo_receptor = QComboBox()
        combo_layout.addWidget(self._combo_with_label("Donador", self.combo_donador))
        combo_layout.addWidget(self._combo_with_label("Receptor", self.combo_receptor))
        self.layout.addLayout(combo_layout)

        btn_swap = QPushButton("🔃 Swap")
        btn_swap.setFixedSize(200, 36)
        btn_swap.setStyleSheet("font-size: 15px; font-weight: bold;")
        btn_swap.clicked.connect(self.realizar_swap)
        self.layout.addWidget(btn_swap, alignment=Qt.AlignCenter)

    def _combo_with_label(self, title, combo):
        frame = QFrame()
        vbox = QVBoxLayout(frame)
        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-weight: bold;")
        vbox.addWidget(label)
        vbox.addWidget(combo)
        return frame

    def realizar_swap(self):
        base = os.path.join(self.ruta_unk, "Character_Voices") if self.ruta_unk else ""
        if not base or not os.path.exists(base):
            QMessageBox.critical(self, "Error", "Selecciona primero la carpeta con los .unk")
            return
        realizar_swap(self.combo_donador, self.combo_receptor, base)

# FUNCIONES AUXILIARES COMPATIBLES CON PyQt5

def actualizar_lista_personajes(ruta_unk, combo_donador, combo_receptor):
    ruta = os.path.join(ruta_unk, "Character_Voices")
    if not os.path.isdir(ruta):
        return
    personajes = sorted([f for f in os.listdir(ruta) if os.path.isdir(os.path.join(ruta, f))])
    combo_donador.clear()
    combo_receptor.clear()
    combo_donador.addItems(personajes)
    combo_receptor.addItems(personajes)

def realizar_swap(combo_donador, combo_receptor, base):
    donador = combo_donador.currentText()
    receptor = combo_receptor.currentText()

    if not donador or not receptor:
        QMessageBox.critical(None, "Error", "Debes seleccionar ambas carpetas")
        return

    if donador == receptor:
        QMessageBox.critical(None, "Error", "El donador y receptor no pueden ser iguales")
        return

    carpeta_donador = os.path.join(base, donador)
    carpeta_receptor = os.path.join(base, receptor)

    if not os.path.isdir(carpeta_donador) or not os.path.isdir(carpeta_receptor):
        QMessageBox.critical(None, "Error", "Una o ambas carpetas no existen")
        return

    errores = []
    for archivo in os.listdir(carpeta_donador):
        origen = os.path.join(carpeta_donador, archivo)
        destino = os.path.join(carpeta_receptor, archivo)
        try:
            shutil.copy2(origen, destino)
        except Exception as e:
            errores.append(f"{archivo}: {e}")

    if errores:
        QMessageBox.warning(None, "Swap con errores", "\n".join(errores))
    else:
        QMessageBox.information(None, "Swap exitoso", f"Audios de '{donador}' copiados en '{receptor}'")

