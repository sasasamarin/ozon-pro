"""
AI Chat Service — оркестратор tool-calling loop.

Алгоритм:
  1. user message → запись в БД
  2. собрать history (последние N сообщений)
  3. LLM-call (model, system, history+new, tools=tools_schema)
  4. response.stop_reason:
     - "end_turn" / "max_tokens" → текст assistant'у в БД, выход
     - "tool_use" → выполнить call_tool для каждого tool_use,
       приклеить tool_result → goto 3
  5. iter limit AI_MAX_TOOL_ITERATIONS — чтобы не зациклиться.

Usage tracking: каждый LLM-call инкрементирует AIUsageMonthly
(input/output tokens, requests_count).
"""
from __future__ import annotations

import json
import uuid
from datetime import date as date_cls, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log
from app.models.ai import AIChat, AIMessage, AIMessageRole, AIUsageMonthly
from app.services.ai import proxy, tools


SYSTEM_PROMPT = """\
Ты — Flowoi AI: финансовый помощник для селлера Ozon. Твоя задача — отвечать
на вопросы о бизнесе пользователя, используя ТОЛЬКО реальные данные из его \
кабинетов (вызывай tools чтобы их получить).

Принципы:
1. Зеркало Ozon: базовые цифры (выручка, заказы, остатки) должны совпадать с кабинетом.
2. Два контура: «Официальные отчёты Ozon» (из транзакций) vs «Наша модель» (расчёт).
3. Source-флаг: если цифра — оценка (estimated/model), явно скажи об этом.

Стиль:
- Кратко и по делу. Цифры в ₽/штуках, проценты с одним знаком.
- Не выдумывай. Если данных нет — скажи «нет данных» и предложи как их получить.
- Если у SKU история <365 дней — НЕ строй сезонность, скажи «недостаточно данных».
- Когда юзер называет товар по имени — сначала найди его через list_products, чтобы получить product_id.

Не пиши «как ИИ-модель я …». Просто отвечай.\
"""


def _msg_dict(role: str, content: Any) -> dict:
    """Anthropic format. content может быть строкой или list[block]."""
    return {"role": role, "content": content}


async def _load_history(db: AsyncSession, chat_id: uuid.UUID, limit: int = 40) -> list[dict]:
    """История чата в формате Anthropic messages."""
    rows = (await db.execute(
        select(AIMessage)
        .where(AIMessage.chat_id == chat_id)
        .order_by(AIMessage.created_at)
        .limit(limit)
    )).scalars().all()
    out: list[dict] = []
    for m in rows:
        # tool-сообщения сохраняем как JSON в content (восстанавливаем структуру)
        if m.role == AIMessageRole.TOOL.value:
            try:
                content = json.loads(m.content)
            except (ValueError, TypeError):
                content = m.content
            out.append({"role": "user", "content": content})
        else:
            out.append({"role": m.role, "content": m.content})
    return out


async def _save_message(
    db: AsyncSession, chat_id: uuid.UUID, role: str, content: str,
    model: str | None = None, tokens: int | None = None,
    context_page: str | None = None,
) -> AIMessage:
    msg = AIMessage(
        chat_id=chat_id, role=role, content=content,
        model_used=model, tokens=tokens, context_page=context_page,
    )
    db.add(msg)
    await db.flush()
    return msg


async def _track_usage(
    db: AsyncSession, user_id: uuid.UUID, model: str,
    input_tokens: int, output_tokens: int,
) -> None:
    period = date_cls.today().strftime("%Y-%m")
    stmt = pg_insert(AIUsageMonthly).values(
        user_id=user_id, period=period, model=model,
        requests_count=1, tokens_input=input_tokens, tokens_output=output_tokens,
    ).on_conflict_do_update(
        constraint="uq_ai_usage_monthly_triple",
        set_={
            "requests_count": AIUsageMonthly.requests_count + 1,
            "tokens_input": AIUsageMonthly.tokens_input + input_tokens,
            "tokens_output": AIUsageMonthly.tokens_output + output_tokens,
        },
    )
    await db.execute(stmt)


