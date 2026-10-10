#!/usr/bin/env python3
"""
PSPRecomp-style PSP ELF import scanner.

This version follows the relevant logic from PSPRecomp's elf32.cpp:
- Reads ELF32 little-endian MIPS program headers.
- Locates the .rodata.sceModuleInfo / .sceModuleInfo section.
- Uses the exact ModuleInfo32 layout.
- Reads stub_top/stub_end.
- Walks PSP import stub records using their length_words field.
- Extracts library name, NID and stub address.

Usage:
    python elf_imports.py EBOOT_patched.ELF
"""

import struct
import sys
from dataclasses import dataclass


@dataclass
class Segment:
    offset: int
    vaddr: int
    filesz: int
    memsz: int
    type: int


@dataclass
class Section:
    name: str
    addr: int
    offset: int
    size: int
    type: int


@dataclass
class PspImport:
    library: str
    nid: int
    stub_address: int


class Elf32:
    def __init__(self, data: bytes):
        self.data = data
        self.segments = []
        self.sections = []
        self._parse()

    def _parse(self):
        if self.data[:4] != b"\x7fELF":
            raise ValueError("No es un ELF.")
        if self.data[4] != 1 or self.data[5] != 1:
            raise ValueError("Se esperaba ELF32 little-endian.")

        # ELF32 header
        phoff = struct.unpack_from("<I", self.data, 28)[0]
        shoff = struct.unpack_from("<I", self.data, 32)[0]
        phentsize = struct.unpack_from("<H", self.data, 42)[0]
        phnum = struct.unpack_from("<H", self.data, 44)[0]
        shentsize = struct.unpack_from("<H", self.data, 46)[0]
        shnum = struct.unpack_from("<H", self.data, 48)[0]
        shstrndx = struct.unpack_from("<H", self.data, 50)[0]

        # Program headers
        for i in range(phnum):
            off = phoff + i * phentsize
            if off + 32 > len(self.data):
                raise ValueError("Program header truncado.")

            p_type, p_offset, p_vaddr, _, p_filesz, p_memsz, _, _ = \
                struct.unpack_from("<IIIIIIII", self.data, off)

            self.segments.append(
                Segment(p_offset, p_vaddr, p_filesz, p_memsz, p_type)
            )

        # Section headers
        raw_sections = []
        for i in range(shnum):
            off = shoff + i * shentsize
            if off + 40 > len(self.data):
                raise ValueError("Section header truncado.")

            name, typ, flags, addr, offset, size, link, info, addralign, entsize = \
                struct.unpack_from("<IIIIIIIIII", self.data, off)

            raw_sections.append((name, typ, addr, offset, size))

        # Section-name string table
        names = b""
        if shstrndx < len(raw_sections):
            _, _, _, off, size = raw_sections[shstrndx]
            names = self.data[off:off + size]

        for name_idx, typ, addr, offset, size in raw_sections:
            name = ""
            if name_idx < len(names):
                end = names.find(b"\0", name_idx)
                if end != -1:
                    name = names[name_idx:end].decode("ascii", errors="replace")

            self.sections.append(
                Section(name, addr, offset, size, typ)
            )

    def vaddr_to_offset(self, address):
        for seg in self.segments:
            if seg.type != 1:  # PT_LOAD
                continue
            if seg.vaddr <= address < seg.vaddr + seg.filesz:
                return seg.offset + (address - seg.vaddr)
        return None

    def load8(self, address):
        off = self.vaddr_to_offset(address)
        if off is None or off >= len(self.data):
            raise ValueError(f"Dirección no mapeada: 0x{address:08X}")
        return self.data[off]

    def load16(self, address):
        off = self.vaddr_to_offset(address)
        if off is None or off + 2 > len(self.data):
            raise ValueError(f"Dirección no mapeada: 0x{address:08X}")
        return struct.unpack_from("<H", self.data, off)[0]

    def load32(self, address):
        off = self.vaddr_to_offset(address)
        if off is None or off + 4 > len(self.data):
            raise ValueError(f"Dirección no mapeada: 0x{address:08X}")
        return struct.unpack_from("<I", self.data, off)[0]

    def read_c_string(self, address, max_len=128):
        result = bytearray()
        for i in range(max_len):
            c = self.load8(address + i)
            if c == 0:
                break
            result.append(c)
        return result.decode("ascii", errors="replace")


