from pathlib import Path
import numpy as np
from PIL import Image
import struct


def unswizzle_psp(data, width, height, bpp):

    if bpp == 8:
        block_w = 16
        block_h = 8
    else:  # 4bpp
        block_w = 32
        block_h = 8

    out = np.zeros_like(data)

    i = 0
    for by in range(0, height, block_h):
        for bx in range(0, width, block_w):

            for y in range(block_h):
                for x in range(block_w):

                    pixel = (by + y) * width + (bx + x)

                    if bpp == 8:
                        dst = pixel
                    else:
                        dst = pixel // 2

                    if dst < len(out) and i < len(data):
                        out[dst] = data[i]

                    i += 1

    return out


path_file = Path(r"C:\Users\Carlos ec\Documents\odi\com.neon.sgu\games\ext_PACKFILE_BIN_DBZTTT4colores sin mods\Characters\11_Vegeta_Scouter\1513_char_vegeta_scouter_1\3_effects\00_skill_001\5-5.unk")

file = path_file.read_bytes()


# ---------- HEADER PRINCIPAL ----------
texture_count = struct.unpack_from("<I", file, 0x0)[0]
bpp_header = struct.unpack_from("<I", file, 0x4)[0]

print("Texture count:", texture_count)
print("Header BPP:", bpp_header)

# donde empiezan los datos reales
data_offset = 0x20 + (texture_count * 0x60)


for texture in range(texture_count):

    # bloque descriptor
    tex_block_offset = (0x60 * texture) + 0x20

    texture_bytes = struct.unpack_from("<I", file, tex_block_offset + 0x08)[0]
    palette_bytes = struct.unpack_from("<I", file, tex_block_offset + 0x0C)[0]
    dimension = struct.unpack_from("<I", file, tex_block_offset + 0x10)[0]

    width = dimension
    height = dimension

    tex_offset = data_offset
    pal_offset = tex_offset + texture_bytes

    print("\n----- TEXTURE", texture, "-----")
    print("Dimensions:", width, "x", height)
    print("Texture bytes:", hex(texture_bytes))
    print("Palette bytes:", hex(palette_bytes))
    print("Texture offset:", hex(tex_offset))
    print("Palette offset:", hex(pal_offset))

    # ---------- TEXTURA ----------
    img_data = np.frombuffer(
        file[tex_offset:tex_offset + texture_bytes],
        dtype=np.uint8
    )

    palette = np.frombuffer(
        file[pal_offset:pal_offset + palette_bytes],
        dtype=np.uint8
    ).copy().reshape(-1, 4)

    # ---------- DETECTAR BPP REAL ----------
    palette_colors = palette_bytes // 4

    if palette_colors == 16:
        bpp = 4
    elif palette_colors == 256:
        bpp = 8
    else:
        raise ValueError("Paleta desconocida")

    # ---------- UNSWIZZLE ----------
    img_data = unswizzle_psp(img_data, width, height, bpp)

    # ---------- CORREGIR ALPHA PSP ----------
    alpha = palette[:, 3]
    palette[:, 3] = np.where(alpha >= 0x80, 255, alpha)

    # ---------- APLICAR PALETA ----------
    if bpp == 8:

        pixel_count = width * height
        img_data = img_data[:pixel_count]

        pixels = palette[img_data]

    else:  # 4bpp real

        pixel_count = width * height
        real_bytes = pixel_count // 2

        data = img_data[:real_bytes]

        pixels = np.empty((pixel_count, 4), dtype=np.uint8)

        pixels[0::2] = palette[data & 0x0F]
        pixels[1::2] = palette[data >> 4]

    pixels = pixels.reshape(height, width, 4)

    img = Image.fromarray(pixels, "RGBA")

    # ---------- GUARDAR ----------
    output_path = path_file.with_name(f"{path_file.stem}_{texture}.png")
    img.save(output_path)

    print("Exported:", output_path)

    # avanzar al siguiente bloque
    data_offset += texture_bytes + palette_bytes
