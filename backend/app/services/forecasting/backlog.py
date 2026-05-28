"""
Backlog: фичи которые подсмотрели у nepsell и хотим внедрить позже.

ЭТО НЕ ЗАГЛУШКИ-ДЛЯ-СЕЙЧАС. Это место в коде, чтобы при возврате к задаче
было ясно где должна жить новая логика.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GeographyDistribution:
    """География заказов по кластерам Ozon (куда заказывают, не откуда отгружают).

    Дает локализационный индекс: какие города покупают больше, где разместить
    дополнительный склад FBO/FBS, какой кластер тестировать рекламой.

    TODO: считать из `orders.cluster_to` (уже синхронизируем).
    """

    pass


def compute_geography_index(account_id: str) -> GeographyDistribution:
    """ЗАГЛУШКА. Реальная имплементация:

    SELECT cluster_to, COUNT(*), SUM(total_amount)
    FROM orders
    WHERE ozon_account_id = $1 AND order_created_at > now() - interval '90 days'
    GROUP BY cluster_to ORDER BY SUM(total_amount) DESC

    Затем нормализовать в индекс 0..1 и сопоставить с market_competitor_prices
    (есть ли конкуренты в этих кластерах).
    """
    raise NotImplementedError("geography_index — Phase 5 backlog")


@dataclass
class AssociatedConversions:
    """Ассоциированные конверсии: клик по рекламе одного товара → покупка другого.

    У Ozon Performance API есть search_promotion / sku-trade attribution, но
    собственная модель нужна для связки внутри одной сессии покупателя.

    TODO: требует session-level данных из /v1/analytics/data + ad_statistics
    с поправкой на atribution-window (3/7/14 дней).
    """

    pass


def compute_associated_conversions(account_id: str) -> AssociatedConversions:
    """ЗАГЛУШКА. Реальная имплементация требует:

    1. analytics_daily по item-level
    2. ad_statistics с product_id (у нас есть)
    3. session-level join — Ozon attribution-окно

    Phase 5+.
    """
    raise NotImplementedError("associated_conversions — Phase 5+ backlog")
