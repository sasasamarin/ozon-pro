"""
Прокси-клиент к Anthropic.

Если settings.AI_PROXY_URL задан — все запросы идут через него
(нужно для VPS в РФ где api.anthropic.com заблокирован).
Иначе fallback на прямой anthropic.com.

Прокси принимает body 1:1 как Anthropic Messages API + заголовок
Authorization: Bearer <AI_PROXY_TOKEN>. Возвращает то что отдал Anthropic.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import log


class AIProxyError(Exception):
    """Ошибка вызова Anthropic (через прокси или напрямую)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def is_configured() -> bool:
    """True если можно делать запросы (есть прокси или прямой ключ)."""
    return bool(settings.AI_PROXY_URL) or bool(settings.ANTHROPIC_API_KEY)


async def messages_create(
    *,
    model: str,
    messages: list[dict],
    system: str | None = None,
    tools: list[dict] | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
) -> dict:
    """
    Один вызов Anthropic Messages API. Возвращает raw response.

    Структура response:
      {
        "content": [{"type": "text", "text": "..."} |
                    {"type": "tool_use", "id": "...", "name": "...", "input": {...}}],
        "stop_reason": "end_turn" | "tool_use" | "max_tokens",
        "usage": {"input_tokens": N, "output_tokens": M},
        "model": "claude-..."
      }
    """
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools

    if settings.AI_PROXY_URL:
        url = settings.AI_PROXY_URL.rstrip("/") + "/v1/messages"
        headers = {
            "Authorization": f"Bearer {settings.AI_PROXY_TOKEN}",
            "Content-Type": "application/json",
        }
    elif settings.ANTHROPIC_API_KEY:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
    else:
        raise AIProxyError(
            "AI не настроен. Добавь AI_PROXY_URL (Render-прокси) или "
            "ANTHROPIC_API_KEY в .env.",
            status=503,
        )

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as e:
            log.exception("ai_proxy_network_error", url=url)
            raise AIProxyError(f"Сеть: {e}", status=502) from e
        if resp.status_code != 200:
            txt = resp.text[:500]
            log.warning("ai_proxy_bad_status", status=resp.status_code, body=txt)
            raise AIProxyError(
                f"AI proxy {resp.status_code}: {txt}", status=resp.status_code
            )
        return resp.json()
