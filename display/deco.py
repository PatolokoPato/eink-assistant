"""Adornos de estética Y2K dibujados con primitivas (sin imágenes externas).

Estrellas de cuatro puntas, soles de rayos, planetas con anillo, globos de
malla y píldoras. Todos en negro sobre blanco, pensados para 1 bit.
"""

from __future__ import annotations

import math

from PIL import ImageDraw

BLACK, WHITE = 0, 1


def sparkle(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, *, fill: int = BLACK,
            sharpness: float = 2.6) -> None:
    """Estrella de cuatro puntas con lados cóncavos (✦): una astroide.

    sharpness = 3 es la astroide clásica (puntas finas); valores menores la engordan.
    """
    pts = []
    for i in range(64):
        t = i * 2 * math.pi / 64
        c, s = math.cos(t), math.sin(t)
        pts.append((cx + r * math.copysign(abs(c) ** sharpness, c),
                    cy + r * math.copysign(abs(s) ** sharpness, s)))
    d.polygon(pts, fill=fill)


def starburst(d: ImageDraw.ImageDraw, cx: float, cy: float, r_in: float, r_out: float,
              rays: int = 12, *, fill: int = BLACK) -> None:
    """Sol de rayos triangulares alrededor de un disco."""
    pts = []
    for i in range(rays * 2):
        a = i * math.pi / rays - math.pi / 2
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=fill)


def pill(d: ImageDraw.ImageDraw, box: tuple[float, float, float, float], *, fill: int | None = BLACK,
         outline: int | None = None, width: int = 1) -> None:
    """Rectángulo con los extremos completamente redondeados."""
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=min(x1 - x0, y1 - y0) / 2, fill=fill, outline=outline, width=width)


def planet(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float) -> None:
    """Planeta con anillo inclinado: el anillo pasa por delante en la mitad inferior."""
    ring = [cx - r * 1.9, cy - r * 0.55, cx + r * 1.9, cy + r * 0.55]
    d.ellipse(ring, outline=BLACK, width=max(1, round(r / 5)))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BLACK)
    # Hueco blanco del anillo sobre el disco (parte delantera)
    d.arc([ring[0] + 2, ring[1] + 2, ring[2] - 2, ring[3] - 2], 20, 160, fill=WHITE, width=2)
    d.arc(ring, 10, 170, fill=BLACK, width=max(1, round(r / 5)))


def globe(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float) -> None:
    """Globo de malla: contorno, meridianos y paralelos."""
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=BLACK)
    for k in (0.45, 0.9):
        d.ellipse([cx - r * k * 0.55, cy - r, cx + r * k * 0.55, cy + r], outline=BLACK)
    d.line([cx, cy - r, cx, cy + r], fill=BLACK)
    for f in (-0.5, 0, 0.5):
        y = cy + f * r
        half = r * math.sqrt(1 - f * f)
        d.line([cx - half, y, cx + half, y], fill=BLACK)


def divider(d: ImageDraw.ImageDraw, x0: float, x1: float, y: float, *, star_at: float = 0.5) -> None:
    """Línea horizontal con una pequeña estrella intercalada."""
    sx = x0 + (x1 - x0) * star_at
    d.line([x0, y, sx - 9, y], fill=BLACK)
    d.line([sx + 9, y, x1, y], fill=BLACK)
    sparkle(d, sx, y, 6)


# --- Iconos del tiempo --------------------------------------------------------

def _cloud(d: ImageDraw.ImageDraw, cx: float, cy: float, s: float) -> None:
    pill(d, [cx - s, cy, cx + s, cy + s * 0.75])
    d.ellipse([cx - s * 0.55, cy - s * 0.55, cx + s * 0.25, cy + s * 0.35], fill=BLACK)
    d.ellipse([cx - s * 0.05, cy - s * 0.35, cx + s * 0.7, cy + s * 0.4], fill=BLACK)


def weather_icon(d: ImageDraw.ImageDraw, code: int, cx: float, cy: float, s: float = 16) -> None:
    """Icono para un código WMO de Open-Meteo, centrado en (cx, cy), radio aproximado `s`."""
    if code in (0, 1):                               # despejado: sol de rayos
        starburst(d, cx, cy, s * 0.62, s, rays=12)
        d.ellipse([cx - s * 0.4, cy - s * 0.4, cx + s * 0.4, cy + s * 0.4], fill=WHITE)
        d.ellipse([cx - s * 0.28, cy - s * 0.28, cx + s * 0.28, cy + s * 0.28], fill=BLACK)
    elif code == 2:                                  # parcialmente nuboso: sol detrás de nube
        starburst(d, cx + s * 0.35, cy - s * 0.3, s * 0.4, s * 0.65, rays=10)
        _cloud(d, cx - s * 0.15, cy, s * 0.75)
    elif code in (45, 48):                           # niebla: píldoras horizontales
        for i, w in enumerate((1.0, 0.75, 0.9)):
            y = cy - s * 0.6 + i * s * 0.55
            pill(d, [cx - s * w, y, cx + s * w, y + s * 0.28])
    elif code in (71, 73, 75, 77, 85, 86):           # nieve: estrellas
        sparkle(d, cx, cy, s * 0.9)
        for dx, dy in ((-0.7, -0.7), (0.75, 0.6)):
            sparkle(d, cx + dx * s, cy + dy * s, s * 0.3)
    elif code >= 95:                                 # tormenta: nube + rayo
        _cloud(d, cx, cy - s * 0.35, s * 0.8)
        d.polygon([(cx + 2, cy + s * 0.2), (cx - s * 0.35, cy + s * 0.75), (cx - 1, cy + s * 0.7),
                   (cx - s * 0.2, cy + s * 1.15), (cx + s * 0.4, cy + s * 0.5), (cx + 2, cy + s * 0.55)],
                  fill=BLACK)
    elif code >= 51:                                 # llovizna / lluvia / chubascos
        _cloud(d, cx, cy - s * 0.35, s * 0.8)
        for dx in (-0.45, 0, 0.45):
            x = cx + dx * s
            d.line([x, cy + s * 0.45, x - s * 0.18, cy + s * 0.95], fill=BLACK, width=2)
    else:                                            # nublado
        _cloud(d, cx, cy - s * 0.2, s)
