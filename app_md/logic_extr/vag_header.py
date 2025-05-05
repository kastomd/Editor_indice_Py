import struct

class VAGHeader:
    def __init__(self, data_size:int, sample_rate=int, name=str):
        """
        Crea un header VAGp.

        :param data_size: size de los datos de audio en bytes (int)
        :param sample_rate: Frecuencia de muestreo en Hz (int, ej 44100)
        :param name: Nombre del archivo (max 16 bytes, se trunca o rellena)
        """
        self.magic = b'VAGp'                    # 4 bytes
        self.version = 0x00000003               # 4 bytes
        self.reserved1 = 0x00000000             # 4 bytes
        self.data_size = data_size-0x20 if data_size != 0 else 0xFFFFFFF0             # 4 bytes
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
