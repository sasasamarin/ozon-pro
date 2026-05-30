"""
Синхронизация финансовых продуктов Ozon — наполняет ozon_financing +
ozon_financing_movements из transactions.

Юзер: "Ozon удерживает выплаты по кредитам/рассрочкам". В transactions
видны операции:
  - OperationMarketplaceServiceEarlyPaymentAccrual    → early_payout
    (досрочная выплата за %)
  - OperationMarketplaceFlexiblePaymentSchedule       → commission_installment
    (гибкий график оплаты комиссии)

Для каждого operation_type + ozon_account_id создаём ОДИН OzonFinancing
parent, и каждую транзакцию подкладываем как WITHHOLDING-movement.
Idempotent: повторный запуск не дублирует movements (по (time, fin_id, seq)).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.models import (
    FinancingMovementType,
    FinancingProductType,
    FinancingStatus,
    OzonAccount,
    OzonFinancing,
    OzonFinancingMovement,
    Transaction,
    User,
)
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import (
    get_active_accounts,
    run_celery_async,
    track_sync_log,
)


# Маппинг operation_type → FinancingProductType
_FIN_OP_TO_PRODUCT = {
    "OperationMarketplaceServiceEarlyPaymentAccrual": FinancingProductType.EARLY_PAYOUT.value,
    "OperationMarketplaceFlexiblePaymentSchedule":    FinancingProductType.COMMISSION_INSTALLMENT.value,
}


@celery_app.task(name="app.workers.tasks.sync_financing.sync_all_financing")
def sync_all_financing(account_id: str | None = None) -> dict:
    """Собираем OzonFinancing + movements из transactions для всех кабинетов."""
    return run_celery_async(_sync_all_financing_async, account_id)


async def _sync_all_financing_async(
    SessionLocal: async_sessionmaker[AsyncSession],
    account_id: str | None = None,
) -> dict:
    async with SessionLocal() as db:
        if account_id:
            acc = (await db.execute(
                select(OzonAccount).where(
                    OzonAccount.id == uuid.UUID(account_id),
                    OzonAccount.deleted_at.is_(None),
                )
            )).scalar_one_or_none()
            accounts = [acc] if acc else []
        else:
            accounts = await get_active_accounts(db)

    log.info("sync_financing_started", accounts=len(accounts))
    results = await asyncio.gather(
        *[_sync_one_account(SessionLocal, a.id) for a in accounts],
        return_exceptions=True,
    )
    success = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "success")
    total_mv = sum(r.get("movements", 0) for r in results if isinstance(r, dict))
    return {
        "total": len(accounts),
        "success": success,
        "failed": len(results) - success,
        "movements_created": total_mv,
    }


async def _sync_one_account(
    SessionLocal: async_sessionmaker[AsyncSession],
    account_id: uuid.UUID,
) -> dict:
    async with SessionLocal() as db:
        account = (await db.execute(
            select(OzonAccount).where(OzonAccount.id == account_id)
        )).scalar_one_or_none()
        if not account:
            return {"status": "failed", "error": "account_not_found"}

        # Owner user_id (нужен для OzonFinancing FK)
        owner_id = (await db.execute(
            select(User.id).where(User.company_id == account.company_id).limit(1)
        )).scalar_one_or_none()
        if not owner_id:
            return {"status": "failed", "error": "no_user_in_company"}

        try:
            async with track_sync_log(db, account.id, "sync_financing") as stats:
                movements_created = 0

                # === Группируем транзакции по operation_type
                tx_rows = (await db.execute(
                    select(
                        Transaction.id.label("tx_id"),
                        Transaction.operation_type,
                        Transaction.time,
                        Transaction.operation_date,
                        Transaction.amount,
                    ).where(
                        Transaction.ozon_account_id == account_id,
                        Transaction.operation_type.in_(list(_FIN_OP_TO_PRODUCT.keys())),
                    ).order_by(Transaction.time)
                )).all()

                # Для каждого op_type — find-or-create OzonFinancing parent
                fin_by_optype: dict[str, OzonFinancing] = {}
                for op_type, product_type in _FIN_OP_TO_PRODUCT.items():
                    # Берём первую транзакцию этого типа — issued_at
                    first_tx = next((r for r in tx_rows if r.operation_type == op_type), None)
                    if not first_tx:
                        continue

                    fin = (await db.execute(
                        select(OzonFinancing).where(
                            OzonFinancing.ozon_account_id == account_id,
                            OzonFinancing.product_type == product_type,
                        )
                    )).scalar_one_or_none()

                    issued_at_dt = first_tx.time or (
                        datetime.combine(first_tx.operation_date, datetime.min.time(), tzinfo=UTC)
                        if first_tx.operation_date else datetime.now(UTC)
                    )

                    if not fin:
                        # Suma всех транзакций как principal — приблизительно
                        principal = float(sum(abs(float(t.amount or 0))
                                              for t in tx_rows if t.operation_type == op_type))
                        fin = OzonFinancing(
                            ozon_account_id=account_id,
                            user_id=owner_id,
                            product_type=product_type,
                            principal=principal,
                            interest_rate=None,
                            issued_at=issued_at_dt,
                            status=FinancingStatus.REPAYING.value,
                            source="ozon_api",
                            raw_data={"derived_from": op_type},
                        )
                        db.add(fin)
                        await db.flush()
                        stats.created += 1
                    else:
                        # обновляем principal по факту
                        principal = float(sum(abs(float(t.amount or 0))
                                              for t in tx_rows if t.operation_type == op_type))
                        fin.principal = principal
                        stats.updated += 1
                    fin_by_optype[op_type] = fin

                # === Каждую транзакцию → одна movement-строка (idempotent через PK)
                # PK movements = (time, financing_id, seq). seq = index в дне.
                # Дедуп: считаем seq как порядковый номер в группировке по дню+fin_id.
                movements_payload: list[dict] = []
                seq_by_key: dict[tuple, int] = {}
                for tx in tx_rows:
                    fin = fin_by_optype.get(tx.operation_type)
                    if not fin:
                        continue
                    if not tx.time:
                        continue
                    key = (tx.time.date(), fin.id)
                    seq_by_key.setdefault(key, 0)
                    seq = seq_by_key[key]
                    seq_by_key[key] += 1

                    amount = abs(float(tx.amount or 0))
                    if amount == 0:
                        continue

                    movements_payload.append({
                        "time": tx.time,
                        "financing_id": fin.id,
                        "seq": seq,
                        "movement_type": FinancingMovementType.WITHHOLDING.value,
                        "amount": amount,
                        # EarlyPaymentAccrual = % за досрочную выплату → P&L
                        # FlexiblePaymentSchedule = удержание комиссии → не P&L (это
                        # уже отражено в другом месте, мы тут только трекаем cashflow)
                        "affects_pnl": tx.operation_type == "OperationMarketplaceServiceEarlyPaymentAccrual",
                        "affects_cashflow": True,
                        "affects_debt": 0,
                        "raw_data": {
                            "tx_id": str(tx.tx_id),
                            "operation_type": tx.operation_type,
                        },
                    })

                if movements_payload:
                    stmt = pg_insert(OzonFinancingMovement).values(movements_payload)
                    # ON CONFLICT по PK (time, financing_id, seq) — idempotent
                    stmt = stmt.on_conflict_do_nothing(
                        index_elements=["time", "financing_id", "seq"]
                    )
                    await db.execute(stmt)
                    movements_created = len(movements_payload)

                stats.processed = len(tx_rows)
            await db.commit()
            return {"status": "success", "movements": movements_created}
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            log.exception("sync_financing_failed", account_id=str(account_id))
            return {"status": "failed", "error": str(e)}
