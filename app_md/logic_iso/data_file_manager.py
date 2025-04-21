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
        with open(self.contenedor.contenedor.path_iso, "rb") as f_iso:
            for dat_file in self.contenedor.indexs:
                dat_bytes = None

                f_iso.seek(int(dat_file[1],16))
                dat_bytes = f_iso.read(int(dat_file[2],16))

                name_file = f"{int(dat_file[0],16)}_{dat_file[0]}.unk"
                path_file = self.contenedor.new_folder / name_file

                with open(path_file, "wb") as f:
                    f.write(dat_bytes)

            #comprobar si existen datos despues del ultimo archivo
            ulOfsset = f_iso.tell()
            size_iso = f_iso.seek(0, 2) or f_iso.tell()
            if ulOfsset != size_iso:
                f_iso.seek(ulOfsset)
                dat_bytes = f_iso.read(size_iso-ulOfsset)

                name_file ="leftover.unk"
                path_file = self.contenedor.new_folder / name_file

                with open(path_file, "wb") as f:
                    f.write(dat_bytes)

                res+= f"<br><br>The leftover.unk file was created, with a size<br>of {size_iso-ulOfsset} bytes."

                if size_iso-ulOfsset < 0:
                    res+="<br><br>Your leftover.unk file has a negative size. Check the entered<br>parameters, as they might be incorrect."
        return [res]

    def import_files(self):
        self.new_indexs = []#guarda los offset y longitudes
        offset = 0

        with open(self.contenedor.contenedor.path_iso+".compress", "wb") as f_iso_c:#backup
            with open(self.contenedor.contenedor.path_iso, "rb") as f_iso:#iso original
                size_indexs = (int(self.contenedor.edit_lbl_files.text(),16)+1)*0x10

                dex = int(self.contenedor.edit_lbl_data_size.text(),16)-size_indexs#relleno de ceros antes del primer archivo
                dex = b'\x00'*dex

                f_iso.seek(0)
                data_iso = f_iso.read(self.contenedor.index_Packfile[0]+size_indexs)

                data_iso = data_iso+dex
                #escribir datos inciales del iso
                f_iso_c.write(data_iso)

            #escribir los datos de los archivos
            for file_number in range(1, int(self.contenedor.edit_lbl_files.text(),16)+1):
                path_file =self.contenedor.new_folder / f"{file_number}_{file_number:X}.unk"

                with open(path_file, "rb") as file_content:
                    content = file_content.read()

                    current_size = len(content)
                    # Calcular cuanto falta para que sea multiplo de 0x800
                    residuo = current_size % 0x800
                    if residuo != 0:
                        padding = 0x800 - residuo  # Bytes de relleno
                        content += b'\x00' * padding  # Rellenar con ceros

                    #escribir y guarda el index del archivo
                    self.new_indexs.append([file_number, offset, current_size])
                    f_iso_c.write(content)
                    offset += len(content)

            self.new_indexs = [self.new_indexs, False]
            #escribir el restante si existe
            path_file = self.contenedor.new_folder / "leftover.unk"

            if path_file.exists():
                with open(path_file, "rb") as file_content:
                    content = file_content.read()
                    f_iso_c.write(content)

                self.new_indexs[1] = True

        return self.new_indexs