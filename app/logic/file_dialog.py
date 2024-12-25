from tkinter import filedialog

class FileDialog:
    def __init__(self):
        self.path_abs = ""
    
    def openFile(self):
        ruta_archivo = filedialog.askopenfilename(
        title="Choose a file",
        filetypes=[("Iso files", "*.iso"), ("All files", "*.*")]
        )
        if ruta_archivo:
            print(f"Archivo seleccionado: {ruta_archivo}")
            self.path_abs = ruta_archivo
