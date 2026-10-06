import json
import urllib.error
import urllib.request

import pytest

from ui.local_api import CLIENT_HEADER, Handlers, LocalApi


@pytest.fixture
def api():
    calls = []
    handlers = Handlers(
        show=lambda text, q: calls.append(("show", text, q)) or 2,
        page=lambda d: (calls.append(("page", d)), (2, 3))[1],
        home=lambda: calls.append(("home",)),
        status=lambda: {"connected": True, "view": "home"},
    )
    server = LocalApi(handlers, port=0)  # puerto libre cualquiera
    server.start()
    yield f"http://127.0.0.1:{server.port}", calls
    server.stop()


def _req(url, payload=None, headers=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={CLIENT_HEADER: "test"} if headers is None else headers,
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)


def test_show_page_home_status(api):
    base, calls = api
    assert _req(base + "/show", {"text": "hola", "question": "q"}) == {"pages": 2}
    assert _req(base + "/page", {"delta": -1}) == {"page": 2, "pages": 3}
    assert _req(base + "/home", {}) == {}
    assert _req(base + "/status")["connected"] is True
    assert calls == [("show", "hola", "q"), ("page", -1), ("home",)]


@pytest.mark.parametrize("headers", [{}, {CLIENT_HEADER: "x", "Origin": "https://malicioso.example"}])
def test_rejects_requests_without_header_or_from_web_pages(api, headers):
    base, calls = api
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(base + "/show", {"text": "hola"}, headers=headers)
    assert e.value.code == 403 and calls == []


def test_validates_body(api):
    base, _ = api
    with pytest.raises(urllib.error.HTTPError) as e:
        _req(base + "/show", {"text": "   "})
    assert e.value.code == 400


def test_mcp_tools_talk_to_the_api(api, monkeypatch):
    from mcp_server import eink_mcp

    base, calls = api
    monkeypatch.setattr(eink_mcp, "BASE", base)
    assert "2 páginas" in eink_mcp.mostrar_en_eink("texto", "pregunta")
    assert eink_mcp.pasar_pagina_eink("anterior") == "Página 2 de 3."
    assert json.loads(eink_mcp.estado_eink())["view"] == "home"
    assert calls[0] == ("show", "texto", "pregunta") and calls[1] == ("page", -1)


def test_mcp_tool_explains_when_app_is_closed(monkeypatch):
    from mcp_server import eink_mcp

    monkeypatch.setattr(eink_mcp, "BASE", "http://127.0.0.1:9")  # nadie escucha
    with pytest.raises(RuntimeError, match="no está abierto"):
        eink_mcp.mostrar_en_eink("hola")
