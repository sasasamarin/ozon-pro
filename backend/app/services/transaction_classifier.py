"""
Классификатор Ozon transaction services по корзинам P&L.

Ozon в `services[]` передаёт массив `{"name": "MarketplaceServiceItem...", "price": -123.45}`.
Имена услуг закодированы в стиле PascalCase + Camel — мы группируем их в 8
финансовых корзин для honest P&L breakdown:

  delivery_to_customer  — прямая логистика к покупателю
  return_logistics      — возвратная логистика (после доставки, не дошёл, drop-off)
  last_mile             — последняя миля (курьер / PVZ)
  storage               — хранение и движение по складам
  placement             — упаковка / drop-off / размещение
  acquiring             — эквайринг (банковский процессинг)
  advertising           — реклама (если кодируется в services, обычно sale_commission)
  utilization           — утилизация
  fine                  — штрафы

Возвращаем (bucket_name, signed_amount). Ozon хранит расходы как
отрицательные числа в `price`; мы приводим к ABS-положительным при записи в
колонку, чтобы UI breakdown отображал как «сумма расхода».

ПРИНЦИП FAIL-OPEN: неизвестная услуга → bucket=None (никуда не пишем, но
в `services` JSON сохраняется для drill-down). Это не теряет данные.
"""
from __future__ import annotations

# Группировка имён → колонка в Transaction
_BUCKET_MAP: dict[str, str] = {
    # Direct flow (delivery to customer)
    "MarketplaceServiceItemDirectFlowLogistic":            "delivery_to_customer",
    "MarketplaceServiceItemDirectFlowLogisticVDC":         "delivery_to_customer",
    "MarketplaceServiceItemDelivToCustomer":               "delivery_to_customer",
    "MarketplaceServiceItemDeliveryToHandoverPlaceOzon":   "delivery_to_customer",

    # Last mile (доставка курьером / самовывоз)
    "MarketplaceServiceItemRedistributionLastMileCourier": "last_mile",
    "MarketplaceServiceItemRedistributionLastMilePVZ":     "last_mile",

    # Return flow (всё связанное с возвратами)
    "MarketplaceServiceItemReturnFlowLogistic":            "return_logistics",
    "MarketplaceServiceItemReturnNotDelivToCustomer":      "return_logistics",
    "MarketplaceServiceItemReturnAfterDelivToCustomer":    "return_logistics",
    "MarketplaceServiceItemRedistributionReturnsPVZ":      "return_logistics",
    "MarketplaceServiceItemReturnPartGoodsCustomer":       "return_logistics",
    "MarketplaceServiceSellerReturnsCargoAssortment":      "return_logistics",

    # Placement / drop-off / packaging
    "MarketplaceServiceItemDropoffPVZ":                    "placement",
    "MarketplaceServiceItemDropoffPPZ":                    "placement",
    "MarketplaceServiceItemRedistributionDropOffAppz":     "placement",
    "MarketplaceServiceItemRedistributionDropOffApvz":     "placement",
    "MarketplaceServiceItemPackageRedistribution":         "placement",
    "MarketplaceServiceItemPackageMaterialsProvision":     "placement",

    # Storage (хранение и движение по складам)
    "MarketplaceServiceItemTemporaryStorage":              "storage",
    "MarketplaceServiceItemTemporaryStorageRedistribution": "storage",
    "MarketplaceServiceProductMovementFromWarehouse":      "storage",

    # Acquiring (эквайринг + рассрочка как financial processing)
    "MarketplaceRedistributionOfAcquiringOperation":       "acquiring",
    "MarketplaceServiceItemInstallment":                   "acquiring",

    # Utilization
    "MarketplaceServiceItemDisposalDetailed":              "utilization",
}


# Все имена бакетов (для тестов и UI-breakdown)
BUCKETS = (
    "delivery_to_customer",
    "return_logistics",
    "last_mile",
    "storage",
    "placement",
    "acquiring",
    "advertising",
    "utilization",
    "fine",
)


def classify_service(name: str | None) -> str | None:
    """Возвращает имя bucket-колонки или None если услуга неизвестна."""
    if not name:
        return None
    return _BUCKET_MAP.get(name)


def aggregate_services(services: list[dict] | None) -> dict[str, float]:
    """services[] → dict[bucket → ABS-positive amount].

    Сумма всех элементов одной корзины, в положительных рублях. Неизвестные
    услуги игнорируются (видимы в raw `services` JSON).
    """
    result: dict[str, float] = {b: 0.0 for b in BUCKETS}
    if not services:
        return result
    for s in services:
        if not isinstance(s, dict):
            continue
        bucket = classify_service(s.get("name"))
        if not bucket:
            continue
        price = s.get("price")
        if price is None:
            continue
        try:
            result[bucket] += abs(float(price))
        except (TypeError, ValueError):
            continue
    return result
