class DataConvert():
    def __init__(self, contenedor):
        self.content=contenedor

    def load_offsets(self):
        with open(self.content.path_file, "rb") as f:
            bytes_keys = f.read(4)
            data_file = self.content.datafilemanager.dataKey.get(bytes_keys)
            if not data_file:
                data_file = self.content.datafilemanager.dataKey.get(bytes_keys[:2])
                if not data_file:
                    raise ValueError("unknow file, The file key could not be identified.")

            pad_offset = data_file.get("eoinx")
            if pad_offset == None:
                pad_offset=True

            starSeek = data_file.get("star")
            if starSeek != None:
                bytes_keys += f.read(starSeek-len(bytes_keys))
                f.seek(starSeek)

            offsetStar = f.read(4)
            endian = self.content.datafilemanager.guess_endianness(offsetStar)

            if "unknown" in endian:
                raise ValueError(endian)
                

            offset_fin = int.from_bytes(offsetStar, byteorder=endian)
            f.seek(starSeek if starSeek else 4)
            self.data_offsets = []

            while f.tell() < offset_fin:
                offsetStar = f.read(4)


                offsetStar = int.from_bytes(offsetStar, byteorder=endian)

                if offsetStar==0:
                    break
                
                self.data_offsets.append(offsetStar)

            ispair=False
            if data_file.get("ispair") == None:
                # print(len(self.data_offsets))
                ispair=True
            self.content.datafilemanager.update_entry(key_bytes=bytes_keys,endianness=endian,pad_offset=pad_offset,ispair=ispair)
            
            self.typedata = data_file.get("data")

            f.seek(0)
            self.bytes_file=f.read()

        return self.save_files()
    
    def save_files(self):
        name_folder = self.content.path_file.parent / self.content.path_file.stem
        name_folder.mkdir(exist_ok=True)
        size_indexs = len(self.data_offsets)-1 if self.content.datafilemanager.entry.get("ispair") else len(self.data_offsets)
        previewtxt = b'\xFF\xFE'

        for x in range(size_indexs):
            try:
                uloffset=self.data_offsets[x+1]
            except Exception as e:
                uloffset=len(self.bytes_file)

            data_bytes = self.bytes_file[self.data_offsets[x]:uloffset]

            #si se trata de un txt
            if self.typedata == "txt":
                name_file = f"{x+1}-{x+1:X}.txt\n"
                name_file=name_file.encode('utf-16-le')

                #obtener los bytes hasta cierto punto
                terminator_index = data_bytes.find(b'\x00\x00')                                
                if terminator_index != -1:
                    if len(data_bytes) == 2:
                        terminator_index = 1
                    data_bytes = data_bytes[:terminator_index+1]

                #guardar el previewtxt
                previewtxt+=name_file
                fragment = data_bytes[:0x3e] if len(data_bytes) >= 0x3e else data_bytes[:]
                previewtxt+=fragment
                previewtxt+=b'\x2e\x00'*3
                previewtxt+="\n\n".encode('utf-16-le')

                #guarda el archivo txt utf-16-le con BOM
                data_bytes = b'\xFF\xFE'+data_bytes
                with open(name_folder / f"{x+1}-{x+1:X}.txt","wb") as f:
                    f.write(data_bytes)
                continue

            #guarda el archivo binario
            with open(name_folder / f"{x+1}-{x+1:X}.unk","wb") as f:
                f.write(data_bytes)

        #guarda el previewtxts
        if self.typedata == "txt":
            with open(name_folder / "preview_txts.txt","wb") as f:
                f.write(previewtxt)

        with open(name_folder / "config.set", "w") as cf:
            cf.write(self.content.datafilemanager.data)
        return ['Files saved <a href="#">open folder</a>', name_folder]

    def import_config(self):
        content_file = b''
        if self.content.path_file.is_dir():
            name_folder = self.content.path_file
        else:
            name_folder = self.content.path_file.parent / self.content.path_file.stem

        self.content.datafilemanager.load_entry(path=(name_folder / "config.set"))

        n_files = sum(1 for f in name_folder.iterdir() if f.is_file())
        #evita el archivo config
        n_files-=1


        keydata = bytes.fromhex(self.content.datafilemanager.entry.get("key"))
        content_file = keydata

        self.typedata = self.content.datafilemanager.dataKey.get(keydata[:2]).get("data")

        if self.typedata == "txt":
            #evita el archivo previewtxt
            n_files-=1

        if self.content.datafilemanager.entry.get("ispair"):
            size_indexs=8 + (n_files - 1) * 4
        else:
            size_indexs=n_files*4#usado para archivos txt

        content_file+=b'\x00'*size_indexs

        if self.content.datafilemanager.entry.get("pad_offset"):
            content_file = self.pad_to_16(content_file)

        n_row = self.content.datafilemanager.dataKey.get(keydata[:4])
        if not n_row:
            n_row = self.content.datafilemanager.dataKey.get(keydata[:2])
        n_row = n_row.get("row")
        if n_row:
            content_file+=b'\x00'*(16*n_row)

        return self.import_files(conten=content_file, n_files=n_files)

    def import_files(self, conten: bytes, n_files: int):
        name_file_compress = self.content.path_file.parent / f"compress_{self.content.path_file.name}"

        if name_file_compress.exists():
            raise ValueError(f"The \"{name_file_compress.name}\" file already exists and cannot be overwritten.")
        
        if self.content.path_file.is_dir():
            name_folder = self.content.path_file
        else:
            name_folder = self.content.path_file.parent / self.content.path_file.stem
        offset = len(conten)
        # data_offsets = []
        dataKeys=self.content.datafilemanager.dataKey.get(conten[:4])
        if not dataKeys:
            dataKeys=self.content.datafilemanager.dataKey.get(conten[:2])

        pos_index=dataKeys.get("star")

        if not pos_index:
            pos_index=4

        #obtiene el endian y escribe el primer offset
        endian = self.content.datafilemanager.entry.get("endianness")
        conten=conten[:pos_index] + offset.to_bytes(4, byteorder=endian) + conten[pos_index+4:]
        ispair= self.content.datafilemanager.entry.get("ispair")
        
        exten = "txt" if self.typedata == "txt" else "unk"
        for x in range(1, n_files+1):
            name_file = name_folder / f"{x}-{x:X}.{exten}"
            with open(name_file, "rb") as f:
                content_file = f.read()

                #si es un txt
                if self.typedata == "txt":
                    encabezado = content_file[:4]

                    if encabezado.startswith(b'\xff\xfe'):
                        # print("UTF-16 LE con BOM")
                        content_file=content_file[2:]

                    elif encabezado.startswith(b'\xfe\xff'):
                        # print("UTF-16 BE con BOM")
                        content_file=content_file[2:]
                        decode_utf16_be=content_file.decode('utf-16-be')
                        content_file=decode_utf16_be.encode('utf-16-le')

                    elif encabezado.startswith(b'\xef\xbb\xbf'):
                        # print("UTF-8 con BOM")
                        content_file=content_file[3:]
                        decode_utf8=content_file.decode('utf-8')
                        content_file=decode_utf8.encode('utf-16-le')

                    else:
                        # print("tratado como UTF-8 sin BOM")
                        decode_utf8=content_file.decode('utf-8')
                        content_file=decode_utf8.encode('utf-16-le')

                    #asigna el null al final, si no lo tiene
                    if content_file[-2:] != b'\x00'*2 : content_file+=b'\x00'*2

                #realiza el padding a los archivos
                if self.content.ischeckbox: content_file = self.pad_to_16(content_file)

                #agrega el archivo al compress_file
                conten+=content_file

                #modifica el offset y lo escribe en el compress_file
                offset+=len(content_file)
                pos_index+=4
                
                if x < n_files if not ispair else n_files+1:
                    conten=conten[:pos_index] + offset.to_bytes(4, byteorder=endian) + conten[pos_index+4:]

                # data_offsets.append(offset)
        #guarda el archivo compress_file
        
        with open(name_file_compress, "wb") as c:
            #dar padding al archivo final
            conten=self.pad_to_16(conten)
            c.write(conten)
        
        return [f"Compress file created.\n\n{name_file_compress.name}"]

    def pad_to_16(self, b: bytes) -> bytes:
        resto = len(b) % 16
        if resto != 0:
            padding = 16 - resto
            b += b'\x00' * padding
        return b
