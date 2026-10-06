"""Vista de mes: cuadrícula lunes-domingo con el día de hoy resaltado.

`render_month` ocupa la pantalla entera; `draw_month_grid` dibuja solo la
cuadrícula dentro de un recuadro, para incluirla en otras pantallas.
"""

from __future__ import annotations

import calendar
import datetime as dt

from PIL import Image, ImageDraw

from .bitmap import HEIGHT, WIDTH
from .deco import sparkle
from .fonts import load_display_font, load_font

BLACK, WHITE = 0, 1

MONTHS = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
          "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")
WEEKDAYS = ("L", "M", "X", "J", "V", "S", "D")
WEEKDAY_NAMES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")

MARGIN = 4
HEADER_H = 40


def draw_month_grid(d: ImageDraw.ImageDraw, box: tuple[int, int, int, int], year: int, month: int,
                    today: dt.date, *, day_size: int = 18, head_size: int = 13) -> None:
    """Fila de iniciales L..D y cuadrícula de días dentro de box = (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    col_w = (x1 - x0) // 7
    grid_x = x0 + (x1 - x0 - 7 * col_w) // 2
    head_h = head_size + 7
    grid_y = y0 + head_h
    row_h = (y1 - grid_y) // len(weeks)

    head_font = load_font(head_size, bold=True)
    for c, name in enumerate(WEEKDAYS):
        d.text((grid_x + c * col_w + col_w // 2, y0 + head_h // 2), name,
               font=head_font, fill=BLACK, anchor="mm")

    grid_bottom = grid_y + len(weeks) * row_h
    for r in range(len(weeks) + 1):
        y = grid_y + r * row_h
        d.line([grid_x, y, grid_x + 7 * col_w, y], fill=BLACK)
    for c in range(8):
        x = grid_x + c * col_w
        d.line([x, grid_y, x, grid_bottom], fill=BLACK)

    day_font, weekend_font = load_font(day_size), load_font(day_size, bold=True)
    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            if not day:
                continue
            cx, cy = grid_x + c * col_w, grid_y + r * row_h
            is_today = dt.date(year, month, day) == today
            if is_today:
                d.rectangle([cx, cy, cx + col_w, cy + row_h], fill=BLACK)  # celda entera
            d.text((cx + col_w // 2, cy + row_h // 2), str(day),
                   font=weekend_font if c >= 5 or is_today else day_font,
                   fill=WHITE if is_today else BLACK, anchor="mm")


def render_month(year: int, month: int, today: dt.date | None = None) -> Image.Image:
    """Dibuja el mes. `today` se resalta si cae dentro de él (por defecto, la fecha actual)."""
    today = today or dt.date.today()
    img = Image.new("1", (WIDTH, HEIGHT), WHITE)
    d = ImageDraw.Draw(img)

    # Cabecera: "Octubre 2026" a la izquierda, "martes 6" a la derecha si es este mes.
    title = f"{MONTHS[month - 1]} {year}".upper()
    title_font = load_display_font(26)
    d.text((MARGIN + 6, HEADER_H // 2), title, font=title_font, fill=BLACK, anchor="lm")
    sparkle(d, MARGIN + 6 + d.textlength(title, font=title_font) + 14, HEADER_H // 2 - 2, 9)
    if (today.year, today.month) == (year, month):
        d.text((WIDTH - MARGIN - 6, HEADER_H // 2), f"{WEEKDAY_NAMES[today.weekday()]} {today.day}",
               font=load_font(16), fill=BLACK, anchor="rm")
    d.line([MARGIN, HEADER_H, WIDTH - MARGIN - 1, HEADER_H], fill=BLACK, width=2)

    draw_month_grid(d, (MARGIN, HEADER_H + 2, WIDTH - MARGIN, HEIGHT - MARGIN), year, month, today)
    return img
