"""
Ежедневная email-рассылка дайджеста алертов.

Для каждого юзера, у которого есть AlertRule с channel="email":
  - собираем активные AlertHistory за последние 24 часа
  - отправляем письмо «N алертов за сегодня» с группировкой по типу

Запуск через celery beat — раз в день в 09:00 UTC = 12:00 МСК.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.models import User
from app.models.alert import AlertHistory, AlertRule
from app.services.email import EmailJob, queue_email
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import run_celery_async


TYPE_LABEL = {
    "stockout": "Кончается товар",
    "overstock": "Затоварен",
    "sales_drop": "Падение продаж",
    "margin_below_min": "Маржа критическая",
    "price_below_cost": "Цена ниже с/с",
    "credit_payment_due": "Платёж по кредиту",
    "negative_review": "Негативный отзыв",
    "cashflow_gap": "Кассовый разрыв",
    "position_drop": "Падение позиции",
    "rating_drop": "Падение рейтинга",
    "fbs_not_shipped": "FBS не отгружен",
    "ad_budget_exceeded": "Перерасход рекламы",
    "tax_due": "Срок налога",
    "commission_change": "Изменение комиссии",
    "competitor_dump": "Демпинг конкурента",
    "low_conversion": "Низкая конверсия",
    "return_received": "Возврат принят",
}


@celery_app.task(name="app.workers.tasks.alerts_digest.send_daily_digests")
def send_daily_digests() -> dict:
    """Прогнать всех юзеров с email-каналом, разослать дайджест."""
    return run_celery_async(_run_async)


async def _run_async(SessionLocal: async_sessionmaker[AsyncSession]) -> dict:
    async with SessionLocal() as db:
        # Юзеры с email-каналом хотя бы в одном включённом правиле
        users_q = (
            select(User.id, User.email, User.full_name)
            .where(User.is_active.is_(True))
        )
        users = (await db.execute(users_q)).all()
        if not users:
            return {"users_total": 0, "sent": 0, "skipped": 0}

        since = datetime.now(UTC) - timedelta(hours=24)
        sent = skipped = 0

        for uid, email, name in users:
            if not email:
                skipped += 1
                continue

            # Есть ли активные правила с email-каналом?
            has_email_channel = (await db.execute(
                select(AlertRule).where(
                    AlertRule.user_id == uid,
                    AlertRule.is_active.is_(True),
                )
            )).scalars().all()
            wants_email = any(
                "email" in (r.channels_json or [])
                for r in has_email_channel
            )
            if not wants_email:
                skipped += 1
                continue

            # Алерты за 24 часа
            alerts = (await db.execute(
                select(AlertHistory).where(
                    AlertHistory.user_id == uid,
                    AlertHistory.triggered_at >= since,
                    AlertHistory.resolved_at.is_(None),
                ).order_by(AlertHistory.triggered_at.desc()).limit(100)
            )).scalars().all()

            if not alerts:
                skipped += 1
                continue

            items = [
                {
                    "marker_type": a.marker_type,
                    "type_label": TYPE_LABEL.get(a.marker_type, a.marker_type),
                    "severity": a.severity,
                    "message": a.message,
                }
                for a in alerts
            ]

            res = await queue_email(EmailJob(
                to_email=email,
                template="alerts_digest",
                subject=None,
                user_id=uid,
                context={
                    "user_name": (name or "").split()[0] if name else "",
                    "period": "последние 24 часа",
                    "items": items,
                },
            ))
            if res.get("ok"):
                sent += 1
                log.info("alert_digest_sent", user_id=str(uid), count=len(items))
            else:
                skipped += 1
                log.warning("alert_digest_send_failed",
                            user_id=str(uid), error=res.get("error"))

        return {"users_total": len(users), "sent": sent, "skipped": skipped}
