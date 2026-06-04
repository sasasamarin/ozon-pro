"""
/api/v1/procurement/quality — качество поставок.

Связывает SupplierOrder с Return через product_id:
показывает % возвратов по товарам каждого поставщика
+ топ проблемных поставщиков по доле брака.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, UTC

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User


router = APIRouter()


class SupplierQualityRow(BaseModel):
    supplier_id: str | None
    supplier_name: str
    products_count: int
    units_supplied: int
    units_returned: int
    return_rate_pct: float
    avg_lead_time_days: float | None
    overdue_orders: int          # сколько заказов пришло позже expected
    avg_overdue_days: float | None


class ProblemProductRow(BaseModel):
    product_id: str
    product_name: str
    offer_id: str
    supplier_name: str | None
    units_supplied: int
    units_returned: int
    return_rate_pct: float
    top_reason: str | None


class QualityResp(BaseModel):
    period_from: str
    period_to: str
    suppliers: list[SupplierQualityRow]
    problem_products: list[ProblemProductRow]
    summary: dict


@router.get("/quality", response_model=QualityResp)
async def procurement_quality(
    days: int = Query(180, ge=30, le=730),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QualityResp:
    """Качество поставок: брак/возвраты по поставщикам и SKU."""
    df = date.today() - timedelta(days=days)
    uid = str(current_user.id)
    cid = str(current_user.company_id)

    # 1) Агрегация по поставщикам
    sup_rows = (await db.execute(text("""
        WITH supplied AS (
            SELECT
                so.supplier_id::text,
                so.product_id,
                SUM(so.qty) AS units,
                COUNT(*) AS orders,
                AVG(EXTRACT(EPOCH FROM (so.received_date - so.order_date)) / 86400)
                  FILTER (WHERE so.received_date IS NOT NULL) AS lead,
                COUNT(*) FILTER (
                    WHERE so.received_date IS NOT NULL
                      AND so.expected_date IS NOT NULL
                      AND so.received_date > so.expected_date
                ) AS overdue,
                AVG(EXTRACT(EPOCH FROM (so.received_date - so.expected_date)) / 86400)
                  FILTER (WHERE so.received_date > so.expected_date) AS avg_overdue
            FROM supplier_orders so
            WHERE so.user_id = :uid AND so.order_date >= :df
            GROUP BY so.supplier_id, so.product_id
        ),
        returns_agg AS (
            SELECT r.product_id, SUM(r.quantity) AS units_ret
            FROM returns r
            JOIN ozon_accounts oa ON oa.id = r.ozon_account_id
            WHERE oa.company_id = :cid AND r.return_date >= :df
            GROUP BY r.product_id
        )
        SELECT
            s.supplier_id,
            COALESCE(sup.name, '— без поставщика —') AS supplier_name,
            COUNT(DISTINCT s.product_id)::int AS products_count,
            COALESCE(SUM(s.units), 0)::int AS units_supplied,
            COALESCE(SUM(ra.units_ret), 0)::int AS units_returned,
            AVG(s.lead) AS lead,
            COALESCE(SUM(s.overdue), 0)::int AS overdue_orders,
            AVG(s.avg_overdue) AS avg_overdue
        FROM supplied s
        LEFT JOIN suppliers sup ON sup.id::text = s.supplier_id
        LEFT JOIN returns_agg ra ON ra.product_id = s.product_id
        GROUP BY s.supplier_id, sup.name
        ORDER BY units_supplied DESC
    """), {"uid": uid, "cid": cid, "df": df})).all()

    suppliers = []
    total_supplied = total_returned = 0
    for r in sup_rows:
        units = int(r.units_supplied or 0)
        ret = int(r.units_returned or 0)
        rate = (ret / units * 100) if units else 0
        total_supplied += units
        total_returned += ret
        suppliers.append(SupplierQualityRow(
            supplier_id=r.supplier_id,
            supplier_name=r.supplier_name,
            products_count=int(r.products_count or 0),
            units_supplied=units,
            units_returned=ret,
            return_rate_pct=round(rate, 2),
            avg_lead_time_days=round(float(r.lead), 1) if r.lead else None,
            overdue_orders=int(r.overdue_orders or 0),
            avg_overdue_days=round(float(r.avg_overdue), 1) if r.avg_overdue else None,
        ))

    # 2) Проблемные SKU (топ по % возвратов)
    prob_rows = (await db.execute(text("""
        WITH supplied AS (
            SELECT so.product_id,
                   SUM(so.qty) AS units,
                   MIN(sup.name) AS sup_name
            FROM supplier_orders so
            LEFT JOIN suppliers sup ON sup.id = so.supplier_id
            WHERE so.user_id = :uid AND so.order_date >= :df
            GROUP BY so.product_id
        ),
        returns_agg AS (
            SELECT r.product_id, SUM(r.quantity) AS units_ret,
                   MODE() WITHIN GROUP (ORDER BY r.return_reason) AS top_reason
            FROM returns r
            JOIN ozon_accounts oa ON oa.id = r.ozon_account_id
            WHERE oa.company_id = :cid AND r.return_date >= :df
            GROUP BY r.product_id
        )
        SELECT s.product_id::text,
               p.name AS pname, p.offer_id,
               s.sup_name,
               s.units AS supplied,
               COALESCE(ra.units_ret, 0) AS returned,
               ra.top_reason
        FROM supplied s
        LEFT JOIN products p ON p.id = s.product_id
        LEFT JOIN returns_agg ra ON ra.product_id = s.product_id
        WHERE s.units > 0
        ORDER BY (COALESCE(ra.units_ret, 0) * 1.0 / NULLIF(s.units, 0)) DESC NULLS LAST
        LIMIT 20
    """), {"uid": uid, "cid": cid, "df": df})).all()

    problem_products = [
        ProblemProductRow(
            product_id=r.product_id,
            product_name=r.pname or "(удалён)",
            offer_id=r.offer_id or "",
            supplier_name=r.sup_name,
            units_supplied=int(r.supplied or 0),
            units_returned=int(r.returned or 0),
            return_rate_pct=round(
                (int(r.returned or 0) / int(r.supplied or 1)) * 100, 2
            ),
            top_reason=r.top_reason,
        )
        for r in prob_rows
    ]

    overall_rate = (total_returned / total_supplied * 100) if total_supplied else 0
    return QualityResp(
        period_from=df.isoformat(),
        period_to=date.today().isoformat(),
        suppliers=suppliers,
        problem_products=problem_products,
        summary={
            "total_supplied": total_supplied,
            "total_returned": total_returned,
            "overall_return_rate_pct": round(overall_rate, 2),
            "suppliers_count": len(suppliers),
            "note": (
                "% возврата = возвраты от покупателей за период / закупленных единиц "
                "за период. Не различает «дефект» и «не подошёл», нужно фильтровать по reason."
            ),
        },
    )
