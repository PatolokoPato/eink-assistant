import random

from device import protocol as p


def test_crc_reference_vector():
    # CRC-16/CCITT-FALSE de "123456789" = 0x29B1
    assert p.crc16(b"123456789") == 0x29B1
    assert p.crc16_fast(b"123456789") == 0x29B1


def test_encode_layout():
    raw = p.encode(p.Frame(p.MsgType.PING, 7))
    assert raw[:6] == bytes([0xA5, 0x5A, 0x01, 7, 0, 0]) and len(raw) == 8


def test_parse_with_noise_and_arbitrary_chunks():
    frames = [p.Frame(p.MsgType.PAGE, i, bytes(random.randbytes(15005))) for i in range(3)]
    stream = b"rst:0x1 boot noise \xa5 \xa5\x5a\x00" + b"".join(p.encode(f) for f in frames)
    parser = p.FrameParser()
    out = []
    i = 0
    rng = random.Random(1)
    while i < len(stream):
        n = rng.randint(1, 700)
        out += parser.feed(stream[i : i + n])
        i += n
    assert out == frames


def test_corrupted_frame_is_skipped_and_next_one_recovered():
    good = p.Frame(p.MsgType.ACK, 1, b"\x01\x00")
    bad = bytearray(p.encode(p.Frame(p.MsgType.ACK, 2, b"\x02\x00")))
    bad[7] ^= 0xFF
    parser = p.FrameParser()
    assert parser.feed(bytes(bad) + p.encode(good)) == [good]
    assert parser.crc_errors == 1


def test_hello_roundtrip():
    h = p.Hello(1, 400, 300, p.CAP_BUTTONS)
    assert p.Hello.parse(h.pack()) == h and h.has_buttons and not h.has_partial
