"""Pantalla principal 400x300: hora, fecha, tiempo, estado del PC y calendario del mes.

Solo dibuja: los datos llegan ya obtenidos (ver sources/). Cualquiera de ellos
puede faltar (None) y la pantalla lo indica sin romperse. Estética Y2K sobria:
tipografía ancha, píldoras y algunas estrellas (display/deco.py).
"""

from __future__ import annotations

import datetime as dt

from PIL import Image, ImageDraw

from sources.system import SystemStatus
from sources.weather import Weather

from . import deco
from .bitmap import HEIGHT, WIDTH
from .calendar import MONTHS, WEEKDAY_NAMES, draw_month_grid
from .fonts import load_display_font, load_font

BLACK, WHITE = 0, 1

LEFT_X0, LEFT_X1 = 8, 212   # columna izquierda: hora, tiempo, PC
SPLIT_X = 220               # línea vertical
RIGHT_X0, RIGHT_X1 = 226, WIDTH - 4  # columna derecha: calendario


def _fmt_temp(t: float | None) -> str:
    return "--" if t is None else f"{t:.0f}°"


def _fit_font(d: ImageDraw.ImageDraw, text: str, max_w: float, size: int, bold: bool = True):
    while size > 10 and d.textlength(text, font=load_font(size, bold=bold)) > max_w:
        size -= 1
    return load_font(size, bold=bold)


def _bar_row(d: ImageDraw.ImageDraw, y: int, label: str, percent: float) -> None:
    font = load_font(13)
    d.text((LEFT_X0, y), label, font=font, fill=BLACK, anchor="lm")
    bx0, bx1 = LEFT_X0 + 44, LEFT_X1 - 42
    deco.pill(d, [bx0, y - 5, bx1, y + 5], fill=None, outline=BLACK)
    fill_w = (bx1 - bx0 - 4) * max(0.0, min(percent, 100.0)) / 100
    if fill_w >= 6:  # por debajo no se distingue una píldora
        deco.pill(d, [bx0 + 2, y - 3, bx0 + 2 + fill_w, y + 3])
    d.text((LEFT_X1, y), f"{percent:.0f} %", font=font, fill=BLACK, anchor="rm")


def _draw_clock(d: ImageDraw.ImageDraw, now: dt.datetime) -> None:
    clock = now.strftime("%H:%M")
    font = load_display_font(64)
    d.text((LEFT_X0 - 2, 2), clock, font=font, fill=BLACK, anchor="lt")
    # Un par de estrellas junto a la hora
    x = LEFT_X0 + d.textlength(clock, font=font) + 4
    deco.sparkle(d, x + 10, 16, 10)
    deco.sparkle(d, x + 4, 36, 5)
    date = f"{WEEKDAY_NAMES[now.weekday()].capitalize()}, {now.day} de {MONTHS[now.month - 1].lower()}"
    d.text((LEFT_X0, 84), date, font=load_font(16), fill=BLACK, anchor="lm")
    deco.divider(d, LEFT_X0, LEFT_X1, 102, star_at=0.82)


def _draw_weather(d: ImageDraw.ImageDraw, w: Weather | None) -> None:
    top = 110
    if w is None:
        deco.globe(d, LEFT_X0 + 14, top + 22, 13)
        d.text((LEFT_X0 + 36, top + 16), "Tiempo: sin datos", font=load_font(14), fill=BLACK, anchor="lm")
        d.text((LEFT_X0 + 36, top + 34), "(sin conexión)", font=load_font(12), fill=BLACK, anchor="lm")
    else:
        # Fila 1: icono, temperatura grande y, a la derecha, lugar y humedad
        deco.weather_icon(d, w.code, LEFT_X0 + 16, top + 20, 15)
        d.text((LEFT_X0 + 38, top + 20), f"{w.temperature:.0f}°", font=load_display_font(42),
               fill=BLACK, anchor="lm")
        small = load_font(13)
        place_w = d.textlength(w.place, font=small)
        d.text((LEFT_X1, top + 10), w.place, font=small, fill=BLACK, anchor="rm")
        deco.globe(d, LEFT_X1 - place_w - 10, top + 10, 6)
        d.text((LEFT_X1, top + 30), f"Hum. {w.humidity} %", font=small, fill=BLACK, anchor="rm")
        # Fila 2: descripción y mínima/máxima
        minmax = f"{w.temp_min:.0f}° / {w.temp_max:.0f}°"
        d.text((LEFT_X1, top + 52), minmax, font=small, fill=BLACK, anchor="rm")
        max_desc = LEFT_X1 - d.textlength(minmax, font=small) - 8 - LEFT_X0
        d.text((LEFT_X0, top + 52), w.description, font=_fit_font(d, w.description, max_desc, 14),
               fill=BLACK, anchor="lm")
    deco.divider(d, LEFT_X0, LEFT_X1, 176, star_at=0.18)


def _draw_system(d: ImageDraw.ImageDraw, s: SystemStatus | None) -> None:
    top = 190
    if s is None:
        d.text((LEFT_X0, top), "PC: sin datos", font=load_font(14), fill=BLACK, anchor="lm")
    else:
        _bar_row(d, top, "CPU", s.cpu_percent)
        _bar_row(d, top + 20, "RAM", s.ram_percent)
        d.text((LEFT_X0, top + 42), f"Temp. CPU {_fmt_temp(s.cpu_temp)}   GPU {_fmt_temp(s.gpu_temp)}",
               font=load_font(13), fill=BLACK, anchor="lm")
    # Rincón inferior: un planeta pequeño y una estrella, sin más
    deco.planet(d, LEFT_X1 - 20, HEIGHT - 20, 9)
    deco.sparkle(d, LEFT_X1 - 52, HEIGHT - 13, 6)


def _draw_calendar(d: ImageDraw.ImageDraw, today: dt.date) -> None:
    title = f"{MONTHS[today.month - 1]} {today.year}".upper()
    font = load_display_font(15)
    cx = (RIGHT_X0 + RIGHT_X1) // 2
    half = d.textlength(title, font=font) / 2 + 12
    deco.pill(d, [cx - half, 6, cx + half, 26])
    d.text((cx, 16), title, font=font, fill=WHITE, anchor="mm")
    draw_month_grid(d, (RIGHT_X0, 32, RIGHT_X1, HEIGHT - 6), today.year, today.month, today,
                    day_size=14, head_size=11)


def render_home(now: dt.datetime, weather: Weather | None, system: SystemStatus | None) -> Image.Image:
    img = Image.new("1", (WIDTH, HEIGHT), WHITE)
    d = ImageDraw.Draw(img)
    _draw_clock(d, now)
    _draw_weather(d, weather)
    _draw_system(d, system)
    d.line([SPLIT_X, 6, SPLIT_X, HEIGHT - 6], fill=BLACK)
    _draw_calendar(d, now.date())
    return img
