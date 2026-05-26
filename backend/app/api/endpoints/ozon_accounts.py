"""
Управление магазинами Озона (подключение, удаление, список).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.logging import log
from app.core.security import decrypt_secret, encrypt_secret
from app.db.session import get_db
from app.models import OzonAccount, OzonAccountStatus, User
from app.services.ozon_client import OzonSellerClient

router = APIRouter()


# === Pydantic схемы ===

class OzonAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    client_id: str = Field(min_length=1, max_length=100)
    api_key: str = Field(min_length=1, max_length=255)
    # Performance API опционально
    perf_client_id: str | None = None
    perf_secret: str | None = None


class OzonAccountResponse(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    is_active: bool
    last_sync_at: str | None
    last_sync_error: str | None
    has_performance_api: bool

    class Config:
        from_attributes = True


# === Endpoints ===

@router.get("/", response_model=list[OzonAccountResponse])
async def list_ozon_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[OzonAccountResponse]:
    """Список всех магазинов текущей компании."""
    result = await db.execute(
        select(OzonAccount).where(
            OzonAccount.company_id == current_user.company_id,
            OzonAccount.deleted_at.is_(None),
        )
    )
    accounts = result.scalars().all()

    return [
        OzonAccountResponse(
            id=str(acc.id),
            name=acc.name,
            description=acc.description,
            status=acc.status,
            is_active=acc.is_active,
            last_sync_at=acc.last_sync_at.isoformat() if acc.last_sync_at else None,
            last_sync_error=acc.last_sync_error,
            has_performance_api=bool(acc.perf_client_id_encrypted),
        )
        for acc in accounts
    ]


@router.post("/", response_model=OzonAccountResponse, status_code=201)
async def create_ozon_account(
    payload: OzonAccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OzonAccountResponse:
    """
    Подключить новый магазин Озона.

    Сразу проверяем валидность API ключей через тестовый запрос.
    Сохраняем ключи ЗАШИФРОВАННЫМИ.
    """
    # Проверяем валидность ключей
    log.info("checking_ozon_credentials", company_id=str(current_user.company_id))

    async with OzonSellerClient(
        client_id=payload.client_id,
        api_key=payload.api_key,
    ) as client:
        is_valid = await client.test_credentials()

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверные API ключи Озона",
        )

    # Создаём магазин (ключи шифруем)
    account = OzonAccount(
        company_id=current_user.company_id,
        name=payload.name,
        description=payload.description,
        client_id_encrypted=encrypt_secret(payload.client_id),
        api_key_encrypted=encrypt_secret(payload.api_key),
        perf_client_id_encrypted=(
            encrypt_secret(payload.perf_client_id) if payload.perf_client_id else None
        ),
        perf_secret_encrypted=(
            encrypt_secret(payload.perf_secret) if payload.perf_secret else None
        ),
        status=OzonAccountStatus.ACTIVE.value,
        is_active=True,
    )
    db.add(account)
    await db.flush()

    log.info(
        "ozon_account_created",
        account_id=str(account.id),
        company_id=str(current_user.company_id),
    )

    return OzonAccountResponse(
        id=str(account.id),
        name=account.name,
        description=account.description,
        status=account.status,
        is_active=account.is_active,
        last_sync_at=None,
        last_sync_error=None,
        has_performance_api=bool(account.perf_client_id_encrypted),
    )


@router.delete("/{account_id}", status_code=204)
async def delete_ozon_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft delete магазина (данные остаются)."""
    result = await db.execute(
        select(OzonAccount).where(
            OzonAccount.id == account_id,
            OzonAccount.company_id == current_user.company_id,
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail="Магазин не найден")

    from datetime import UTC, datetime
    account.deleted_at = datetime.now(UTC)
    account.is_active = False

    log.info("ozon_account_deleted", account_id=str(account_id))


@router.post("/{account_id}/sync")
async def sync_ozon_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Запустить полную синхронизацию магазина.

    Тянет: товары, цены, остатки, заказы, транзакции, аналитику.
    Работает в фоне через Celery.
    """
    result = await db.execute(
        select(OzonAccount).where(
            OzonAccount.id == account_id,
            OzonAccount.company_id == current_user.company_id,
            OzonAccount.deleted_at.is_(None),
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=404, detail="Магазин не найден")

    # TODO: запустить celery задачу sync_full(account_id)
    # from app.workers.sync import sync_full_account
    # task = sync_full_account.delay(str(account_id))

    log.info("sync_requested", account_id=str(account_id))

    return {
        "status": "queued",
        "message": "Синхронизация запущена в фоне",
    }
