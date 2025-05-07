import json
from pathlib import Path
from app_md.logic_extr.vag_header import VAGHeader

class PPVA:
    def __init__(self, content):
        self.content = content  # Objeto que contiene path_file y datafilemanager
        self.vag_header = None  # Se inicializa por cada archivo VAG
        self.bytes_file = None

    def compress(self, keydata: bytes, entry, name_folder: Path, path_file: Path, to_wav = False):
        name_file = name_folder.parent / f"compress_{path_file.name}"
        if name_file.exists():
            raise ValueError(f"The \"{name_file.name}\" file already exists and cannot be overwritten.")

        name_vag_content = name_folder.parent.parent / "compress_1-1.unk"
        if name_vag_content.exists():
            raise ValueError(f"The \"{name_vag_content.name}\" file already exists and cannot be overwritten.")

        ppva_file = keydata
        content_file = b''

        # Contar archivos .vag
        n_vag_files = sum(
            1 for f in name_folder.iterdir()
            if f.is_file() and f.suffix == '.vag'
        )
        # self.vag_header.convert_wav_to_vag(folder_audios / "1-1.wav", loop=True)
        frecuencia = None
        vag_content = []
        for x in range(1, n_vag_files+1):
            #obtener los parametros del audio
            with open(name_folder / f"{x}-{x:X}.vag", "rb") as vag:
                vag.seek(0x10)
                frecuencia = int.from_bytes(vag.read(4), byteorder='big')
                vag.seek(0x30)
                vag_data = vag.read()
                
                #si es un audio vacio
                if all(b == 0 for b in vag_data):
                    vag_data=b''

                vag_content.append([len(content_file), frecuencia, len(vag_data)])
                content_file += vag_data

        # guarda el 1-1.unk
        with open(name_vag_content, "wb") as vag_ct:
            content_file+=b'\x00'*0x30
            vag_ct.write(content_file)
        
        # rellena los parametros del audio
        ppva_file += bytes.fromhex(entry.get("fill", '00')) * (n_vag_files * 0x10)
        seek_start = self.content.datafilemanager.dataKey.get(keydata[:4]).get("star")
        endian = entry.get("endianness")
        
        # modifica para del offset 0x4
        ppva_file = ppva_file[:4] + len(ppva_file[8:]).to_bytes(4, byteorder=endian) + ppva_file[8:]

        for data_audio in vag_content:
            if data_audio[2] == 0: data_audio[2] = 0xFFFFFFD0

            ppva_file = ppva_file[:seek_start] + data_audio[0].to_bytes(4, byteorder=endian) + data_audio[1].to_bytes(4, byteorder=endian) + data_audio[2].to_bytes(4, byteorder=endian) + ppva_file[seek_start + 0xc:]
            
            seek_start+=0x10

        # guardar el ppva
        with open(name_file, "wb") as f:
            f.write(ppva_file)

        return [f"1-1.unk y {name_file.name} creados"]

    def extract(self, data_file: dict, bytes_file: bytes):
        self.bytes_file = bytes_file
        audio_entries = []

        # Determinar orden de bytes (endianness)
        offset_bytes = self.bytes_file[4:8]
        endian = self.content.datafilemanager.guess_endianness(offset_bytes)

        if "unk" in endian:
            raise ValueError(endian)

        # Calcular el final de la tabla de entradas
        offset_end = int.from_bytes(offset_bytes, byteorder=endian) + 8

        # Obtener posicion inicial de lectura
        seek = data_file.get("star")
        fill_value = data_file.get("fill")

        # Actualizar entrada en el datafile
        self.content.datafilemanager.update_entry(
            key_bytes=self.bytes_file[:seek],
            endianness=endian,
            pad_offset=data_file.get("eoinx", True),
            ispair=data_file.get("ispair", True),
            fill=fill_value
        )

        # Leer entradas de audio (offset, frecuencia, longitud)
        while seek < offset_end and seek + 16 <= len(self.bytes_file):
            offset = self.bytes_file[seek:seek + 4]
            freq = self.bytes_file[seek + 4:seek + 8]
            length = self.bytes_file[seek + 8:seek + 12]
            seek += 16

            if offset + freq + length == b'\x00' * 12:
                break

            audio_entries.append((offset, freq, length))

        # Leer archivo contenedor con los datos de audio
        container_path = self.content.path_file.parent.parent / "1-1.unk"
        if not container_path.exists():
            raise ValueError(f"Missing container file: {container_path}")

        with open(container_path, "rb") as f:
            container_data = f.read()

        # Crear carpeta de salida
        output_dir = self.content.path_file.parent / self.content.path_file.stem
        if output_dir.is_dir():
            raise ValueError(f"Folder \"{output_dir.name}\" already exists.")
        output_dir.mkdir(exist_ok=True)

        # Guardar configuracion original
        with open(output_dir / "config.set", "w") as config_file:
            config_file.write(self.content.datafilemanager.data)

        exported_files = []

        # Extraer y guardar cada archivo VAG
        for index, (raw_start, raw_freq, raw_end) in enumerate(audio_entries, start=1):
            start = int.from_bytes(raw_start, byteorder=endian)
            freq = int.from_bytes(raw_freq, byteorder=endian)
            end = int.from_bytes(raw_end, byteorder=endian) if raw_end != b'\xD0\xFF\xFF\xFF' else 0
            end += start

            self.vag_header = VAGHeader(
                data_size=end - start,
                sample_rate=freq,
                name=f"{index}-{index:X}"
            )
            header_bytes = self.vag_header.build()

            vag_file = output_dir / f"{index}-{index:X}.vag"
            exported_files.append(vag_file)

            audio_data = container_data[start:end] or b'\x00' * 0x10
            with open(vag_file, "wb") as out_vag:
                out_vag.write(header_bytes + audio_data)

        # Convertir cada VAG a WAV
        for vag_file in exported_files:
            wav_file = output_dir / f"{vag_file.stem}.wav"
            self.vag_header.convert_vag_to_wav(vag_file, wav_file)

        # Guardar metadatos por archivo
        metadata = {}
        for vag_file in exported_files:
            info = self.vag_header.get_audio_info(vag_file,False)
            if info:
                metadata[vag_file.name] = info

        with open(output_dir / "metadato_for_wav.json", "w") as meta_file:
            json.dump(metadata, meta_file, indent=4)

        return [f"{len(exported_files)} VAG audio files exported"]
