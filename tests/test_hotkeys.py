import sys

import pytest

from ui.hotkeys import MOD_ALT, MOD_CONTROL, MOD_SHIFT, GlobalHotkeys, Hotkey
from ui.views import CYCLE, cycle_view


def test_cycle_view_wraps_and_skips_test():
    assert "test" not in CYCLE
    first, last = CYCLE[0], CYCLE[-1]
    assert cycle_view(last, 1) == first
    assert cycle_view(first, -1) == last
    assert cycle_view(first, 1) == CYCLE[1]
    # Desde una vista fuera del ciclo (la de prueba) se entra por un extremo.
    assert cycle_view("test", 1) == first
    assert cycle_view("test", -1) == last


@pytest.mark.skipif(sys.platform != "win32", reason="RegisterHotKey es de Windows")
def test_register_and_detect_taken_hotkey():
    # Una combinación rara para no chocar con nada real del usuario.
    hk = Hotkey("Ctrl+Alt+Mayús+F24", MOD_CONTROL | MOD_ALT | MOD_SHIFT, 0x87, lambda: None)
    a = GlobalHotkeys([hk])
    try:
        assert a.start() == []
        b = GlobalHotkeys([hk])
        assert b.start() == ["Ctrl+Alt+Mayús+F24"]  # ya la tiene `a`
        b.stop()
    finally:
        a.stop()
    c = GlobalHotkeys([hk])  # al parar `a` queda libre otra vez
    assert c.start() == []
    c.stop()
