# import json
from pathlib import Path
from PyQt5.QtCore import QThreadPool
# from PyQt5.QtWidgets import QMessageBox


from app_md.logic_iso.worker import Worker
from app_md.wav.wav_header import AT3HeaderBuilder
from app_md.wav.wav_cd import WavCd
from app_md.logic_extr.vag_header import VAGHeader




class DataFileManager():
    def __init__(self, conten):
        self.contenedor = conten

        self.thread_pool = QThreadPool()
        self.at3_header = AT3HeaderBuilder()
        self.wavcd = WavCd()
        self.vagheader = VAGHeader()

        self.at3_audios = []
        self.wav_audios = []


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

    def task_audio_convert(self):
        #crear una tarea asincrona para conversion de audios arrastrados a la ventana
        worker = Worker(self.detect_conversion_direction)
        worker.signals.resultado.connect(self.contenedor.success_dialog)
        worker.signals.error.connect(self.contenedor.manejar_error)
        self.thread_pool.start(worker)

    def save_files(self):
        mess = self.contenedor.delete_content_folder(path_folder=self.contenedor.new_folder)
        print(mess)

        res = 'export_task finished <a href="#">open folder</a>'
        xDat = 0

        #leer y guardar los archivos
        with open(self.contenedor.contenedor.path_iso, "rb") as f_iso:
            for dat_file in self.contenedor.indexs:
                offset = int(dat_file[1], 16)
                size = int(dat_file[2], 16)
                f_iso.seek(offset)
                self.at3_header = None

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

                # guardar el archivo
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
        num_files = int(self.contenedor.edit_lbl_files.text(), 16) # total de archivos
        size_indexs = (num_files + 1) * 0x10
        data_start = self.contenedor.index_Packfile[0] + size_indexs

        # procesar los wav a at3
        if self.contenedor.ischeckbox_wavs:
            files_wav = list(self.contenedor.new_folder.glob("*.wav"))
            self.convert_wav16bitPCM_to_at3(files_path=files_wav)


        with open(self.contenedor.contenedor.path_iso.parent / f"compress_{self.contenedor.contenedor.path_iso.name}", "wb") as f_iso_c:
            with open(self.contenedor.contenedor.path_iso, "rb") as f_iso:
                dex_len = int(self.contenedor.edit_lbl_data_size.text(), 16) - size_indexs
                dex = b'\x00' * dex_len # relleno o padding antes del contenido de los arrchivos

                f_iso.seek(0)
                data_iso = f_iso.read(data_start) # datos inciales del iso
                f_iso_c.write(data_iso + dex)

            # Escribir los archivos uno a uno
            for file_number in range(1, num_files + 1):
                path_file = self.contenedor.new_folder / f"{file_number}_{file_number:X}.unk"

                with open(path_file, "rb") as file_content:
                    content = file_content.read()
                    # obtener solo el audio del at3
                    if content[:4] == b'RIFF':
                        w_data_pos = content.find(b'data')
                        if w_data_pos != -1:
                            size_audio = int.from_bytes(content[w_data_pos + 4:w_data_pos + 8], byteorder='little')
                            size_audio += w_data_pos + 8
                            content = content[w_data_pos + 8 : size_audio]

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

    def convert_at3_to_wav_16bitPCM(self, at3_files):
        # Si se recibe una lista de rutas, procesar cada archivo individualmente
        if isinstance(at3_files, list):
            for at3_file in at3_files:
                self.convert_at3_to_wav_16bitPCM(at3_file)
            return len(at3_files) > 0

        # Si se recibe una sola ruta (Path)
        elif isinstance(at3_files, Path):
            at3_path = at3_files

            # Leer el contenido del archivo AT3
            with open(at3_path, "rb") as f:
                content = f.read()

            # Verificar si el archivo no tiene header RIFF, agregarlo si es necesario
            if content and content[:4] != b'RIFF':
                header = AT3HeaderBuilder(data_size=len(content))
                content = header.build_header() + content

                # Reescribir el archivo con el header agregado
                with open(at3_path, "wb") as wf:
                    wf.write(content)

            # Verificar que el archivo exista y no este vacio
            if at3_path.is_file() and at3_path.stat().st_size != 0:
                wav_output_path = at3_path.parent / f"{at3_path.stem}.wav"

                # Convertir el archivo AT3 a WAV
                result = self.vagheader.convert_vag_to_wav(
                    vag_path=at3_path,
                    wav_path=wav_output_path,
                    is_vag=False
                )
                print(result)

        # Tipo de entrada no valido
        else:
            raise ValueError("Invalid type. It must be a Path or list")


    def convert_wav16bitPCM_to_at3(self, files_path):
        # Si se recibe una lista de rutas, procesar cada archivo individualmente
        if isinstance(files_path, list):
            for wav_file in files_path:
                self.convert_wav16bitPCM_to_at3(wav_file)
            return len(files_path) > 0

        # Si se recibe una sola ruta (Path)
        elif isinstance(files_path, Path):
            wav_path = files_path

            # Verificar si el archivo es un WAV valido
            if not self.at3_header._is_valid_wav(file_path=wav_path):
                print(f"It is not a WAV file: {wav_path}")
                return

            # Construir la ruta de salida para el archivo AT3 (con extension .unk)
            at3_output_path = wav_path.parent / f"{wav_path.stem}.unk"

            # Realizar la conversion de WAV a AT3
            result = self.at3_header.convert_wav_to_at3(wav_path=wav_path, output_at3_path=at3_output_path)
            print(result)

        # Tipo de entrada no valido
        else:
            raise ValueError("Invalid type. It must be a Path or list")


    def detect_conversion_direction(self):
        print("\nAudios")
        # Intentar convertir archivos AT3 a WAV 16-bit PCM
        at3_to_wav_success = self.convert_at3_to_wav_16bitPCM(at3_files=self.at3_audios)

        # Intentar convertir archivos WAV 16-bit PCM a AT3
        wav_to_at3_success = self.convert_wav16bitPCM_to_at3(files_path=self.wav_audios)

        converted_format = ""
        if at3_to_wav_success and wav_to_at3_success:
            converted_format = "AT3 and WAV"
        elif wav_to_at3_success and not at3_to_wav_success:
            converted_format = "WAV"
        elif at3_to_wav_success and not wav_to_at3_success:
            converted_format = "AT3"

        # Limpiar las listas de entrada despues de procesar
        self.at3_audios = []
        self.wav_audios = []

        return [f"Files converted: {converted_format}"]
