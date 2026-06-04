"""
AI Orchestrator (FLOWOI_AI_TZ §2): function-calling loop.

Алгоритм:
  1. user msg → запись
  2. собрать messages для LLM:
     - system prompt
     - cabinet_scope как контекст в system
     - attachments (контекст графика) как user-msg
     - history (последние N)
     - current user-msg
  3. LLM-call с tools
  4. response.choices[0].finish_reason:
     - 'stop' → текст в БД, выход
     - 'tool_calls' → execute каждый tool → tool-result в messages → goto 3
  5. защита AI_MAX_TOOL_ITERATIONS

LLM не считает цифры. Все числа из tool_calls.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import log
from app.models.ai_chat import AIChatSession, AIChatMessage, ChatRole
from app.services.ai import tools_v2
from app.services.ai.llm_provider import LLMError, get_provider


SYSTEM_PROMPT = """\
Ты — Flowoi AI: аналитический мозг поверх данных Ozon (FLOWOI_AI_TZ.md).

ГЛАВНОЕ ПРАВИЛО — ты НЕ считаешь цифры. Любое число в ответе должно прийти из tool_call.
Если данных нет — пиши «нет данных», не выдумывай.

Принципы:
1. Зеркало Ozon: базовые цифры (выручка/заказы/остатки) должны сходиться с кабинетом.
2. Два контура финансов: вызывая get_pnl, всегда указывай model='operational' (наша
   оперативная модель) ИЛИ 'official' (отчёт Ozon /v2/finance/realization).
   НЕ смешивай контуры в одной цифре. В ответе явно укажи контур.
3. Source-флаг: вызывай tools и используй поле source/contour из ответа.
4. Прогноз/совет = «оценка» (estimated). НЕ объявляй модельные оценки как факт.
5. Действия в кабинете Ozon ты НЕ выполняешь. Только советуешь.

Когда юзер называет товар по имени — сначала найди его через get_metrics или get_stock
(там виден product_id), потом дёргай SKU-specific tools.

Если cabinet_scope активен — он передаётся в system. Используй cabinet_id из него при
любой неоднозначности.

