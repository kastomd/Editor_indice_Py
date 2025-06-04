import json


class DataFileManager():
    def __init__(self):
        self.dataKey = {
            b"\x00\x00\x02\xb7": {"row": 1},
            b"\x00\x00\x00\x23": {"row": 2},
            b"\x00\x00\x00\x02": {"row": 3},
            b"\x00\x00\x00\x0c": {"row": 0},
            b"\x00\x00\x00\x1b": {"row": 0},
            b"\x00\x00\x00\x46": {"row": 2},
            b"\x00\x00\x00\x0f": {"row": 3},
            b"\x00\x00\x00\x08": {"row": 1},
            b"\x00\x00\x00\x10": {"row": 3},
            b"\x00\x00\x00\xff": {"row": 3},
            b"\x00\x00\x00\x14": {"row": 2},
            b"\x00\x00\x00\x0a": {"row": 1},
            b"\x00\x00\x00\x4b": {"row": 0},
            b"\x00\x00\x00\x1e": {"row": 0},
            b"\x00\x00\x00\x35": {"row": 2},
            b"\x00\x00\x00\x1d": {"row": 0},
            b"\x00\x00\x00\x25": {"row": 2},
            b"\x00\x00\x00\x63": {"row": 2},
            b"\x00\x00\x00\x60": {"row": 3},
            b"\x00\x00\x00\x06": {"row": 2},
            b"\x00\x00\x00\x1a": {"row": 1},
            b"\x00\x00\x01\xf1": {"row": 3},
            b"\x00\x00\x00\x05": {"row": 2},
            b"\x00\x00\x00\xfa": {"row": 1},
            b"\x00\x00\x00\x0b": {"row": 0},
            b"\x00\x00\x00\x27": {"row": 1},
            b"\x00\x00\x00\x04": {"row": 2},
            b"\x00\x00\x00\x01": {"row": 3},
            b"\x00\x00\x00\x43": {"row": 2},
            b"\x00\x00\x00\x2e": {"row": 0},
            b"\x00\x00\x00\x37": {"row": 1},
            b"\x00\x00\x00\x07": {"row": 1},
            b"\x00\x00\x00\x3f": {"row": 3},
            b"\x00\x00\x00\x1c": {"row": 0},
            b"\x00\x00\x00\x6d": {"row": 0},
            b"\x50\x50\x48\x44": {"row": 2, "star": 0x10, "fill":b'\xff', "ispair": False},
            b"\x64\x00": {"star": 0x48, "eoinx": False, "ispair": False, "data":"txt"},
            b"\x50\x50\x56\x41": {"star": 0x20, "data":"vag", "fill":b'\xff'},
            b"\x02\x00\x00\x00": {"row": 0}
        }


        self.entry = {
            "key": "00",#key inicial del archivo, tambien contiene datos desconocidos de los txt
            "endianness": "big",#endian de los offsets
            "pad_offset": True,#indica si los offsets terminan en la columna 16, se rellena con 00 hasta esa columna
            "ispair": True, #indica si el ultimo offset marca hasta el final del archivo
            "fill": '00', #tipo de relleno y marcar posible stop en lectura de indices
            "rename": False
        }

        self.data = None # data json

    def guess_endianness(self, data: bytes) -> str:
        little = int.from_bytes(data, byteorder='little')
        big = int.from_bytes(data, byteorder='big')

        if little < big:
            return 'little'
        elif big < little:
            return 'big'
        else:
            return 'unknown_endian'

    def update_entry(self, key_bytes: bytes, endianness: str, pad_offset: bool, ispair: bool, fill: bytes, rename:bool=False):
        self.entry["key"] = key_bytes.hex()
        self.entry["endianness"] = endianness
        self.entry["pad_offset"] = pad_offset
        self.entry["ispair"] = ispair
        self.entry["fill"] = fill.hex()
        self.entry["rename"] = rename

        self.data = json.dumps(self.entry, indent=4)

    def load_entry(self, path):
        with open(path, "r") as f:
            self.entry = json.load(f)
            self.data = json.dumps(self.entry, indent=4)

