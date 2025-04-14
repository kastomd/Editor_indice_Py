from PyQt5.QtCore import QThreadPool

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

    def save_files(self):
        with open(self.contenedor.contenedor.path_iso, "rb") as f_iso:
            for dat_file in self.contenedor.indexs:
                dat_bytes = None

                f_iso.seek(int(dat_file[1],16))
                dat_bytes = f_iso.read(int(dat_file[2],16))

                name_file = f"{int(dat_file[0],16)}_{dat_file[0]}.unk"
                path_file = self.contenedor.new_folder / name_file

                with open(path_file, "wb") as f:
                    f.write(dat_bytes)

        return ["task finished"]

    def import_files(self):
        pass

    

