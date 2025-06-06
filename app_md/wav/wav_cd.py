from pathlib import Path

import wave
import struct
import soundfile as sf
import numpy as np


class WavCd():
    def __init__(self):
        pass


    def add_loop_metadata_to_wav(self, wav_path: Path, loop_start_ms: int, loop_end_ms: int):
        if not wav_path.exists():
            raise FileNotFoundError(f"File not found: {wav_path}")

        with open(wav_path, "rb") as f:
            wav_data = f.read()

        # Obtener datos del chunk 'fmt '
        fmt_index = wav_data.find(b'fmt ')
        if fmt_index == -1:
            raise ValueError("Chunk 'fmt ' not found in the WAV file")

        fmt_chunk_size = struct.unpack("<I", wav_data[fmt_index + 4:fmt_index + 8])[0]
        fmt_chunk_data = wav_data[fmt_index + 8:fmt_index + 8 + fmt_chunk_size]

        audio_format, num_channels, sample_rate, byte_rate, block_align, bits_per_sample = struct.unpack("<HHIIHH", fmt_chunk_data[:16])

        # Obtener size del chunk 'data'
        data_index = wav_data.find(b'data')
        if data_index == -1:
            raise ValueError("Chunk 'data' not found in the WAV file")

        data_chunk_size = struct.unpack("<I", wav_data[data_index + 4:data_index + 8])[0]

        # Total de muestras = size del data / block_align
        total_samples = data_chunk_size // block_align

        # Convertir milisegundos a muestras
        loop_start_sample = int((loop_start_ms / 1000.0) * sample_rate)
        loop_end_sample = int((loop_end_ms / 1000.0) * sample_rate)

        # Verificar limites
        if loop_start_sample >= total_samples:
            raise ValueError(f"loop_start ({loop_start_sample}) exceeds the total number of samples ({total_samples})")
        if loop_end_sample > total_samples:
            # raise ValueError(f"loop_end ({loop_end_sample}) se pasa del total de muestras ({total_samples})")
            loop_end_sample = total_samples

        # Crear el chunk 'smpl'
        manufacturer = 0
        product = 0
        sample_period = 0
        midi_unity_note = 60
        midi_pitch_fraction = 0
        smpte_format = 0
        smpte_offset = 0
        num_sample_loops = 1
        sampler_data = 0

        cue_point_id = 0
        loop_type = 0
        fraction = 0
        play_count = 0

        smpl_chunk_data = struct.pack(
            "<9I", manufacturer, product, sample_period, midi_unity_note,
            midi_pitch_fraction, smpte_format, smpte_offset,
            num_sample_loops, sampler_data
        )

        smpl_chunk_data += struct.pack(
            "<6I", cue_point_id, loop_type, loop_start_sample,
            loop_end_sample, fraction, play_count
        )

        smpl_chunk_id = b'smpl'
        smpl_chunk_size = len(smpl_chunk_data)
        smpl_chunk = smpl_chunk_id + struct.pack("<I", smpl_chunk_size) + smpl_chunk_data

        # agregar chunk 'smpl' al final
        smpl_is = wav_data.find(b'smpl')
        if smpl_is != -1:
            #elimina el chunk si existe
            wav_data = wav_data[:smpl_is]

        new_data = wav_data + smpl_chunk

        # Actualizar size del RIFF
        riff_size = len(new_data) - 8
        new_data = new_data[:4] + struct.pack("<I", riff_size) + new_data[8:]

        # Escribir archivo final
        with open(wav_path, "wb") as f:
            f.write(new_data)


    def validar_wav_16bit_pcm(self, wav_path: Path, channels:int=1) -> bool:
        if not wav_path.exists():
            raise FileNotFoundError(f"File not found: {wav_path}")

        try:
            with wave.open(str(wav_path), 'rb') as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                comptype = wf.getcomptype()  # 'NONE' indica PCM sin compresion
        except Exception as e:
            raise ValueError(f"error file: {wav_path}\n\n{e}")

        return n_channels == channels and sampwidth == 2 and comptype == 'NONE'

    def time_str_to_milliseconds(self, time_str: str) -> int:
        # transforma el string "m:s.ms" a milisegundo
        minutes, rest = time_str.split(":")
        seconds, milliseconds = rest.split(".")
        total_ms = (int(minutes) * 60 + int(seconds)) * 1000 + int(milliseconds)
        return total_ms

    
    def convert_wav_to_16bit(self, wav_path: Path, to_mono: bool = True):
        if not wav_path.exists():
            raise FileNotFoundError(f"File not found: {wav_path}")

        data, samplerate = sf.read(wav_path)

        # Si se desea mono
        if to_mono:
            if len(data.shape) > 1 and data.shape[1] > 1:
                # Convertir estereo a mono por promedio de canales
                data = data.mean(axis=1)
            # Si ya es mono, no se hace nada
        else:
            # Convertir mono a estereo si es necesario
            if len(data.shape) == 1:
                data = np.stack((data, data), axis=1)

        # Asegurar tipo int16
        if data.dtype != np.int16:
            data = np.clip(data, -1.0, 1.0)  # Limitar para evitar desbordes
            data = (data * 32767).astype(np.int16)

        # Guardar como PCM_16 (respeta canales actuales)
        sf.write(wav_path, data, samplerate, subtype='PCM_16')

        return True

    @staticmethod
    def convert_to_mono_stereo(input_path:Path):

        # Leer el archivo de audio
        data, samplerate = sf.read(input_path)

        # Verificar si el audio es stereo
        if data.ndim == 1 or data.shape[1] != 2:
            raise ValueError("The file must have 2 channels (stereo)")

        # Calcular el promedio de los dos canales (mezcla mono)
        mono = data.mean(axis=1)

        # Duplicar el canal mono en los dos canales para mantener formato stereo
        mono_stereo = np.stack((mono, mono), axis=1)

        # Guardar el nuevo archivo con ambos canales iguales
        sf.write(input_path, mono_stereo, samplerate)

        return f"Success mono stereo: {input_path.name}"