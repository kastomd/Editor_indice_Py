from PyQt5.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot

import traceback
class WorkerSignals(QObject):
    #senales devueltas
    resultado = pyqtSignal(list)
    error = pyqtSignal(str)

class Worker(QRunnable):
    def __init__(self, funcion):
        super().__init__()
        self.funcion = funcion
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            resultado = self.funcion()
            self.signals.resultado.emit(resultado)
        except Exception as e:
            error_msg = traceback.format_exc()  # Obtener la traza del error como texto
            self.signals.error.emit(error_msg)
