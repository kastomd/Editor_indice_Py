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
        path_iso = self.contenedor.contenedor.path_iso
        index_packfile = self.contenedor.index_Packfile[0]
        nume_files = int(self.contenedor.edit_lbl_files.text(), 16)

        # Leer el bloque completo de datos necesario
        read_size = (nume_files * 0x10) + 0x10
        with open(path_iso, "rb") as f:
            f.seek(index_packfile)
            self.data_iso_packfile = f.read(read_size)

        # Procesar cada entrada del packfile
        data_filter = []
        for file_index in range(1, len(self.data_iso_packfile) // 0x10):
            base = file_index * 0x10

            file_id = hex(file_index)[2:].upper()
            raw_offset = " ".join(f"{byte:02x}" for byte in self.data_iso_packfile[base : base + 4])
            raw_size = self.data_iso_packfile[base + 4 : base + 8]

            address = self.getOffsetConvert(raw_offset)
            size = self.getSizeConvert(hex(file_index - 1)[2:], raw_size)

            data_filter.append([file_id, address, size])

        return data_filter

    
    def setDataIso(self):
        path_compress = self.contenedor.contenedor.path_iso.parent / f"compress_{self.contenedor.contenedor.path_iso.name}"
        index_packfile = self.contenedor.index_Packfile[0]
        nume_files = int(self.contenedor.edit_lbl_files.text(), 16)
        reem = ""

        with open(path_compress, "r+b") as f:
            # Escribir nuevos offsets y longitudes
            for file in range(1, nume_files + 1):
                new_index = self.contenedor.new_indexs[file - 1]
            
                # Preparar offset
                offset_words = new_index[1] // 0x800
                offset_bytes_str = " ".join(f"{byte:02x}" for byte in offset_words.to_bytes(4, byteorder="little"))
                new_offset = self.getOffsetConvert(offset_bytes_str, False)
                offset_bytes = bytes.fromhex(new_offset)

                # Preparar longitudes
                size_bytes_input = new_index[2].to_bytes(4, byteorder="little")
                new_size = self.getSizeConvert(f"{file - 1:x}", size_bytes_input, False)
                size_bytes = bytes.fromhex(new_size)

                # Escribir en archivo
                f.seek(index_packfile + 0x10 + ((file - 1) * 0x10))
                f.write(offset_bytes)
                f.write(size_bytes)

            # Validar y escribir numero de archivos si es diferente
            f.seek(index_packfile + 4)
            files_old = int.from_bytes(f.read(4), byteorder="little")
            if files_old != nume_files:
                f.seek(index_packfile + 4)
                new_size_bytes = nume_files.to_bytes(4, byteorder="little")
                f.write(new_size_bytes)

                hex_str = "".join(f"{byte:02x}" for byte in new_size_bytes)
                reem = f".\nThe value at position \"0x{index_packfile + 4:X}\" was replaced with \"0x{hex_str}\"."

            # Mensaje adicional si hay leftover
            if self.contenedor.isleftover:
                reem += "\n\nThe leftover.unk file was also written to the ISO."

        return [f"compress_task finished{reem}"]


    def getOffsetConvert(self, val, set_v: bool = True):
        values_address = {
            11: [5, 4, 7, 6, 1, 0, 3, 2, 13, 12, 15, 14, 9, 8, 11, 10],
            22: [1, 0, 3, 2, 5, 4, 7, 6, 9, 8, 11, 10, 13, 12, 15, 14],
            12: [6, 7, 4, 5, 2, 3, 0, 1, 14, 15, 12, 13, 10, 11, 8, 9],
            23: [3, 2, 1, 0, 7, 6, 5, 4, 11, 10, 9, 8, 15, 14, 13, 12],
            13: [6, 7, 4, 5, 2, 3, 0, 1, 14, 15, 12, 13, 10, 11, 8, 9],
            24: [11, 10, 9, 8, 15, 14, 13, 12, 3, 2, 1, 0, 7, 6, 5, 4],
            14: [4, 5, 6, 7, 0, 1, 2, 3, 12, 13, 14, 15, 8, 9, 10, 11],  # algunos datos generados automáticamente, (4,5) correctos
        }

        # Separar el string por espacios y completar hasta tener 4 bytes
        val = val.split(' ')
        val += ['00'] * (4 - len(val))

        for byte_idx in range(4):
            byte = list(val[byte_idx])  # Convertir a lista para mutabilidad

            for bit_idx in range(2):
                key = int(f"{bit_idx + 1}{byte_idx + 1}")
                if key == 21:
                    continue  # Saltar el caso especial

                original_nibble = int(byte[bit_idx], 16)
                mapped_value = values_address.get(key, [])[original_nibble]
                byte[bit_idx] = f"{mapped_value:X}"[-1]  # Convertir a hex sin '0x', solo el ultimo nibble

            val[byte_idx] = "".join(byte)

        val = "".join(val)

        if not set_v:
            return val

        # Reordenar los bytes en formato little endian
        val = int(val[6:8] + val[4:6] + val[2:4] + val[0:2], 16)
        val = val * 0x800
        val += self.contenedor.index_Packfile[0] + int(self.contenedor.edit_lbl_data_size.text(), 16)

        return hex(val)[2:].upper()

        
    def getSizeConvert(self, key: str, bitR, set_v: bool = True):
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

        # Convertir los bytes a string hexadecimal y luego a lista de caracteres
        bitR = list("".join(f"{byte:02x}" for byte in bitR))

        # Rellenar y reorganizar `key` a formato little endian
        key = key.zfill(8)
        key = list(f"{key[6:8]}{key[4:6]}{key[2:4]}{key[0:2]}")

        for i in range(8):
            if key[i] == '0':
                continue  # Saltar si el valor en el key es cero

            key_index = int(key[i], 16)
            bit_index = int(bitR[i], 16)

            # Aplicar la conversion usando el diccionario
            bitR[i] = f"{values_size.get(key_index, [])[bit_index]:X}"

        bitR = "".join(bitR)

        if set_v:
            # Reordenar a little endian y quitar ceros a la izquierda
            bitR = f"{bitR[6:8]}{bitR[4:6]}{bitR[2:4]}{bitR[0:2]}".lstrip('0').upper()

        return bitR if bitR else '0'
