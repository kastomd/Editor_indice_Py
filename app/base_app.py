import tkinter as tk
from app.logic import iso_reader
from app.windows.window1 import Window1
from app.logic.file_dialog import FileDialog

class BaseApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Editor indice")
        self.root.geometry("800x600")
        self.file_dialog = FileDialog()
        # Crear el menu superior
        menu_bar = tk.Menu(self.root)

        # Menu File
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Open iso", command=self.file_dialog.openFile)
        file_menu.add_command(label="Save")
        menu_bar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menu_bar)
        self.ventana_actual = None

    def cambiar_ventana(self, ventana):
        if self.ventana_actual:
            self.ventana_actual.destroy()
        self.ventana_actual = ventana(self.root, self)

    def run(self):
        self.cambiar_ventana(Window1)
        datos = iso_reader.IsoReader.listar_archivos_iso(ruta_iso = 'E:\\Documents\\ODI\\#Gu 133\\com.neon.sgu\\games\\VERSION-LATINO-V0.cso.iso')
        self.root.mainloop()

