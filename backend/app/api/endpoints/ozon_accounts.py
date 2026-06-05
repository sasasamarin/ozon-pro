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
from app.core.security import decrypt_secret, encrypt_secret  # noqa: F401
from app.db.session import get_db
from app.models import OzonAccount, OzonAccountStatus, OzonPremiumTier, User
from app.services.ozon_client import OzonSellerClient

router = APIRouter()


# === Pydantic схемы ===

VALID_PREMIUM_TIERS = {t.value for t in OzonPremiumTier}


class OzonAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    client_id: str = Field(min_length=1, max_length=100)
    api_key: str = Field(min_length=1, max_length=255)
    # Performance API опционально
    perf_client_id: str | None = None
    perf_client_secret: str | None = None
    # Тариф селлера — управляет тем, какие API доступны
    premium_tier: str = OzonPremiumTier.FREE.value


class OzonAccountResponse(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    is_active: bool
    premium_tier: str
    last_sync_at: str | None
    last_sync_error: str | None
    has_performance_api: bool

    class Config:
        from_attributes = True


def _account_to_response(account: OzonAccount) -> OzonAccountResponse:
    return OzonAccountResponse(
        id=str(account.id),
        name=account.name,
        description=account.description,
        status=account.status,
        is_active=account.is_active,
        premium_tier=account.premium_tier,
        last_sync_at=account.last_sync_at.isoformat() if account.last_sync_at else None,
        last_sync_error=account.last_sync_error,
        has_performance_api=bool(account.perf_client_id_encrypted),
    )


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

    return [_account_to_response(acc) for acc in accounts]


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
    if payload.premium_tier not in VALID_PREMIUM_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"premium_tier должен быть одним из {sorted(VALID_PREMIUM_TIERS)}",
        )

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
        perf_client_secret_encrypted=(
            encrypt_secret(payload.perf_client_secret) if payload.perf_client_secret else None
        ),
        premium_tier=payload.premium_tier,
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

    return _account_to_response(account)


class OzonAccountUpdate(BaseModel):
    """Все поля опциональные — обновляем только пришедшие."""

    name: str | None = None
    description: str | None = None
    client_id: str | None = None
    api_key: str | None = None
    perf_client_id: str | None = None
    perf_client_secret: str | None = None
    premium_tier: str | None = None
    is_active: bool | None = None


class PerfTestRequest(BaseModel):
    perf_client_id: str = Field(min_length=1)
    perf_client_secret: str = Field(min_length=1)


class PerfTestResponse(BaseModel):
    ok: bool
    expires_in: int | None = None
    error: str | None = None


@router.get("/{account_id}", response_model=OzonAccountResponse)
async def get_ozon_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OzonAccountResponse:
    """Один магазин по ID — для страницы /cabinets/:id."""
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
    return _account_to_response(account)


@router.patch("/{account_id}", response_model=OzonAccountResponse)
async def update_ozon_account(
    account_id: uuid.UUID,
    payload: OzonAccountUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OzonAccountResponse:
    """Частичное обновление магазина — только присланные поля.

    Изменение perf_client_secret сбрасывает кэшированный access_token.
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

    if payload.premium_tier is not None and payload.premium_tier not in VALID_PREMIUM_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"premium_tier должен быть одним из {sorted(VALID_PREMIUM_TIERS)}",
        )

    if payload.name is not None:
        account.name = payload.name
    if payload.description is not None:
        account.description = payload.description
    if payload.client_id is not None:
        account.client_id_encrypted = encrypt_secret(payload.client_id)
    if payload.api_key is not None:
        account.api_key_encrypted = encrypt_secret(payload.api_key)

    perf_credentials_changed = False
    if payload.perf_client_id is not None:
        account.perf_client_id_encrypted = (
            encrypt_secret(payload.perf_client_id)
            if payload.perf_client_id.strip()
            else None
        )
        perf_credentials_changed = True
    if payload.perf_client_secret is not None:
        account.perf_client_secret_encrypted = (
            encrypt_secret(payload.perf_client_secret)
            if payload.perf_client_secret.strip()
            else None
        )
        perf_credentials_changed = True

    if perf_credentials_changed:
        # Кэш токена больше не валиден
        account.perf_access_token_encrypted = None
        account.perf_token_expires_at = None

    if payload.premium_tier is not None:
        account.premium_tier = payload.premium_tier
    if payload.is_active is not None:
        account.is_active = payload.is_active

    await db.flush()
    log.info("ozon_account_updated", account_id=str(account.id))
    return _account_to_response(account)


@router.post("/test-perf-credentials", response_model=PerfTestResponse)
async def test_performance_credentials(
    payload: PerfTestRequest,
    _: User = Depends(get_current_user),
) -> PerfTestResponse:
    """Проверка Performance API ключей без сохранения.

    Делает один запрос на POST /api/client/token. Если 200 — ключи валидные;
    иначе возвращает текст ошибки от Ozon.
    """
    import httpx

    from app.core.config import settings

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                f"{settings.OZON_PERFORMANCE_API_BASE_URL}/api/client/token",
                json={
                    "client_id": payload.perf_client_id,
                    "client_secret": payload.perf_client_secret,
                    "grant_type": "client_credentials",
                },
            )
        if res.status_code == 200:
            data = res.json()
            return PerfTestResponse(ok=True, expires_in=data.get("expires_in"))
        return PerfTestResponse(
            ok=False,
            error=f"HTTP {res.status_code}: {res.text[:200]}",
        )
    except httpx.RequestError as e:
        return PerfTestResponse(ok=False, error=f"Сеть: {e}")
    except Exception as e:  # noqa: BLE001 — show the real reason to the user
        return PerfTestResponse(ok=False, error=str(e))


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
    db: AsyncSession = Depends(get_db),
) -> dict:
    # ВРЕМЕННО ДЛЯ ТЕСТА БЕЗ АВТОРИЗАЦИИ:
    from app.models import User
    import uuid as _uuid
    current_user = User(company_id=_uuid.UUID("8e0d3d28-1e02-48e3-ac38-97e95f24a8b1"))
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

    from app.workers.celery_app import celery_app
    celery_app.send_task("app.workers.tasks.sync_products.sync_full_account", args=[str(account_id)])

    log.info("sync_requested", account_id=str(account_id))

    return {
        "status": "queued",
        "message": "Синхронизация запущена в фоне",
    }
