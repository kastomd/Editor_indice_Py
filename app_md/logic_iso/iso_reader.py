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
                # Extraer información del archivo
                size = record.inode.data_length
                #posicion del archivo
                offset = record.fp_offset
                
                #agregar la info dl archivo
                data_files[archivo_path] = [offset, size]

        # Cerrar el archivo ISO
        iso.close()
        return data_files
    
    #data = '/PSP_GAME/USRDIR/PACKFILE.BIN' = [offset, size]
