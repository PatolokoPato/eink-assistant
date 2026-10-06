"""Genera una imagen de prueba 400x300 pensada para verificar la pantalla.

Qué comprobar en la E-Ink:
  - El cuadrado negro debe quedar ARRIBA A LA IZQUIERDA (si no, la rotación o
    el orden de bits están mal; ver EINK_ROTATION en config.h).
  - El texto debe leerse de izquierda a derecha (si sale en espejo, el orden
    de bits dentro del byte está invertido).
  - El marco debe tocar los cuatro bordes sin cortarse (resolución correcta).
  - Las marcas de la regla superior van cada 50 px.

Uso:
    python -m tools.make_test_image                 # guarda out/test_400x300.png y .bin
    python -m tools.make_test_image --out prueba.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from display.bitmap import HEIGHT, WIDTH, image_to_bitmap
from display.fonts import load_font

BLACK, WHITE = 0, 1


def make_test_image(label: str = "Fase 1 · prueba 400×300") -> Image.Image:
    img = Image.new("1", (WIDTH, HEIGHT), WHITE)
    d = ImageDraw.Draw(img)

    # Marco exterior de 1 px exactamente en el borde + marco interior
    d.rectangle([0, 0, WIDTH - 1, HEIGHT - 1], outline=BLACK)
    d.rectangle([3, 3, WIDTH - 4, HEIGHT - 4], outline=BLACK)

    # Marcador asimétrico de orientación: arriba-izquierda
    d.rectangle([8, 8, 27, 27], fill=BLACK)
    d.text((33, 10), "ARRIBA-IZQ", font=load_font(12, bold=True), fill=BLACK)

    # Regla superior cada 10 px (larga cada 50)
    for x in range(50, WIDTH, 10):
        d.line([x, 3, x, 3 + (10 if x % 50 == 0 else 4)], fill=BLACK)

    # Título
    title_font, sub_font = load_font(30, bold=True), load_font(16)
    d.text((WIDTH // 2, 70), "E-Ink Assistant", font=title_font, fill=BLACK, anchor="mm")
    d.text((WIDTH // 2, 102), label, font=sub_font, fill=BLACK, anchor="mm")
    d.text((WIDTH // 2, 126), "Ñandú ¿qué tal? áéíóú ü ç €", font=sub_font, fill=BLACK, anchor="mm")

    # Ajedrez de 1 px (detalle fino) y de 4 px
    for y in range(150, 200):
        for x in range(16, 76):
            if (x + y) % 2 == 0:
                img.putpixel((x, y), BLACK)
    for y in range(150, 200):
        for x in range(84, 144):
            if ((x - 84) // 4 + (y - 150) // 4) % 2 == 0:
                img.putpixel((x, y), BLACK)
    small = load_font(11)
    d.text((16, 204), "1 px", font=small, fill=BLACK)
    d.text((84, 204), "4 px", font=small, fill=BLACK)

    # Círculo y diagonal
    d.ellipse([170, 145, 230, 205], outline=BLACK, width=3)
    d.line([250, 145, 310, 205], fill=BLACK, width=2)
    d.line([250, 205, 310, 145], fill=BLACK, width=1)

    # Degradado con tramado (simula grises)
    grad = Image.linear_gradient("L").rotate(90, expand=True).resize((360, 36))
    grad = grad.transpose(Image.Transpose.FLIP_LEFT_RIGHT)  # blanco -> negro
    img.paste(grad.convert("1", dither=Image.Dither.FLOYDSTEINBERG), (20, 228))
    d.rectangle([20, 228, 379, 263], outline=BLACK)

    # Abajo-derecha: indicador tipo página
    d.text((WIDTH - 12, HEIGHT - 12), "1 / 1", font=small, fill=BLACK, anchor="rd")
    d.text((12, HEIGHT - 12), "abajo-izq", font=small, fill=BLACK, anchor="ld")
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="out/test_400x300.png", help="ruta del PNG (el .bin va al lado)")
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img = make_test_image()
    img.save(out)
    out.with_suffix(".bin").write_bytes(image_to_bitmap(img))
    print(f"Guardado {out} y {out.with_suffix('.bin')} (15000 bytes)")


if __name__ == "__main__":
    main()
