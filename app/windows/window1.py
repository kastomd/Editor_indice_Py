import tkinter as tk
from tkinter import ttk
from  tkinter import BOTTOM, RIGHT, Y, Scrollbar, ttk
from app.logic.data_file_manager import DataFileManager
from tkinter import filedialog
import re
import os


class Window1(tk.Frame):
    def __init__(self, master, controlador):
        super().__init__(master)
        self.controlador = controlador
        self.pack(fill="both", expand=True)
        self.datFileManger = DataFileManager(self.controlador)
        #self.configure(bg=settings.COLORS["background"])
        self.data_import={}
        
        #scrollbar
        self.scroll = tk.Scrollbar(self)
        self.scroll.pack(side=RIGHT, fill=Y)
        # Crear el Treeview (tabla)
        columns = ("col1", "col2", "col3")  # Nombres de las columnas
        
        # estilo
        style = ttk.Style()
        style.configure("Treeview", font=("Arial", 12))
        style.configure("Treeview.Heading", font=("Arial", 13, "bold"))
        
        self.tree = ttk.Treeview(self, columns=columns, show="headings", yscrollcommand=self.scroll.set, selectmode="extended")


        self.scroll.config(command=self.tree.yview)

        # Configurar encabezados de las columnas
        self.tree.heading("col1", text="Files")
        self.tree.heading("col2", text="Address")
        self.tree.heading("col3", text="Size")

        # Ajustar el ancho de las columnas
        self.tree.column("col1", width=150, anchor="center")
        self.tree.column("col2", width=150, anchor="center")
        self.tree.column("col3", width=150, anchor="center")

        
        # Crear el menu contextual
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Import", command=self.import_data)
        self.context_menu.add_command(label="Export", command=self.export_data)

        

        # Asociar el evento de clic derecho (Button-3) al Treeview
        self.tree.bind("<Button-3>", self.show_context_menu)

        # Colocar el Treeview en la ventana
        self.tree.pack(expand=True, fill="both")
        
        #verificar si esta vacia la tabla
        self.isclean = True
        
    #programar una boton para limpiar la tabla

    # Funcion para cargar datos en la tabla
    def load_data(self, files_data):
        
        #limpiar la tabla
        self.clear_table()
        self.isclean = False
        
        # Insertar datos en la tabla
        for row in files_data:
            self.tree.insert("", tk.END, values=row, tags=(row[0], ))
        #self.tree.tag_configure("10", foreground="red")
        
    # Funcion para mostrar el menu contextual al hacer clic derecho
    def show_context_menu(self, event):
        if self.isclean or not self.tree.selection():
            return
        self.context_menu.post(event.x_root, event.y_root)
        
    # Funcion para importar archivo
    def import_data(self):
        selected_item = self.tree.selection()
        if selected_item:
            item_values = self.tree.item(selected_item, "values")
            print(f"file {item_values[0]}")
            
            ruta_archivos = filedialog.askopenfilenames(
                title="Choose files",
                filetypes=[("file", "*.unk"), ("All files", "*.*")]
                )
            
            if ruta_archivos:
                #import un archivo
                if len(ruta_archivos) == 1:
                    with open(ruta_archivos[0], "rb") as file:
                        data = file.read()
                        self.data_import[item_values[0]] = data
                        
                        #obtener los items del treeview
                        items = self.tree.get_children()
                        
                        #obtener valores de la fila
                        valores = list(self.tree.item(items[int(item_values[0], 16) - 1], "values"))
                        # Modificar solo la columna size
                        valores[2] = hex(len(data))[2:]
                        # Actualizar el Treeview
                        self.tree.item(items[int(item_values[0], 16) - 1], values=valores)
                        #cambiar el color
                        self.tree.tag_configure(item_values[0], foreground="red")
                    return
                
                #by chat gpt
                # Funcion para extraer el numero entero del nombre del archivo
                def extraer_numero_entero(ruta):
                    nombre_archivo = ruta.split("/")[-1]  # Obtener solo el nombre del archivo
                    match = re.match(r"(\d+)-[0-9a-fA-F]+\.unk", nombre_archivo)
                    if match:
                        return int(match.group(1))  # Retornar el numero entero como entero
                    return float('inf')  # En caso de no coincidir, devolver un valor alto para que quede al final

                # Ordenar las rutas basandose en el numero entero
                rutas_ordenadas = sorted(ruta_archivos, key=extraer_numero_entero)
                if  self.controlador.DEBUG:print(rutas_ordenadas)
                #[{file:bytes}]
                
                for x in rutas_ordenadas:
                    with open(x, "rb") as file:
                        name_without_extension = os.path.splitext(x.split("/")[-1])[0]
                        self.data_import[name_without_extension] = file.read()
            
            
            

    # Funcion para exportar archivo
    def export_data(self):
        file_path = None
        folder_path = None
        data_files_exp = []
        
        #obtener items
        selected_items = self.tree.selection()
        if selected_items:
            for itemTree in selected_items:
                #obtener valores de la fila
                item_values = self.tree.item(itemTree, "values")
                if  self.controlador.DEBUG: print(f"file {item_values[0]}")
                
                #estructura [{file:bytes}]
                with open(self.controlador.file_dialog.path_abs, "rb") as iso:
                    #ir a la pos del archivo en la iso
                    iso.seek(int(
                        self.controlador.file_dialog.datos[
                            int(item_values[0], 16) - 1][1], 16))
                
                    #leer los bytes del archivo
                    file_bytes = iso.read(int(
                        self.controlador.file_dialog.datos[
                            int(item_values[0], 16) - 1][2], 16))
                
                #guardar el archivo y mostrar filedialogo si es un solo archivo
                if len(selected_items) == 1:
                    
                    file_path = filedialog.asksaveasfilename(
                        defaultextension=".unk",  # Extension predeterminada
                        filetypes=[("file", "*.unk"), ("All files", "*.*")],
                        title="Save file as ",
                        initialfile=f"{int(item_values[0], 16)}-{item_values[0]}.unk"#nombre incial
                    )
                    if not file_path: return
                    file_path = os.path.normpath(file_path)
                else:
                    if not folder_path:
                        folder_path = filedialog.askdirectory(
                            title="Choose a folder",
                        )
                    if not folder_path: return
                    #folder_path = os.path.join(folder_path, f"{int(item_values[0], 16)}-{item_values[0]}.unk")
                data_files_exp.append({
                item_values[0] : file_bytes
                })
    
            #guardar archivos
            self.datFileManger.exportFiles(data_files=data_files_exp,
                name_file=file_path, path_abs=folder_path)#guardar un solo archivo
            
    #Funcion para limpiar la tabla
    def clear_table(self):
        if not self.isclean:
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.isclean = True
            if  self.controlador.DEBUG: print("is clean treeview")

