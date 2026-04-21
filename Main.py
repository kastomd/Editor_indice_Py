import sys
import traceback
from PyQt5.QtWidgets import QApplication, QMessageBox

if __name__ == "__main__":
    try:
        # Importar dentro del try para capturar errores de carga
        from app_md.base_app import BaseApp

        app = BaseApp()
        app.run()
    except Exception:
        error_text = traceback.format_exc()

        # carga una ventana temp para mostrar el problema
        temp_app = QApplication.instance()
        if temp_app is None:
            temp_app = QApplication(sys.argv)

        msg = QMessageBox()
        msg.setWindowTitle("Error starting the application")
        msg.setIcon(QMessageBox.Critical)
        msg.setText("An error has occurred while starting the application")
        msg.setDetailedText(error_text)
        msg.exec_()
