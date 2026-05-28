"""
Отправка email через SMTP. Логирование — в email_log.

ЗАГЛУШКА в Phase 1: пишем строку в email_log со status=queued, реальной
отправки нет. Реальная Celery-задача и шаблоны (Jinja2 или просто
форматирование строк) — Phase 1.5/2.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.logging import log


@dataclass
class EmailJob:
    to_email: str
    template: str          # EmailTemplate value
    subject: str | None
    context: dict[str, Any]
    user_id: uuid.UUID | None = None


async def queue_email(job: EmailJob) -> None:
    """Положить письмо в очередь (Phase 1: только пишем в email_log).

    В Phase 1.5+ здесь будет: создать EmailLog (status=queued),
    зашейдулить Celery-task `send_email`, который рендерит шаблон и шлёт по SMTP.
    """
    log.info(
        "email_queued_stub",
        to=job.to_email,
        template=job.template,
        subject=job.subject,
        ts=datetime.now(UTC).isoformat(),
    )
    # TODO: insert EmailLog row, schedule send_email.delay(...)


def render_template(template: str, context: dict[str, Any]) -> tuple[str, str]:
    """Заглушка рендера шаблона → (subject, html_body).

    В Phase 1.5+ — Jinja2 + шаблоны из templates/email/.
    """
    subject = f"[Flowoi] {template}"
    body = f"<p>Шаблон '{template}' не реализован.</p><pre>{context}</pre>"
    return subject, body
