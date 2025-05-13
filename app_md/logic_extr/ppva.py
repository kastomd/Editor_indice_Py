import json
import os
from pathlib import Path
from app_md.logic_extr.vag_header import VAGHeader
from app_md.wav.wav_cd import WavCd

class PPVA:
    def __init__(self, content):
        self.content = content
        self.vag_header = VAGHeader()
        self.bytes_file = None
        self.wavcd = WavCd()
        self.conten_vag_name = None
        self.force_loop = {}

    def compress(self, keydata: bytes, entry, name_folder: Path, path_file: Path, is_wav:bool=False, conten_vag_name:str="1-1.unk"):
        self.conten_vag_name = conten_vag_name
        name_file, name_vag_content = self._validate_output_files(name_folder, path_file)
        n_vag_files = self._count_vag_files(name_folder)
        data_wav_loop = self._load_wav_loop_metadata(name_folder)

        if is_wav:
            self._ensure_wav_format(name_folder, n_vag_files)
        if data_wav_loop and is_wav:
            self._apply_loop_metadata(name_folder, n_vag_files, data_wav_loop)

        if is_wav:
            self._convert_wav_to_vag(name_folder, n_vag_files)

        content_file, vag_content, frecuencia = self._build_vag_content(name_folder, n_vag_files)
        
        subdirec = {}
        if self.content.ischeckbox_subdirec:
            self._write_unk_file(name_vag_content, content_file)
        else:
            # guardar en temp contenedor de audios
            name_vag_content =  name_folder.parent.parent / self.conten_vag_name
            self._write_unk_file(name_vag_content, content_file)
            print(name_vag_content)
            subdirec[name_vag_content] = True

        ppva_file = self._build_ppva_file(keydata, entry, vag_content)
        if self.content.ischeckbox_subdirec:
            #guarda en la raiz del path
            self._save_ppva_file(name_file, ppva_file)

            return [f"{self.conten_vag_name} and {name_file.name} created"]
        else:
            # guardar en temp
            name_file =  name_folder.parent / path_file.name
            self._save_ppva_file(name_file, ppva_file)
            print(name_file)
            subdirec[name_file] = True

            # confirmacion de archivo guardado o modificado
            return subdirec

    def extract(self, data_file: dict, bytes_file: bytes, conten_vag_name:str="1-1.unk", is_wav:bool=False):
        self.conten_vag_name = conten_vag_name
        self.bytes_file = bytes_file
        endian = self._detect_endianness()
        offset_end, seek = self._get_table_range(data_file, endian)

        self._update_entry(data_file, seek, endian)
        audio_entries = self._read_audio_entries(seek, offset_end, endian)

        container_data = self._load_container_data()
        output_dir = self._prepare_output_folder()

        self._save_config(output_dir)
        exported_files = self._extract_vag_files(audio_entries, container_data, output_dir, endian)
        if is_wav:
            self._convert_all_to_wav(exported_files, output_dir)
        self._write_metadata(exported_files, output_dir)

        return [f"{len(exported_files)} VAG audio files exported"]

    # -----------------------
    # Metodos auxiliares
    # -----------------------

    def _validate_output_files(self, name_folder, path_file):
        name_file = name_folder.parent / f"compress_{path_file.name}"
        name_vag_content = name_folder.parent.parent / f"compress_{self.conten_vag_name}"
        for f in (name_file, name_vag_content):
            if f.exists():
                raise ValueError(f"The \"{f.name}\" file already exists and cannot be overwritten.")
        return name_file, name_vag_content

    def _count_vag_files(self, folder):
        return sum(1 for f in folder.iterdir() if f.is_file() and f.suffix == '.vag')

    def _load_wav_loop_metadata(self, folder):
        metadata_path = folder / "metadato_for_wav.json"
        if metadata_path.exists():
            with open(metadata_path, "r") as f:
                return json.load(f)
        return None

    def _ensure_wav_format(self, folder, count):
        for i in range(1, count + 1):
            path = folder / f"{i}-{i:X}.wav"
            if not self.wavcd.validar_wav_mono_16bit_pcm(path):
                self.wavcd.convert_wav_to_16bit_mono(path)

    def _apply_loop_metadata(self, folder, count, metadata):
        self.force_loop = {}
        for i in range(1, count + 1):
            name = f"{i}-{i:X}.vag"
            if name in metadata:
                path = folder / f"{i}-{i:X}.wav"
                info = metadata[name]
                start = info.get("loop_start")
                end = info.get("loop_end")
                force_loop = info.get("force_loop")
                if not force_loop:
                    start = self.wavcd.time_str_to_milliseconds(start)
                    end = self.wavcd.time_str_to_milliseconds(end)
                    self.wavcd.add_loop_metadata_to_wav(path, start, end)
                else:
                    self.force_loop[path.name] = force_loop

    def _convert_wav_to_vag(self, folder, count):
        for i in range(1, count + 1):
            no_force_loop = False
            force_loop = False
            path = folder / f"{i}-{i:X}.wav"
            if path.exists():
                loop = self.force_loop.get(path.name)
                if loop == "-L":
                    force_loop = True
                elif loop == "-1":
                    no_force_loop = True

                self.vag_header.convert_wav_to_vag(wav_path=path,force_loop=force_loop,no_force_loop=no_force_loop)

    def _build_vag_content(self, folder, count):
        content_file = b''
        vag_content = []
        frecuencia = None
        e_re = b'\x00\x07' + (b'\x77' * 0xe)

        for i in range(1, count + 1):
            with open(folder / f"{i}-{i:X}.vag", "rb") as f:
                f.seek(0x10)
                frecuencia = int.from_bytes(f.read(4), 'big')
                f.seek(0x30)
                data = f.read()
                if all(b == 0 for b in data):
                    data = b''
                # if data and data[-16:] != e_re: audio con looparrojo error en su reproduccion en game
                #     data += e_re
                vag_content.append([len(content_file), frecuencia, len(data)])
                content_file += data
        return content_file, vag_content, frecuencia

    def _write_unk_file(self, path, content):
        with open(path, "wb") as f:
            f.write(content + b'\x00' * 0x30)

    def _build_ppva_file(self, keydata, entry, vag_data):
        fill = bytes.fromhex(entry.get("fill", '00'))
        endian = entry.get("endianness")
        seek_start = self.content.datafilemanager.dataKey[keydata[:4]]["star"]

        ppva = keydata + fill * (len(vag_data) * 0x10)
        ppva = ppva[:4] + len(ppva[8:]).to_bytes(4, endian) + ppva[8:]
                
        for offset, freq, length in vag_data:
            length = length or 0xFFFFFFD0
            if self.content.ischeckbox_narut and length == 0xFFFFFFD0:
                offset = 0xFFFFFFFF
                length = offset
                freq = offset
            chunk = offset.to_bytes(4, endian) + freq.to_bytes(4, endian) + length.to_bytes(4, endian)
            ppva = ppva[:seek_start] + chunk + ppva[seek_start + 0xC:]
            seek_start += 0x10
        return ppva

    def _save_ppva_file(self, path, data):
        with open(path, "wb") as f:
            f.write(data)

    def _detect_endianness(self):
        endian = self.content.datafilemanager.guess_endianness(self.bytes_file[4:8])
        if "unk" in endian:
            raise ValueError(endian)
        return endian

    def _get_table_range(self, data_file, endian):
        offset_end = int.from_bytes(self.bytes_file[4:8], endian) + 8
        seek = data_file.get("star")
        return offset_end, seek

    def _update_entry(self, data_file, seek, endian):
        self.content.datafilemanager.update_entry(
            key_bytes=self.bytes_file[:seek],
            endianness=endian,
            pad_offset=data_file.get("eoinx", True),
            ispair=data_file.get("ispair", True),
            fill=data_file.get("fill")
        )

    def _read_audio_entries(self, seek, offset_end, endian):
        entries = []
        while seek < offset_end and seek + 16 <= len(self.bytes_file):
            chunk = self.bytes_file[seek:seek + 12]
            if chunk == b'\x00' * 12:
                break
            entries.append((
                chunk[0:4],
                chunk[4:8],
                chunk[8:12]
            ))
            seek += 16
        return entries

    def _load_container_data(self):
        path = self.content.path_file.parent.parent / self.conten_vag_name
        if not path.exists():
            raise ValueError(f"Missing container file: {path}")
        return path.read_bytes()

    def _prepare_output_folder(self):
        out_dir = self.content.path_file.parent / self.content.path_file.stem
        if out_dir.exists():
            raise ValueError(f"Folder \"{out_dir.name}\" already exists.")
        out_dir.mkdir()
        return out_dir

    def _save_config(self, folder):
        with open(folder / "config.set", "w") as f:
            f.write(self.content.datafilemanager.data)

    def _extract_vag_files(self, entries, container_data, folder, endian):
        files = []
        for i, (raw_off, raw_freq, raw_len) in enumerate(entries, 1):
            start = int.from_bytes(raw_off, endian) if raw_off != b'\xFF\xFF\xFF\xFF' else 0
            freq = int.from_bytes(raw_freq, endian) if raw_freq != b'\xFF\xFF\xFF\xFF' else 0
            end = int.from_bytes(raw_len, endian) if raw_len not in [b'\xD0\xFF\xFF\xFF', b'\xFF\xFF\xFF\xFF'] else 0
            end += start

            self.vag_header = VAGHeader(end - start, freq, f"{i}-{i:X}")
            out_file = folder / f"{i}-{i:X}.vag"
            data = container_data[start:end] or b'\x00' * 0x10
            out_file.write_bytes(self.vag_header.build() + data)
            files.append(out_file)
        return files

    def _convert_all_to_wav(self, files, folder):
        for f in files:
            self.vag_header.convert_vag_to_wav(f, folder / f"{f.stem}.wav")

    def _write_metadata(self, files, folder):
        metadata = {}
        for f in files:
            info = self.vag_header.get_audio_info(f, False)
            if info:
                metadata[f.name] = info
        with open(folder / "metadato_for_wav.json", "w") as f:
            json.dump(metadata, f, indent=4)
