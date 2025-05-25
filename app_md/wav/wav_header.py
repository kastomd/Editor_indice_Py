import os
from pathlib import Path
import struct
import subprocess
import sys

class AT3HeaderBuilder:
    def __init__(self, data_size=0, sample_rate=44100, channels=2, samples=0, byte_rate=13092):
        self.data_size = data_size
        self.sample_rate = sample_rate
        self.channels = channels
        self.samples = samples

        # Valores comunes para ATRAC3
        self.audio_format = 0x0270
        self.block_align = 0x0130
        self.byte_rate = byte_rate
        self.bits_per_sample = 0
        self.extra_size = 14
        self.fact_chunk_size = 12

    def build_header(self):
        # Calculo del size total del chunk RIFF
        riff_size = (
            4 +              # "WAVE"
            (8 + 0x20) +     # "fmt " chunk
            (8 + self.fact_chunk_size) +  # "fact" chunk
            (8 + self.data_size)          # "data" chunk
        )

        header = b""

        # Encabezado RIFF
        header += b"RIFF"
        header += struct.pack("<I", riff_size)
        header += b"WAVE"

        # Chunk "fmt "
        header += b"fmt "
        header += struct.pack("<I", 0x20)
        header += struct.pack("<H", self.audio_format)
        header += struct.pack("<H", self.channels)
        header += struct.pack("<I", self.sample_rate)
        header += struct.pack("<I", self.byte_rate)
        header += struct.pack("<H", self.block_align)
        header += struct.pack("<H", self.bits_per_sample)
        header += struct.pack("<H", self.extra_size)
        header += struct.pack("<H", 1)
        header += struct.pack("<Q", 0x10)
        header += struct.pack("<I", 1)

        # Chunk "fact"
        header += b"fact"
        header += struct.pack("<I", self.fact_chunk_size)
        header += struct.pack("<I", self.samples)
        header += struct.pack("<H", 4)
        header += struct.pack("<H", 0)
        header += struct.pack("<H", 4)
        header += struct.pack("<H", 0)

        # Chunk "data"
        header += b"data"
        header += struct.pack("<I", self.data_size)

        return header

    @staticmethod
    def write_file(output_path, header, audio_data):
        with open(output_path, "wb") as f:
            f.write(header)
            f.write(audio_data)

    @staticmethod
    def _get_resources_path(rel_path: Path) -> Path:
        # Retorna la ruta absoluta del recurso, compatible con PyInstaller
        if hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS) / rel_path
        return Path(__file__).resolve().parent / rel_path

    @staticmethod
    def _run_subprocess(command: list) -> subprocess.CompletedProcess:
        # Ejecuta un comando en subprocess y evita ventana emergente en Windows
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            creationflags=creation_flags
        )

    @staticmethod
    def _is_valid_wav(file_path: Path) -> bool:
        # Verifica si el archivo wav tiene el encabezado correcto y no esta vacio
        with open(file_path, "rb") as f:
            f.seek(0, 2)  # Mover el puntero al final del archivo
            size = f.tell()
            if size == 0:
                return False

            #obtiene el riff y wave
            f.seek(0)
            riff = f.read(4)
            f.seek(8)
            wav = f.read(4)

        return riff == b'RIFF' and wav == b'WAVE'

    def convert_wav_to_at3(self, wav_path: Path, output_at3_path: Path, bitrate:int=105, loop:bool=False):
        if not wav_path.is_file():
            raise FileNotFoundError(f"WAV file not found: {wav_path}")

        exe_path = self._get_resources_path(Path("tools/psp_atrac3/psp_at3tool.exe"))
        command = [str(exe_path), "-e", "-br", str(bitrate)]

        # aplica el chunk smpl(looping) de inicio a fin
        if loop:
            command.append("-wholeloop")

        command.append(str(wav_path))
        command.append(str(output_at3_path))

        # ejecutar proceso
        result = self._run_subprocess(command)

        if result.returncode != 0:
            raise ValueError(f"Error converting \"{wav_path.name}\":\n{result.stderr}\nThe audio must be WAV PCM 16-bit at 44100 Hz stereo")
        
        return f"Success: {output_at3_path.name}"

