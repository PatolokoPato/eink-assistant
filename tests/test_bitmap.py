import pytest
from PIL import Image

from display.bitmap import BITMAP_SIZE, HEIGHT, WIDTH, bitmap_to_image, image_to_bitmap
from display.page import Page


def test_white_image_is_all_zero():
    assert image_to_bitmap(Image.new("L", (WIDTH, HEIGHT), 255)) == bytes(BITMAP_SIZE)


def test_bit_order_top_left_black_is_msb_of_first_byte():
    img = Image.new("1", (WIDTH, HEIGHT), 1)
    img.putpixel((0, 0), 0)
    img.putpixel((WIDTH - 1, 1), 0)  # último píxel de la segunda fila
    bm = image_to_bitmap(img)
    assert bm[0] == 0x80
    assert bm[2 * (WIDTH // 8) - 1] == 0x01
    assert sum(bin(b).count("1") for b in bm) == 2


def test_roundtrip():
    img = Image.effect_noise((WIDTH, HEIGHT), 64).convert("1")
    assert bitmap_to_image(image_to_bitmap(img)).tobytes() == img.tobytes()


def test_wrong_size_requires_fit():
    big = Image.new("RGB", (800, 300), "black")
    with pytest.raises(ValueError):
        image_to_bitmap(big)
    bm = image_to_bitmap(big, fit=True)
    out = bitmap_to_image(bm)
    # 800x300 -> 400x150 centrado: franja superior blanca, centro negro
    assert out.getpixel((200, 10)) == 255 and out.getpixel((200, 150)) == 0


def test_transparent_png_goes_on_white():
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    assert image_to_bitmap(img) == bytes(BITMAP_SIZE)


def test_page_validates_size():
    with pytest.raises(ValueError):
        Page(b"\x00" * 10)
