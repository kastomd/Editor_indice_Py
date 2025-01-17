
from tkinter import filedialog
from app.logic import iso_reader
from app.logic.hex_morph_ttt.offset_convert import OffsetConvert
from tkinter import messagebox
import os
import copy

class FileDialog:
    def __init__(self, controlador):
        #controlador base_app
        self.controlador = controlador
        #ruta del archivo iso
        self.path_abs = None
        #datos de los indices y longitudes del packfile
        self.datos = {}
        self.ttt = OffsetConvert(self)
        #paths de los arhivos de la iso
        self.paths_iso = None
        
    
    def openFile(self):
        # if not self.controlador.ventana_actual.isclean:
        #     messagebox.showinfo("Warning", "close the file")
        #     return
       
        ruta_archivo = filedialog.askopenfilename(
        title="Choose a file",
        filetypes=[("Iso files", "*.iso"), ("All files", "*.*")]
        )
        if ruta_archivo:
            self.controlador.root.config(cursor="watch")  # Cambia el cursor a "wait" o "watch"
            self.controlador.root.update()  # Asegurate de que el cambio sea inmediato
            
            ruta_archivo = os.path.normpath(ruta_archivo)
            #resetear todo
            # self.controlador.close_iso(view = False)
            #usar la funcion close iso
            if  self.controlador.DEBUG:print(f"Archivo seleccionado: {ruta_archivo}")
            self.path_abs = ruta_archivo
            self.controlador.label_packfile.config(text=ruta_archivo)
            
            #'/PSP_GAME/USRDIR/PACKFILE.BIN' = [4128768, 1001226240]
            self.datos = iso_reader.IsoReader.listar_archivos_iso(ruta_iso = self.path_abs)
            
            #path y files de la iso
            self.paths_iso = self.datos

            #obtener info de los archivos, estructura ("file", "address", "size")
            self.datos = self.ttt.getDataIso()
            #cargar los datos de las archivos en la tabla
            # self.controlador.ventana_actual.load_data(self.datos)
            
    def save_as_iso(self):
        # Funcion para extraer el numero hexadecimal de la clave
        def extraer_hex(diccionario):
            clave = list(diccionario.keys())[0]  # Obtiene la clave del diccionario
            try:
                return int(clave, 16)  # Convierte la clave hexadecimal a entero
            except ValueError:
                raise ValueError("Error when reordering file paths.")  # En caso de error
        
        if not self.path_abs: 
            return
        file_path = filedialog.asksaveasfilename(
                    defaultextension=".iso", 
                    filetypes=[("file iso", "*.iso"), ("All files", "*.*")],
                    title="Save file as "
                )

        if file_path:
            #normalizar la ruta
            file_path = os.path.normpath(file_path)
            #ordenar la lista de los archivos importados
            lista_ordenada = sorted(self.controlador.ventana_actual.data_import, key=extraer_hex)
            
            #guardar los datos de la iso
            self.controlador.ventana_actual.datFileManger.importfile(root=file_path, iso=self.path_abs, files=lista_ordenada, datosOri=copy.deepcopy(self.datos))
            
            #arreglar los offsets y longitudes
            self.ttt.setDataIso(iso=file_path, files_imp=lista_ordenada, data_og=copy.deepcopy(self.datos))