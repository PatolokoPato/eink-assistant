import datetime as dt

import pytest

from display.bitmap import HEIGHT, WIDTH
from display.calendar import render_month
from display.page import Page


def _black_ratio(img, box):
    region = img.crop(box)
    return region.histogram()[0] / (region.width * region.height)


@pytest.mark.parametrize("year,month", [(2026, 2), (2026, 10), (2026, 11), (2027, 2)])
def test_renders_any_month_as_valid_page(year, month):
    img = render_month(year, month, dt.date(2026, 10, 6))
    assert img.size == (WIDTH, HEIGHT) and img.mode == "1"
    Page.from_image(img, dither=False)


def test_today_cell_is_filled_only_in_its_month():
    # Octubre 2026 empieza en jueves: el 6 (martes) está en la 2.ª fila, 2.ª columna.
    today = dt.date(2026, 10, 6)
    img = render_month(2026, 10, today)
    other = render_month(2026, 10, dt.date(2026, 11, 6))
    cell = (62, 110, 114, 152)  # interior de esa celda (columnas de 56 px, filas de 46)
    assert _black_ratio(img, cell) > 0.9
    assert _black_ratio(other, cell) < 0.1
