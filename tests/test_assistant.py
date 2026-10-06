from types import SimpleNamespace

import pytest

from ai import ChatbotError, ChatbotProvider, ClaudeProvider
from display.assistant import render_answer_pages, render_welcome
from display.fonts import load_font
from display.text import Line, layout, paginate, wrap
from ui.assistant import Assistant

FONT, BOLD = load_font(16), load_font(16, bold=True)


def test_wrap_respects_width_and_splits_long_words():
    lines = wrap("hola " * 40 + "https://" + "x" * 200, FONT, 300)
    assert all(FONT.getlength(ln) <= 300 for ln in lines)
    assert "".join(lines).endswith("x" * 10)


def test_layout_understands_basic_markdown():
    text = "Intro con **negrita** y `código`.\n\n**Título:**\n- uno\n* dos\n1. tres\n# Encabezado\nfin"
    lines = layout(text, FONT, BOLD, 376, 16)
    assert lines[0] == Line("Intro con negrita y código.")
    assert lines[1] == Line("Título:", bold=True, gap_before=True)
    assert [ln.text for ln in lines if ln.bullet] == ["uno", "dos", "tres"]
    assert Line("Encabezado", bold=True) in lines


def test_paginate_never_leaves_a_heading_alone_at_the_bottom():
    lines = [Line(f"l{i}") for i in range(3)] + [Line("Título", bold=True)] + [Line("x")] * 3
    pages = paginate(lines, line_h=10, gap_h=0, first_h=40, other_h=100)
    assert pages[0][-1].text == "l2"
    assert pages[1][0].text == "Título"


def test_answer_pages_are_valid_images():
    pages = render_answer_pages("¿Pregunta?", "Respuesta muy larga. " * 200)
    assert len(pages) > 1
    assert all(p.size == (400, 300) and p.mode == "1" for p in pages)
    assert render_welcome().size == (400, 300)


class FakeProvider(ChatbotProvider):
    name = "Falso"

    def __init__(self):
        self.asked = []

    def ask(self, question):
        self.asked.append(question)
        return "respuesta " * 300

    def reset(self):
        self.asked.clear()


def test_assistant_state_and_paging():
    a = Assistant(FakeProvider())
    welcome = a.build()
    a.ask("hola")
    assert a.page_count > 1 and a.page == 0
    assert a.go(-1) is False
    assert a.go(1) is True and a.page == 1
    assert a.build().tobytes() != welcome.tobytes()
    a.reset()
    assert a.page_count == 1 and a.history == []


class FakeStream:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.response


def _response(text, stop="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
        stop_reason=stop, stop_details=None, model="claude-opus-5-5",
        usage=SimpleNamespace(output_tokens=5),
    )


def _fake_client(responses, calls):
    def stream(**kwargs):
        calls.append(kwargs)
        return FakeStream(responses.pop(0))

    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))


def test_claude_provider_keeps_append_only_history():
    calls = []
    p = ClaudeProvider(client=_fake_client([_response("uno"), _response("dos")], calls))
    assert p.ask("primera") == "uno"
    assert p.ask("segunda") == "dos"
    second = calls[1]
    assert second["model"] == "claude-opus-5-5" and second["fallbacks"] == "default"
    roles = [m["role"] for m in second["messages"]]
    assert roles == ["user", "assistant", "user"]
    # El turno del asistente se reenvía completo (incluido el bloque de thinking)
    assert len(second["messages"][1]["content"]) == 2


def test_claude_provider_refusal_and_missing_key():
    p = ClaudeProvider(client=_fake_client([_response("", stop="refusal")], []))
    assert "No puedo" in p.ask("x")

    def no_key(**kwargs):
        raise TypeError("Could not resolve authentication method. Expected one of api_key...")

    p = ClaudeProvider(client=SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=no_key))))
    with pytest.raises(ChatbotError, match="ANTHROPIC_API_KEY"):
        p.ask("x")
