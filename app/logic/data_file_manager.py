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
                    
    def importfile(self, root, iso, files, datosOri):
        size_iso = os.path.getsize(iso)
        if root == iso:
            raise ValueError("no se puede sobreescribir en la iso base")
        
        with open(iso, "rb") as file:#iso original
            
         #crear un backup de la iso
            with open(root, "wb") as file_back:#iso backup
                offset = 0#posicion actual
                file.seek(0)
                file_back.seek(0)
                
                #archivos keys
                files_keys = [list(diccionario.keys())[0] for diccionario in files]
                idx = 0
                while offset < size_iso:
                    chunks_bytes = 0x800
                    # no leer demas de la posicion del archivo a insertar
                    if idx < len(files_keys) and (chunks_bytes+offset) >= int(datosOri[int(files_keys[idx], 16) - 1][1], 16):
                        chunks_bytes = chunks_bytes - ((chunks_bytes+offset) - int(datosOri[int(files_keys[idx], 16) - 1][1], 16))
                        
                    content = file.read(chunks_bytes)#bytes origin
                    offset = file.tell()#obtener la posicion actual en la iso
                    
                    if idx < len(files_keys) and offset == int(datosOri[int(files_keys[idx], 16) - 1][1], 16):#escribir los bytes nuevos
                        #escribir los bytes leidos, antes de los nuevos bytes
                        file_back.write(content)
                        content = None
                        content = files[idx][files_keys[idx]]#obtener los bytes nuevos
                        
                        #comprobar si cumple con la especificacion de tamano
                        if len(content) % 0x800 != 0:
                            # Calcular cuantos bytes adicionales se necesitan
                            padding_needed = 0x800 - (len(content) % 0x800)
                            # Agregar los bytes de relleno
                            content += b'\x00' * padding_needed
                        #mover el curso a la posicion del siguiente archivo
                        file.seek(int(datosOri[int(files_keys[idx], 16)][1], 16))
                        offset = int(datosOri[int(files_keys[idx], 16)][1], 16)
                        #idx para iter en la keys de los archivos
                        idx += 1
                    #poswb = file_back.tell()
                    #escibir los datos en la iso bck
                    file_back.write(content)
                    
        if self.controlador.file_dialog.controlador.DEBUG: print("saved iso")
        # insertar los bytes del archivo
        # new_content = content[:1] + 0 + content[2:]
    
        
        
            

        
