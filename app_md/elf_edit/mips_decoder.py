from dataclasses import dataclass


@dataclass
class MipsInstruction:
    raw: int
    opcode: int
    rs: int
    rt: int
    rd: int
    shamt: int
    funct: int
    immediate: int
    target: int
    mnemonic: str


REGISTER_NAMES = [
    "$zero", "$at",
    "$v0", "$v1",
    "$a0", "$a1", "$a2", "$a3",
    "$t0", "$t1", "$t2", "$t3",
    "$t4", "$t5", "$t6", "$t7",
    "$s0", "$s1", "$s2", "$s3",
    "$s4", "$s5", "$s6", "$s7",
    "$t8", "$t9",
    "$k0", "$k1",
    "$gp", "$sp", "$fp", "$ra"
]


def register_name(reg: int) -> str:
    if 0 <= reg < 32:
        return REGISTER_NAMES[reg]

    return "$unknown"


def sign_extend_16(value: int) -> int:
    value &= 0xFFFF

    if value & 0x8000:
        return value - 0x10000

    return value


def decode_mips(instruction: int) -> MipsInstruction:

    instruction &= 0xFFFFFFFF

    opcode = (instruction >> 26) & 0x3F
    rs = (instruction >> 21) & 0x1F
    rt = (instruction >> 16) & 0x1F
    rd = (instruction >> 11) & 0x1F
    shamt = (instruction >> 6) & 0x1F
    funct = instruction & 0x3F

    immediate = sign_extend_16(instruction & 0xFFFF)

    target = instruction & 0x03FFFFFF

    mnemonic = "unknown"

    if opcode == 0x00:

        if funct == 0x00:
            mnemonic = "sll"

        elif funct == 0x02:
            mnemonic = "srl"

        elif funct == 0x03:
            mnemonic = "sra"

        elif funct == 0x08:
            mnemonic = "jr"

        elif funct == 0x09:
            mnemonic = "jalr"

        elif funct == 0x20:
            mnemonic = "add"

        elif funct == 0x21:

            # addu rd, rs, zero = move rd, rs
            if rt == 0:
                mnemonic = "move"

            # addu rd, zero, rt = move rd, rt
            elif rs == 0:
                mnemonic = "move"

            else:
                mnemonic = "addu"

        elif funct == 0x22:
            mnemonic = "sub"

        elif funct == 0x23:
            mnemonic = "subu"

        elif funct == 0x24:
            mnemonic = "and"

        elif funct == 0x25:
            mnemonic = "or"

        elif funct == 0x26:
            mnemonic = "xor"

        elif funct == 0x27:
            mnemonic = "nor"

        elif funct == 0x2A:
            mnemonic = "slt"

        elif funct == 0x2B:
            mnemonic = "sltu"

        elif funct == 0x04:
            mnemonic = "sllv"

        elif funct == 0x06:
            mnemonic = "srlv"

        elif funct == 0x07:
            mnemonic = "srav"

        elif funct == 0x0C:
            mnemonic = "syscall"

        elif funct == 0x0D:
            mnemonic = "break"

        elif funct == 0x10:
            mnemonic = "mfhi"

        elif funct == 0x11:
            mnemonic = "mthi"

        elif funct == 0x12:
            mnemonic = "mflo"

        elif funct == 0x13:
            mnemonic = "mtlo"

        elif funct == 0x18:
            mnemonic = "mult"

        elif funct == 0x19:
            mnemonic = "multu"

        elif funct == 0x1A:
            mnemonic = "div"

        elif funct == 0x1B:
            mnemonic = "divu"

        elif funct == 0x0F:
            mnemonic = "sync"

    elif opcode == 0x02:
        mnemonic = "j"

    elif opcode == 0x03:
        mnemonic = "jal"

    elif opcode == 0x04:
        mnemonic = "beq"

    elif opcode == 0x05:
        mnemonic = "bne"

    elif opcode == 0x06:
        mnemonic = "blez"

    elif opcode == 0x07:
        mnemonic = "bgtz"

    elif opcode == 0x14:
        mnemonic = "beql"

    elif opcode == 0x15:
        mnemonic = "bnel"

    elif opcode == 0x16:
        mnemonic = "blezl"

    elif opcode == 0x17:
        mnemonic = "bgtzl"

    elif opcode == 0x01:
        regimm = rt
        if regimm == 0x00:
            mnemonic = "bltz"
        elif regimm == 0x01:
            mnemonic = "bgez"
        elif regimm == 0x10:
            mnemonic = "bltzal"
        elif regimm == 0x11:
            mnemonic = "bgezal"

    elif opcode == 0x08:
        mnemonic = "addi"

    elif opcode == 0x09:
        mnemonic = "addiu"

    elif opcode == 0x0A:
        mnemonic = "slti"

    elif opcode == 0x0B:
        mnemonic = "sltiu"

    elif opcode == 0x0C:
        mnemonic = "andi"

    elif opcode == 0x0D:
        mnemonic = "ori"

    elif opcode == 0x0E:
        mnemonic = "xori"

    elif opcode == 0x0F:
        mnemonic = "lui"

    elif opcode == 0x20:
        mnemonic = "lb"

    elif opcode == 0x21:
        mnemonic = "lh"

    elif opcode == 0x22:
        mnemonic = "lwl"

    elif opcode == 0x23:
        mnemonic = "lw"

    elif opcode == 0x24:
        mnemonic = "lbu"

    elif opcode == 0x25:
        mnemonic = "lhu"

    elif opcode == 0x26:
        mnemonic = "lwr"

    elif opcode == 0x28:
        mnemonic = "sb"

    elif opcode == 0x29:
        mnemonic = "sh"

    elif opcode == 0x2A:
        mnemonic = "swl"

    elif opcode == 0x2B:
        mnemonic = "sw"

    elif opcode == 0x2E:
        mnemonic = "swr"

    elif opcode == 0x1F:
        # Allegrex bit-manipulation family (SPECIAL3/BSHFL encodings).
        if funct == 0x20:
            if shamt == 0x02:
                mnemonic = "wsbh"
            elif shamt == 0x03:
                mnemonic = "wsbw"
            elif shamt == 0x10:
                mnemonic = "seb"
            elif shamt == 0x18:
                mnemonic = "seh"
            elif shamt == 0x1E:
                mnemonic = "bitrev"

    return MipsInstruction(
        raw=instruction,
        opcode=opcode,
        rs=rs,
        rt=rt,
        rd=rd,
        shamt=shamt,
        funct=funct,
        immediate=immediate,
        target=target,
        mnemonic=mnemonic
    )


