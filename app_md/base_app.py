import sys


from PyQt5.QtWidgets import QAction, QApplication, QMainWindow, QMessageBox, QSplashScreen, QWidget
from PyQt5.QtGui import QGuiApplication, QIcon, QPixmap
from PyQt5.QtCore import Qt, QTimer
from pathlib import Path
from app_md.windows.about_dialog import AboutDialog

class BaseApp:
    def __init__(self):
        self.version = "1.20250408"

        # Crear QApplication primero
        self.app = QApplication(sys.argv)

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
        self.window = QMainWindow()
        self.window.setWindowTitle("Editor indice tag team")
        self.window.resize(800, 600)
        self.center_on_screen()
        
        self.icon = Path(__file__).resolve().parent / "images" / "icon.ico"
        self.window.setWindowIcon(QIcon(str(self.icon)))
        
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
        exit_action = QAction("Exit", self.window)
        exit_action.triggered.connect(self.window.close)
        file_menu.addAction(exit_action)

        # Menu About
        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About", self.window)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def show_about(self):
        self.about = AboutDialog(self)
        self.about.show_about()
