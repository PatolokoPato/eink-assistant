import datetime as dt
import time

import pytest

from device import USBDisplayDevice
from device.simulator import SimulatedESP32
from ui import controller as ctl
from ui.app_settings import AppSettings
from ui.views import VIEWS, get_view


def _wait_idle(c: ctl.DisplayController, timeout: float = 5.0) -> ctl.Status:
    deadline = time.monotonic() + timeout
    time.sleep(0.05)
    while time.monotonic() < deadline:
        st = c.status
        if st.busy is None and c._cmds.empty():
            return st
        time.sleep(0.02)
    raise AssertionError("el controlador no terminó")


@pytest.fixture
def sim_controller(monkeypatch):
    # La vista principal consulta internet y el PC: en los tests se sustituye.
    monkeypatch.setattr(ctl, "get_view", lambda vid: get_view("test" if vid == "home" else vid))
    sims = []

    def factory(port):
        sims.append(SimulatedESP32(boot_noise=False))
        return USBDisplayDevice(port, transport=sims[-1], connect_timeout=2, ack_timeout=2)

    c = ctl.DisplayController(None, factory=factory)
    c.start()
    yield c, sims
    c.stop()


def test_first_page_full_then_partial(sim_controller):
    c, sims = sim_controller
    c.show("calendar")
    _wait_idle(c)
    c.show("calendar")
    st = _wait_idle(c)
    assert st.connected and st.last_error is None and st.view_id == "calendar"
    flags = [page[2] for page in sims[0].pages]
    assert flags == [0, 1]  # completo y luego parcial
    c.show("calendar", full=True)
    _wait_idle(c)
    assert sims[0].pages[-1][2] == 0


def test_view_change_forces_full_refresh(sim_controller):
    # El parcial B/N deja la imagen anterior "fantasma" si cambia mucho.
    c, sims = sim_controller
    c.show("calendar")
    _wait_idle(c)
    c.show("test")
    _wait_idle(c)
    c.show("test")
    _wait_idle(c)
    assert [page[2] for page in sims[0].pages] == [0, 0, 1]


def test_invert_sends_inverted_bitmap_with_full_refresh(sim_controller):
    c, sims = sim_controller
    c.show("calendar")
    _wait_idle(c)
    c.set_invert(True)
    st = _wait_idle(c)
    assert st.invert
    normal, inverted = sims[0].pages[0][3], sims[0].pages[1][3]
    assert inverted == ctl.invert_bitmap(normal)
    assert sims[0].pages[1][2] == 0  # cambia todo: refresco completo


def test_repeated_shows_are_merged():
    # Varias pulsaciones de → durante un refresco: solo se dibuja la última vista.
    c = ctl.DisplayController(None, factory=lambda port: None)
    c.show("calendar")
    c.show("assistant")
    c.show(None, full=True)  # p. ej. "Refresco completo": no cambia la vista pedida
    c.clear()
    first = c._cmds.get_nowait()
    assert c._latest_show(first) == ("show", "assistant", True)
    assert c._deferred == ("clear",)  # lo que venía detrás se conserva


def test_changed_fraction():
    assert ctl.changed_fraction(bytes(4), bytes(4)) == 0
    assert ctl.changed_fraction(bytes(4), b"\xff\x00\x00\x01") == 9 / 32


def test_clear(sim_controller):
    c, sims = sim_controller
    c.clear()
    _wait_idle(c)
    assert sims[0].clears == 1


def test_connection_error_is_reported_and_retried():
    attempts = []

    def factory(port):
        attempts.append(port)
        if len(attempts) == 1:
            return USBDisplayDevice("COM_INEXISTENTE_99", connect_timeout=0.2)
        return USBDisplayDevice(port, transport=SimulatedESP32(boot_noise=False), connect_timeout=2)

    c = ctl.DisplayController(None, factory=factory)
    c.start()
    try:
        c.show("calendar")
        st = _wait_idle(c)
        assert not st.connected and st.last_error
        c.show("calendar")
        st = _wait_idle(c)
        assert st.connected and st.last_error is None
    finally:
        c.stop()


def test_seconds_to_next_aligns_to_interval():
    now = dt.datetime(2026, 10, 6, 14, 7, 30)
    assert ctl.seconds_to_next(5, now) == 150      # 14:10
    assert ctl.seconds_to_next(60, now) == 52 * 60 + 30  # 15:00


def test_views_build_valid_images():
    for v in VIEWS:
        if v.id == "home":
            continue  # necesita red; se prueba en test_home.py
        img = v.build()
        assert img.size == (400, 300)
    assert get_view("no-existe").id == VIEWS[0].id


def test_settings_roundtrip(tmp_path):
    path = tmp_path / "s.json"
    AppSettings(port="COM3", view_id="calendar", auto=False, interval_min=10).save(path)
    s = AppSettings.load(path)
    assert (s.port, s.view_id, s.auto, s.interval_min) == ("COM3", "calendar", False, 10)
    path.write_text("{roto", encoding="utf-8")
    assert AppSettings.load(path) == AppSettings()