async def ensure_chat(
    db: AsyncSession, user_id: uuid.UUID, chat_id: uuid.UUID | None,
    first_message: str | None = None,
) -> AIChat:
    """Создать новый чат или вернуть существующий (с проверкой owner)."""
    if chat_id:
        chat = (await db.execute(
            select(AIChat).where(AIChat.id == chat_id, AIChat.user_id == user_id)
        )).scalar_one_or_none()
        if not chat:
            raise ValueError("chat_not_found")
        return chat
    # Новый чат — title из первого сообщения (первые 60 символов)
    title = None
    if first_message:
        title = first_message.strip()[:60]
    chat = AIChat(user_id=user_id, title=title)
    db.add(chat)
    await db.flush()
    return chat


async def send_message(
    db: AsyncSession, *,
    chat: AIChat, user_id: uuid.UUID, company_id: uuid.UUID,
    text: str, model: str | None = None, context_page: str | None = None,
) -> dict:
    """
    Послать сообщение в чат, получить ответ ассистента.

    Возвращает {answer, tool_calls, model, input_tokens, output_tokens, iterations}.
    """
    model = model or settings.AI_DEFAULT_MODEL

    # 1) запись user-сообщения
    await _save_message(
        db, chat.id, AIMessageRole.USER.value, text,
        context_page=context_page,
    )

    # 2) подготовка messages для LLM
    history = await _load_history(db, chat.id)
    schema = tools.tools_schema()

    total_in = 0
    total_out = 0
    tool_calls_log: list[dict] = []
    final_text = ""

    for iteration in range(settings.AI_MAX_TOOL_ITERATIONS):
        try:
            resp = await proxy.messages_create(
                model=model, messages=history, system=SYSTEM_PROMPT,
                tools=schema, max_tokens=4096,
            )
        except proxy.AIProxyError as e:
            err = f"Не удалось вызвать AI: {e}"
            await _save_message(db, chat.id, AIMessageRole.ASSISTANT.value, err, model=model)
            return {
                "answer": err, "tool_calls": tool_calls_log,
                "model": model, "input_tokens": total_in, "output_tokens": total_out,
                "iterations": iteration, "error": True,
            }

        usage = resp.get("usage") or {}
        total_in += int(usage.get("input_tokens") or 0)
        total_out += int(usage.get("output_tokens") or 0)
        stop = resp.get("stop_reason")
        content = resp.get("content") or []

        # Текстовые блоки в content
        text_blocks = [b for b in content if b.get("type") == "text"]
        tool_blocks = [b for b in content if b.get("type") == "tool_use"]

        if stop == "tool_use" and tool_blocks:
            # Сохраняем assistant-блок с tool_use целиком
            history.append({"role": "assistant", "content": content})
            await _save_message(
                db, chat.id, AIMessageRole.ASSISTANT.value,
                json.dumps(content, ensure_ascii=False),
                model=model,
            )

            # Выполняем все tool_use из этого turn
            tool_results = []
            for tb in tool_blocks:
                tname = tb.get("name") or ""
                targs = tb.get("input") or {}
                tid = tb.get("id") or ""
                log.info("ai_tool_call", tool=tname, args=targs)
                result = await tools.call_tool(tname, targs, db, company_id)
                tool_calls_log.append({"tool": tname, "args": targs, "result_preview": str(result)[:200]})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tid,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                })
            # tool_result-блок — сообщение от user-роли
            history.append({"role": "user", "content": tool_results})
            await _save_message(
                db, chat.id, AIMessageRole.TOOL.value,
                json.dumps(tool_results, ensure_ascii=False),
                model=model,
            )
            continue  # → следующая итерация: LLM на основе tool_results

        # end_turn / max_tokens / stop_sequence → финальный ответ
        if text_blocks:
            final_text = "\n".join(b.get("text", "") for b in text_blocks)
        else:
            final_text = "(пустой ответ)"
        break
    else:
        final_text = (
            f"AI остановлен после {settings.AI_MAX_TOOL_ITERATIONS} tool-итераций. "
            "Возможно вопрос слишком сложный или зациклил инструменты."
        )

    # Сохраняем финальный ответ
    await _save_message(
        db, chat.id, AIMessageRole.ASSISTANT.value, final_text,
        model=model, tokens=total_out,
    )
    if total_in or total_out:
        await _track_usage(db, user_id, model, total_in, total_out)

    # Если у чата нет title — берём из первого user-msg
    if not chat.title and text:
        chat.title = text.strip()[:60]

    chat.updated_at = datetime.utcnow()  # type: ignore[assignment]
    await db.commit()
    return {
        "answer": final_text, "tool_calls": tool_calls_log,
        "model": model, "input_tokens": total_in, "output_tokens": total_out,
        "iterations": iteration + 1, "error": False,
    }
