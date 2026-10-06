"""Vista del asistente: la pregunta y la respuesta del chatbot, en páginas 400x300."""

from __future__ import annotations

from PIL import Image, ImageDraw

from . import deco
from .bitmap import HEIGHT, WIDTH
from .fonts import load_display_font, load_font
from .text import Line, layout, paginate, wrap

BLACK, WHITE = 0, 1

MARGIN = 12
HEADER_H = 34
BODY_SIZE = 16
LINE_H = 21
GAP_H = 8
BULLET_W = 16
QUESTION_SIZE = 13
QUESTION_LINES = 2


def _header(d: ImageDraw.ImageDraw, page: int, total: int) -> None:
    title = "ASISTENTE"
    font = load_display_font(15)
    w = d.textlength(title, font=font)
    deco.pill(d, [MARGIN - 4, 7, MARGIN + w + 30, 29])
    deco.sparkle(d, MARGIN + 8, 18, 6, fill=WHITE)
    d.text((MARGIN + 20, 18), title, font=font, fill=WHITE, anchor="lm")
    if total > 1:
        label = f"{page} / {total}"
        lf = load_font(13, bold=True)
        lw = d.textlength(label, font=lf)
        deco.pill(d, [WIDTH - MARGIN - lw - 16, 8, WIDTH - MARGIN + 2, 28], fill=None, outline=BLACK)
        d.text((WIDTH - MARGIN - 7, 18), label, font=lf, fill=BLACK, anchor="rm")


def _question_block(d: ImageDraw.ImageDraw, question: str, top: int) -> int:
    """Dibuja "Tú: ..." en 2 líneas como mucho; devuelve la y donde acaba."""
    bold, regular = load_font(QUESTION_SIZE, bold=True), load_font(QUESTION_SIZE)
    prefix = "Tú: "
    pw = d.textlength(prefix, font=bold)
    width = WIDTH - 2 * MARGIN
    lines = wrap(" ".join(question.split()), regular, width - pw)
    if len(lines) > QUESTION_LINES:
        lines = lines[:QUESTION_LINES]
        while lines[-1] and d.textlength(lines[-1] + "…", font=regular) > width - pw:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "…"
    d.text((MARGIN, top), prefix, font=bold, fill=BLACK, anchor="lt")
    for i, ln in enumerate(lines):
        d.text((MARGIN + pw, top + i * 17), ln, font=regular, fill=BLACK, anchor="lt")
    bottom = top + len(lines) * 17 + 4
    deco.divider(d, MARGIN, WIDTH - MARGIN, bottom + 3, star_at=0.92)
    return bottom + 12


def _body(d: ImageDraw.ImageDraw, lines: list[Line], top: int) -> None:
    font, bold = load_font(BODY_SIZE), load_font(BODY_SIZE, bold=True)
    y = top
    for i, ln in enumerate(lines):
        if ln.gap_before and i:
            y += GAP_H
        x = MARGIN + (BULLET_W if ln.indent else 0)
        if ln.bullet:
            deco.sparkle(d, MARGIN + 5, y + LINE_H / 2 - 1, 5)
        d.text((x, y), ln.text, font=bold if ln.bold else font, fill=BLACK, anchor="lt")
        y += LINE_H


def render_answer_pages(question: str, answer: str) -> list[Image.Image]:
    """La respuesta repartida en tantas páginas como haga falta."""
    font, bold = load_font(BODY_SIZE), load_font(BODY_SIZE, bold=True)
    lines = layout(answer, font, bold, WIDTH - 2 * MARGIN, BULLET_W)

    # Altura de la pregunta en la primera página: se mide dibujándola aparte.
    # Sin pregunta (texto enviado desde fuera), el cuerpo empieza bajo la cabecera.
    probe = ImageDraw.Draw(Image.new("1", (WIDTH, HEIGHT), WHITE))
    first_top = _question_block(probe, question, HEADER_H + 4) if question.strip() else HEADER_H + 8
    bottom = HEIGHT - 16  # deja sitio para la marca "sigue"
    pages = paginate(lines, LINE_H, GAP_H, bottom - first_top, bottom - (HEADER_H + 8))

    images = []
    for n, page_lines in enumerate(pages, start=1):
        img = Image.new("1", (WIDTH, HEIGHT), WHITE)
        d = ImageDraw.Draw(img)
        _header(d, n, len(pages))
        top = _question_block(d, question, HEADER_H + 4) if n == 1 and question.strip() else HEADER_H + 8
        _body(d, page_lines, top)
        if n < len(pages):
            # "sigue" + triángulo dibujado (la tipografía no tiene ▸)
            x1, y = WIDTH - MARGIN, HEIGHT - 9
            d.polygon([(x1 - 7, y - 5), (x1, y), (x1 - 7, y + 5)], fill=BLACK)
            d.text((x1 - 11, y), "sigue", font=load_font(12, bold=True), fill=BLACK, anchor="rm")
        images.append(img)
    return images


def render_welcome(provider: str = "Claude") -> Image.Image:
    """Pantalla de espera antes de la primera pregunta."""
    img = Image.new("1", (WIDTH, HEIGHT), WHITE)
    d = ImageDraw.Draw(img)
    _header(d, 1, 1)
    deco.planet(d, WIDTH // 2, 118, 26)
    deco.sparkle(d, WIDTH // 2 - 78, 92, 9)
    deco.sparkle(d, WIDTH // 2 + 84, 140, 6)
    deco.sparkle(d, WIDTH // 2 + 64, 78, 4)
    d.text((WIDTH // 2, 190), "¿En qué te ayudo?", font=load_display_font(26), fill=BLACK, anchor="mm")
    d.text((WIDTH // 2, 224), "Escribe tu pregunta en el PC", font=load_font(15), fill=BLACK, anchor="mm")
    d.text((WIDTH // 2, 246), f"Responde {provider}", font=load_font(13), fill=BLACK, anchor="mm")
    return img
