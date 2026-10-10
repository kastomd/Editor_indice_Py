import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QComboBox,
    QCheckBox, QFileDialog, QMessageBox, QGroupBox, QProgressBar,
    QScrollArea
)
from PIL import Image


class CheckerboardPreview(QLabel):
    """Visor con fondo de cuadros tipo editor de imágenes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAutoFillBackground(False)

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QColor

        painter = QPainter(self)

        # Fondo base.
        painter.fillRect(self.rect(), QColor(220, 220, 220))

        # Cuadrícula de transparencia.
        square = 16
        light = QColor(235, 235, 235)
        dark = QColor(195, 195, 195)

        for y in range(0, self.height(), square):
            for x in range(0, self.width(), square):
                color = light if ((x // square) + (y // square)) % 2 == 0 else dark
                painter.fillRect(x, y, square, square, color)

        # Pintar encima el texto o la textura.
        super().paintEvent(event)

        painter.end()


class PSPTextureExtractor(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PSP Texture Extractor")
        self.setFixedWidth(720)

        self.setAcceptDrops(True)

        self.file_path = None
        self.file_data = b""

        self.build_ui()

    def dragEnterEvent(self, event):
        """Acepta archivos arrastrados a la ventana."""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()

            if urls and urls[0].isLocalFile():
                event.acceptProposedAction()
                return

        event.ignore()

    def dropEvent(self, event):
        """Abre BIN o importa PNG según el archivo arrastrado."""
        urls = event.mimeData().urls()

        if not urls:
            event.ignore()
            return

        url = urls[0]

        if not url.isLocalFile():
            event.ignore()
            return

        dropped_path = Path(url.toLocalFile())

        if not dropped_path.is_file():
            event.ignore()
            return

        # PNG: reemplaza la textura actualmente seleccionada,
        # preguntando antes de modificarla.
        if dropped_path.suffix.lower() == ".png":
            self.replace_preview_texture_from_path(dropped_path)
        else:
            # Cualquier otro archivo se abre directamente como BIN.
            self.open_texture_file(dropped_path)

        event.acceptProposedAction()

    def open_texture_file(self, path):
        """Carga directamente un archivo de texturas/BIN."""
        try:
            self.file_data = path.read_bytes()
            self.file_path = path

            self.file_edit.setText(str(path))

            self.update_file_info()

            # Volver a la primera textura al abrir otro archivo.
            self.preview_texture.blockSignals(True)
            self.preview_texture.setValue(1)
            self.preview_texture.blockSignals(False)

            self.update_preview()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"No se pudo abrir el archivo:\n\n{e}"
            )

    def replace_preview_texture_from_path(self, png_path):
        """Importa un PNG arrastrado sobre la textura actual."""
        if not self.file_data:
            # Si no hay BIN abierto, un PNG no puede reemplazar una textura.
            QMessageBox.information(
                self,
                "Importar textura",
                "Primero debes abrir un archivo de texturas."
            )
            return

        texture_number = self.preview_texture.value()

        result = QMessageBox.question(
            self,
            "Reemplazar textura",
            f"¿Deseas reemplazar la textura {texture_number} "
            f"con el archivo:\n\n{png_path.name}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if result != QMessageBox.Yes:
            return

        self.replace_preview_texture_from_selected_path(png_path)

    def replace_preview_texture_from_selected_path(self, png_path):
        """Realiza el reemplazo usando un PNG ya seleccionado."""
        try:
            image = Image.open(png_path)
            new_bytes = self.image_to_texture_bytes(image)

            bpt = self.bytes_per_texture()

            if len(new_bytes) != bpt:
                raise ValueError(
                    f"La textura convertida tiene {len(new_bytes):,} bytes, "
                    f"pero se esperaban {bpt:,} bytes."
                )

            texture_number = self.preview_texture.value()
            start = (texture_number - 1) * bpt
            end = start + bpt

            if end > len(self.file_data):
                raise ValueError(
                    "La textura seleccionada está fuera del tamaño actual."
                )

            data = bytearray(self.file_data)
            data[start:end] = new_bytes
            self.file_data = bytes(data)

            if self.file_path:
                self.file_path.write_bytes(self.file_data)

            self.update_file_info()
            self.update_preview()

            self.import_info_label.setText(
                f"Textura {texture_number} reemplazada: {png_path.name}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error al importar",
                f"No se pudo reemplazar la textura:\n\n{e}"
            )

    def build_ui(self):
        # ---------------------------------------------------------
        # Área desplazable
        # ---------------------------------------------------------
        # La ventana mantiene un tamaño fijo, pero _todo su contenido
        # puede recorrerse mediante la barra de desplazamiento vertical.
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(8, 8, 8, 8)

        scroll.setWidget(content_widget)
        outer_layout.addWidget(scroll)

        self.scroll_area = scroll
        self.scroll_content = content_widget

        # ---------------------------------------------------------
        # Archivo
        # ---------------------------------------------------------
        file_group = QGroupBox("Archivo")
        file_layout = QHBoxLayout(file_group)

        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)

        open_btn = QPushButton("Abrir...")
        open_btn.clicked.connect(self.open_file)

        file_layout.addWidget(self.file_edit)
        file_layout.addWidget(open_btn)

        layout.addWidget(file_group)

        # ---------------------------------------------------------
        # Configuración
        # ---------------------------------------------------------
        config_group = QGroupBox("Configuración de textura")
        form = QFormLayout(config_group)

        self.texture_count = QSpinBox()
        self.texture_count.setRange(1, 10000)
        self.texture_count.setValue(1)
        self.texture_count.valueChanged.connect(self.update_preview_texture_range)
        self.texture_count.valueChanged.connect(self.update_total_texture_bytes)

        self.width_edit = QSpinBox()
        self.width_edit.setRange(1, 8192)
        self.width_edit.setValue(480)

        self.height_edit = QSpinBox()
        self.height_edit.setRange(1, 8192)
        self.height_edit.setValue(272)

        self.bpp_combo = QComboBox()
        self.bpp_combo.addItems([
            "8 bpp",
            "16 bpp",
            "24 bpp",
            "32 bpp",
        ])
        self.bpp_combo.setCurrentText("32 bpp")
        self.bpp_combo.currentIndexChanged.connect(self.update_format_options)
        self.bpp_combo.currentIndexChanged.connect(self.update_preview)
        self.bpp_combo.currentIndexChanged.connect(self.update_total_texture_bytes)

        self.format_combo = QComboBox()
        self.update_format_options()
        self.format_combo.currentIndexChanged.connect(self.update_preview)

        self.order_combo = QComboBox()
        self.order_combo.addItems([
            "RGBA",
            "BGRA",
            "ARGB",
            "ABGR",
        ])
        self.order_combo.currentIndexChanged.connect(self.update_preview)

        self.width_edit.valueChanged.connect(self.update_total_texture_bytes)
        self.height_edit.valueChanged.connect(self.update_total_texture_bytes)

        form.addRow("Cantidad de texturas:", self.texture_count)
        form.addRow("Ancho:", self.width_edit)
        form.addRow("Alto:", self.height_edit)
        form.addRow("Bits por pixel:", self.bpp_combo)
        form.addRow("Formato:", self.format_combo)
        form.addRow("Orden de bytes:", self.order_combo)

        layout.addWidget(config_group)

        # ---------------------------------------------------------
        # Opciones
        # ---------------------------------------------------------
        options_group = QGroupBox("Opciones")
        options_layout = QVBoxLayout(options_group)

        self.swizzle_check = QCheckBox(
            "Datos swizzled de PSP (desactivar si los píxeles están lineales)"
        )
        self.swizzle_check.setChecked(False)
        self.swizzle_check.stateChanged.connect(self.update_preview)

        self.flip_vertical_check = QCheckBox("Voltear verticalmente")
        self.flip_vertical_check.setChecked(False)
        self.flip_vertical_check.stateChanged.connect(self.update_preview)

        self.ignore_alpha_check = QCheckBox(
            "Ignorar alpha (mostrar todos los píxeles con alpha 255)"
        )
        self.ignore_alpha_check.setChecked(False)
        self.ignore_alpha_check.stateChanged.connect(self.update_preview)

        options_layout.addWidget(self.swizzle_check)
        options_layout.addWidget(self.flip_vertical_check)
        options_layout.addWidget(self.ignore_alpha_check)

        layout.addWidget(options_group)

        # ---------------------------------------------------------
        # Información
        # ---------------------------------------------------------
        self.info_label = QLabel("Archivo no cargado.")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.total_texture_bytes_label = QLabel(
            "Total de bytes por textura: 0 bytes"
        )
        layout.addWidget(self.total_texture_bytes_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # ---------------------------------------------------------
        # Vista previa
        # ---------------------------------------------------------
        preview_group = QGroupBox("Vista previa")
        preview_layout = QVBoxLayout(preview_group)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Textura:"))

        self.preview_texture = QSpinBox()
        self.preview_texture.setRange(1, 1)
        self.preview_texture.setValue(1)
        self.preview_texture.setReadOnly(True)
        self.preview_texture.setButtonSymbols(QSpinBox.NoButtons)
        self.preview_texture.setFocusPolicy(Qt.NoFocus)
        controls.addWidget(self.preview_texture)

        self.previous_texture_btn = QPushButton("◀ Anterior")
        self.previous_texture_btn.clicked.connect(self.previous_preview_texture)
        controls.addWidget(self.previous_texture_btn)

        self.next_texture_btn = QPushButton("Siguiente ▶")
        self.next_texture_btn.clicked.connect(self.next_preview_texture)
        controls.addWidget(self.next_texture_btn)
        controls.addStretch()

        preview_layout.addLayout(controls)

        self.preview_label = CheckerboardPreview("Sin vista previa")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(480, 272)
        preview_layout.addWidget(self.preview_label)

        self.preview_info = QLabel("")
        self.preview_info.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self.preview_info)

        layout.addWidget(preview_group)

        # ---------------------------------------------------------
        # Importar / reemplazar textura
        # ---------------------------------------------------------
        import_group = QGroupBox("Importar textura")
        import_layout = QVBoxLayout(import_group)

        import_options = QHBoxLayout()

        self.import_flip_vertical_check = QCheckBox(
            "Voltear verticalmente"
        )
        self.import_flip_vertical_check.setChecked(False)

        self.import_ignore_alpha_check = QCheckBox(
            "Ignorar alpha (establecer alpha = 0)"
        )
        self.import_ignore_alpha_check.setChecked(False)

        import_options.addWidget(self.import_flip_vertical_check)
        import_options.addWidget(self.import_ignore_alpha_check)
        import_options.addStretch()

        import_layout.addLayout(import_options)

        import_buttons = QHBoxLayout()

        self.replace_texture_btn = QPushButton(
            "Reemplazar textura actual"
        )
        self.replace_texture_btn.clicked.connect(
            self.replace_preview_texture
        )

        self.add_texture_btn = QPushButton(
            "Añadir otra textura"
        )
        self.add_texture_btn.clicked.connect(
            self.add_texture
        )

        self.export_preview_btn = QPushButton(
            "Exportar textura actual"
        )
        self.export_preview_btn.clicked.connect(
            self.export_preview_texture
        )

        self.delete_texture_btn = QPushButton(
            "Eliminar textura actual"
        )
        self.delete_texture_btn.clicked.connect(
            self.delete_preview_texture
        )

        import_buttons.addWidget(self.replace_texture_btn)
        import_buttons.addWidget(self.add_texture_btn)
        import_buttons.addWidget(self.export_preview_btn)
        import_buttons.addWidget(self.delete_texture_btn)

        import_layout.addLayout(import_buttons)

        self.import_info_label = QLabel(
            "La textura PNG se convertirá usando los parámetros seleccionados."
        )
        self.import_info_label.setWordWrap(True)
        import_layout.addWidget(self.import_info_label)

        layout.addWidget(import_group)

        # ---------------------------------------------------------
        # Botón
        # ---------------------------------------------------------
        extract_btn = QPushButton("Extraer texturas")
        extract_btn.setMinimumHeight(40)
        extract_btn.clicked.connect(self.extract_textures)

        layout.addWidget(extract_btn)

    def update_format_options(self):
        current = self.format_combo.currentText()

        self.format_combo.blockSignals(True)
        self.format_combo.clear()

        bpp = int(self.bpp_combo.currentText().split()[0])

        if bpp == 8:
            self.format_combo.addItems([
                "L8 - Escala de grises",
            ])

        elif bpp == 16:
            self.format_combo.addItems([
                "RGB565",
                "RGBA5551",
                "RGBA4444",
            ])

        elif bpp == 24:
            self.format_combo.addItems([
                "RGB888",
            ])

        elif bpp == 32:
            self.format_combo.addItems([
                "RGBA8888",
            ])

        if current:
            index = self.format_combo.findText(current)
            if index >= 0:
                self.format_combo.setCurrentIndex(index)

        self.format_combo.blockSignals(False)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo PSP",
            "",
            "Archivos BIN (*.bin);;Todos los archivos (*.*)"
        )

        if not path:
            return

        self.open_texture_file(Path(path))

    def update_file_info(self):
        if not self.file_data:
            return

        width = self.width_edit.value()
        height = self.height_edit.value()
        count = self.texture_count.value()
        bpp = int(self.bpp_combo.currentText().split()[0])

        bytes_per_texture = width * height * bpp // 8
        expected_size = bytes_per_texture * count

        self.info_label.setText(
            f"Tamaño del archivo: {len(self.file_data):,} bytes\n"
            f"Tamaño esperado: {expected_size:,} bytes\n"
            f"Por textura: {bytes_per_texture:,} bytes\n"
            f"Diferencia: {len(self.file_data) - expected_size:+,} bytes"
        )

        self.update_total_texture_bytes()

        self.preview_texture.blockSignals(True)
        self.preview_texture.setRange(1, max(1, count))
        if self.preview_texture.value() > count:
            self.preview_texture.setValue(count)
        self.preview_texture.blockSignals(False)
        self.update_preview()

    def update_total_texture_bytes(self):
        """Calcula bytes por textura × cantidad de texturas."""
        bytes_per_texture = self.bytes_per_texture()
        count = self.texture_count.value()
        total = bytes_per_texture * count

        self.total_texture_bytes_label.setText(
            f"Total de bytes por textura: {total:,} bytes"
        )

        # Mostrar el total en rojo cuando supera el tamaño real del archivo.
        if self.file_data and total > len(self.file_data):
            self.total_texture_bytes_label.setStyleSheet("color: red;")
        else:
            self.total_texture_bytes_label.setStyleSheet("")

    def bytes_per_texture(self):
        width = self.width_edit.value()
        height = self.height_edit.value()
        bpp = int(self.bpp_combo.currentText().split()[0])
        return width * height * bpp // 8

    def decode_texture(self, raw):
        width = self.width_edit.value()
        height = self.height_edit.value()
        bpp = int(self.bpp_combo.currentText().split()[0])
        fmt = self.format_combo.currentText()

        if bpp == 8:
            # L8 -> RGB para guardar PNG fácilmente.
            img = Image.frombytes("L", (width, height), raw)
            return img.convert("RGBA")

        if bpp == 24:
            # RGB888.
            if self.order_combo.currentText() == "BGRA":
                raise ValueError("BGRA no es válido para 24 bpp.")

            if len(raw) != width * height * 3:
                raise ValueError("Cantidad de datos incorrecta para RGB888.")

            if self.order_combo.currentText() in ("BGR", "BGRA"):
                img = Image.frombytes("RGB", (width, height), raw, "raw", "BGR")
            else:
                img = Image.frombytes("RGB", (width, height), raw)

            return img.convert("RGBA")

        if bpp == 16:
            pixels = []

            for i in range(0, len(raw), 2):
                value = raw[i] | (raw[i + 1] << 8)

                if fmt == "RGB565":
                    r = ((value >> 11) & 0x1F) * 255 // 31
                    g = ((value >> 5) & 0x3F) * 255 // 63
                    b = (value & 0x1F) * 255 // 31
                    a = 255

                elif fmt == "RGBA5551":
                    r = ((value >> 11) & 0x1F) * 255 // 31
                    g = ((value >> 6) & 0x1F) * 255 // 31
                    b = ((value >> 1) & 0x1F) * 255 // 31
                    a = 255 if (value & 1) else 0

                elif fmt == "RGBA4444":
                    r = ((value >> 12) & 0xF) * 17
                    g = ((value >> 8) & 0xF) * 17
                    b = ((value >> 4) & 0xF) * 17
                    a = (value & 0xF) * 17

                else:
                    raise ValueError(f"Formato no soportado: {fmt}")

                pixels.append((r, g, b, a))

            img = Image.new("RGBA", (width, height))
            img.putdata(pixels)
            return img

        if bpp == 32:
            # El archivo proporcionado por el usuario encaja exactamente
            # con 3 * 480 * 272 * 4 bytes.
            #
            # Se realiza el intercambio de canales aquí para que sea fácil
            # adaptar el extractor si el juego usa otro orden.
            order = self.order_combo.currentText()

            img = Image.frombytes("RGBA", (width, height), raw)

            if order == "RGBA":
                return img

            channels = img.split()
            mapping = {
                "BGRA": (2, 1, 0, 3),
                "ARGB": (3, 0, 1, 2),
                "ABGR": (3, 2, 1, 0),
            }

            if order in mapping:
                img = Image.merge(
                    "RGBA",
                    tuple(channels[i] for i in mapping[order])
                )

            return img

        raise ValueError("BPP no soportado.")

    def unswizzle_32(self, raw):
        """
        Desenrollado PSP para textura 32 bpp.

        Esta función está separada para que puedas reemplazarla fácilmente
        si tu formato concreto usa otra variante de swizzle.
        """
        width = self.width_edit.value()
        height = self.height_edit.value()

        pixel_size = 4
        row_bytes = width * pixel_size

        out = bytearray(len(raw))

        # Algoritmo estándar de des-swish en bloques de 16x8 para 32 bpp.
        block_width = 16
        block_height = 8

        for y in range(height):
            for x in range(width):
                block_x = x // block_width
                block_y = y // block_height

                local_x = x % block_width
                local_y = y % block_height

                blocks_per_row = (width + block_width - 1) // block_width

                block_index = (
                    block_y * blocks_per_row + block_x
                )

                src_pixel = (
                    block_index * block_width * block_height
                    + local_y * block_width
                    + local_x
                )

                src = src_pixel * pixel_size
                dst = (y * width + x) * pixel_size

                if src + pixel_size <= len(raw):
                    out[dst:dst + pixel_size] = raw[src:src + pixel_size]

        return bytes(out)

    def update_preview_texture_range(self, count):
        """Actualiza el rango de navegación de la vista previa."""
        if not hasattr(self, "preview_texture"):
            return

        count = max(1, int(count))
        current = min(self.preview_texture.value(), count)

        self.preview_texture.blockSignals(True)
        self.preview_texture.setRange(1, count)
        self.preview_texture.setValue(current)
        self.preview_texture.blockSignals(False)

        if hasattr(self, "previous_texture_btn"):
            self.previous_texture_btn.setEnabled(current > 1)

        if hasattr(self, "next_texture_btn"):
            self.next_texture_btn.setEnabled(current < count)

        if self.file_data:
            self.update_preview()

    def previous_preview_texture(self):
        value = self.preview_texture.value()
        if value <= 1:
            return

        self.preview_texture.blockSignals(True)
        self.preview_texture.setValue(value - 1)
        self.preview_texture.blockSignals(False)
        self.update_preview()

    def next_preview_texture(self):
        value = self.preview_texture.value()
        maximum = self.preview_texture.maximum()

        if value >= maximum:
            return

        self.preview_texture.blockSignals(True)
        self.preview_texture.setValue(value + 1)
        self.preview_texture.blockSignals(False)
        self.update_preview()

    def update_preview(self):
        """Muestra la textura seleccionada usando la misma decodificación del extractor."""
        if not self.file_data:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Sin archivo cargado")
            self.preview_info.setText("")
            return

        try:
            texture_number = self.preview_texture.value()
            count = self.texture_count.value()

            bpt = self.bytes_per_texture()
            start = (texture_number - 1) * bpt
            end = start + bpt

            if end > len(self.file_data):
                raise ValueError("El archivo no contiene suficientes datos.")

            raw = self.file_data[start:end]

            if self.swizzle_check.isChecked():
                bpp = int(self.bpp_combo.currentText().split()[0])
                if bpp == 32:
                    raw = self.unswizzle_32(raw)
                else:
                    raise ValueError(
                        "El deswizzle de vista previa está implementado "
                        "actualmente para 32 bpp."
                    )

            image = self.decode_texture(raw)

            if self.flip_vertical_check.isChecked():
                image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

            if self.ignore_alpha_check.isChecked():
                image = image.convert("RGBA")
                alpha = Image.new("L", image.size, 255)
                image.putalpha(alpha)

            rgba = image.convert("RGBA")
            qimage = QImage(
                rgba.tobytes("raw", "RGBA"),
                rgba.width,
                rgba.height,
                rgba.width * 4,
                QImage.Format_RGBA8888
            ).copy()

            pixmap = QPixmap.fromImage(qimage)
            scaled = pixmap.scaled(
                self.preview_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            self.preview_label.setText("")
            self.preview_label.setPixmap(scaled)
            self.preview_info.setText(
                f"Textura {texture_number} / {count}    "
                f"{image.width} × {image.height}"
            )

            self.previous_texture_btn.setEnabled(texture_number > 1)
            self.next_texture_btn.setEnabled(texture_number < count)

        except Exception as e:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(f"Error: {e}")
            self.preview_info.setText("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "preview_label"):
            self.update_preview()

    def image_to_texture_bytes(self, image):
        """Convierte una imagen PIL a los bytes del formato seleccionado."""
        width = self.width_edit.value()
        height = self.height_edit.value()
        bpp = int(self.bpp_combo.currentText().split()[0])
        fmt = self.format_combo.currentText()
        order = self.order_combo.currentText()

        image = image.convert("RGBA").resize(
            (width, height),
            Image.Resampling.LANCZOS
        )

        pixels = list(image.get_flattened_data())

        if self.import_flip_vertical_check.isChecked():
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            pixels = list(image.get_flattened_data())

        if self.import_ignore_alpha_check.isChecked():
            pixels = [(r, g, b, 0) for r, g, b, a in pixels]

        output = bytearray()

        if bpp == 32:
            for r, g, b, a in pixels:
                channels = {
                    "RGBA": (r, g, b, a),
                    "BGRA": (b, g, r, a),
                    "ARGB": (a, r, g, b),
                    "ABGR": (a, b, g, r),
                }

                if order not in channels:
                    raise ValueError(f"Orden no soportado: {order}")

                output.extend(channels[order])

        elif bpp == 24:
            for r, g, b, a in pixels:
                if fmt == "RGB888":
                    output.extend((r, g, b))
                else:
                    output.extend((r, g, b))

        elif bpp == 16:
            for r, g, b, a in pixels:
                if self.import_ignore_alpha_check.isChecked():
                    a = 0

                if fmt == "RGB565":
                    value = (
                        ((r * 31 // 255) << 11)
                        | ((g * 63 // 255) << 5)
                        | (b * 31 // 255)
                    )

                elif fmt == "RGBA5551":
                    value = (
                        ((r * 31 // 255) << 11)
                        | ((g * 31 // 255) << 6)
                        | ((b * 31 // 255) << 1)
                        | (1 if a >= 128 else 0)
                    )

                elif fmt == "RGBA4444":
                    value = (
                        ((r * 15 // 255) << 12)
                        | ((g * 15 // 255) << 8)
                        | ((b * 15 // 255) << 4)
                        | (a * 15 // 255)
                    )
                else:
                    raise ValueError(f"Formato no soportado: {fmt}")

                output.extend((value & 0xFF, (value >> 8) & 0xFF))

        elif bpp == 8:
            for r, g, b, a in pixels:
                # Para L8 usamos luminancia.
                gray = (
                    299 * r + 587 * g + 114 * b
                ) // 1000
                output.append(gray)

        else:
            raise ValueError("BPP no soportado.")

        return bytes(output)

    def select_import_png(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar textura PNG",
            "",
            "Imágenes PNG (*.png);;Imágenes (*.png *.jpg *.jpeg *.bmp)"
        )
        return Path(path) if path else None

    def replace_preview_texture(self):
        """Reemplaza los bytes de la textura actualmente seleccionada."""
        if not self.file_data:
            QMessageBox.warning(
                self,
                "Archivo",
                "Primero abre un archivo de texturas."
            )
            return

        png_path = self.select_import_png()
        if not png_path:
            return

        try:
            image = Image.open(png_path)
            new_bytes = self.image_to_texture_bytes(image)

            bpt = self.bytes_per_texture()

            if len(new_bytes) != bpt:
                raise ValueError(
                    f"La textura convertida tiene {len(new_bytes):,} bytes, "
                    f"pero se esperaban {bpt:,} bytes."
                )

            texture_number = self.preview_texture.value()
            start = (texture_number - 1) * bpt
            end = start + bpt

            if end > len(self.file_data):
                raise ValueError(
                    "La textura seleccionada está fuera del tamaño actual."
                )

            data = bytearray(self.file_data)
            data[start:end] = new_bytes
            self.file_data = bytes(data)

            # Guardado automático sobre el mismo archivo.
            if self.file_path:
                self.file_path.write_bytes(self.file_data)

            self.update_file_info()
            self.update_preview()

            QMessageBox.information(
                self,
                "Textura reemplazada",
                f"Se reemplazó la textura {texture_number} y "
                "se guardaron automáticamente los cambios."
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error al importar",
                f"No se pudo importar la textura:\n\n{e}"
            )

    def add_texture(self):
        """Añade una nueva textura al final del archivo."""
        png_path = self.select_import_png()
        if not png_path:
            return

        try:
            image = Image.open(png_path)
            new_bytes = self.image_to_texture_bytes(image)

            bpt = self.bytes_per_texture()

            if len(new_bytes) != bpt:
                raise ValueError(
                    f"La textura convertida tiene {len(new_bytes):,} bytes, "
                    f"pero se esperaban {bpt:,} bytes."
                )

            self.file_data += new_bytes

            new_count = self.texture_count.value() + 1
            self.texture_count.blockSignals(True)
            self.texture_count.setValue(new_count)
            self.texture_count.blockSignals(False)

            self.update_preview_texture_range(new_count)
            self.preview_texture.blockSignals(True)
            self.preview_texture.setValue(new_count)
            self.preview_texture.blockSignals(False)

            if self.file_path:
                self.file_path.write_bytes(self.file_data)

            self.update_file_info()
            self.update_preview()

            QMessageBox.information(
                self,
                "Textura añadida",
                f"Se añadió la textura {new_count} y "
                "se guardaron automáticamente los cambios."
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error al añadir",
                f"No se pudo añadir la textura:\n\n{e}"
            )

    def delete_preview_texture(self):
        """Elimina del archivo la textura actualmente seleccionada."""
        if not self.file_data:
            QMessageBox.warning(
                self,
                "Archivo",
                "Primero abre un archivo de texturas."
            )
            return

        count = self.texture_count.value()

        if count <= 1:
            QMessageBox.warning(
                self,
                "Eliminar textura",
                "No se puede eliminar la última textura."
            )
            return

        texture_number = self.preview_texture.value()
        bpt = self.bytes_per_texture()

        start = (texture_number - 1) * bpt
        end = start + bpt

        if end > len(self.file_data):
            QMessageBox.warning(
                self,
                "Textura",
                "La textura seleccionada no existe en el archivo."
            )
            return

        result = QMessageBox.question(
            self,
            "Eliminar textura",
            f"¿Deseas eliminar la textura {texture_number}?\n\n"
            "Esta acción modificará el archivo y se guardará automáticamente.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if result != QMessageBox.Yes:
            return

        try:
            data = bytearray(self.file_data)
            del data[start:end]
            self.file_data = bytes(data)

            new_count = count - 1

            self.texture_count.blockSignals(True)
            self.texture_count.setValue(new_count)
            self.texture_count.blockSignals(False)

            # Si eliminamos la última textura, mostramos la anterior.
            new_preview = min(texture_number, new_count)

            self.update_preview_texture_range(new_count)

            self.preview_texture.blockSignals(True)
            self.preview_texture.setValue(new_preview)
            self.preview_texture.blockSignals(False)

            if self.file_path:
                self.file_path.write_bytes(self.file_data)

            self.update_file_info()
            self.update_preview()

            QMessageBox.information(
                self,
                "Textura eliminada",
                f"Se eliminó la textura {texture_number} y "
                "se guardaron automáticamente los cambios."
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error al eliminar",
                f"No se pudo eliminar la textura:\n\n{e}"
            )

    def export_preview_texture(self):
        """Exporta únicamente la textura mostrada en el preview."""
        if not self.file_data:
            QMessageBox.warning(
                self,
                "Archivo",
                "Primero abre un archivo de texturas."
            )
            return

        texture_number = self.preview_texture.value()
        bpt = self.bytes_per_texture()

        start = (texture_number - 1) * bpt
        end = start + bpt

        if end > len(self.file_data):
            QMessageBox.warning(
                self,
                "Textura",
                "La textura seleccionada no existe en el archivo."
            )
            return

        output, _ = QFileDialog.getSaveFileName(
            self,
            "Exportar textura",
            f"texture_{texture_number:03d}.png",
            "PNG (*.png)"
        )

        if not output:
            return

        try:
            raw = self.file_data[start:end]

            if self.swizzle_check.isChecked():
                bpp = int(self.bpp_combo.currentText().split()[0])
                if bpp == 32:
                    raw = self.unswizzle_32(raw)
                else:
                    raise ValueError(
                        "El deswizzle está implementado actualmente "
                        "para 32 bpp."
                    )

            image = self.decode_texture(raw)

            if self.flip_vertical_check.isChecked():
                image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

            if self.ignore_alpha_check.isChecked():
                image = image.convert("RGBA")
                image.putalpha(Image.new("L", image.size, 255))

            image.save(output, "PNG")

            QMessageBox.information(
                self,
                "Exportación",
                f"Textura {texture_number} exportada correctamente."
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error al exportar",
                f"No se pudo exportar la textura:\n\n{e}"
            )

    def extract_textures(self):
        if not self.file_data:
            QMessageBox.warning(
                self,
                "Archivo",
                "Primero selecciona un archivo."
            )
            return

        count = self.texture_count.value()
        expected = self.bytes_per_texture() * count

        if len(self.file_data) < expected:
            QMessageBox.critical(
                self,
                "Tamaño incorrecto",
                "El archivo es demasiado pequeño para la configuración indicada.\n\n"
                f"Archivo: {len(self.file_data):,} bytes\n"
                f"Necesario: {expected:,} bytes"
            )
            return

        if len(self.file_data) > expected:
            result = QMessageBox.question(
                self,
                "Datos adicionales",
                f"El archivo contiene {len(self.file_data) - expected:,} bytes "
                "adicionales.\n\n"
                "¿Continuar usando solamente los datos necesarios?"
            )

            if result != QMessageBox.Yes:
                return

        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Seleccionar carpeta de salida"
        )

        if not output_dir:
            return

        output_dir = Path(output_dir)

        bpt = self.bytes_per_texture()

        self.progress.setValue(0)

        try:
            for i in range(count):
                start = i * bpt
                end = start + bpt

                raw = self.file_data[start:end]

                if self.swizzle_check.isChecked():
                    bpp = int(self.bpp_combo.currentText().split()[0])

                    if bpp == 32:
                        raw = self.unswizzle_32(raw)
                    else:
                        raise ValueError(
                            "El desenrollado incluido actualmente está "
                            "implementado para 32 bpp."
                        )

                image = self.decode_texture(raw)

                if self.flip_vertical_check.isChecked():
                    image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

                if self.ignore_alpha_check.isChecked():
                    image = image.convert("RGBA")
                    alpha = Image.new("L", image.size, 255)
                    image.putalpha(alpha)

                output = output_dir / f"texture_{i:03d}.png"
                image.save(output, "PNG")

                self.progress.setValue(int((i + 1) * 100 / count))
                QApplication.processEvents()

            QMessageBox.information(
                self,
                "Extracción completada",
                f"Se extrajeron {count} textura(s).\n\n"
                f"Carpeta:\n{output_dir}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error al extraer",
                f"No se pudo extraer la textura:\n\n{e}"
            )
