from PyQt5.QtCore import QThreadPool
# from PyQt5.QtWidgets import QMessageBox


from app_md.logic_iso.worker import Worker


class DataFileManager():
    def __init__(self, conten):
        self.contenedor = conten

        self.thread_pool = QThreadPool()

    def task_save(self):
        #crear una tarea asincrona
        worker = Worker(self.save_files)
        worker.signals.resultado.connect(self.contenedor.success_dialog)
        worker.signals.error.connect(self.contenedor.manejar_error)
        self.thread_pool.start(worker)

    def task_import(self):
        #crear una tarea asincrona
        worker = Worker(self.import_files)
        worker.signals.resultado.connect(self.contenedor.indexs_import)
        worker.signals.error.connect(self.contenedor.manejar_error)
        self.thread_pool.start(worker)

    def save_files(self):
        res = 'export_task finished <a href="#">open folder</a>'
        xDat = 0

        #leer y guardar los archivos
        with open(self.contenedor.contenedor.path_iso, "rb") as f_iso:
            for dat_file in self.contenedor.indexs:
                offset = int(dat_file[1], 16)
                size = int(dat_file[2], 16)
                f_iso.seek(offset)

                try:
                    # Determina si hay un siguiente indice valido para evitar archivos incompletos
                    if xDat + 1 <= self.contenedor.indexs[-1][0] - 1:
                        next_data = self.contenedor.indexs[xDat + 1]
                        next_offset = int(next_data[1], 16)

                        # Verifica si hay datos adicionales entre el final del chunk actual y el inicio del siguiente
                        if next_offset > offset + size:
                            chunk_size = next_offset - offset
                            dat_bytes = f_iso.read(chunk_size)

                            # Verifica si el exceso de datos es solo padding
                            padding = dat_bytes[size:]
                            if all(b == 0 for b in padding):
                                dat_bytes = dat_bytes[:size]
                        else:
                            dat_bytes = f_iso.read(size)
                    else:
                        dat_bytes = f_iso.read(size)

                except Exception:
                    # En caso de error, vuelve al offset y lee el size estandar
                    f_iso.seek(offset)
                    dat_bytes = f_iso.read(size)

                name_file = f"{int(dat_file[0], 16)}_{dat_file[0]}.unk"
                path_file = self.contenedor.new_folder / name_file

                with open(path_file, "wb") as f_out:
                    f_out.write(dat_bytes)

                xDat+=1

            # Verificar si existe "leftover"
            ulOffset = f_iso.tell()
            f_iso.seek(0, 2)
            size_iso = f_iso.tell()

            if ulOffset != size_iso:
                f_iso.seek(ulOffset)
                dat_bytes = f_iso.read(size_iso - ulOffset)

                path_file = self.contenedor.new_folder / "leftover.unk"
                with open(path_file, "wb") as f_leftover:
                    f_leftover.write(dat_bytes)

                leftover_size = size_iso - ulOffset
                res += f"<br><br>The leftover.unk file was created, with a size<br>of {leftover_size} bytes."

                if leftover_size < 0:
                    res += "<br><br>Your leftover.unk file has a negative size. Check the entered<br>parameters, as they might be incorrect."

        return [res]


    def import_files(self):
        new_indexs = []  # guarda los offset y longitudes
        offset = 0
        num_files = int(self.contenedor.edit_lbl_files.text(), 16) #total de archivos
        size_indexs = (num_files + 1) * 0x10
        data_start = self.contenedor.index_Packfile[0] + size_indexs

        with open(self.contenedor.contenedor.path_iso.parent / f"compress_{self.contenedor.contenedor.path_iso.name}", "wb") as f_iso_c:
            with open(self.contenedor.contenedor.path_iso, "rb") as f_iso:
                dex_len = int(self.contenedor.edit_lbl_data_size.text(), 16) - size_indexs
                dex = b'\x00' * dex_len #relleno o padding antes del contenido de los arrchivos

                f_iso.seek(0)
                data_iso = f_iso.read(data_start) #datos inciales del iso
                f_iso_c.write(data_iso + dex)

            # Escribir los archivos uno a uno
            for file_number in range(1, num_files + 1):
                path_file = self.contenedor.new_folder / f"{file_number}_{file_number:X}.unk"

                with open(path_file, "rb") as file_content:
                    content = file_content.read()
                    current_size = len(content)

                    # Padding si no es multiplo de 0x800
                    if current_size % 0x800 != 0:
                        padding = 0x800 - (current_size % 0x800)
                        content += b'\x00' * padding

                    new_indexs.append([file_number, offset, current_size])
                    f_iso_c.write(content)
                    offset += len(content)

            new_indexs = [new_indexs, False]

            # Escribir leftover.unk si existe
            path_file = self.contenedor.new_folder / "leftover.unk"
            if path_file.exists():
                with open(path_file, "rb") as file_content:
                    f_iso_c.write(file_content.read())
                new_indexs[1] = True

        return new_indexs