def format_signed_hex(value: int) -> str:

    if value < 0:
        return f"-0x{-value:X}"

    return f"0x{value:X}"


def disassemble_mips(instruction: int, address: int = 0) -> str:
    if instruction == 0:
        return "nop"

    inst = decode_mips(instruction)

    if inst.mnemonic == "unknown":
        return f"0x{inst.raw:08X}"

    out = inst.mnemonic

    if inst.opcode == 0x00:

        if inst.funct in (0x00, 0x02, 0x03):

            out += (
                f" {register_name(inst.rd)}, "
                f"{register_name(inst.rt)}, "
                f"0x{inst.shamt:X}"
            )

        elif inst.funct == 0x08:

            out += f" {register_name(inst.rs)}"

        elif inst.funct == 0x09:

            out += (
                f" {register_name(inst.rd)}, "
                f"{register_name(inst.rs)}"
            )


        elif inst.funct == 0x21 and inst.mnemonic == "move":

            if inst.rt == 0:
                out += (
                    f" {register_name(inst.rd)}, "
                    f"{register_name(inst.rs)}"
                )
            else:
                out += (
                    f" {register_name(inst.rd)}, "
                    f"{register_name(inst.rt)}"
                )


        elif inst.funct in (
            0x20, 0x21, 0x22, 0x23,
            0x24, 0x25, 0x26, 0x27,
            0x2A, 0x2B
        ):

            out += (
                f" {register_name(inst.rd)}, "
                f"{register_name(inst.rs)}, "
                f"{register_name(inst.rt)}"
            )

        elif inst.funct in (0x04, 0x06, 0x07):
            out += (
                f" {register_name(inst.rd)}, "
                f"{register_name(inst.rt)}, "
                f"{register_name(inst.rs)}"
            )

        elif inst.funct in (0x10, 0x12):
            out += f" {register_name(inst.rd)}"

        elif inst.funct in (0x11, 0x13):
            out += f" {register_name(inst.rs)}"

        elif inst.funct in (0x18, 0x19, 0x1A, 0x1B):
            out += (
                f" {register_name(inst.rs)}, "
                f"{register_name(inst.rt)}"
            )

        elif inst.funct in (0x0C, 0x0D, 0x0F):
            # syscall/break/sync no operands in our canonical format.
            pass

    elif inst.opcode in (0x02, 0x03):

        # Las instrucciones J utilizan 26 bits de target.
        target = (inst.target << 2) & 0xFFFFFFFF

        if address:
            target = (address & 0xF0000000) | target

        out += f" 0x{target:X}"

    elif inst.opcode == 0x01:
        branch_target = (
            address + 4 +
            (inst.immediate << 2)
        ) & 0xFFFFFFFF
        out += (
            f" {register_name(inst.rs)}, "
            f"0x{branch_target:X}"
        )

    elif inst.opcode in (0x04, 0x05):

        # Branch:
        #
        # target = PC + 4 + (immediate << 2)
        #
        branch_target = (
            address + 4 +
            (inst.immediate << 2)
        ) & 0xFFFFFFFF

        out += (
            f" {register_name(inst.rs)}, "
            f"{register_name(inst.rt)}, "
            f"0x{branch_target:X}"
        )

    elif inst.opcode in (0x14, 0x15, 0x16, 0x17):
        branch_target = (
            address + 4 +
            (inst.immediate << 2)
        ) & 0xFFFFFFFF

        if inst.opcode in (0x16, 0x17):
            out += (
                f" {register_name(inst.rs)}, "
                f"0x{branch_target:X}"
            )
        else:
            out += (
                f" {register_name(inst.rs)}, "
                f"{register_name(inst.rt)}, "
                f"0x{branch_target:X}"
            )

    elif inst.opcode in (0x06, 0x07):

        branch_target = (
            address + 4 +
            (inst.immediate << 2)
        ) & 0xFFFFFFFF

        out += (
            f" {register_name(inst.rs)}, "
            f"0x{branch_target:X}"
        )

    elif inst.opcode in (
        0x08, 0x09,
        0x0A, 0x0B
    ):

        out += (
            f" {register_name(inst.rt)}, "
            f"{register_name(inst.rs)}, "
            f"{format_signed_hex(inst.immediate)}"
        )

    elif inst.opcode in (0x0C, 0x0D, 0x0E):

        out += (
            f" {register_name(inst.rt)}, "
            f"{register_name(inst.rs)}, "
            f"0x{inst.immediate & 0xFFFF:X}"
        )

    elif inst.opcode == 0x0F:

        out += (
            f" {register_name(inst.rt)}, "
            f"0x{inst.immediate & 0xFFFF:X}"
        )

    elif inst.opcode == 0x1F and inst.funct == 0x20:
        if inst.mnemonic in ("wsbh", "wsbw", "bitrev"):
            out += (
                f" {register_name(inst.rd)}, "
                f"{register_name(inst.rt)}"
            )
        elif inst.mnemonic in ("seb", "seh"):
            out += (
                f" {register_name(inst.rd)}, "
                f"{register_name(inst.rt)}"
            )

    elif inst.opcode in (
        0x20, 0x21, 0x22,
        0x23, 0x24, 0x25,
        0x26, 0x28, 0x29,
        0x2A, 0x2B, 0x2E
    ):

        out += (
            f" {register_name(inst.rt)}, "
            f"{format_signed_hex(inst.immediate)}"
            f"({register_name(inst.rs)})"
        )

    return out
