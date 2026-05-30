"""
/email — журнал отправленных писем + шаблоны (read-only).

GET /api/v1/email/log → последние отправленные письма
GET /api/v1/email/templates → список доступных шаблонов (из enum EmailTemplate)
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import EmailLog, EmailStatus, EmailTemplate, User
from app.services.email import EmailJob, queue_email

router = APIRouter()


class EmailLogRow(BaseModel):
    id: str
    to_email: str
    subject: str | None
    template: str | None
    status: str
    error_message: str | None
    sent_at: str | None
    created_at: str


class TemplateRow(BaseModel):
    key: str
    label: str


TEMPLATE_LABELS = {
    "welcome": "Приветствие",
    "password_reset": "Сброс пароля",
    "email_verify": "Подтверждение email",
    "team_invite": "Приглашение в команду",
    "stockout_alert": "Стокаут",
    "weekly_report": "Еженедельный отчёт",
    "monthly_report": "Ежемесячный отчёт",
    "payment_received": "Оплата получена",
    "subscription_expiring": "Подписка истекает",
    "abandoned_cart": "Брошенная корзина",
}


@router.get("/templates", response_model=list[TemplateRow])
async def list_templates(
    current_user: User = Depends(get_current_user),
) -> list[TemplateRow]:
    return [
        TemplateRow(key=t.value, label=TEMPLATE_LABELS.get(t.value, t.value))
        for t in EmailTemplate
    ]


@router.get("/log", response_model=list[EmailLogRow])
async def list_email_log(
    days: int = Query(30, ge=1, le=365),
    status: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[EmailLogRow]:
    # EmailLog не имеет company_id — фильтр через user_id юзеров компании
    from app.models import User as U
    user_ids = (await db.execute(
        select(U.id).where(U.company_id == current_user.company_id)
    )).scalars().all()
    q = select(EmailLog).where(EmailLog.user_id.in_(user_ids))
    if status:
        q = q.where(EmailLog.status == status)
    q = q.order_by(desc(EmailLog.created_at)).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [
        EmailLogRow(
            id=str(e.id),
            to_email=e.to_email,
            subject=e.subject,
            template=e.template,
            status=e.status,
            error_message=e.error,
            sent_at=e.sent_at.isoformat() if e.sent_at else None,
            created_at=e.created_at.isoformat(),
        )
        for e in rows
    ]


# =====================================================================
# Реальная отправка
# =====================================================================


class TestSendInput(BaseModel):
    to: EmailStr
    template: str = "test"
    user_name: str | None = None


@router.post("/test-send")
async def test_send_email(
    payload: TestSendInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отправить тестовое письмо. Юзер: проверка что Beget работает."""
    result = await queue_email(EmailJob(
        to_email=payload.to,
        template=payload.template,
        subject=None,
        context={"user_name": payload.user_name or current_user.email or ""},
        user_id=current_user.id,
    ))
    db.add(EmailLog(
        user_id=current_user.id,
        to_email=payload.to,
        subject=f"Flowoi: {payload.template}",
        template=payload.template,
        status=EmailStatus.SENT.value if result.get("ok") else EmailStatus.FAILED.value,
        error=result.get("error"),
        sent_at=datetime.now(UTC) if result.get("ok") else None,
    ))
    await db.commit()
    if not result.get("ok"):
        raise HTTPException(500, result.get("error") or "SMTP send failed")
    return {"ok": True, "to": payload.to, "template": payload.template}
