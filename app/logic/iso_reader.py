import pycdlib

class IsoReader:
    iso_size = 0
    
    
    def listar_archivos_iso(ruta_iso: str = ''):
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
                
                
                data_files[archivo_path] = [offset, size]

        # Cerrar el archivo ISO
        iso.close()
        return data_files
    

    # Ruta al archivo ISO
    #ruta_iso = 'E:\\Documents\\ODI\\#Gu 133\\com.neon.sgu\\games\\VERSION-LATINO-V0.cso.iso'
    #listar_archivos_iso(ruta_iso)

    #archivo_iso = '/PSP_GAME/USRDIR/PACKFILE.BIN'
