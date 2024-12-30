from pydoc import text
from tkinter import filedialog
from app.logic import iso_reader
from app.logic.hex_morph_ttt.offset_convert import OffsetConvert
from tkinter import messagebox

class FileDialog:
    def __init__(self, controlador):
        self.controlador = controlador
        self.path_abs = ""
        self.datos = {}
        self.ttt = OffsetConvert(self)
        
    
    def openFile(self):
        if not self.controlador.ventana_actual.isclean:
            if messagebox.askquestion("Warning", "Are you sure you want to do this?") == "no": return
       
        ruta_archivo = filedialog.askopenfilename(
        title="Choose a file",
        filetypes=[("Iso files", "*.iso"), ("All files", "*.*")]
        )
        if ruta_archivo:
            #resetear todo
            self.controlador.close_iso(view = False)
            #usar la funcion close iso
            if  self.controlador.DEBUG:print(f"Archivo seleccionado: {ruta_archivo}")
            self.path_abs = ruta_archivo
            self.controlador.label_packfile.config(text=ruta_archivo)
            
            #'/PSP_GAME/USRDIR/PACKFILE.BIN' = [4128768, 1001226240]
            self.datos = iso_reader.IsoReader.listar_archivos_iso(ruta_iso = self.path_abs)
            
            #obtener info de los archivos, estructura ("file", "address", "size")
            self.datos = self.ttt.getDataIso()
            
            #cargar los datos de las archivos en la tabla
            self.controlador.ventana_actual.load_data(self.datos)