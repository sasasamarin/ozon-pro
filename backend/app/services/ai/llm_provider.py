"""
LLM Provider — абстракция для function calling.

OpenAI Chat Completions API формат:
  request:
    {model, messages: [{role, content, tool_calls?, tool_call_id?}],
     tools: [{type:'function', function:{name, description, parameters}}],
     tool_choice: 'auto'}
  response.choices[0].message:
    {role:'assistant', content, tool_calls:[{id, function:{name, arguments}}]}
  finish_reason: 'stop' | 'tool_calls' | ...

Ключ берётся ТОЛЬКО из env (OPENAI_API_KEY). Не коммитим ключ, не
кладём во фронт, не пишем в URL/логи.
"""
from __future__ import annotations

from typing import Any, Protocol

import httpx

from app.core.config import settings
from app.core.logging import log


class LLMError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class LLMProvider(Protocol):
    """Минимальный контракт. Реализации: OpenAI, потом Claude, любой свой."""

    name: str

    async def chat(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> dict: ...

    def is_configured(self) -> bool: ...


class OpenAIProvider:
    """OpenAI Chat Completions (function calling). Stateless."""

    name = "openai"

    def is_configured(self) -> bool:
        return bool(settings.OPENAI_API_KEY)

    @property
    def base_url(self) -> str:
        return (settings.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip("/")

    async def chat(
        self,
        *,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> dict:
        if not self.is_configured():
            raise LLMError("OPENAI_API_KEY не задан в env", status=503)

        body: dict[str, Any] = {
            "model": settings.OPENAI_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            try:
                r = await client.post(
                    f"{self.base_url}/chat/completions", json=body, headers=headers,
                )
            except httpx.HTTPError as e:
                log.exception("openai_network_error", url=self.base_url)
                raise LLMError(f"Сеть: {e}", status=502) from e
            if r.status_code != 200:
                # НЕ логируем тело которое может содержать ключ; берём короткий преview
                preview = r.text[:300]
                log.warning("openai_bad_status", status=r.status_code, body=preview)
                raise LLMError(f"OpenAI {r.status_code}: {preview}", status=r.status_code)
            return r.json()


# Singleton-фабрика — один провайдер на процесс
_default_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _default_provider
    if _default_provider is None:
        _default_provider = OpenAIProvider()
    return _default_provider