# ----------------------------------------------------------------------
# MIPS assembler (subset matching the decoder above)
# ----------------------------------------------------------------------


def _parse_register(value: str) -> int:
    value = value.strip()

    if value.startswith("$r") and value[2:].isdigit():
        n = int(value[2:], 10)
        if 0 <= n < 32:
            return n

    if value.startswith("$"):
        try:
            return REGISTER_NAMES.index(value)
        except ValueError:
            pass

    raise ValueError(f"Registro inválido: {value}")


def _parse_int(value: str) -> int:
    return int(value.strip(), 0)


def _split_operands(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def _encode_r(rs: int, rt: int, rd: int, shamt: int, funct: int) -> int:
    return (
        (rs << 21) |
        (rt << 16) |
        (rd << 11) |
        (shamt << 6) |
        funct
    )


def _encode_i(opcode: int, rs: int, rt: int, immediate: int) -> int:
    if not -0x8000 <= immediate <= 0xFFFF:
        raise ValueError(f"Immediate fuera de rango: {immediate}")
    return (
        (opcode << 26) |
        (rs << 21) |
        (rt << 16) |
        (immediate & 0xFFFF)
    )


def assemble_mips(text: str, address: int = 0) -> int:
    """Convierte una instrucción MIPS del formato producido por disassemble_mips() a uint32."""
    text = text.strip()
    if not text:
        raise ValueError("Instrucción vacía")

    # Permite importar directamente instrucciones desconocidas que quedaron en hex.
    if text.lower().startswith("0x"):
        value = int(text, 0)
        if not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("Instrucción hexadecimal fuera de rango")
        return value

    parts = text.split(None, 1)
    mnemonic = parts[0].lower()
    operands = _split_operands(parts[1]) if len(parts) > 1 else []

    if mnemonic == "nop":
        if operands:
            raise ValueError("nop no acepta operandos")
        return 0

    # R-type
    r_funct = {
        "add": 0x20,
        "addu": 0x21,
        "sub": 0x22,
        "subu": 0x23,
        "and": 0x24,
        "or": 0x25,
        "xor": 0x26,
        "nor": 0x27,
        "slt": 0x2A,
        "sltu": 0x2B,
    }

    if mnemonic in ("sll", "srl", "sra"):
        if len(operands) != 3:
            raise ValueError(f"{mnemonic} requiere rd, rt, shamt")
        rd = _parse_register(operands[0])
        rt = _parse_register(operands[1])
        shamt = _parse_int(operands[2])
        if not 0 <= shamt <= 31:
            raise ValueError("shamt fuera de rango")
        funct = {"sll": 0x00, "srl": 0x02, "sra": 0x03}[mnemonic]
        return _encode_r(0, rt, rd, shamt, funct)

    if mnemonic in r_funct:
        if len(operands) != 3:
            raise ValueError(f"{mnemonic} requiere rd, rs, rt")
        rd = _parse_register(operands[0])
        rs = _parse_register(operands[1])
        rt = _parse_register(operands[2])
        return _encode_r(rs, rt, rd, 0, r_funct[mnemonic])

    if mnemonic in ("sllv", "srlv", "srav"):
        if len(operands) != 3:
            raise ValueError(f"{mnemonic} requiere rd, rt, rs")
        rd = _parse_register(operands[0])
        rt = _parse_register(operands[1])
        rs = _parse_register(operands[2])
        funct = {"sllv": 0x04, "srlv": 0x06, "srav": 0x07}[mnemonic]
        return _encode_r(rs, rt, rd, 0, funct)

    if mnemonic in ("mfhi", "mflo"):
        if len(operands) != 1:
            raise ValueError(f"{mnemonic} requiere rd")
        rd = _parse_register(operands[0])
        return _encode_r(0, 0, rd, 0, 0x10 if mnemonic == "mfhi" else 0x12)

    if mnemonic in ("mthi", "mtlo"):
        if len(operands) != 1:
            raise ValueError(f"{mnemonic} requiere rs")
        rs = _parse_register(operands[0])
        return _encode_r(rs, 0, 0, 0, 0x11 if mnemonic == "mthi" else 0x13)

    if mnemonic in ("mult", "multu", "div", "divu"):
        if len(operands) != 2:
            raise ValueError(f"{mnemonic} requiere rs, rt")
        rs = _parse_register(operands[0])
        rt = _parse_register(operands[1])
        funct = {"mult": 0x18, "multu": 0x19, "div": 0x1A, "divu": 0x1B}[mnemonic]
        return _encode_r(rs, rt, 0, 0, funct)

    if mnemonic in ("syscall", "break", "sync"):
        if operands:
            raise ValueError(f"{mnemonic} no acepta operandos")
        funct = {"syscall": 0x0C, "break": 0x0D, "sync": 0x0F}[mnemonic]
        return _encode_r(0, 0, 0, 0, funct)

    if mnemonic == "move":
        if len(operands) != 2:
            raise ValueError("move requiere rd, rs")
        rd = _parse_register(operands[0])
        rs = _parse_register(operands[1])
        return _encode_r(rs, 0, rd, 0, 0x21)

    if mnemonic == "jr":
        if len(operands) != 1:
            raise ValueError("jr requiere rs")
        rs = _parse_register(operands[0])
        return _encode_r(rs, 0, 0, 0, 0x08)

    if mnemonic == "jalr":
        if len(operands) == 1:
            rs = _parse_register(operands[0])
            rd = 31
        elif len(operands) == 2:
            rd = _parse_register(operands[0])
            rs = _parse_register(operands[1])
        else:
            raise ValueError("jalr requiere rs o rd, rs")
        return _encode_r(rs, 0, rd, 0, 0x09)

    # J-type
    if mnemonic in ("j", "jal"):
        if len(operands) != 1:
            raise ValueError(f"{mnemonic} requiere target")
        target = _parse_int(operands[0])
        if target & 3:
            raise ValueError("Target no está alineado a 4 bytes")
        if (target & 0xF0000000) != (address & 0xF0000000):
            raise ValueError(
                f"Target {target:#x} no puede representarse con el J-type desde {address:#x}"
            )
        opcode = 0x02 if mnemonic == "j" else 0x03
        return (opcode << 26) | ((target >> 2) & 0x03FFFFFF)

    # REGIMM branches
    if mnemonic in ("bltz", "bgez", "bltzal", "bgezal"):
        if len(operands) != 2:
            raise ValueError(f"{mnemonic} requiere rs, target")
        rs = _parse_register(operands[0])
        target = _parse_int(operands[1])
        delta = target - (address + 4)
        if delta % 4:
            raise ValueError("Target de branch no está alineado")
        immediate = delta // 4
        if not -0x8000 <= immediate <= 0x7FFF:
            raise ValueError("Target de branch fuera de rango")
        rt = {
            "bltz": 0x00,
            "bgez": 0x01,
            "bltzal": 0x10,
            "bgezal": 0x11,
        }[mnemonic]
        return _encode_i(0x01, rs, rt, immediate)

    # Branch-likely instructions
    if mnemonic in ("beql", "bnel", "blezl", "bgtzl"):
        if mnemonic in ("blezl", "bgtzl"):
            if len(operands) != 2:
                raise ValueError(f"{mnemonic} requiere rs, target")
            rs = _parse_register(operands[0])
            target = _parse_int(operands[1])
            rt = 0
        else:
            if len(operands) != 3:
                raise ValueError(f"{mnemonic} requiere rs, rt, target")
            rs = _parse_register(operands[0])
            rt = _parse_register(operands[1])
            target = _parse_int(operands[2])

        delta = target - (address + 4)
        if delta % 4:
            raise ValueError("Target de branch no está alineado")
        immediate = delta // 4
        if not -0x8000 <= immediate <= 0x7FFF:
            raise ValueError("Target de branch fuera de rango")

        opcode = {
            "beql": 0x14,
            "bnel": 0x15,
            "blezl": 0x16,
            "bgtzl": 0x17,
        }[mnemonic]
        return _encode_i(opcode, rs, rt, immediate)

    # Allegrex bit manipulation
    if mnemonic in ("wsbh", "wsbw", "bitrev", "seb", "seh"):
        if len(operands) != 2:
            raise ValueError(f"{mnemonic} requiere rd, rt")
        rd = _parse_register(operands[0])
        rt = _parse_register(operands[1])
        shamt = {
            "wsbh": 0x02,
            "wsbw": 0x03,
            "seb": 0x10,
            "seh": 0x18,
            "bitrev": 0x1E,
        }[mnemonic]
        return (
            (0x1F << 26) |
            (rt << 16) |
            (rd << 11) |
            (shamt << 6) |
            0x20
        )

    # Branches
    if mnemonic in ("beq", "bne"):
        if len(operands) != 3:
            raise ValueError(f"{mnemonic} requiere rs, rt, target")
        rs = _parse_register(operands[0])
        rt = _parse_register(operands[1])
        target = _parse_int(operands[2])
        delta = target - (address + 4)
        if delta % 4:
            raise ValueError("Target de branch no está alineado")
        immediate = delta // 4
        if not -0x8000 <= immediate <= 0x7FFF:
            raise ValueError("Target de branch fuera de rango")
        opcode = 0x04 if mnemonic == "beq" else 0x05
        return _encode_i(opcode, rs, rt, immediate)

    if mnemonic in ("blez", "bgtz"):
        if len(operands) != 2:
            raise ValueError(f"{mnemonic} requiere rs, target")
        rs = _parse_register(operands[0])
        target = _parse_int(operands[1])
        delta = target - (address + 4)
        if delta % 4:
            raise ValueError("Target de branch no está alineado")
        immediate = delta // 4
        if not -0x8000 <= immediate <= 0x7FFF:
            raise ValueError("Target de branch fuera de rango")
        opcode = 0x06 if mnemonic == "blez" else 0x07
        return _encode_i(opcode, rs, 0, immediate)

    # Immediate instructions
    i_opcodes = {
        "addi": 0x08,
        "addiu": 0x09,
        "slti": 0x0A,
        "sltiu": 0x0B,
        "andi": 0x0C,
        "ori": 0x0D,
        "xori": 0x0E,
    }

    if mnemonic in i_opcodes:
        if len(operands) != 3:
            raise ValueError(f"{mnemonic} requiere rt, rs, immediate")
        rt = _parse_register(operands[0])
        rs = _parse_register(operands[1])
        immediate = _parse_int(operands[2])
        if mnemonic in ("andi", "ori", "xori") and not 0 <= immediate <= 0xFFFF:
            raise ValueError("Immediate fuera de rango")
        return _encode_i(i_opcodes[mnemonic], rs, rt, immediate)

    if mnemonic == "lui":
        if len(operands) != 2:
            raise ValueError("lui requiere rt, immediate")
        rt = _parse_register(operands[0])
        immediate = _parse_int(operands[1])
        if not 0 <= immediate <= 0xFFFF:
            raise ValueError("Immediate fuera de rango")
        return _encode_i(0x0F, 0, rt, immediate)

    # Load/store: rt, offset(rs)
    memory_opcodes = {
        "lb": 0x20,
        "lh": 0x21,
        "lwl": 0x22,
        "lw": 0x23,
        "lbu": 0x24,
        "lhu": 0x25,
        "lwr": 0x26,
        "sb": 0x28,
        "sh": 0x29,
        "swl": 0x2A,
        "sw": 0x2B,
        "swr": 0x2E,
    }

    if mnemonic in memory_opcodes:
        if len(operands) != 2:
            raise ValueError(f"{mnemonic} requiere rt, offset(rs)")
        rt = _parse_register(operands[0])
        mem = operands[1].replace(" ", "")
        left = mem.find("(")
        right = mem.rfind(")")
        if left <= 0 or right != len(mem) - 1:
            raise ValueError(f"Operando de memoria inválido: {operands[1]}")
        offset = _parse_int(mem[:left])
        rs = _parse_register(mem[left + 1:right])
        return _encode_i(memory_opcodes[mnemonic], rs, rt, offset)

    raise ValueError(f"Instrucción MIPS no soportada: {text}")