def _is_load_address(elf: Elf32, address: int, size: int = 1) -> bool:
    """Comprueba que un rango de memoria esté respaldado por un PT_LOAD."""
    for seg in elf.segments:
        if seg.type != 1:
            continue
        if seg.vaddr <= address and address + size <= seg.vaddr + seg.filesz:
            return True
    return False


def _is_memory_address(elf: Elf32, address: int, size: int = 1) -> bool:
    """Comprueba que un rango esté dentro de la memoria de un PT_LOAD.

    A diferencia de _is_load_address(), también acepta la zona BSS
    (memsz > filesz), que es válida para campos como gp.
    """
    for seg in elf.segments:
        if seg.type != 1:
            continue
        if seg.vaddr <= address and address + size <= seg.vaddr + seg.memsz:
            return True
    return False


def _find_string(elf: Elf32, address: int, max_len: int = 128) -> str:
    try:
        return elf.read_c_string(address, max_len)
    except ValueError:
        return ""


def _looks_like_module_name(name: str) -> bool:
    if not name or len(name) > 28:
        return False
    # Module names PSP habituales: letras, números, '_' y '-'.
    return all(c.isalnum() or c in "_-" for c in name)


def _fallback_module_info(elf: Elf32):
    """
    Busca ModuleInfo directamente dentro de los PT_LOAD cuando el ELF no
    conserva nombres de secciones.

    Algunos EBOOT de PSP tienen el ModuleInfo perfectamente intacto, pero
    los section headers/nombres fueron eliminados. En ese caso no debemos
    elegir simplemente una cadena seguida por un TITLE ID: hay que validar
    la estructura completa de ModuleInfo32 y, sobre _todo, sus rangos
    ent_top/ent_end y stub_top/stub_end.
    """
    candidates = []

    for seg in elf.segments:
        if seg.type != 1 or seg.filesz < 52:
            continue

        # ModuleInfo puede estar en cualquier offset, pero normalmente está
        # razonablemente alineado. Probamos cada 4 bytes para no depender de
        # un layout concreto.
        start = seg.vaddr
        end = seg.vaddr + seg.filesz - 52

        address = (start + 3) & ~3
        while address <= end:
            try:
                attributes = elf.load16(address)
                version_major = elf.load8(address + 2)
                version_minor = elf.load8(address + 3)

                raw_name = bytes(
                    elf.load8(address + 4 + i)
                    for i in range(28)
                )
                name = raw_name.split(b"\0", 1)[0].decode(
                    "ascii", errors="strict"
                )

                if not _looks_like_module_name(name):
                    address += 4
                    continue

                gp = elf.load32(address + 32)
                ent_top = elf.load32(address + 36)
                ent_end = elf.load32(address + 40)
                stub_top = elf.load32(address + 44)
                stub_end = elf.load32(address + 48)

                # Los campos de punteros deben estar dentro de los PT_LOAD.
                if gp and not _is_memory_address(elf, gp):
                    address += 4
                    continue

                if not _is_load_address(elf, address, 52):
                    address += 4
                    continue

                # ent_top/end y stub_top/end son rangos virtuales.
                if ent_top and ent_end:
                    if ent_top > ent_end:
                        address += 4
                        continue
                    if not _is_load_address(elf, ent_top):
                        address += 4
                        continue
                    if ent_end > ent_top and not _is_load_address(elf, ent_end - 1):
                        address += 4
                        continue

                if not (
                    stub_top
                    and stub_end
                    and stub_top < stub_end
                    and _is_load_address(elf, stub_top)
                    and _is_load_address(elf, stub_end - 1)
                ):
                    address += 4
                    continue

                # Validar que stub_top realmente apunta a una secuencia de
                # import headers. Esto es la señal más fuerte de que estamos
                # ante ModuleInfo y no ante una estructura del juego que
                # casualmente contiene una string ASCII.
                try:
                    first_header = _is_valid_import_header(elf, stub_top)
                except (ValueError, NameError):
                    first_header = None

                if first_header is None:
                    address += 4
                    continue

                # Puntuación para escoger el candidato estructuralmente más
                # consistente. Un ModuleInfo real suele tener version 0x0100
                # o 0x0101 y stub_top/stub_end inmediatamente utilizables.
                score = 0
                score += 10
                if version_major in (0, 1, 2):
                    score += 2
                if version_minor in (0, 1, 2):
                    score += 1
                if gp:
                    score += 1
                if ent_top < ent_end:
                    score += 2
                if first_header:
                    score += 10

                candidates.append(
                    (
                        score,
                        {
                            "section": "<stripped / structural>" ,
                            "address": address,
                            "attributes": attributes,
                            "version_major": version_major,
                            "version_minor": version_minor,
                            "name": name,
                            "gp": gp,
                            "ent_top": ent_top,
                            "ent_end": ent_end,
                            "stub_top": stub_top,
                            "stub_end": stub_end,
                        },
                    )
                )

            except (ValueError, UnicodeDecodeError):
                pass

            address += 4

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    return None

