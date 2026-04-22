import struct

import pycdlib


class IsoReader:
    #size del iso
    iso_size = 0


    def listar_archivos_iso(ruta_iso: str = ''):
        #paths de los archivos
        data_files = {}

        # Cargar el archivo ISO
        iso = pycdlib.PyCdlib()
        iso.open(ruta_iso)
        global iso_size
        iso_size = iso._get_iso_size()

        # Usar walk para explorar el contenido
        for path, dirs, files in iso.walk(iso_path='/'):
            # Procesar archivos
            for archivo in files:
                archivo_path = f"{path}/{archivo.strip()}"
                # Obtener el record del archivo
                record = iso.get_record(iso_path=archivo_path)
                # Extraer informacion del archivo
                size = record.inode.data_length
                #posicion del archivo
                offset = record.fp_offset

                # crear record parcial
                dr_len = record.dr_len
                xattr_len = record.xattr_len
                extent = record.orig_extent_loc
                # Empaquetar
                data = bytearray()

                # 0 - Length of Directory Record
                data += struct.pack("B", dr_len)
                # 1 - Extended Attribute Length
                data += struct.pack("B", xattr_len)
                # 2–5 - Extent Location (LE)
                data += struct.pack("<I", extent)
                # 6–9 - Extent Location (BE)
                data += struct.pack(">I", extent)
                # 10–13 - Data Length (LE)
                data += struct.pack("<I", size)
                # 14–17 - Data Length (BE)
                data += struct.pack(">I", size)

                #agregar la info dl archivo
                data_files[archivo_path] = [offset, size, data]

        # Cerrar el archivo ISO
        iso.close()

        # buscar patron en la iso
        with open(ruta_iso, "rb") as f:
            entry = data_files.get('//UMD_DATA.BIN') or next(iter(data_files.values()))
            offset, size, data = entry

            data = f.read(offset)

        for k, v in data_files.items():
            posiciones = []
            offset = 0
            while True:
                pos = data.find(data_files[k][2], offset)
                if pos == -1:
                    break

                posiciones.append(pos)
                offset = pos + 1  # seguir buscando

            data_files[k][2] = posiciones[0] if len(posiciones) == 1 else None

        print(data_files)
        return data_files

    #data = '/PSP_GAME/USRDIR/PACKFILE.BIN' = [offset, size]
