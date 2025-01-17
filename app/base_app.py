import tkinter as tk
from tkinter import RIGHT, Y, ttk
from app.windows.window1 import Window1
from app.logic.file_dialog import FileDialog
from tkinter import messagebox

import sv_ttk
import pywinstyles, sys
import webbrowser
import threading


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
        self.import_name_files = None
        self.check_var = tk.BooleanVar()
        self.check_var.set(False)
        self.file_dialog = FileDialog(self)
        self.ventana_actual = None
        self.label_packfile = None
        self.import_window = None
        self.export_window = None
        self.about_window = None
        self.about_iso_window = None
        self.Pack_File = '/PSP_GAME/USRDIR/PACKFILE.BIN'
        self.DEBUG = True
        
        
        # Crear el menu superior
        menu_bar = tk.Menu(self.root)

        # Menu File
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Open iso", command=self.open_iso_task, accelerator="Ctrl+O")
        file_menu.add_command(label="Save as", command=self.save_iso_task, accelerator="Ctrl+s")
        file_menu.add_command(label="Close file", command=self.close_iso, accelerator="Ctrl+Q")
        menu_bar.add_cascade(label="File", menu=file_menu)
        
        # Vincular atajo de teclado
        self.root.bind("<Control-o>", lambda event: self.open_iso_task())
        self.root.bind("<Control-q>", lambda event: self.close_iso())
        self.root.bind("<Control-s>", lambda event: self.save_iso_task())
        
        # Vincular el boton de cerrar
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        #Menu operation
        op_menu = tk.Menu(menu_bar, tearoff=0)
        op_menu.add_command(label="view imported files", command= lambda: self.import_small_window(self.root))
        menu_bar.add_cascade(label="View", menu=op_menu)
        
        #Menu about
        about_menu = tk.Menu(menu_bar, tearoff=0)
        about_menu.add_command(label="About iso", command= lambda: self.about_iso(self.root))
        about_menu.add_command(label="About", command= lambda: self.about(self.root))
        menu_bar.add_cascade(label="About", menu=about_menu)

        #establecer menu al root
        self.root.config(menu=menu_bar)

    #cambia la ventana principal
    def change_window(self, ventana):
        if self.ventana_actual:
            self.ventana_actual.destroy()
        self.ventana_actual = ventana(self.root, self)
        
    #by repo Sun-Valley-ttk-theme
    def apply_theme_to_titlebar(self, root):
        version = sys.getwindowsversion()

        if version.major == 10 and version.build >= 22000:
            # Set the title bar color to the background color on Windows 11 for better appearance
            pywinstyles.change_header_color(root, "#1c1c1c" if sv_ttk.get_theme() == "dark" else "#fafafa")
        elif version.major == 10:
            pywinstyles.apply_style(root, "dark" if sv_ttk.get_theme() == "dark" else "normal")

            # A hacky way to update the title bar's color on Windows 10 (it doesn't update instantly like on Windows 11)
            root.wm_attributes("-alpha", 0.99)
            root.wm_attributes("-alpha", 1)

    #inciador
    def run(self):
        #usar theme light
        sv_ttk.use_light_theme()
        #asignar la ventana
        self.change_window(Window1)
        
        #label path iso
        self.label_packfile = ttk.Label(self.root, text="//")
        self.label_packfile.pack(side="left")#colocar a la izquierda del todo
        
        #aplicar el theme a la barra
        self.apply_theme_to_titlebar(self.root)
        self.root.mainloop()
        
    #event tarea en hilo secundario
    def open_iso_task(self):
        def check_data_after():
            # Verificar si el hilo ha terminado
            if proceso.is_alive():
                self.root.after(100, check_data_after)  # Revisar nuevamente en 100 ms
            else:
                #cargar los datos en la tabla en el hilo principal
                self.ventana_actual.load_data(self.file_dialog.datos)
                
                self.root.config(cursor="")  # Restaura el cursor al predeterminado
                self.root.update()
                
        if not self.ventana_actual.isclean:
            messagebox.showinfo("Warning", "close the file")
            return
        
        #procesar la tarea a un hilo secundario
        proceso = threading.Thread(target=self.file_dialog.openFile)
        proceso.start()
        
        #verificar si el hilo termino
        check_data_after()
        
    def save_iso_task(self):
        #crear un hilo
        proceso = threading.Thread(target=self.file_dialog.save_as_iso)
        proceso.start()

    #ventana de archivos importados
    def import_small_window(self, root):
        if self.import_window is None or not self.import_window.winfo_exists():
            self.import_window = tk.Toplevel(root)  # Crea una nueva ventana independiente
            self.import_window.geometry("300x100")
            self.import_window.title("import files")

            scroll = ttk.Scrollbar(self.import_window)
            scroll.pack(side=RIGHT, fill=Y)
            label = ttk.Label(self.import_window, text="Esta es una ventana \nasdjaidiieja\nodoajifojoajjooi\naoijiojsjisao")
            label.pack(pady=20)
            scroll.config(command=label)

            button = ttk.Button(self.import_window, text="Cerrar", style='Accent.TButton', command=self.import_window.destroy)
            button.pack()
        else:
            self.import_window.lift()
        
    #muestra ciertos datos importantes de la iso
    def about_iso(self, root):
        if self.about_iso_window is None or not self.about_iso_window.winfo_exists():
            self.about_iso_window = tk.Toplevel(root)  # Crea una nueva ventana independiente
            self.about_iso_window.geometry("400x200")
            self.about_iso_window.title("About iso")

            label = ttk.Label(self.about_iso_window, text="path Packfile", font=("Arial", 11))
            label.pack(side="left", padx=10, pady=10)

            entry = ttk.Entry(self.about_iso_window, font=("Arial", 12))
            entry.delete(0, tk.END)
            entry.insert(0, self.Pack_File) 
            entry.pack(side="right", padx=10, pady=10)
            
            button = ttk.Button(self.about_iso_window, text="Cerrar", style='Accent.TButton', command=self.about_iso_window.destroy)
            button.pack(side="bottom")
        else:
            self.about_iso_window.lift()
            
    def about(self, root):
        #comprobar la instancia de la ventana
        if self.about_window is None or not self.about_window.winfo_exists():
            self.about_window = tk.Toplevel(root)
            self.about_window.geometry("260x100")
            self.about_window.title("About")
            
            #quitar redimensionamiento
            self.about_window.resizable(False, False)
            
            label = ttk.Label(self.about_window, text="by kasto", foreground="blue", cursor="hand2")
            label.pack(side="top", anchor="w", padx=10, pady=10)
            
            label.bind(
                "<Button-1>", lambda event: webbrowser.open("https://www.youtube.com/@KASTOMODDER15")
            )
            
            #check para cambiar theme de la app
            switch = ttk.Checkbutton(self.about_window, text='dark theme', style='Switch.TCheckbutton', variable=self.check_var, command=lambda: (
                sv_ttk.use_dark_theme() or self.apply_theme_to_titlebar(root)
                if self.check_var.get()
                else sv_ttk.use_light_theme() or self.apply_theme_to_titlebar(root)
            ))
            
            switch.pack(side="bottom", anchor="w", padx=10, pady=15)
        else:
            #traer al frente
            self.about_window.lift()

    #event cerra app
    def on_close(self):
        #evitar un cierre de la app no previsto
        if self.ventana_actual.isclean or messagebox.askokcancel("Exit", "Are you sure you want to close the window?"):
            self.root.destroy()

    #funcion para vaciar los datos del iso de la memoria
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
        self.ventana_actual.data_import = []
        self.file_dialog.path_abs = None
        self.file_dialog.datos = {}
        self.file_dialog.paths_iso = None
        self.file_dialog.ttt.data_iso_packfile = None
        self.ventana_actual.datFileManger.path_iso = None
        if self.DEBUG: print("All cleaned")
        