def find_module_info(elf: Elf32):
    """Encuentra ModuleInfo usando primero el metodo ELF estándar y luego fallback."""
    wanted = {".rodata.sceModuleInfo", ".sceModuleInfo"}

    for section in elf.sections:
        if section.name in wanted and section.size >= 52:
            addr = section.addr

            name_bytes = bytes(
                elf.load8(addr + 4 + i) for i in range(28)
            )
            name = name_bytes.split(b"\0", 1)[0].decode(
                "ascii", errors="replace"
            )

            return {
                "section": section.name,
                "address": addr,
                "attributes": elf.load16(addr),
                "version_major": elf.load8(addr + 2),
                "version_minor": elf.load8(addr + 3),
                "name": name,
                "gp": elf.load32(addr + 32),
                "ent_top": elf.load32(addr + 36),
                "ent_end": elf.load32(addr + 40),
                "stub_top": elf.load32(addr + 44),
                "stub_end": elf.load32(addr + 48),
            }

    fallback = _fallback_module_info(elf)
    if fallback is not None:
        return fallback

    raise RuntimeError(
        "No se encontró ModuleInfo ni un nombre de módulo reconocible."
    )


def _is_valid_import_header(elf: Elf32, address: int):
    """Devuelve los datos de un import header PSP válido o None."""
    if not _is_load_address(elf, address, 20):
        return None

    try:
        libname = elf.load32(address)
        length_words = elf.load8(address + 8)
        count = elf.load16(address + 10)
        nid_table = elf.load32(address + 12)
        stub_table = elf.load32(address + 16)
    except ValueError:
        return None

    # Los headers PSPRecomp habituales tienen al menos 20 bytes.
    if length_words < 5 or length_words > 64:
        return None

    if count > 0x400:
        return None

    library = _find_string(elf, libname, 128)
    if not library or not _looks_like_import_library(library):
        return None

    header_size = max(20, length_words * 4)
    if not _is_load_address(elf, address, header_size):
        return None

    if count:
        if not _is_load_address(elf, nid_table, count * 4):
            return None
        if not _is_load_address(elf, stub_table, count * 8):
            return None

        # Una tabla de imports PSP contiene normalmente jr $ra / nop.
        # Esta comprobación reduce falsos positivos al buscar headers
        # cuando no existe stub_top/stub_end en ModuleInfo.
        for i in range(min(count, 4)):
            stub = stub_table + i * 8
            try:
                if elf.load32(stub) != 0x03E00008:
                    return None
            except ValueError:
                return None

    return {
        "address": address,
        "library": library,
        "length_words": length_words,
        "count": count,
        "nid_table": nid_table,
        "stub_table": stub_table,
        "end": address + header_size,
    }


