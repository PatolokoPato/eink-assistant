"""Carga de tipografías con alternativas (Windows / Linux / la de Pillow)."""

from __future__ import annotations

from functools import lru_cache

from PIL import ImageFont

_REGULAR = ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf")
_BOLD = ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf")


@lru_cache(maxsize=32)
def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _BOLD if bold else _REGULAR:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


@lru_cache(maxsize=32)
def load_display_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Tipografía de titulares (estética Y2K): Bahnschrift Bold si existe (Windows 10+)."""
    try:
        font = ImageFont.truetype("bahnschrift.ttf", size)
        font.set_variation_by_name("Bold")
        return font
    except OSError:
        return load_font(size, bold=True)
