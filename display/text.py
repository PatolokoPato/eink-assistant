"""Texto largo -> líneas ajustadas al ancho en píxeles -> páginas (Fase 3).

No dibuja pantallas completas: da las líneas ya cortadas para que cada vista
las coloque. Entiende un Markdown mínimo, porque los chatbots lo usan aunque
se les pida texto plano: **negrita** y `código` se limpian, "# Título" pasa a
línea en negrita y "- " / "* " / "1. " son elementos de lista.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from PIL import ImageFont

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont

_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
_BOLD_LINE_RE = re.compile(r"^\s*(?:\*\*|__)(.+?)(?:\*\*|__)\s*(:?)\s*$")  # "**Título:**" o "**Título**:"


@dataclass(frozen=True)
class Line:
    text: str
    bold: bool = False
    bullet: bool = False      # primera línea de un elemento de lista (lleva viñeta)
    indent: bool = False      # línea de lista (sangrada), sea o no la primera
    gap_before: bool = False  # separación extra: empieza un párrafo nuevo


def clean_markdown(text: str) -> str:
    """Quita **negrita**, __negrita__ y `código` dentro de una línea."""
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def _split_word(word: str, font: Font, max_w: float) -> list[str]:
    """Parte una palabra más ancha que la línea (URLs, rutas...)."""
    parts, cur = [], ""
    for ch in word:
        if cur and font.getlength(cur + ch) > max_w:
            parts.append(cur)
            cur = ""
        cur += ch
    return [*parts, cur] if cur else parts


def wrap(text: str, font: Font, max_w: float) -> list[str]:
    """Ajusta un párrafo (sin saltos de línea) a `max_w` píxeles."""
    lines: list[str] = []
    cur = ""
    for word in text.split():
        candidate = f"{cur} {word}" if cur else word
        if font.getlength(candidate) <= max_w:
            cur = candidate
            continue
        if cur:
            lines.append(cur)
        if font.getlength(word) <= max_w:
            cur = word
        else:
            *full, cur = _split_word(word, font, max_w)
            lines.extend(full)
    if cur:
        lines.append(cur)
    return lines


def layout(text: str, font: Font, bold_font: Font, width: float, indent_w: float) -> list[Line]:
    """Convierte el texto en líneas listas para dibujar."""
    out: list[Line] = []
    gap = False
    text = re.sub(r"```[a-zA-Z0-9]*\n?", "", text.replace("\r\n", "\n"))
    for raw in text.split("\n"):
        if not raw.strip():
            gap = bool(out)
            continue
        whole_bold = _BOLD_LINE_RE.match(raw)
        if whole_bold:
            parts = [(whole_bold.group(1) + whole_bold.group(2), bold_font, width, {"bold": True})]
        elif _HEADING_RE.match(raw):
            parts = [(_HEADING_RE.sub("", raw), bold_font, width, {"bold": True})]
        elif _BULLET_RE.match(raw):
            parts = [(_BULLET_RE.sub("", raw), font, width - indent_w, {"indent": True})]
        else:
            parts = [(raw, font, width, {})]
        for body, f, w, kind in parts:
            for i, ln in enumerate(wrap(clean_markdown(body), f, w)):
                first = i == 0
                out.append(Line(ln, bullet=first and kind.get("indent", False),
                                gap_before=gap and first, **kind))
        gap = False
    return out


def paginate(lines: list[Line], line_h: int, gap_h: int, first_h: int, other_h: int) -> list[list[Line]]:
    """Reparte las líneas en páginas; la primera puede tener otra altura útil.

    Un título (línea en negrita) nunca se queda solo al final de una página:
    pasa a la siguiente junto con su contenido.
    """
    pages: list[list[Line]] = [[]]
    used, avail = 0, first_h
    for ln in lines:
        extra = gap_h if ln.gap_before and pages[-1] else 0
        if pages[-1] and used + extra + line_h > avail:
            carry = [pages[-1].pop()] if pages[-1][-1].bold and len(pages[-1]) > 1 else []
            pages.append(carry)
            used, avail, extra = len(carry) * line_h, other_h, 0
        pages[-1].append(ln)
        used += extra + line_h
    return pages
