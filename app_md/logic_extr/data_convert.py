from app_md.logic_extr.vag_header import VAGHeader


class DataConvert():
    def __init__(self, contenedor):
        self.content=contenedor

    def load_offsets(self):
        # Leer el archivo completo en memoria
        with open(self.content.path_file, "rb") as f:
            file_bytes = f.read()
        self.bytes_file = file_bytes  # Guarda los bytes para otros usos

        # Obtener clave de 4 bytes
        bytes_keys = file_bytes[:4]
        # file_ppva = True if bytes_keys == b'\x50\x50\x56\x41' else False
        data_file = self.content.datafilemanager.dataKey.get(bytes_keys)

        if bytes_keys == b'\x50\x50\x56\x41':
            return self.ppva_extract(data_file=data_file)

        # Intentar con 2 bytes si los 4 fallan
        if not data_file:
            bytes_keys = bytes_keys[:2]
            data_file = self.content.datafilemanager.dataKey.get(bytes_keys)
            if not data_file:
                raise ValueError("Unknown file: The file key could not be identified.")

        # Leer configuracion del archivo
        pad_offset = data_file.get("eoinx", True)
        star_seek = data_file.get("star")
        fill = data_file.get("fill", b'\x00')

        # Preparar posicion inicial de lectura
        if star_seek is not None:
            extra_bytes = file_bytes[4:star_seek]
            bytes_keys = file_bytes[:4]
            bytes_keys += extra_bytes

        # Determinar endianness
        offset_start = file_bytes[star_seek or 4 : (star_seek or 4) + 4]
        endian = self.content.datafilemanager.guess_endianness(offset_start)
        if "unknown" in endian:
            # segundo intento para determinar el endianness
            f_offset_start = file_bytes[(star_seek or 4) + 4: (star_seek or 4) + 8]
            endian = self.content.datafilemanager.guess_endianness(f_offset_start)

            if "unknown" in endian:
                raise ValueError(endian)

        # Calcular fin del bloque de offsets
        offset_fin = int.from_bytes(offset_start, byteorder=endian)

        # Leer todos los offsets
        self.data_offsets = []
        cursor = star_seek if star_seek else 4
        while cursor < offset_fin:
            raw_offset = file_bytes[cursor:cursor+4]
            if len(raw_offset) < 4:
                break  # EOF inesperado
            value = int.from_bytes(raw_offset, byteorder=endian)
            if value == int.from_bytes(fill * 4, byteorder=endian):
                break
            self.data_offsets.append(value)
            cursor += 4

        # Determinar si es par
        ispair = data_file.get("ispair")
        if ispair is None:
            ispair = True

        # Actualizar entrada
        self.content.datafilemanager.update_entry(
            key_bytes=bytes_keys,
            endianness=endian,
            pad_offset=pad_offset,
            ispair=ispair,
            fill=fill
        )

        self.typedata = data_file.get("data")
        return self.save_files()

    
    def save_files(self):
        output_path = self.content.path_file.parent / self.content.path_file.stem
        if output_path.is_dir():
            raise ValueError(f'folder "{output_path}" already exists and cannot be overwritten.')
        output_path.mkdir(exist_ok=True)

        ispair = self.content.datafilemanager.entry.get("ispair")
        size_indexs = len(self.data_offsets) - 1 if ispair else len(self.data_offsets)
        is_txt = self.typedata == "txt"

        previewtxt = b'\xFF\xFE'  # UTF-16LE BOM

        for idx in range(size_indexs):
            start = self.data_offsets[idx]
            end = self.data_offsets[idx + 1] if idx + 1 < len(self.data_offsets) else len(self.bytes_file)
            data_bytes = self.bytes_file[start:end]

            file_name = f"{idx+1}-{idx+1:X}"
            file_path = output_path / f"{file_name}.{'txt' if is_txt else 'unk'}"

            if is_txt:
                # Nombre del archivo codificado como UTF-16LE
                encoded_name = f"{file_name}.txt\n".encode('utf-16-le')

                # Detectar fin de cadena (doble cero en UTF-16)
                terminator_index = data_bytes.find(b'\x00\x00')
                if terminator_index != -1:
                    if len(data_bytes) == 2:
                        terminator_index = 1
                    data_bytes = data_bytes[:terminator_index + 1]
                    if data_bytes == b'\x00\x00':
                        data_bytes = b''

                # Agregar fragmento al preview
                previewtxt += encoded_name
                fragment = data_bytes[:0x3e] if len(data_bytes) >= 0x3e else data_bytes
                if len(fragment) != 0:
                    previewtxt += fragment
                    previewtxt += b'\x2e\x00' * 3  # Tres puntos en UTF-16LE
                else:
                    previewtxt += "null".encode('utf-16-le')
                previewtxt += "\n\n".encode('utf-16-le')

                # Prepend BOM para archivo
                data_bytes = b'\xFF\xFE' + data_bytes

            # Escribir archivo
            with open(file_path, "wb") as f:
                f.write(data_bytes)

        # Guardar archivo de vista previa
        if is_txt:
            with open(output_path / "preview_txts.txt", "wb") as f:
                f.write(previewtxt)

        # Guardar configuracion
        with open(output_path / "config.set", "w") as cf:
            cf.write(self.content.datafilemanager.data)

        self.bytes_file = None
        # eliminar entrada
        self.content.datafilemanager.update_entry(
            key_bytes=b'\x00',
            endianness='little',
            pad_offset=True,
            ispair=True,
            fill=b'\x00'
        )
        return ['Files saved <a href="#">open folder</a>', output_path]


    def import_config(self):
        # Determinar el directorio que contiene los archivos
        name_folder = self.content.path_file if self.content.path_file.is_dir() \
            else self.content.path_file.parent / self.content.path_file.stem

        # Cargar configuracion desde archivo
        config_path = name_folder / "config.set"
        self.content.datafilemanager.load_entry(path=config_path)

        # Contar archivos en el directorio (excluyendo "config.set")
        n_files = sum(1 for f in name_folder.iterdir() if f.is_file()) - 1

        # Obtener clave de entrada
        entry = self.content.datafilemanager.entry
        key_hex = entry.get("key")
        key_data = bytes.fromhex(key_hex)
        content_file = bytearray(key_data)

        # Obtener tipo de datos si es "txt"
        data_key_info = self.content.datafilemanager.dataKey.get(key_data[:2])
        self.typedata = data_key_info.get("data") if data_key_info else None

        # Excluir preview_txts.txt si es tipo texto
        if self.typedata == "txt":
            n_files -= 1

        # Tamano del bloque de indices
        ispair = entry.get("ispair")
        size_indexs = 8 + (n_files - 1) * 4 if ispair else n_files * 4

        # Relleno de bytes para los offsets
        fill_byte = bytes.fromhex(entry.get("fill"))
        content_file += fill_byte * size_indexs

        # Alineacion a 16 bytes si es requerido
        if entry.get("pad_offset"):
            content_file = self.pad_to_16(content_file)

        # Anadir padding por filas si es necesario
        key_lookup = self.content.datafilemanager.dataKey
        row_info = key_lookup.get(key_data[:4]) or key_lookup.get(key_data[:2])
        row_count = row_info.get("row") if row_info else 0
        if row_count:
            content_file += fill_byte * (16 * row_count)

        # Ejecutar importacion con el archivo generado
        return self.import_files(conten=bytes(content_file), n_files=n_files)


    def import_files(self, conten: bytes, n_files: int):
        output_path = self.content.path_file.parent / f"compress_{self.content.path_file.name}"
        if output_path.exists():
            raise ValueError(f"The \"{output_path.name}\" file already exists and cannot be overwritten.")

        folder_path = self.content.path_file if self.content.path_file.is_dir() \
            else self.content.path_file.parent / self.content.path_file.stem

        # Determinar cabecera y posicion inicial
        offset = len(conten)
        data_key = self.content.datafilemanager.dataKey.get(conten[:4]) or \
                   self.content.datafilemanager.dataKey.get(conten[:2])
        pos_index = data_key.get("star", 4)
        endian = self.content.datafilemanager.entry.get("endianness")
        conten = conten[:pos_index] + offset.to_bytes(4, byteorder=endian) + conten[pos_index+4:]

        ispair = self.content.datafilemanager.entry.get("ispair")
        file_ext = "txt" if self.typedata == "txt" else "unk"

        for idx in range(1, n_files + 1):
            file_path = folder_path / f"{idx}-{idx:X}.{file_ext}"
            with open(file_path, "rb") as f:
                file_data = f.read()

            # si es txt, convierte al formato correspondiente
            if self.typedata == "txt":
                header = file_data[:4]
                if header.startswith(b'\xff\xfe'):
                    file_data = file_data[2:]
                elif header.startswith(b'\xfe\xff'):
                    file_data = file_data[2:].decode('utf-16-be').encode('utf-16-le')
                elif header.startswith(b'\xef\xbb\xbf'):
                    file_data = file_data[3:].decode('utf-8').encode('utf-16-le')
                else:
                    file_data = file_data.decode('utf-8').encode('utf-16-le')

                # agrega el null al final
                if file_data[-2:] != b'\x00\x00':
                    file_data += b'\x00\x00'

            if self.content.ischeckbox:
                file_data = self.pad_to_16(file_data)

            conten += file_data
            offset += len(file_data)
            pos_index += 4

            if idx < n_files if not ispair else idx <= n_files:
                conten = conten[:pos_index] + offset.to_bytes(4, byteorder=endian) + conten[pos_index+4:]

        conten = self.pad_to_16(conten)

        with open(output_path, "wb") as out_file:
            out_file.write(conten)

        return [f"Compress file created.\n\nName file: {output_path.name}"]


    def pad_to_16(self, b: bytes, fill: None) -> bytes:
        resto = len(b) % 16
        if resto != 0:
            padding = 16 - resto
            b += bytes.fromhex(self.content.datafilemanager.entry.get("fill") if not fill else fill) * padding
        return b

    def ppva_extract(self, data_file:dict):
        data_audio = []
        offset_fin = self.bytes_file[4:8]
        endian = self.content.datafilemanager.guess_endianness(offset_fin)
        
        if "unk" in endian:
            raise ValueError(endian)

        offset_fin = int.from_bytes(offset_fin, byteorder=endian)
        offset_fin+=8

        seek_start = data_file.get("star")
        fill = data_file.get("fill")

        # Actualizar entrada
        self.content.datafilemanager.update_entry(
            key_bytes=self.bytes_file[:seek_start],
            endianness=endian,
            pad_offset=data_file.get("eoinx", True),
            ispair=data_file.get("ispair", True),
            fill=fill
        )

        # leer offsets, frecuencia y long
        while seek_start < offset_fin or seek_start < len(self.bytes_file):
            if seek_start+16 > len(self.bytes_file):
                break

            data_audio.append([self.bytes_file[seek_start:seek_start + 4], self.bytes_file[seek_start + 4:seek_start + 8], self.bytes_file[seek_start + 8:seek_start + 12]])
            seek_start+=16

            if data_audio[-1][0] == b'\x00'*4 and data_audio[-1][1] == b'\x00'*4 and data_audio[-1][2] == b'\x00'*4:
                data_audio.pop()
                break

        # print(data_audio)
        content_audios = None
        folder_path = self.content.path_file.parent
        folder_path = folder_path.parent
        with open(folder_path / "1-1.unk", "rb") as f:
            content_audios = f.read()

        folder_audios = self.content.path_file.parent / self.content.path_file.stem
        folder_audios.mkdir(exist_ok=True)

        # Guardar configuracion
        with open(folder_audios / "config.set", "w") as cf:
            cf.write(self.content.datafilemanager.data)

        x = 0
        # guardar el vag
        for audio_inf in data_audio:
            x+=1
            start = int.from_bytes(audio_inf[0], byteorder=endian)
            end = int.from_bytes(audio_inf[2], byteorder=endian) if audio_inf[2] != b'\xD0\xFF\xFF\xFF' else 0

            vag_header = VAGHeader(data_size=end, sample_rate=int.from_bytes(audio_inf[1], byteorder=endian), name=f"{x}-{x:X}")
            header_bytes = vag_header.build()
            # header_bytes = self.pad_to_16(b=header_bytes, fill='00')
            
            end+=start
            with open(folder_audios / f"{x}-{x:X}.vag", "wb") as vag:
                content_audio = content_audios[start:end]
                if not content_audio: content_audio = b'\x00'*0x10

                vag.write(header_bytes + content_audio)

        return [f"{x} VAG audio files exported"]


