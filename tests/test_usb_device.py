import threading

import pytest

from device import ButtonEvent, DeviceError, USBDisplayDevice
from device import protocol as p
from device.simulator import SimulatedESP32
from display.page import Page
from tools.make_test_image import make_test_image


@pytest.fixture
def sim():
    return SimulatedESP32()


@pytest.fixture
def dev(sim):
    d = USBDisplayDevice(transport=sim, connect_timeout=2, ack_timeout=2)
    d.connect()
    yield d
    d.close()


def test_connect_reads_hello_despite_boot_noise(dev):
    assert dev.info.width == 400 and dev.info.height == 300 and dev.info.has_buttons


def test_send_page_arrives_intact(dev, sim):
    page = Page.from_image(make_test_image(), number=2, total=5, partial=True)
    dev.send_page(page)
    number, total, flags, bitmap = sim.pages[-1]
    assert (number, total, flags) == (2, 5, p.PAGE_FLAG_PARTIAL)
    assert bitmap == page.bitmap


def test_retries_after_bad_crc(dev, sim):
    sim.corrupt_next_rx = 1
    dev.send_page(Page(bytes(15000)))
    assert len(sim.pages) == 1


def test_gives_up_after_retries(dev, sim):
    sim.corrupt_next_rx = 10
    with pytest.raises(DeviceError):
        dev.send_page(Page(bytes(15000)))


def test_button_handler_can_send_page(dev, sim):
    # El handler corre en su propio hilo, así que puede llamar a send_page.
    done = threading.Event()
    got = []

    def handler(ev):
        got.append(ev)
        dev.send_page(Page(bytes(15000), number=2, total=2))
        done.set()

    dev.on_button(handler)
    sim.press(p.Button.NEXT)
    assert done.wait(2)
    assert got == [ButtonEvent.NEXT] and sim.pages[-1][0] == 2


def test_no_device_fails_cleanly():
    class Dead:
        in_waiting = 0
        def read(self, n=1):
            import time; time.sleep(0.01); return b""
        def write(self, b): return len(b)
        def flush(self): pass
        def close(self): pass

    with pytest.raises(DeviceError, match="no responde"):
        USBDisplayDevice(transport=Dead(), connect_timeout=0.6).connect()


def test_autodetect_tries_every_port(monkeypatch):
    from device import usb

    monkeypatch.setattr(usb, "candidate_ports", lambda: ["COM_NO_EXISTE_1", "COM_NO_EXISTE_2"])
    with pytest.raises(DeviceError) as e:
        USBDisplayDevice(connect_timeout=0.2).connect()
    assert "COM_NO_EXISTE_1" in str(e.value) and "COM_NO_EXISTE_2" in str(e.value)

    monkeypatch.setattr(usb, "candidate_ports", lambda: [])
    with pytest.raises(DeviceError, match="ningún puerto"):
        USBDisplayDevice(connect_timeout=0.2).connect()