def _looks_like_import_library(name: str) -> bool:
    if not name or len(name) > 64:
        return False

    # Evita interpretar strings arbitrarios del juego como headers.
    prefixes = (
        "sce",
        "IoFileMgr",
        "Kernel_",
        "LoadExec",
        "ModuleMgr",
        "Stdio",
        "SysMem",
        "ThreadMan",
        "Utils",
    )

    return name.startswith(prefixes)


def scan_imports(elf: Elf32, module):
    """
    Escanea imports PSP.

    Si ModuleInfo tiene stub_top/stub_end válidos, se utiliza el metodo
    original. Si el ELF está stripped y esos campos no están disponibles,
    se busca directamente por _todo el contenido de los PT_LOAD.
    """
    imports = []

    stub_top = module.get("stub_top", 0)
    stub_end = module.get("stub_end", 0)

    # --------------------------------------------------------------
    # Metodo estándar: ModuleInfo -> stub_top/stub_end
    # --------------------------------------------------------------
    if (
        stub_top
        and stub_end
        and stub_top < stub_end
        and _is_load_address(elf, stub_top)
        and _is_load_address(elf, stub_end - 1)
    ):
        cursor = stub_top
        end = stub_end

        while cursor < end:
            header = _is_valid_import_header(elf, cursor)
            if header is None:
                raise RuntimeError(
                    f"Import stub corrupto en 0x{cursor:08X}"
                )

            _append_imports(elf, imports, header)
            cursor = header["end"]

        return imports

    # --------------------------------------------------------------
    # Fallback para ELF stripped
    # --------------------------------------------------------------
    candidates = []

    for seg in elf.segments:
        if seg.type != 1:
            continue

        # Los headers están alineados a 4 bytes.
        start = (seg.vaddr + 3) & ~3
        end = seg.vaddr + seg.filesz

        address = start
        while address + 20 <= end:
            header = _is_valid_import_header(elf, address)
            if header is not None:
                candidates.append(header)
                # Los headers consecutivos normalmente están a length_words*4.
                address = header["end"]
                continue
            address += 4

    # El mismo header puede aparecer una vez; eliminar duplicados.
    unique = {}
    for header in candidates:
        unique[header["address"]] = header

    candidates = sorted(unique.values(), key=lambda x: x["address"])

    for header in candidates:
        _append_imports(elf, imports, header)

    return imports


def _append_imports(elf: Elf32, imports, header):
    library = header["library"]
    nid_table = header["nid_table"]
    stub_table = header["stub_table"]
    count = header["count"]

    for i in range(count):
        nid = elf.load32(nid_table + i * 4)
        stub_address = stub_table + i * 8

        item = PspImport(
            library=library,
            nid=nid,
            stub_address=stub_address,
        )

        # Evitar duplicados si una región ha sido encontrada por más de un
        # metodo/falso solapamiento.
        if not any(
            x.stub_address == item.stub_address
            and x.nid == item.nid
            and x.library == item.library
            for x in imports
        ):
            imports.append(item)


def main():
    if len(sys.argv) != 2:
        print("Uso:")
        print("  python elf_imports.py EBOOT_patched.ELF")
        return 1

    path = sys.argv[1]

    with open(path, "rb") as f:
        data = f.read()

    elf = Elf32(data)
    module = find_module_info(elf)
    imports = scan_imports(elf, module)

    print("PSPRecomp ELF Import Scanner")
    print("=" * 78)
    print(f"Module:       {module['name']}")
    print(f"Section:      {module['section']}")
    print(f"ModuleInfo:   0x{module['address']:08X}")
    print(f"GP:           0x{module['gp']:08X}")
    print(f"ent_top:      0x{module['ent_top']:08X}")
    print(f"ent_end:      0x{module['ent_end']:08X}")
    print(f"stub_top:     0x{module['stub_top']:08X}")
    print(f"stub_end:     0x{module['stub_end']:08X}")
    print()

    print(f"{'LIBRARY':32} {'NID':12} {'STUB ADDRESS':14}")
    print("-" * 78)

    for imp in imports:
        print(
            f"{imp.library:32} "
            f"0x{imp.nid:08X} "
            f"0x{imp.stub_address:08X}"
        )

    print()
    print(f"Total imports: {len(imports)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
