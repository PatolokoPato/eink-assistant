import socket
import threading

import pytest

from device import DeviceError, WiFiDisplayDevice
from device.simulator import SimulatedESP32
from device.wifi import DEFAULT_TCP_PORT, parse_wifi_target
from display.page import Page
from tools.make_test_image import make_test_image


@pytest.fixture
def tcp_sim():
    """Un servidor TCP local que se comporta como el firmware con Wi-Fi."""
    sim = SimulatedESP32()
    srv = socket.create_server(("127.0.0.1", 0))
    stop = threading.Event()

    def serve():
        conn, _ = srv.accept()
        conn.settimeout(0.05)

        def pump_out():
            while not stop.is_set():
                data = sim.read(4096)
                if data:
                    conn.sendall(data)

        threading.Thread(target=pump_out, daemon=True).start()
        while not stop.is_set():
            try:
                data = conn.recv(4096)
            except TimeoutError:
                continue
            except OSError:
                break
            if not data:
                break
            sim.write(data)
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    yield sim, srv.getsockname()[1]
    stop.set()
    sim.close()
    srv.close()


def test_page_over_tcp(tcp_sim):
    sim, port = tcp_sim
    dev = WiFiDisplayDevice("127.0.0.1", port, connect_timeout=2, ack_timeout=2)
    info = dev.connect()
    try:
        assert info.transport == "wifi:127.0.0.1" and info.width == 400
        page = Page.from_image(make_test_image())
        dev.send_page(page)
        assert sim.last_bitmap == page.bitmap
    finally:
        dev.close()


def test_unreachable_host_raises():
    srv = socket.create_server(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.close()  # puerto libre: nadie escucha
    with pytest.raises(DeviceError, match="Wi-Fi"):
        WiFiDisplayDevice("127.0.0.1", port, connect_timeout=1).connect()


def test_parse_mdns_answer():
    from device.wifi import _parse_a_record

    # Respuesta como la de la placa a "eink.local" (A, 192.168.1.50).
    name = b"\x04eink\x05local\x00"
    answer = (bytes.fromhex("000084000000000100000000") + name
              + bytes.fromhex("00018001" "00000078" "0004") + bytes([192, 168, 1, 50]))
    assert _parse_a_record(answer) == "192.168.1.50"
    query = bytes.fromhex("000000000001000000000000") + name + bytes.fromhex("00018001")
    assert _parse_a_record(query) is None


def test_parse_wifi_target():
    assert parse_wifi_target("wifi:eink.local") == ("eink.local", DEFAULT_TCP_PORT)
    assert parse_wifi_target("wifi:192.168.1.50:4000") == ("192.168.1.50", 4000)
    assert parse_wifi_target("wifi:") == ("eink.local", DEFAULT_TCP_PORT)
