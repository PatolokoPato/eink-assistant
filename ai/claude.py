"""ChatbotProvider con Claude (API de Anthropic).

Credenciales: las resuelve el SDK solo (variable ANTHROPIC_API_KEY, o un
perfil de `ant auth login`). Modelo configurable con EINK_AI_MODEL.
"""

from __future__ import annotations

import logging
import os
import threading

import anthropic

from .base import ChatbotError, ChatbotProvider

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """\
Eres un asistente de escritorio. Tus respuestas se muestran en una pantalla de tinta \
electrónica pequeña (400×300 píxeles, blanco y negro), así que:
- Responde en el idioma del usuario (normalmente español), de forma clara y directa.
- Sé breve por defecto: unas pocas frases o una lista corta. Extiéndete solo si te lo piden.
- Usa texto plano. Nada de tablas, bloques de código largos, emojis ni Markdown complejo; \
para listas, empieza cada elemento con "- ".
- No hagas preguntas de seguimiento salvo que de verdad falte información.
- Latency-sensitive; begin your visible answer immediately."""


class ClaudeProvider(ChatbotProvider):
    name = "Claude"

    def __init__(self, model: str | None = None, *, effort: str = "low",
                 client: anthropic.Anthropic | None = None) -> None:
        self.model = model or os.environ.get("EINK_AI_MODEL") or DEFAULT_MODEL
        self.effort = effort  # charla: "low" responde rápido y basta para preguntas cotidianas
        self._client = client
        self._messages: list[dict] = []
        self._lock = threading.Lock()

    @property
    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def reset(self) -> None:
        with self._lock:
            self._messages = []

    def ask(self, question: str) -> str:
        with self._lock:
            # Historial solo de añadir: se reenvía tal cual (incluidos los bloques
            # de thinking), así la conversación conserva su razonamiento y caché.
            messages = [*self._messages, {"role": "user", "content": question}]
            try:
                with self.client.beta.messages.stream(
                    model=self.model,
                    max_tokens=16000,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    output_config={"effort": self.effort},
                    cache_control={"type": "ephemeral"},
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",  # si el modelo declina, la API reintenta con otro
                ) as stream:
                    response = stream.get_final_message()
            except anthropic.AuthenticationError as e:
                raise ChatbotError("Clave de API de Anthropic no válida (ANTHROPIC_API_KEY).") from e
            except anthropic.PermissionDeniedError as e:
                raise ChatbotError("La clave de API no tiene permiso para usar este modelo.") from e
            except anthropic.NotFoundError as e:
                raise ChatbotError(f"Modelo no encontrado: {self.model}") from e
            except anthropic.RateLimitError as e:
                raise ChatbotError("Límite de uso de la API alcanzado; prueba en un rato.") from e
            except anthropic.APIStatusError as e:
                raise ChatbotError(f"Error de la API ({e.status_code}): {e.message}") from e
            except anthropic.APIConnectionError as e:
                raise ChatbotError("Sin conexión con la API de Anthropic.") from e
            except TypeError as e:
                # El SDK lanza TypeError si no encuentra ninguna credencial.
                if "authentication" in str(e).lower() or "api_key" in str(e).lower():
                    raise ChatbotError(
                        "Falta la clave de API: define ANTHROPIC_API_KEY (ver README) y reinicia el programa."
                    ) from e
                raise

            if response.stop_reason == "refusal":
                category = getattr(response.stop_details, "category", None) if response.stop_details else None
                log.info("Claude declinó la pregunta (categoría %s)", category)
                return "No puedo responder a esa pregunta."

            text = "\n".join(b.text for b in response.content if b.type == "text").strip()
            if response.stop_reason == "max_tokens":
                text += "\n\n[Respuesta cortada por longitud]"
            self._messages = [*messages, {"role": "assistant", "content": response.content}]
            log.info("Claude (%s) respondió: %d caracteres, %s tokens de salida",
                     response.model, len(text), response.usage.output_tokens)
            return text or "(Respuesta vacía)"
