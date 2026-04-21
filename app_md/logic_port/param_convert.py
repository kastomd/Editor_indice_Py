import struct


def convert_param17(bt3_data: bytes) -> bytes:
    result = bytearray(bt3_data)
    for pos, count in [(0xCA, 2), (0x98, 1), (0x88, 1), (0x12, 8)]:
        result = result[:pos] + bytearray(count) + result[pos:]
    return bytes(result[:len(bt3_data)])


def convert_skill_cameras_pak(bt3_data: bytes) -> bytes:
    count = struct.unpack_from("<I", bt3_data, 0)[0]
    offsets_le = [struct.unpack_from("<I", bt3_data, 4 + i * 4)[0] for i in range(count + 1)]
    index_size = 4 + (count + 1) * 4
    first_offset = offsets_le[0]
    out = bytearray()
    out += struct.pack(">I", count)
    for o in offsets_le:
        out += struct.pack(">I", o)
    out += bt3_data[index_size:first_offset]
    out += bt3_data[first_offset:]
    return bytes(out)