# import time
# import struct
# from tkinter import messagebox


# from PyQt5.QtWidgets import QMessageBox


class DataConvert():
    def __init__(self, conte):
        self.contenedor = conte
        #datos generales del packfile
        self.data_iso_packfile = None
        
        
    def getDataIso(self):
        # time.sleep(5)
        with open(self.contenedor.contenedor.path_iso, "rb") as f:  # Abrir el archivo en modo binario
            
            # f.seek(self.contenedor.index_Packfile[0] + 4 )# posicion de los files total
            # nume_files = struct.unpack('<I', f.read(4))[0]  # Entero sin signo, Little-endian
            nume_files = int(self.contenedor.edit_lbl_files.text(),16)
            
            f.seek(self.contenedor.index_Packfile[0])  # Mover el puntero a la posicion deseada
            self.data_iso_packfile = f.read((nume_files * 16) + 0x10)  # Leer la cantidad de bytes especificada
           
            
            #obtener data de los archivos
            data_filter = []
            for file in range(len(self.data_iso_packfile) // 0x10):
                #skip file 0
                if file == 0:
                    continue
                #" ".join(f"{byte:02x}" for byte in self.data_iso_packfile[file * 0x10 : (file * 0x10) + 4][::-1])
                #[file, address, size] con swap en bytes
                data_filter.append([hex(file)[2:].upper(), 
                                    self.getOffsetConvert(" ".join(f"{byte:02x}" for byte in self.data_iso_packfile[file * 0x10 : (file * 0x10) + 4])), 
                                    self.getSizeConvert(hex(file - 1)[2:], 
                                                        self.data_iso_packfile[ (file * 0x10) + 4 : (file * 0x10) + 0x8])])
            
        return data_filter
    
    def setDataIso(self):
        with open(self.contenedor.contenedor.path_iso+".compress", "r+b") as f:
            nume_files = int(self.contenedor.edit_lbl_files.text(),16)
            f.seek(self.contenedor.index_Packfile[0]+0x10)  # Mover el puntero a la posicion deseada
            # self.data_iso_packfile = f.read(nume_files*0x10) # data indexs

            for file in range(1, nume_files+1):
                offset_bytes = self.contenedor.new_indexs[file-1][1] // 0x800
                offset_bytes = " ".join(f"{byte:02x}" for byte in offset_bytes.to_bytes(4, byteorder='little'))
                # if file == 3: print(f"{offset_bytes}-{file}")
                new_offset = self.getOffsetConvert(offset_bytes, False)
                new_size = self.getSizeConvert(f"{file-1:x}", self.contenedor.new_indexs[file-1][2].to_bytes(4, byteorder='little'), False)

                # if file == 3: print(f"{new_offset}-{file}")
                #convertir el string "5061634b" a bytes
                offset_bytes = bytes.fromhex(new_offset)
                size_bytes = bytes.fromhex(new_size)

                #escribir los offset y longitude nuevas
                f.seek(self.contenedor.index_Packfile[0]+0x10+((file-1)*0x10))
                f.write(offset_bytes)
                f.write(size_bytes)

            #escribir el total de archivos
            f.seek(self.contenedor.index_Packfile[0]+4)
            files_old =f.read(4)
            files_old = int.from_bytes(files_old, byteorder="little")
            reem = ""
            if files_old != nume_files:
                # respuesta = self.contenedor.question_dialog("The number of files in the old ISO is different from the current one.\nDo you want to write the total number of files declared in the program?")
                
                # if respuesta != QMessageBox.Cancel:
                f.seek(self.contenedor.index_Packfile[0]+4)
                new_size_files = nume_files.to_bytes(4, byteorder="little")
                f.write(new_size_files)

                new_size_files = "".join(f"{byte:02x}" for byte in new_size_files)
                reem = f".\nThe value at position \"0x{self.contenedor.index_Packfile[0]+4:X}\" was replaced with \"0x{new_size_files}\"."

        return [f"compress_task finished{reem}"]

    def getOffsetConvert(self, val, set_v:bool=True):
        key:int
        values_address = {
            11: [5, 4, 7, 6, 1, 0, 3, 2, 13, 12, 15, 14, 9, 8, 11, 10],
            22: [1, 0, 3, 2, 5, 4, 7, 6, 9, 8, 11, 10, 13, 12, 15, 14],
            12: [6, 7, 4, 5, 2, 3, 0, 1, 14, 15, 12, 13, 10, 11, 8, 9],
            23: [3, 2, 1, 0, 7, 6, 5, 4, 11, 10, 9, 8, 15, 14, 13, 12],
            13: [6, 7, 4, 5, 2, 3, 0, 1, 14, 15, 12, 13, 10, 11, 8, 9],
            24: [11, 10, 9, 8, 15, 14, 13, 12, 3, 2, 1, 0, 7, 6, 5, 4],
            14: [4, 5, 6, 7, 0, 1, 2, 3, 12, 13, 14, 15, 8, 9, 10, 11],#datos 4,5 y 0,1 bien, los demas se completaron usando IA, no se garantiza que esten bien
        }
        #tomar el primer byte 21 12 58 4b, uno-uno = key, 2 = val= 1bit
        #['50', '61', '63', '4b']
        val = val.split(' ')
        
        #asegurar que tenga 4 elementos
        while len(val) < 4:
            val.append('00')

        for x in range(4):#byte
            for y in range(2):#bit
                key = int(f"{y + 1}{x + 1}")
                #skip el 1 byte, 2 bit
                if key == 21:
                    continue
                
                byte = list(val[x])#lista del byte
                byte[y] = hex(values_address.get(key)[int(byte[y], 16)])[2:]#obtener valor real del bit
                val[x] = "".join(byte)#reemplazar el byte
                
        val = "".join(val)#str
        
        if not set_v:
            return val
        
        val = int(f"{val[6:8]}{val[4:6]}{val[2:4]}{val[0:2]}", 16)#reordenar
        #multiplicar por 0x800
        val *= 0x800
        #sumarle 0x38000 y pos packfile
        val = val + self.contenedor.index_Packfile[0] + int(self.contenedor.edit_lbl_data_size.text(), 16)
        
        return hex(val)[2:].upper()
        
    def getSizeConvert(self, key:str, bitR, set_v:bool=True):
        values_size = {
            1: [1, 0, 3, 2, 5, 4, 7, 6, 9, 8, 11, 10, 13, 12, 15, 14],
            2: [2, 3, 0, 1, 6, 7, 4, 5, 10, 11, 8, 9, 14, 15, 12, 13],
            3: [3, 2, 1, 0, 7, 6, 5, 4, 11, 10, 9, 8, 15, 14, 13, 12],
            4: [4, 5, 6, 7, 0, 1, 2, 3, 12, 13, 14, 15, 8, 9, 10, 11],
            5: [5, 4, 7, 6, 1, 0, 3, 2, 13, 11, 15, 14, 9, 8, 11, 10],
            6: [6, 7, 4, 5, 2, 3, 0, 1, 14, 15, 12, 13, 10, 11, 8, 9],
            7: [7, 6, 5, 4, 3, 2, 1, 0, 15, 14, 13, 12, 11, 10, 9, 8],
            8: [8, 9, 10, 11, 12, 13, 14, 15, 0, 1, 2, 3, 4, 5, 6, 7],
            9: [9, 8, 11, 10, 13, 12, 15, 14, 1, 0, 3, 2, 5, 4, 7, 6],
            10: [10, 11, 8, 9, 14, 15, 12, 13, 2, 3, 0, 1, 6, 7, 4, 5],
            11: [11, 10, 9, 8, 15, 14, 13, 12, 3, 2, 1, 0, 7, 6, 5, 4],
            12: [12, 13, 14, 15, 8, 9, 10, 11, 4, 5, 6, 7, 0, 1, 2, 3],
            13: [13, 12, 15, 14, 9, 8, 11, 10, 5, 4, 7, 6, 1, 0, 3, 2],
            14: [14, 15, 12, 13, 10, 11, 8, 9, 6, 7, 4, 5, 2, 3, 0, 1],
            15: [15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
        }
        #tomar los bytes file 1d, bit c = key = file = 0x1c, obtener del array bitR = 0xd = 1

        bitR = "".join(f"{byte:02x}" for byte in bitR)
        bitR = list(bitR)#convertir los bytes del size a una lista

        key = key.zfill(8)#rellenar con 0
        key = list(f"{key[6:8]}{key[4:6]}{key[2:4]}{key[0:2]}")# Reorganizar los bytes
        
        for x in range(8):
            #skip el file o valor 0
            if key[x] == '0':
                continue
            #cambiar los valores del size
            bitR[x] = hex(values_size.get(
                int(key[x], 16))[int(bitR[x], 16)])[2:]
            
        bitR = "".join(bitR)#convertir en un str
        if set_v:
            #quitar los ceros y reorganizar
            bitR = f"{bitR[6:8]}{bitR[4:6]}{bitR[2:4]}{bitR[0:2]}".lstrip('0').upper()
        return bitR if bitR else '0' #retornar 0 si esta vacia