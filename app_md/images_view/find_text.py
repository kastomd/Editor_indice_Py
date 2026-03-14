from pathlib import Path
import struct
import numpy as np
from PIL import Image


def psp_tex_to_png(file_path, out_png):

    file_path = Path(file_path)

    with open(file_path, "rb") as f:
        data = f.read()

    # tamaños
    tex_size = struct.unpack_from("<I", data, 0x28)[0]
    pal_size = struct.unpack_from("<I", data, 0x2C)[0]

    data_offset = 0x80

    # leer paleta
    palette_data = data[data_offset:data_offset + pal_size]

    # leer indices de textura
    tex_offset = data_offset + pal_size
    tex_data = data[tex_offset:tex_offset + tex_size]

    # convertir paleta
    palette = [
        tuple(palette_data[i:i+4])
        for i in range(0, pal_size, 4)
    ]

    width = 16
    height = 16

    img = np.zeros((height, width, 4), dtype=np.uint8)

    for y in range(height):
        for x in range(width):

            index = tex_data[y * width + x]
            img[y, x] = palette[index]

    image = Image.fromarray(img, "RGBA")
    image.save(out_png)


if __name__ == "__main__":

    path = r"C:\Users\Carlos ec\Documents\odi\com.neon.sgu\games\ext_PACKFILE_BIN_DBZTTT4colores sin mods\Characters\11_Vegeta_Scouter\1513_char_vegeta_scouter_1\3_effects\00_skill_001\5-5.unk"
    path = Path(path)

    psp_tex_to_png(
        path,
        path.with_suffix(".png")
    )
