"""
Агрегация ответа /v2/finance/realization → per-SKU weighted-avg.

Realization отдаёт МНОГО строк на один SKU за месяц (по rowNumber, каждая
строка = отдельная транзакция). Эта функция складывает их в один агрегат
на (sku, month):
- weighted_cp = SUM(price_per_instance × qty) / SUM(qty)
- qty_sold = SUM(quantity)
- qty_returned, bonus, standard_fee, returned_amount — суммы.

Поля payload:
- r["item"]["sku" | "offer_id" | "name"]
- r["seller_price_per_instance"] — цена что Ozon начислил продавцу
- r["delivery_commission"]["price_per_instance"] — СПП-цена покупателя
- r["delivery_commission"]["quantity"] — кол-во доставленных в этой транзакции
- r["delivery_commission"]["bonus"] — СПП-компенсация Ozon продавцу
- r["delivery_commission"]["standard_fee"] — комиссия Ozon
- r["return_commission"] — null или такая же структура (для возвратов)

Выделено отдельно от sync_marketplace для unit-тестирования: чистая функция
без БД, без I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def _safe_float(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class SkuAggregate:
    sku: int
    offer_id: str | None = None
    name: str | None = None
    qty_sold: int = 0
    qty_returned: int = 0
    sum_cp_qty: float = 0.0   # для weighted_cp
    sum_sp_qty: float = 0.0   # для weighted_sp
    sum_bonus: float = 0.0
    sum_fee: float = 0.0
    sum_amount_sold: float = 0.0
    sum_amount_returned: float = 0.0
    rows: int = 0

    @property
    def weighted_cp(self) -> float | None:
        """СПП-цена покупателя за единицу, взвешенно по qty."""
        return self.sum_cp_qty / self.qty_sold if self.qty_sold else None

    @property
    def weighted_sp(self) -> float | None:
        """Цена что Ozon начислил продавцу за единицу."""
        return self.sum_sp_qty / self.qty_sold if self.qty_sold else None


def aggregate_realization_rows(rows: list[dict]) -> dict[int, SkuAggregate]:
    """
    Свернуть rows из realization payload в один агрегат на SKU.

    Возвращает {sku: SkuAggregate}. SKU без quantity или без sku в payload —
    пропускаются.
    """
    per_sku: dict[int, SkuAggregate] = {}
    for r in rows:
        item = r.get("item") or {}
        sku = item.get("sku")
        if not sku:
            continue
        sku = int(sku)
        dc = r.get("delivery_commission") or {}
        cp = _safe_float(dc.get("price_per_instance"))
        qty = int(dc.get("quantity") or 0)
        sp = _safe_float(r.get("seller_price_per_instance"))
        rc = r.get("return_commission") or {}
        ret_qty = int(rc.get("quantity") or 0) if rc else 0
        ret_amount = _safe_float(rc.get("amount")) if rc else 0.0
        bonus = _safe_float(dc.get("bonus"))
        standard_fee = _safe_float(dc.get("standard_fee"))

        agg = per_sku.get(sku)
        if agg is None:
            agg = SkuAggregate(
                sku=sku,
                offer_id=item.get("offer_id"),
                name=item.get("name"),
            )
            per_sku[sku] = agg

        agg.sum_cp_qty += cp * qty
        agg.sum_sp_qty += sp * qty
        agg.qty_sold += qty
        agg.qty_returned += ret_qty
        agg.sum_bonus += bonus
        agg.sum_fee += standard_fee
        agg.sum_amount_sold += cp * qty
        agg.sum_amount_returned += ret_amount
        agg.rows += 1

    return per_sku
