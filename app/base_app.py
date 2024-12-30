import tkinter as tk
from tkinter import ttk
from app.windows.window1 import Window1
from app.logic.file_dialog import FileDialog
from tkinter import messagebox


class BaseApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Editor indice")
        self.dimensions = [800,600]
        
        #centrar la ventana
        y = (self.root.winfo_screenheight() // 2) - (self.dimensions[1] // 2)
        x = (self.root.winfo_screenwidth() // 2) - (self.dimensions[0] // 2)
        self.root.geometry(f"{self.dimensions[0]}x{self.dimensions[1]}+{x}+{y}")
        
        
        #variables
        self.file_dialog = FileDialog(self)
        self.ventana_actual = None
        self.label_packfile = None
        self.import_window = None
        self.export_window = None
        self.Pack_File = '/PSP_GAME/USRDIR/PACKFILE.BIN'
        self.DEBUG = True
        
        
        # Crear el menu superior
        menu_bar = tk.Menu(self.root)

        # Menu File
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Open iso", command=self.file_dialog.openFile, accelerator="Ctrl+O")
        file_menu.add_command(label="Save as", accelerator="Ctrl+s")
        file_menu.add_command(label="Close file", command=self.close_iso, accelerator="Ctrl+Q")
        menu_bar.add_cascade(label="File", menu=file_menu)
        
        # Vincular atajo de teclado
        self.root.bind("<Control-o>", lambda event: self.file_dialog.openFile())
        self.root.bind("<Control-q>", lambda event: self.close_iso())
        
        # Vincular el boton de cerrar
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        #Menu operation
        op_menu = tk.Menu(menu_bar, tearoff=0)
        op_menu.add_command(label="view imported files", command= lambda: self.import_small_window(self.root))
        menu_bar.add_cascade(label="View", menu=op_menu)
        
        #Menu about
        about_menu = tk.Menu(menu_bar, tearoff=0)
        about_menu.add_command(label="About iso", command= lambda: self.import_small_window(self.root))
        menu_bar.add_cascade(label="About", menu=about_menu)

        self.root.config(menu=menu_bar)

    def cambiar_ventana(self, ventana):
        if self.ventana_actual:
            self.ventana_actual.destroy()
        self.ventana_actual = ventana(self.root, self)
        

    def run(self):
        self.cambiar_ventana(Window1)
        
        self.label_packfile = tk.Label(self.root, text="path iso")
        self.label_packfile.pack(side="left")#colocar a la izquierda del todo
        
        self.root.mainloop()
        
    def import_small_window(self, root):
        #reemplazar por un visualizar hexadecimal
        if self.import_window is None or not self.import_window.winfo_exists():
            self.import_window = tk.Toplevel(root)  # Crea una nueva ventana independiente
            self.import_window.geometry("300x100")
            self.import_window.title("import files")

            label = tk.Label(self.import_window, text="Esta es una ventana")
            label.pack(pady=20)

            button = tk.Button(self.import_window, text="Cerrar", command=self.import_window.destroy)
            button.pack()
        else:
            self.import_window.lift()
        
    def export_small_window(self, root):
        if self.export_window is None or not self.export_window.winfo_exists():
            self.export_window = tk.Toplevel(root)  # Crea una nueva ventana independiente
            self.export_window.geometry("300x100")
            self.export_window.title("export files")

            label = tk.Label(self.export_window, text="Esta es una ventana")
            label.pack(pady=20)

            button = tk.Button(self.export_window, text="Cerrar", command=self.export_window.destroy)
            button.pack()
        else:
            self.export_window.lift()

    def on_close(self):
        if self.ventana_actual.isclean or messagebox.askokcancel("Exit", "Are you sure you want to close the window?"):
            self.root.destroy()

    def close_iso(self, view:bool = True):
        #confi cerrar iso
        if view and not self.ventana_actual.isclean and messagebox.askquestion("Warning", "Are you sure you want to do this?") == "no":
                return
        #resetear label
        self.label_packfile.config(text="")
        
        #resetear background de la tabla
        for item in self.file_dialog.datos:
            self.ventana_actual.tree.tag_configure(item[0], foreground = "")
        if self.DEBUG: print("reset tag")
        #limpiar tabla
        self.ventana_actual.clear_table()
        
        #vaciar variables
        self.ventana_actual.data_import = {}
        self.file_dialog.path_abs = ""
        self.file_dialog.datos = {}
        self.file_dialog.ttt.data_iso_packfile = None
        self.ventana_actual.datFileManger.path_iso = None
        if self.DEBUG: print("All cleaned")
        