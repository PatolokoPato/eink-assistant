"""Todo lo relacionado con producir páginas 400x300. No sabe nada del ESP32."""

from .bitmap import BITMAP_SIZE, HEIGHT, WIDTH, bitmap_to_image, image_to_bitmap
from .page import Page

__all__ = ["BITMAP_SIZE", "HEIGHT", "WIDTH", "Page", "bitmap_to_image", "image_to_bitmap"]
