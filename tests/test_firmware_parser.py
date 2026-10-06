"""Compila el parser del firmware (C++) y comprueba que entiende lo que manda Python."""

import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from device import protocol as p

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def parser_bin(tmp_path_factory):
    gxx = shutil.which("g++")
    if not gxx:
        pytest.skip("g++ no disponible")
    exe = tmp_path_factory.mktemp("fw") / "parser_test"
    subprocess.run([gxx, "-std=c++17", "-Wall", "-Werror", "-O2", "-o", str(exe),
                    str(HERE / "firmware_parser_test.cpp")], check=True)
    return exe


def test_cpp_parser_matches_python(parser_bin):
    rng = random.Random(42)
    bitmap = bytes(rng.randbytes(15000))
    page = p.Frame(p.MsgType.PAGE, 3, p.page_payload(1, 4, bitmap))
    bad = bytearray(p.encode(p.Frame(p.MsgType.PAGE, 4, p.page_payload(2, 4, bitmap))))
    bad[100] ^= 0x01
    too_long = p.SYNC + bytes([p.MsgType.PAGE, 5]) + (20000).to_bytes(2, "little")
    stream = (b"ets Jun  8 2016\r\n" + p.encode(p.Frame(p.MsgType.PING, 1)) + p.encode(page)
              + bytes(bad) + too_long + p.encode(p.Frame(p.MsgType.CLEAR, 6)))

    out = subprocess.run([str(parser_bin)], input=stream, capture_output=True, check=True).stdout.decode()
    lines = out.strip().splitlines()
    assert lines[:-1] == [
        "FRAME 1 1 0 ffff",
        f"FRAME 16 3 15005 {p.crc16_fast(page.payload):04x}",
        "BADCRC 4",
        "TOOLONG 5",
        "FRAME 17 6 0 ffff",
    ]
    encoded = bytes.fromhex(lines[-1].removeprefix("ENCODED "))
    assert p.FrameParser().feed(encoded) == [p.Frame(p.MsgType.ACK, 0x2A, b"\x2a\x00")]


def test_constants_match_protocol_h():
    src = (HERE.parent / "firmware" / "esp32_eink" / "protocol.h").read_text(encoding="utf-8")
    cpp = {name: int(val, 0) for name, val in
           re.findall(r"constexpr uint8_t (\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+);", src)}
    expected = {"VERSION": p.VERSION, "PF_PARTIAL": p.PAGE_FLAG_PARTIAL,
                "CAP_BUTTONS": p.CAP_BUTTONS, "CAP_PARTIAL": p.CAP_PARTIAL}
    expected |= {f"T_{m.name}": m.value for m in p.MsgType}
    expected |= {f"ST_{s.name}": s.value for s in p.Status}
    expected |= {f"BTN_{b.name}": b.value for b in p.Button}
    assert cpp == expected | {"SYNC0": 0xA5, "SYNC1": 0x5A}
