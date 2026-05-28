"""
Все модели в одном месте для импорта.
Используется Alembic и приложением для регистрации всех таблиц.
"""
from app.db.base import Base  # noqa: F401
from app.models.ad import (  # noqa: F401
    AdCampaign,
    AdCampaignState,
    AdCampaignType,
    AdStatistics,
)
from app.models.company import Company, Role, RoleName, User  # noqa: F401
from app.models.marker import AuditLog, Marker, MarkerType  # noqa: F401
from app.models.marketplace import (  # noqa: F401
    Question,
    RealizationLine,
    Return,
    Review,
)
from app.models.order import (  # noqa: F401
    AnalyticsDaily,
    Order,
    OrderItem,
    OrderStatus,
    OrderType,
    Transaction,
)
from app.models.ozon_account import (  # noqa: F401
    OzonAccount,
    OzonAccountStatus,
    OzonPremiumTier,
    SyncLog,
    SyncStatus,
)
from app.models.product import PriceHistory, Product, Stock  # noqa: F401


__all__ = [
    "Base",
    "Company",
    "User",
    "Role",
    "RoleName",
    "OzonAccount",
    "OzonAccountStatus",
    "OzonPremiumTier",
    "SyncLog",
    "SyncStatus",
    "Product",
    "PriceHistory",
    "Stock",
    "Order",
    "OrderItem",
    "OrderStatus",
    "OrderType",
    "Transaction",
    "AnalyticsDaily",
    "Marker",
    "MarkerType",
    "AuditLog",
    "Return",
    "RealizationLine",
    "Review",
    "Question",
    "AdCampaign",
    "AdCampaignType",
    "AdCampaignState",
    "AdStatistics",
]
