class DataConvert():
    def __init__(self, contenedor):
        self.content=contenedor

    def load_offsets(self):
        with open(self.content.path_file, "rb") as f:
            bytes_keys = f.read(4)
            data_file = self.content.datafilemanager.dataKey.get(bytes_keys)
            if not data_file:
                print("archivo desconocido")
                return

            pad_offset = data_file.get("eoinx")
            if not pad_offset:
                pad_offset=True
            starSeek = data_file.get("star")
            if starSeek:
                f.seek(starSeek)

            offsetStar = f.read(4)
            endian = self.content.datafilemanager.guess_endianness(offsetStar)

            if "unknown" in endian:
                print(endian)
                return

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
            if len(self.data_offsets)%2==0:
                ispair=True
            self.content.datafilemanager.update_entry(key_bytes=bytes_keys,endianness=endian,pad_offset=pad_offset,ispair=ispair)

            f.seek(0)
            self.bytes_file=f.read()
    
    def save_files(self):
        name_folder = self.content.path_file.parent / self.content.path_file.stem
        name_folder.mkdir(exist_ok=True)
        size_indexs = len(self.data_offsets)-1 if self.content.datafilemanager.entry.get("ispair") else len(self.data_offsets)
        
        for x in range(size_indexs):
            try:
                uloffset=self.data_offsets[x+1]
            except Exception as e:
                uloffset=len(self.bytes_file)

            data_bytes = self.bytes_file[self.data_offsets[x]:uloffset]


            with open(name_folder / f"{x}-{x:X}.unk","wb") as f:
                f.write(data_bytes)

        with open(name_folder / "config.set", "w") as cf:
            cf.write(self.content.datafilemanager.data)
        print("files saved")

    def import_config(self):
        content_file = b''
        name_folder = self.content.path_file.parent / self.content.path_file.stem

        self.content.datafilemanager.load_entry(path=(name_folder / "config.set"))

        n_files = sum(1 for f in name_folder.iterdir() if f.is_file())
        n_files-=1

        if self.content.datafilemanager.entry.get("ispair"):
            size_indexs=8 + (n_files - 1) * 4

        keydata = bytes.fromhex(self.content.datafilemanager.entry.get("key"))
        content_file = keydata
        content_file+=b'\x00'*size_indexs

        if self.content.datafilemanager.entry.get("pad_offset"):
            content_file = self.pad_to_16(content_file)

        n_row = self.content.datafilemanager.dataKey.get(keydata)
        n_row = n_row.get("row")
        if n_row:
            content_file+=b'\x00'*(16*n_row)

        self.import_files(conten=content_file, n_files=n_files)

    def import_files(self, conten: bytes, n_files: int):
        name_folder = self.content.path_file.parent / self.content.path_file.stem
        offset = len(conten)
        # data_offsets = []
        pos_index=self.content.datafilemanager.dataKey.get(conten[:4]).get("star")

        if not pos_index:
            pos_index=4

        endian = self.content.datafilemanager.entry.get("endianness")
        conten=conten[:pos_index] + offset.to_bytes(4, byteorder=endian) + conten[pos_index+4:]
        
        for x in range(n_files):
            with open(name_folder / f"{x}-{x:X}.unk", "rb") as f:
                content_file = f.read()
                content_file = self.pad_to_16(content_file)

                conten+=content_file

                offset+=len(content_file)
                pos_index+=4

                conten=conten[:pos_index] + offset.to_bytes(4, byteorder=endian) + conten[pos_index+4:]

                # data_offsets.append(offset)
        with open(self.content.path_file.parent / f"compress_{self.content.path_file.name}", "wb") as c:
            c.write(conten)
            print("archivo compress creado")

    def pad_to_16(self, b: bytes) -> bytes:
        resto = len(b) % 16
        if resto != 0:
            padding = 16 - resto
            b += b'\x00' * padding
        return b
