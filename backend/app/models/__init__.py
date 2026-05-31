"""
Все модели в одном месте для импорта.
Используется Alembic и приложением для регистрации всех таблиц.
"""
from app.db.base import Base  # noqa: F401

# Phase 1
from app.models.ad import (  # noqa: F401
    AdCampaign,
    AdCampaignProduct,
    AdCampaignState,
    AdCampaignType,
    AdStatistics,
)
from app.models.company import Company, Role, RoleName, User  # noqa: F401
from app.models.marker import AuditLog, Marker, MarkerType  # noqa: F401
from app.models.marketplace import (  # noqa: F401
    Cancellation,
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
    TransactionCategory,
)
from app.models.ozon_account import (  # noqa: F401
    OzonAccount,
    OzonAccountStatus,
    OzonPremiumTier,
    SyncLog,
    SyncStatus,
)
from app.models.product import PriceHistory, Product, Stock  # noqa: F401

# Phase 2
from app.models.ai import (  # noqa: F401
    AIChat,
    AIMessage,
    AIMessageRole,
    AIModel,
    AIUsageMonthly,
)
from app.models.alert import (  # noqa: F401
    AlertHistory,
    AlertMarkerType,
    AlertRule,
    AlertSeverity,
    Notification,
)
from app.models.communications import Chat, ChatMessage, ChatMessageSender  # noqa: F401
from app.models.cost import (  # noqa: F401
    CostConfidence,
    CostImportLog,
    CostSource,
    PendingCost,
    ProductCostHistory,
    Supplier,
    SupplierOrder,
    SupplierOrderStatus,
)
from app.models.email import EmailLog, EmailStatus, EmailTemplate  # noqa: F401
from app.models.expense import ExpenseCategory, ExternalExpense  # noqa: F401
from app.models.financing import (  # noqa: F401
    FinancingMovementType,
    FinancingProductType,
    FinancingSource,
    FinancingStatus,
    OzonFinancing,
    OzonFinancingMovement,
)
from app.models.market import (  # noqa: F401
    CrossPlatform,
    MarketCompetitor,
    MarketCompetitorPrice,
    MarketCrossPlatform,
    MarketSearchQuery,
    MarketTrendsDaily,
)
from app.models.procurement import (  # noqa: F401
    ForecastConfidence,
    ForecastStrategy,
    ProductSupplyParams,
    SalesVelocityCache,
    TrendSignal,
)
from app.models.reports import (  # noqa: F401
    AccountBalanceSnapshot,
    FinancialReport,
    FinancialReportStatus,
    FinancialReportType,
    ManualReconciliation,
    ManualReconciliationFileType,
    ManualReconciliationLine,
    ManualReconciliationStatus,
    Reconciliation,
    ReconciliationLineStatus,
    ReconciliationStatus,
)
from app.models.category_tree import OzonCategoryTree  # noqa: F401
from app.models.team import (  # noqa: F401
    CompanyMember,
    InvitationStatus,
    MemberAccountAccess,
    MemberRole,
    MemberStatus,
    TeamInvitation,
)


__all__ = [
    "Base",
    # Phase 1
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
    "TransactionCategory",
    "AnalyticsDaily",
    "Marker",
    "MarkerType",
    "AuditLog",
    "Return",
    "RealizationLine",
    "Review",
    "Question",
    "Cancellation",
    "AdCampaign",
    "AdCampaignProduct",
    "AdCampaignType",
    "AdCampaignState",
    "AdStatistics",
    # Phase 2 — себестоимость
    "Supplier",
    "SupplierOrder",
    "SupplierOrderStatus",
    "ProductCostHistory",
    "CostImportLog",
    "PendingCost",
    "ExternalExpense",
    "ExpenseCategory",
    "CostSource",
    "CostConfidence",
    # Phase 2 — финансовые продукты Ozon
    "OzonFinancing",
    "OzonFinancingMovement",
    "FinancingProductType",
    "FinancingStatus",
    "FinancingSource",
    "FinancingMovementType",
    # Phase 2 — представления денег + сверка
    "FinancialReport",
    "FinancialReportType",
    "FinancialReportStatus",
    "AccountBalanceSnapshot",
    "Reconciliation",
    "ReconciliationStatus",
    "ManualReconciliation",
    "ManualReconciliationFileType",
    "ManualReconciliationStatus",
    "ManualReconciliationLine",
    "ReconciliationLineStatus",
    # Phase 2 — market intelligence
    "MarketCompetitor",
    "MarketCompetitorPrice",
    "MarketSearchQuery",
    "MarketCrossPlatform",
    "MarketTrendsDaily",
    "CrossPlatform",
    # Phase 2 — communications
    "Chat",
    "ChatMessage",
    "ChatMessageSender",
    # Phase 2 — team
    "CompanyMember",
    "TeamInvitation",
    "MemberAccountAccess",
    "MemberRole",
    "MemberStatus",
    "InvitationStatus",
    # Phase 2 — AI
    "AIUsageMonthly",
    "AIChat",
    "AIMessage",
    "AIModel",
    "AIMessageRole",
    # Phase 2 — alerts
    "AlertRule",
    "AlertHistory",
    "Notification",
    "AlertMarkerType",
    "AlertSeverity",
    # Phase 2 — email
    "EmailLog",
    "EmailStatus",
    "EmailTemplate",
    # Phase 2 — procurement / forecasting
    "ProductSupplyParams",
    "SalesVelocityCache",
    "ForecastStrategy",
    "TrendSignal",
    "ForecastConfidence",
]