Стиль:
- Кратко, цифры в ₽/штуках, проценты с 1 знаком.
- Без вводных «как языковая модель…».
- Если используешь tool — выводи итог человеческим языком, ссылаясь на источник/контур.\
"""


def _scope_to_system(scope: dict | None) -> str:
    if not scope:
        return ""
    cabs = scope.get("cabinet_ids") or []
    active = scope.get("active")
    if not cabs:
        return ""
    return (
        f"\n\n[CABINET_SCOPE]\nДоступные кабинеты: {cabs}\n"
        + (f"Активный (по умолчанию): {active}\n" if active else "")
    )


def _attachments_to_user_msg(atts: list[dict] | None) -> str | None:
    if not atts:
        return None
    parts = []
    for a in atts:
        t = a.get("type", "context")
        if t == "chart":
            metrics = ", ".join(a.get("metrics", []))
            p = a.get("period") or {}
            pid = a.get("product_id")
            parts.append(
                f"[CHART_CONTEXT] метрики={metrics}, период={p.get('from')}…{p.get('to')}"
                + (f", product_id={pid}" if pid else "")
            )
        else:
            parts.append(f"[{t.upper()}] {json.dumps(a, ensure_ascii=False)[:300]}")
    return "Юзер прикрепил контекст:\n" + "\n".join(parts)


async def _load_history(db: AsyncSession, session_id: uuid.UUID, limit: int = 40) -> list[dict]:
    """История в формате OpenAI Chat."""
    rows = (await db.execute(
        select(AIChatMessage)
        .where(AIChatMessage.session_id == session_id)
        .order_by(AIChatMessage.created_at)
        .limit(limit)
    )).scalars().all()

    out: list[dict] = []
    for m in rows:
        role = m.role
        if role == ChatRole.USER.value:
            out.append({"role": "user", "content": m.content or ""})
        elif role == ChatRole.ASSISTANT.value:
            msg: dict[str, Any] = {"role": "assistant", "content": m.content or ""}
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            out.append(msg)
        elif role == ChatRole.TOOL.value:
            # tool_calls хранит [{tool_call_id, name, content}]
            for tc in (m.tool_calls or []):
                out.append({
                    "role": "tool",
                    "tool_call_id": tc.get("tool_call_id"),
                    "content": tc.get("content", ""),
                })
    return out


async def _save_message(
    db: AsyncSession, session_id: uuid.UUID, role: str,
    content: str | None = None,
    tool_calls: list[dict] | None = None,
    attachments: list[dict] | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> AIChatMessage:
    msg = AIChatMessage(
        session_id=session_id, role=role, content=content,
        tool_calls=tool_calls, attachments=attachments,
        model_used=model, input_tokens=input_tokens, output_tokens=output_tokens,
    )
    db.add(msg)
    await db.flush()
    return msg


async def ensure_session(
    db: AsyncSession, user_id: uuid.UUID,
    session_id: uuid.UUID | None,
    cabinet_scope: dict | None,
    first_message: str | None,
) -> AIChatSession:
    if session_id:
        s = (await db.execute(select(AIChatSession).where(
            AIChatSession.id == session_id, AIChatSession.user_id == user_id,
        ))).scalar_one_or_none()
        if not s:
            raise ValueError("session_not_found")
        if cabinet_scope is not None:
            s.cabinet_scope = cabinet_scope
        return s
    title = (first_message or "").strip()[:60] or None
    s = AIChatSession(
        user_id=user_id, title=title, cabinet_scope=cabinet_scope,
    )
    db.add(s)
    await db.flush()
    return s


async def _chat_via_render(
    db: AsyncSession, *,
    session: AIChatSession,
    user_text: str,
    attachments: list[dict] | None = None,
) -> dict:
    """
    Proxy на внешний AI-сервис (Render). VPS в РФ не может звонить OpenAI
    напрямую (403 unsupported_country_region_territory). Render → OpenAI →
    tools через api.flowoi.ru bridge → данные.

    Сессии: мы храним свою историю в БД (ai_chat_messages), Render держит
    свою in-memory. session_id используется только в нашей БД; Render
    получает каждый запрос как новую сессию (без истории).
    """
    import httpx

    cabinet_ids = (session.cabinet_scope or {}).get("cabinet_ids") or []
    body = {
        "message": user_text,
        "cabinet_scope": cabinet_ids,
        "attachments": [
            {
                "kind": "chart_context",
                "product_id": a.get("product_id"),
                "metrics": a.get("metrics") or [],
                "period_from": (a.get("period") or {}).get("from"),
                "period_to": (a.get("period") or {}).get("to"),
            }
            for a in (attachments or [])
        ],
    }
    url = settings.AI_RENDER_URL.rstrip("/") + "/ai/chat"
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            err = f"AI Render недоступен: {e}"
            await _save_message(
                db, session.id, ChatRole.ASSISTANT.value, content=err,
            )
            await db.commit()
            return {
                "answer": err, "tool_calls": [], "model": "render-proxy",
                "input_tokens": 0, "output_tokens": 0, "iterations": 0, "error": True,
            }

    answer = data.get("answer") or "(пустой ответ)"
    tools_used = data.get("tools_used") or []
    note = data.get("note")
    if note:
        answer = answer + f"\n\n_{note}_"

    await _save_message(
        db, session.id, ChatRole.ASSISTANT.value, content=answer,
        model="render-proxy",
    )
    if not session.title and user_text:
        session.title = user_text.strip()[:60]
    session.updated_at = datetime.utcnow()  # type: ignore[assignment]
    await db.commit()

    return {
        "answer": answer,
        "tool_calls": [
            {"tool": t.get("name"), "args": t.get("arguments") or {},
             "result_preview": t.get("source") or ""}
            for t in tools_used
        ],
        "model": "render-proxy",
        "input_tokens": 0, "output_tokens": 0,
        "iterations": 1, "error": False,
    }


async def chat(
    db: AsyncSession, *,
    session: AIChatSession,
    company_id: uuid.UUID,
    user_text: str,
    attachments: list[dict] | None = None,
) -> dict:
    """Главный метод: либо in-process tool-loop, либо proxy на Render."""

    # 1) user-msg в БД (одинаково для обоих режимов)
    await _save_message(
        db, session.id, ChatRole.USER.value,
        content=user_text, attachments=attachments,
    )

    # 2) Если задан AI_RENDER_URL — проксируем туда. VPS в РФ → OpenAI
    # отвечает 403, in-process orchestrator падает. Render не в РФ.
    if settings.AI_RENDER_URL:
        return await _chat_via_render(
            db, session=session, user_text=user_text, attachments=attachments,
        )

    # In-process путь — если есть прямой OpenAI ключ + сетевой доступ.
    provider = get_provider()
    history = await _load_history(db, session.id, limit=40)
    # history уже содержит только что добавленный user-msg

    # system
    sys_prompt = SYSTEM_PROMPT + _scope_to_system(session.cabinet_scope)
    messages: list[dict] = [{"role": "system", "content": sys_prompt}]
    # attachments как user-message добавляются ДО последнего user-msg
    att_text = _attachments_to_user_msg(attachments)
    # history уже хронологический; вставим attachments-context перед последним юзер-msg
    if att_text:
        # последний msg в history — наш только что сохранённый user_text
        history_pre = history[:-1]
        last_user = history[-1] if history else {"role": "user", "content": user_text}
        messages.extend(history_pre)
        messages.append({"role": "user", "content": att_text})
        messages.append(last_user)
    else:
        messages.extend(history)

    tools_spec = tools_v2.openai_tool_specs()

    total_in = 0
    total_out = 0
    iter_count = 0
    final_text = ""
    tool_calls_log: list[dict] = []

    for iteration in range(settings.OPENAI_MAX_TOOL_ITERATIONS):
        iter_count = iteration + 1
        try:
            resp = await provider.chat(
                messages=messages, tools=tools_spec, temperature=0.2,
            )
        except LLMError as e:
            err = f"AI недоступен: {e}"
            await _save_message(
                db, session.id, ChatRole.ASSISTANT.value, content=err,
                model=settings.OPENAI_MODEL,
            )
            session.updated_at = datetime.utcnow()  # type: ignore[assignment]
            await db.commit()
            return {
                "answer": err, "tool_calls": tool_calls_log,
                "model": settings.OPENAI_MODEL,
                "input_tokens": total_in, "output_tokens": total_out,
                "iterations": iter_count, "error": True,
            }

        usage = resp.get("usage") or {}
        total_in += int(usage.get("prompt_tokens") or 0)
        total_out += int(usage.get("completion_tokens") or 0)

        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        finish = choice.get("finish_reason")

        # Сохраняем assistant-сообщение
        if finish == "tool_calls" and msg.get("tool_calls"):
            # Запоминаем assistant-msg с tool_calls
            assistant_tcs = msg["tool_calls"]
            await _save_message(
                db, session.id, ChatRole.ASSISTANT.value,
                content=msg.get("content"),
                tool_calls=assistant_tcs,
                model=settings.OPENAI_MODEL,
            )
            messages.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": assistant_tcs,
            })
            # Исполняем каждый tool
            tool_results_for_msg = []
            for tc in assistant_tcs:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                args_raw = fn.get("arguments") or "{}"
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                except json.JSONDecodeError:
                    args = {}
                tc_id = tc.get("id") or ""
                log.info("ai_tool_call", tool=name, args=args)
                result = await tools_v2.execute_tool(name, args, db, company_id)
                tool_calls_log.append({
                    "tool": name, "args": args,
                    "result_preview": str(result)[:200],
                })
                content = json.dumps(result, ensure_ascii=False, default=str)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": content,
                })
                tool_results_for_msg.append({
                    "tool_call_id": tc_id, "name": name, "content": content,
                })
            # Сохраняем tool-результаты как одну запись
            await _save_message(
                db, session.id, ChatRole.TOOL.value,
                tool_calls=tool_results_for_msg,
                model=settings.OPENAI_MODEL,
            )
            continue

        # finish='stop' или другие → финал
        final_text = (msg.get("content") or "").strip() or "(пустой ответ)"
        await _save_message(
            db, session.id, ChatRole.ASSISTANT.value,
            content=final_text,
            model=settings.OPENAI_MODEL,
            input_tokens=total_in, output_tokens=total_out,
        )
        break
    else:
        final_text = (
            f"AI остановлен после {settings.OPENAI_MAX_TOOL_ITERATIONS} tool-итераций. "
            "Возможно вопрос слишком общий — попробуй конкретнее."
        )
        await _save_message(
            db, session.id, ChatRole.ASSISTANT.value, content=final_text,
            model=settings.OPENAI_MODEL,
        )

    # обновим session.updated_at и title (если первое сообщение)
    if not session.title and user_text:
        session.title = user_text.strip()[:60]
    session.updated_at = datetime.utcnow()  # type: ignore[assignment]
    await db.commit()

    return {
        "answer": final_text,
        "tool_calls": tool_calls_log,
        "model": settings.OPENAI_MODEL,
        "input_tokens": total_in, "output_tokens": total_out,
        "iterations": iter_count, "error": False,
    }
