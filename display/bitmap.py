"""Conversión entre imágenes Pillow y el bitmap nativo de la pantalla.

Formato del bitmap (el mismo que espera el firmware):
  - 400 x 300 píxeles, 1 bit por píxel.
  - Filas de arriba abajo, 50 bytes por fila.
  - Dentro de cada byte, el bit más significativo es el píxel de la izquierda.
  - 1 = NEGRO, 0 = BLANCO.
  - Tamaño total: 15000 bytes.
"""

from __future__ import annotations

from PIL import Image, ImageOps

WIDTH = 400
HEIGHT = 300
BYTES_PER_ROW = WIDTH // 8
BITMAP_SIZE = BYTES_PER_ROW * HEIGHT  # 15000

# En el modo "1" de Pillow un bit 1 es BLANCO; nuestro formato usa 1 = NEGRO.
_INVERT = bytes(255 - i for i in range(256))


def _flatten_on_white(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        bg.alpha_composite(rgba)
        return bg.convert("RGB")
    return img


def fit_to_screen(img: Image.Image) -> Image.Image:
    """Escala la imagen para que quepa en 400x300 manteniendo proporción,
    centrada sobre fondo blanco."""
    img = _flatten_on_white(img).convert("L")
    if img.size == (WIDTH, HEIGHT):
        return img
    contained = ImageOps.contain(img, (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    canvas = Image.new("L", (WIDTH, HEIGHT), 255)
    canvas.paste(contained, ((WIDTH - contained.width) // 2, (HEIGHT - contained.height) // 2))
    return canvas


def image_to_bitmap(img: Image.Image, *, dither: bool = True, fit: bool = False) -> bytes:
    """Convierte una imagen Pillow en un bitmap de 15000 bytes.

    dither: usa Floyd–Steinberg para simular grises (fotos). Para texto
            renderizado en blanco y negro puro no cambia nada.
    fit:    si la imagen no es 400x300, la escala; si es False, lanza error.
    """
    if img.size != (WIDTH, HEIGHT):
        if not fit:
            raise ValueError(f"La imagen debe ser {WIDTH}x{HEIGHT}, es {img.size[0]}x{img.size[1]}")
        img = fit_to_screen(img)

    if img.mode != "1":
        img = _flatten_on_white(img).convert("L").convert(
            "1", dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
        )

    raw = img.tobytes()
    assert len(raw) == BITMAP_SIZE
    return raw.translate(_INVERT)


def bitmap_to_image(data: bytes) -> Image.Image:
    """Inverso de image_to_bitmap: útil para previsualizar en el PC."""
    if len(data) != BITMAP_SIZE:
        raise ValueError(f"Un bitmap debe ocupar {BITMAP_SIZE} bytes, tiene {len(data)}")
    return Image.frombytes("1", (WIDTH, HEIGHT), bytes(data).translate(_INVERT))
