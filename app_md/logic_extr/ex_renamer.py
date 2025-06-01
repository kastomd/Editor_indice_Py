from pathlib import Path
import struct
import zlib

class ExRenamer():
    def __init__(self, contenedor):
        self.content = contenedor
        self.data_keys = [b'\x00\x00\x01\xF1', b'\x50\x50\x56\x41']
        self.categoria_renamer = None

    def renamer(self, name_unk):
        for cat, items in self.categoria_renamer.items():
            for row in range(len(items)):
                if name_unk == items[row][0]:
                    path_renamer =  f"{items[row][1]}" if "*" in cat else Path(f"{cat}/{items[row][1]}")

                    return path_renamer # retorna la carpeta y el nombre el archivo
        return False

    def check_type(self, key, n_vag:int=0):
        if not key in self.data_keys:
            self.categoria_renamer = None
            return False

        if key == self.data_keys[0]:
            self.categoria_renamer = self.content.extract_dynamic_categories(ruta_txt=self.content.listpack / "patch.txt")
            return True

        if key == self.data_keys[1]:
            if n_vag == 97:
                name_list = "sfx_ch.txt"
            elif n_vag == 85:
                name_list = "sfx_bt.txt"
            else:
                self.categoria_renamer = None
                return False

            self.categoria_renamer = self.content.extract_dynamic_categories(ruta_txt=self.content.listpack / name_list)
            return True

class TanmAnmCompressor():
    def __init__(self):
        pass

    def batch_convert_tanm_anm(self, paths_anm, paths_tanm):
        if paths_tanm:
            self.decompress_tanm_a_anm(paths_anim=paths_tanm)
        if paths_anm:
            self.compress_anm_a_tanm(paths_anim=paths_anm)

    def decompress_tanm_a_anm(self, paths_anim):
        """
        Descomprime un archivo .tanm (ttt) a .anm (bt3-cr) tipo QuickBMS.
        Formato:
            - Big Endian
            - SIZE (4 bytes), ZSIZE (4 bytes), seguido del bloque zlib comprimido
        """
        if isinstance(paths_anim, list):
            for path_file in paths_anim:
                self.decompress_tanm_a_anm(paths_anim=path_file)

        elif isinstance(paths_anim, Path):
            path_anim = paths_anim
            try:
                with open(path_anim, "rb") as f:
                    size = struct.unpack(">I", f.read(4))[0]
                    zsize = struct.unpack(">I", f.read(4))[0]
                    data = f.read(zsize)
                    resultado = zlib.decompress(data)

                with open(path_anim.with_suffix(".anm"), "wb") as out:
                    out.write(resultado)
            except Exception as e:
                raise ValueError(f"Error descomprimiendo {path_anim}: {e}")

    
    def compress_anm_a_tanm(self, paths_anim):
        """
        Comprime un archivo .anm (bt3-cr) de vuelta a formato .tanm (ttt) (zlib + header).
        Guarda: [SIZE descomp][ZSIZE comp][data zlib]
        """
        
        if isinstance(paths_anim, list):
            for path_file in paths_anim:
                self.compress_anm_a_tanm(paths_anim=path_file)

        elif isinstance(paths_anim, Path):
            path_anim = paths_anim
            try:
                with open(path_anim, "rb") as f:
                    data = f.read()
                zdata = zlib.compress(data)

                with open(path_anim.with_suffix(".tanm"), "wb") as out:
                    out.write(struct.pack(">I", len(data)))    # SIZE original
                    out.write(struct.pack(">I", len(zdata)))   # ZSIZE comprimido
                    out.write(zdata)
            except Exception as e:
                raise ValueError(f"Error comprimiendo {path_anim}: {e}")