import os
from tkinter import messagebox


class DataFileManager():
    def __init__(self, controlador):
        #controlador de window1
        self.controlador = controlador
        #ruta del archivo iso
        self.path_iso = self.controlador.file_dialog.path_abs
        
    #funcion para exportar varios o un archivo
    def exportFiles(self, data_files:list, name_file:str = "", path_abs:str = ""):#[{file:bytes}]
        #contenedor de archivos guardados
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
                #guardar en la unidad
                with open(path_file, "wb") as file:
                    file.write(bytes_f)

        if  self.controlador.DEBUG:print(f"saved: {saved}")
        messagebox.showinfo("Success", f"saved:\n{saved}")
                    
    #funcion encargada de crear la iso y incorporar la bytes de los archivos nuevos
    def importfile(self, root, iso, files, datosOri):
        #verificar si no es el iso base
        if root == iso:
            raise ValueError("It is not possible to overwrite the base ISO")
        
        #obtener el size del iso base
        size_iso = os.path.getsize(iso)
        
        with open(iso, "rb") as file:#iso original
            
         #crear un backup de la iso
            with open(root, "wb") as file_back:
                offset = 0#posicion actual

                #asegurar el puntero en el cero
                file.seek(0)
                file_back.seek(0)
                
                #nombres archivos keys
                files_keys = [list(diccionario.keys())[0] for diccionario in files]
                #contador para iter en las files_keys
                idx = 0
                #no pasar el
                while offset < size_iso:

                    #chunk de lectura
                    chunks_bytes = 0x800

                    # no leer demas de la posicion del archivo a insertar
                    if idx < len(files_keys) and (chunks_bytes+offset) >= int(datosOri[int(files_keys[idx], 16) - 1][1], 16):
                        #chunk modificado hasta el offset de insertacion
                        chunks_bytes = chunks_bytes - ((chunks_bytes+offset) - int(datosOri[int(files_keys[idx], 16) - 1][1], 16))
                        
                    content = file.read(chunks_bytes)#bytes de iso base
                    offset = file.tell()#obtener la posicion actual en la iso
                    
                    #verificar si el offset es la posicion para el archivo importado
                    if idx < len(files_keys) and offset == int(datosOri[int(files_keys[idx], 16) - 1][1], 16):
                        #escribir los bytes leidos de la iso base, antes de los nuevos bytes
                        file_back.write(content)

                        content = None
                        content = files[idx][files_keys[idx]]#obtener los bytes nuevos
                        
                        #comprobar si cumple con la especificacion de tamano
                        if len(content) % 0x800 != 0:
                            # Calcular cuantos bytes adicionales se necesitan
                            padding_needed = 0x800 - (len(content) % 0x800)
                            # Agregar los bytes de relleno
                            content += b'\x00' * padding_needed

                        #mover el curso a la posicion del siguiente archivo, en la iso base
                        file.seek(int(datosOri[int(files_keys[idx], 16)][1], 16))
                        #actualizar la varibale al siguiente offset del archivo importado
                        offset = int(datosOri[int(files_keys[idx], 16)][1], 16)
                        
                        idx += 1

                    #poswb = file_back.tell()
                    #escibir los datos en la iso backup
                    file_back.write(content)
                    
        if self.controlador.file_dialog.controlador.DEBUG: print("saved iso")
        # insertar los bytes del archivo
        # new_content = content[:1] + 0 + content[2:]
    
        
        
            

        
