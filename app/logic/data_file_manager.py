import os
from tkinter import messagebox


class DataFileManager():
    def __init__(self, controlador):
        self.controlador = controlador
        self.path_iso = self.controlador.file_dialog.path_abs
        
    def exportFiles(self, data_files:list, name_file:str = "", path_abs:str = ""):#[{file:bytes}]
        saved = []
        for dic in data_files:#iter en los dic
            for file_num, bytes_f in dic.items():#iterar en el archivo y bytes
                #ruta para varios archivos
                if path_abs:
                    path_file = os.path.normpath(os.path.join(path_abs, f"{int(file_num, 16)}-{file_num}.unk"))
                    
                else:
                    #ruta para un solo archivo
                    path_file = name_file
                    
                saved.append(path_file)
                #guardar en el disco
                with open(path_file, "wb") as file:
                    file.write(bytes_f)
        if  self.controlador.DEBUG:print(f"saved: {saved}")
        messagebox.showinfo("Success", f"saved:\n{saved}")
                    
    def importfile(self, root, files):
        size_iso = os.path.getsize(root)
        
        with open(root, "rb") as file:#iso original
            
         #crear un backup de la iso
            with open(root, "wb") as file_back:#iso backup
                offset = 0#posicion actual
                file.seek(0)
                
                while offset <= size_iso:
                    chunks_bytes = 1.5e+7
                    # no leer demas de la posicion del archivo a insertar
                    if (chunks_bytes+offset) > posinsert:
                        chunks_bytes = chunks_bytes - (chunks_bytes+offset - posinsert)
                        
                    content = file.read(chunks_bytes)#bytes origin
                    offset = file.tell()
                    
                    if offset == posinsert:#escribir los bytes nuevos
                        content = posinsert[1]
                    file_back.write(content)
        
        # insertar los bytes del archivo
        new_content = content[:1] + 0 + content[2:]
    
        
        
            

        
