#!/usr/bin/env python3
"""
PSPRecomp ELF loader / PT_LOAD inspector.

Muestra para cada segmento PT_LOAD:
- offset dentro del ELF
- rango de bytes del archivo que se cargan
- dirección virtual de destino
- rango de memoria ocupado
- diferencia FileSize/MemSize (BSS)
- relación entre una dirección virtual y su offset dentro del ELF

Uso:
    python elf_loader.py EBOOT_patched.ELF

También permite consultar una dirección virtual:
    python elf_loader.py EBOOT_patched.ELF 0x08A66900
"""

import struct
import sys
from dataclasses import dataclass


PT_LOAD = 1


@dataclass
class LoadSegment:
    index: int
    offset: int
    vaddr: int
    paddr: int
    filesz: int
    memsz: int
    flags: int
    align: int

    @property
    def file_end(self):
        """Offset exclusivo después del último byte del segmento."""
        return self.offset + self.filesz

    @property
    def file_last(self):
        """Último byte del archivo incluido en el segmento."""
        return self.offset + self.filesz - 1 if self.filesz else self.offset

    @property
    def mem_end(self):
        """Dirección exclusiva después del último byte en memoria."""
        return self.vaddr + self.memsz

    @property
    def mem_last(self):
        """Última dirección ocupada en memoria."""
        return self.vaddr + self.memsz - 1 if self.memsz else self.vaddr

    @property
    def bss_size(self):
        return max(0, self.memsz - self.filesz)


