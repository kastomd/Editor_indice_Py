from pathlib import Path

import struct
import subprocess
import sys
import os
import re

class VAGHeader:
    def __init__(self, data_size:int=0, sample_rate:int=0, name:str="1"):
        """
        Crea un header VAGp.

        :param data_size: size de los datos de audio en bytes (int)
        :param sample_rate: Frecuencia de muestreo en Hz (int, ej 44100)
        :param name: Nombre del archivo (max 16 bytes, se trunca o rellena)
        """
        self.magic = b'VAGp'                    # 4 bytes
        self.version = 0x00000003               # 4 bytes
        self.reserved1 = 0x00000000             # 4 bytes
        self.data_size = data_size if data_size != 0 else 0xFFFFFFF0  # 4 bytes
        self.sample_rate = sample_rate          # 4 bytes
        self.reserved2 = [0] * 3                # 8 bytes
        self.name = name.encode('ascii')[:16]   # maximo 16 bytes
        self.name = self.name.ljust(16, b'\x00')  # Rellenar con ceros si es corto

    def build(self):
        """Devuelve los 48 bytes del header VAGp como bytes."""
        header = b''
        header += self.magic
        header += struct.pack('>I', self.version)
        header += struct.pack('>I', self.reserved1)
        header += struct.pack('>I', self.data_size)
        header += struct.pack('>I', self.sample_rate)
        for r in self.reserved2:
            header += struct.pack('>I', r)
        header += self.name
        return header



    @staticmethod
    def _get_resources_path(rel_path: Path) -> Path:
        # Retorna la ruta absoluta del recurso, compatible con PyInstaller
        if hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS) / rel_path
        return Path(__file__).resolve().parent / rel_path

    @staticmethod
    def _is_valid_vag(file_path: Path) -> bool:
        # Verifica si el archivo VAG tiene el encabezado correcto y no esta vacio
        with open(file_path, "rb") as f:
            if f.read(4) != b'VAGp':
                return False
            f.seek(0x30)
            data = f.read()
        return not all(b == 0 for b in data)

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

    def convert_vag_to_wav(self, vag_path: Path, wav_path: Path, is_vag:bool=True):
        if not vag_path.is_file():
            raise FileNotFoundError(f"VAG file not found: {vag_path}")

        if is_vag and not self._is_valid_vag(vag_path):
            return f"file not converted: {vag_path.name}"

        exe_path = self._get_resources_path(Path("tools/vgmstream/vgmstream-cli.exe"))
        command = [str(exe_path), "-i", "-o", str(wav_path), str(vag_path)]

        result = self._run_subprocess(command)

        if result.returncode != 0:
            raise ValueError(f"Error converting \"{vag_path.name}\":\n{result.stderr}")
        
        return f"Success: {wav_path.name}"

    def convert_wav_to_vag(self, wav_path: Path, force_loop=False, no_force_loop=False):
        if not wav_path.is_file():
            raise FileNotFoundError(f"WAV file not found: {wav_path}")

        loop = ""
        if force_loop:
            loop = "-L"

        if no_force_loop:
            loop = "-1"

        exe_path = self._get_resources_path(Path("tools/AIFF2VAG/AIFF2VAG.exe"))
        command = [str(exe_path), str(wav_path)] 

        if loop != "":
            command.append(loop) # -L fuerza a looping, -1 no looping, "" smpl del wav

        result = self._run_subprocess(command) 

        if result.returncode != 0:
            raise ValueError(f"Error converting \"{wav_path.name}\":\n{result.stderr}")
        
        return f"Success: {wav_path.stem}.vag"

    def get_audio_info(self, audio_path: Path, encod=True):
        if not audio_path.is_file():
            raise FileNotFoundError(f"VAG file not found: {audio_path}")

        if not self._is_valid_vag(audio_path):
            return

        exe_path = self._get_resources_path(Path("tools/vgmstream/vgmstream-cli.exe"))
        command = [str(exe_path), "-m", str(audio_path)]

        result = self._run_subprocess(command)

        if result.returncode != 0:
            raise ValueError(f"Error reading info from \"{audio_path.name}\":\n{result.stderr}")

        info = {
            "loop_start": None,
            "loop_end": None,
            "duration": None,
            "force_loop": "",
            "encoding": None
        }

        for line in result.stdout.splitlines():
            if "loop start" in line:
                match = re.search(r"\(([\d:.]+)", line)
                if match:
                    info["loop_start"] = match.group(1)
            elif "loop end" in line:
                match = re.search(r"\(([\d:.]+)", line)
                if match:
                    info["loop_end"] = match.group(1)
            elif "stream total samples" in line:
                match = re.search(r"\(([\d:.]+)", line)
                if match:
                    info["duration"] = match.group(1)
            elif "encoding:" in line:
                match = re.search(r"encoding:\s*(.+)", line)
                if match:
                    info["encoding"] = match.group(1).strip()

        if encod is False:
            info.pop("encoding", None)

        if not info["loop_start"] and not info["loop_end"]:
            return None

        return info