"""Página lista para enviar a cualquier DisplayDevice."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from .bitmap import BITMAP_SIZE, bitmap_to_image, image_to_bitmap


@dataclass(frozen=True)
class Page:
    bitmap: bytes          # 15000 bytes, ver display/bitmap.py
    number: int = 1        # 1-based
    total: int = 1
    partial: bool = False  # pedir refresco parcial (más rápido, algo de "ghosting")

    def __post_init__(self) -> None:
        if len(self.bitmap) != BITMAP_SIZE:
            raise ValueError(f"bitmap debe tener {BITMAP_SIZE} bytes, tiene {len(self.bitmap)}")
        if not (1 <= self.number <= 0xFFFF and 1 <= self.total <= 0xFFFF):
            raise ValueError("number/total fuera de rango (1..65535)")

    @classmethod
    def from_image(cls, img: Image.Image, number: int = 1, total: int = 1, *,
                   partial: bool = False, dither: bool = True, fit: bool = True) -> "Page":
        return cls(image_to_bitmap(img, dither=dither, fit=fit), number, total, partial)

    def to_image(self) -> Image.Image:
        return bitmap_to_image(self.bitmap)
