"""
Отправка email через SMTP (Beget — info@flowoi.ru).

Стек: aiosmtplib через TLS/SSL. Параметры — в settings (.env на VPS).
Beget: smtp.beget.com — 465 SSL / 2525 STARTTLS.

EmailLog (модель): каждое письмо логируется (queued → sent / failed).
Send выполняется ИНЛАЙНОМ при queue_email (MVP). В нагрузке — Celery task.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

import aiosmtplib

from app.core.config import settings
from app.core.logging import log


@dataclass
class EmailJob:
    to_email: str
    template: str
    subject: str | None
    context: dict[str, Any]
    user_id: uuid.UUID | None = None


def _smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)


async def send_email(
    to: str,
    subject: str,
    html: str,
    text: str | None = None,
) -> dict:
    """Прямая отправка письма по SMTP. Возвращает dict с результатом."""
    if not _smtp_configured():
        log.warning("email_smtp_not_configured", to=to, subject=subject)
        return {"ok": False, "error": "SMTP not configured", "skipped": True}

    msg = EmailMessage()
    msg["From"] = formataddr((settings.EMAIL_FROM_NAME, settings.EMAIL_FROM))
    msg["To"] = to
    msg["Subject"] = subject
    if text:
        msg.set_content(text)
        msg.add_alternative(html, subtype="html")
    else:
        msg.set_content(html, subtype="html")

    # Beget: 465 → SSL on connect (use_tls=True); 587/2525 → STARTTLS
    use_tls = settings.SMTP_PORT == 465
    start_tls = settings.SMTP_PORT in (587, 2525)

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            use_tls=use_tls,
            start_tls=start_tls,
            timeout=30,
        )
        log.info("email_sent", to=to, subject=subject, host=settings.SMTP_HOST)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        log.exception("email_send_failed", to=to, subject=subject)
        return {"ok": False, "error": str(exc)[:200]}


async def queue_email(job: EmailJob) -> dict:
    """Отправить письмо. В MVP — синхронно (внутри request)."""
    subject, html = render_template(job.template, job.context)
    subject = job.subject or subject
    log.info(
        "email_queued",
        to=job.to_email,
        template=job.template,
        subject=subject,
        ts=datetime.now(UTC).isoformat(),
    )
    return await send_email(to=job.to_email, subject=subject, html=html)


def render_template(template: str, context: dict[str, Any]) -> tuple[str, str]:
    """Простой рендер шаблона. Для критичных — Jinja2 с темплейтами."""
    name = (context.get("user_name") or "").strip()
    salutation = f"Здравствуйте, {name}!" if name else "Здравствуйте!"

    if template == "welcome":
        subject = "Добро пожаловать в Flowoi"
        html = f"""
        <p>{salutation}</p>
        <p>Спасибо за регистрацию в Flowoi — финансовом мозге продавца Ozon.</p>
        <p>Подключите кабинет Ozon и подтяните товары — это займёт пару минут.</p>
        <p><a href="https://flowoi.ru/cabinets/new">Открыть Flowoi →</a></p>
        """
        return subject, html

    if template == "test":
        subject = "Flowoi: тест SMTP"
        html = f"<p>{salutation}</p><p>Это тестовое письмо. Если получили — SMTP настроен правильно.</p>"
        return subject, html

    if template == "stockout_alert":
        product = context.get("product_name", "товар")
        subject = f"⚠️ Стокаут: {product}"
        html = f"<p>{salutation}</p><p>На складе закончился товар <b>{product}</b>.</p>"
        return subject, html

    if template == "report":
        period = context.get("period", "период")
        revenue = context.get("revenue", "—")
        subject = f"Flowoi: отчёт за {period}"
        html = f"<p>{salutation}</p><p>Выручка за {period}: <b>{revenue}</b>.</p>"
        return subject, html

    # дефолт
    subject = f"Flowoi: {template}"
    html = f"<p>{salutation}</p><pre>{context}</pre>"
    return subject, html
