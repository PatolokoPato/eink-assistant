import datetime as dt

import pytest

from display.bitmap import HEIGHT, WIDTH
from display.home import render_home
from display.page import Page
from sources.system import SystemStatus
from sources.weather import Weather, describe, parse_forecast

NOW = dt.datetime(2026, 10, 6, 14, 5)
WEATHER = Weather("Madrid", 18.4, "Chubascos débiles", 79, 16.1, 19.6)
SYSTEM = SystemStatus(5.0, 47.2, 14.7, 31.1, 95.6, None, 43.0)


@pytest.mark.parametrize("weather,system", [(WEATHER, SYSTEM), (None, None), (WEATHER, None)])
def test_renders_with_or_without_data(weather, system):
    img = render_home(NOW, weather, system)
    assert img.size == (WIDTH, HEIGHT) and img.mode == "1"
    Page.from_image(img, dither=False)


def test_extreme_values_do_not_break_bars():
    s = SystemStatus(150.0, -3.0, 0, 0, 100.0, 99.9, None)
    render_home(NOW, WEATHER, s)


def test_parse_open_meteo_response():
    data = {
        "current": {"temperature_2m": 21.3, "weather_code": 2, "relative_humidity_2m": 55.4},
        "daily": {"temperature_2m_min": [12.0], "temperature_2m_max": [24.5]},
    }
    w = parse_forecast("Valencia", data)
    assert w == Weather("Valencia", 21.3, "Parcialmente nuboso", 55, 12.0, 24.5, code=2)
    assert describe(1234) == "—"