class ElfLoader:
    def __init__(self, data: bytes):
        self.data = data
        self.segments = []
        self.entry = 0
        self._parse_elf()

    def _parse_elf(self):
        if len(self.data) < 52:
            raise ValueError("El archivo es demasiado pequeño para ser ELF32.")

        if self.data[:4] != b"\x7fELF":
            raise ValueError("El archivo no es un ELF.")

        elf_class = self.data[4]
        endian = self.data[5]

        if elf_class != 1:
            raise ValueError("Este loader espera ELF32.")
        if endian != 1:
            raise ValueError("Este loader espera ELF little-endian.")

        # ELF32 header
        self.entry = struct.unpack_from("<I", self.data, 24)[0]
        phoff = struct.unpack_from("<I", self.data, 28)[0]
        phentsize = struct.unpack_from("<H", self.data, 42)[0]
        phnum = struct.unpack_from("<H", self.data, 44)[0]

        if phentsize < 32:
            raise ValueError("Tamaño inválido de Program Header.")

        for i in range(phnum):
            off = phoff + i * phentsize

            if off + 32 > len(self.data):
                raise ValueError(f"Program Header {i} está truncado.")

            (
                p_type,
                p_offset,
                p_vaddr,
                p_paddr,
                p_filesz,
                p_memsz,
                p_flags,
                p_align,
            ) = struct.unpack_from("<IIIIIIII", self.data, off)

            if p_type == PT_LOAD:
                # Validación: la región que viene del archivo debe existir.
                if p_offset + p_filesz > len(self.data):
                    raise ValueError(
                        f"PT_LOAD #{i} apunta fuera del archivo: "
                        f"offset=0x{p_offset:X}, filesz=0x{p_filesz:X}"
                    )

                self.segments.append(
                    LoadSegment(
                        index=i,
                        offset=p_offset,
                        vaddr=p_vaddr,
                        paddr=p_paddr,
                        filesz=p_filesz,
                        memsz=p_memsz,
                        flags=p_flags,
                        align=p_align,
                    )
                )

    def virtual_to_file_offset(self, address):
        """
        Convierte una dirección virtual a offset del ELF.

        Solo es válida para la parte respaldada por el archivo:
            vaddr <= address < vaddr + filesz

        Si la dirección cae en BSS, devuelve None.
        """
        for seg in self.segments:
            if seg.vaddr <= address < seg.vaddr + seg.filesz:
                return seg.offset + (address - seg.vaddr)
        return None

    def find_segment_for_address(self, address):
        """Devuelve el PT_LOAD que contiene la dirección en memoria."""
        for seg in self.segments:
            if seg.vaddr <= address < seg.vaddr + seg.memsz:
                return seg
        return None

    def print_segments(self):
        print("PSPRecomp ELF Loader")
        print("=" * 82)
        print(f"ELF size : 0x{len(self.data):X} ({len(self.data)} bytes)")
        print(f"Entry    : 0x{self.entry:08X}")
        print()

        if not self.segments:
            print("No se encontraron segmentos PT_LOAD.")
            return

        for n, seg in enumerate(self.segments):
            perms = (
                ("R" if seg.flags & 4 else "-") +
                ("W" if seg.flags & 2 else "-") +
                ("X" if seg.flags & 1 else "-")
            )

            print(f"PT_LOAD #{n} (Program Header index {seg.index})")
            print("-" * 82)
            print(f"Flags        : {perms}  (0x{seg.flags:X})")
            print(f"Alignment    : 0x{seg.align:X}")
            print()
            print(f"ELF offset   : 0x{seg.offset:08X}")
            print(f"ELF end      : 0x{seg.file_last:08X}")
            print(f"ELF next     : 0x{seg.file_end:08X}")
            print(f"File size    : 0x{seg.filesz:08X}")
            print()
            print(f"Memory start : 0x{seg.vaddr:08X}")
            print(f"Memory end   : 0x{seg.mem_last:08X}")
            print(f"Memory next  : 0x{seg.mem_end:08X}")
            print(f"Memory size  : 0x{seg.memsz:08X}")

            if seg.bss_size:
                bss_start = seg.vaddr + seg.filesz
                print()
                print(f"BSS start    : 0x{bss_start:08X}")
                print(f"BSS end      : 0x{seg.mem_last:08X}")
                print(f"BSS size     : 0x{seg.bss_size:08X}")

            print()

    def print_address_info(self, address):
        print(f"Dirección virtual consultada: 0x{address:08X}")
        print("=" * 82)

        seg = self.find_segment_for_address(address)

        if seg is None:
            print("La dirección no pertenece a ningún PT_LOAD.")
            return

        print(f"PT_LOAD #{seg.index}")
        print(f"Rango memoria : 0x{seg.vaddr:08X} - 0x{seg.mem_last:08X}")

        file_offset = self.virtual_to_file_offset(address)

        if file_offset is not None:
            relative = address - seg.vaddr

            print()
            print("Esta dirección está respaldada por bytes del ELF.")
            print(f"Offset ELF    : 0x{file_offset:08X}")
            print(f"Offset relativo: 0x{relative:X}")
            print(
                f"Byte ELF      : 0x{self.data[file_offset]:02X}"
            )

            if file_offset + 4 <= len(self.data):
                word = struct.unpack_from(
                    "<I", self.data, file_offset
                )[0]
                print(f"Word LE      : 0x{word:08X}")
        else:
            bss_start = seg.vaddr + seg.filesz
            print()
            print("Esta dirección está en la zona BSS.")
            print(f"BSS           : 0x{bss_start:08X} - 0x{seg.mem_last:08X}")
            print("No existe un byte correspondiente en el ELF.")

        print()


def main():
    if len(sys.argv) not in (2, 3):
        print("Uso:")
        print("  python elf_loader.py EBOOT_patched.ELF")
        print("  python elf_loader.py EBOOT_patched.ELF 0x08A66900")
        return 1

    path = sys.argv[1]

    try:
        with open(path, "rb") as f:
            data = f.read()

        loader = ElfLoader(data)
        loader.print_segments()

        if len(sys.argv) == 3:
            address = int(sys.argv[2], 0)
            loader.print_address_info(address)

        return 0

    except (OSError, ValueError, struct.error) as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
