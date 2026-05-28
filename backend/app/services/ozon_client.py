"""
Клиент Озон Seller API.

Особенности:
- Async (httpx)
- Retry с exponential backoff при ошибках
- Логирование каждого запроса (для отладки)
- Шифрование API ключей в БД, расшифровка при создании клиента
- Rate limiting (учёт лимитов Озона)
"""
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.logging import log


class OzonAPIError(Exception):
    """Базовое исключение для ошибок Озон API."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_data: dict | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class OzonAuthError(OzonAPIError):
    """Ошибка авторизации (неверные API ключи)."""


class OzonRateLimitError(OzonAPIError):
    """Превышен лимит запросов."""


class OzonSellerClient:
    """
    Клиент для Озон Seller API.

    Использование:
        client = OzonSellerClient(client_id="123", api_key="abc")
        products = await client.get_products()
    """

    def __init__(
        self,
        client_id: str,
        api_key: str,
        base_url: str | None = None,
        timeout: float = 30.0,
    ):
        self.client_id = client_id
        self.api_key = api_key
        self.base_url = base_url or settings.OZON_API_BASE_URL
        self.timeout = timeout

        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "OzonSellerClient":
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "Client-Id": self.client_id,
                "Api-Key": self.api_key,
                "Content-Type": "application/json",
            },
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.NetworkError, OzonRateLimitError)),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """Сделать запрос к Озон API с retry."""
        if not self._client:
            raise RuntimeError("Client must be used as async context manager")

        log.info(
            "ozon_api_request",
            method=method,
            endpoint=endpoint,
            client_id=self.client_id[:8] + "...",  # частично, для безопасности
        )

        try:
            response = await self._client.request(
                method=method,
                url=endpoint,
                json=json,
                params=params,
            )

            # Обработка статусов
            if response.status_code == 401:
                raise OzonAuthError(
                    "Неверные API ключи",
                    status_code=401,
                    response_data=response.json() if response.content else {},
                )

            if response.status_code == 429:
                raise OzonRateLimitError(
                    "Превышен лимит запросов",
                    status_code=429,
                )

            response.raise_for_status()
            data = response.json()

            log.info(
                "ozon_api_response",
                endpoint=endpoint,
                status=response.status_code,
            )

            return data

        except httpx.HTTPStatusError as e:
            log.error(
                "ozon_api_error",
                endpoint=endpoint,
                status=e.response.status_code,
                body=e.response.text[:500],
            )
            raise OzonAPIError(
                f"Ошибка Озон API: {e.response.status_code}",
                status_code=e.response.status_code,
                response_data=e.response.json() if e.response.content else {},
            ) from e

    # ============================================
    # ТОВАРЫ
    # ============================================

    async def get_products(
        self,
        limit: int = 100,
        last_id: str = "",
        filter_params: dict | None = None,
    ) -> dict:
        """
        Получить список товаров.

        Endpoint: POST /v3/product/list
        Docs: https://docs.ozon.ru/api/seller/

        Ozon ВСЕГДА требует поле filter в payload (даже пустое):
        без него 400 «Request validation error: invalid ...Filter: value is required».
        """
        payload = {
            "limit": limit,
            "last_id": last_id,
            "filter": filter_params or {},
        }
        return await self._request("POST", "/v3/product/list", json=payload)

    async def get_product_info(self, sku_list: list[int]) -> dict:
        """
        Получить детальную информацию о товарах.

        Endpoint: POST /v3/product/info/list
        """
        return await self._request(
            "POST",
            "/v3/product/info/list",
            json={"sku": sku_list},
        )

    async def get_product_prices(
        self,
        limit: int = 100,
        cursor: str = "",
        filter_params: dict | None = None,
    ) -> dict:
        """
        Получить цены товаров + индекс цен.

        Endpoint: POST /v5/product/info/prices
        Это самая важная инфа: цены, СПП, индекс цен (выгодно/невыгодно).

        Ozon ВСЕГДА требует поле filter в payload (даже пустое):
        без него 400 «Request validation error: invalid ...Filter: value is required».
        """
        payload: dict[str, Any] = {
            "limit": limit,
            "cursor": cursor,
            "filter": filter_params or {},
        }
        return await self._request(
            "POST", "/v5/product/info/prices", json=payload
        )

    # ============================================
    # ОСТАТКИ
    # ============================================

    async def get_stocks(
        self,
        limit: int = 100,
        cursor: str = "",
        filter_params: dict | None = None,
    ) -> dict:
        """
        Получить остатки товаров.

        Endpoint: POST /v4/product/info/stocks
        Ozon ВСЕГДА требует поле filter в payload (даже пустое).
        """
        payload: dict[str, Any] = {
            "limit": limit,
            "cursor": cursor,
            "filter": filter_params or {},
        }
        return await self._request(
            "POST", "/v4/product/info/stocks", json=payload
        )

    # ============================================
    # ЗАКАЗЫ
    # ============================================

    async def get_fbo_orders(
        self,
        date_from: str,
        date_to: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        """
        Получить заказы FBO (склад Озона).

        Endpoint: POST /v2/posting/fbo/list
        """
        return await self._request(
            "POST",
            "/v2/posting/fbo/list",
            json={
                "dir": "DESC",
                "filter": {
                    "since": date_from,
                    "to": date_to,
                },
                "limit": limit,
                "offset": offset,
                "translit": True,
                "with": {
                    "analytics_data": True,
                    "financial_data": True,
                },
            },
        )

    async def get_fbs_orders(
        self,
        date_from: str,
        date_to: str,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        """
        Получить заказы FBS (свой склад).

        Endpoint: POST /v3/posting/fbs/list
        """
        return await self._request(
            "POST",
            "/v3/posting/fbs/list",
            json={
                "dir": "DESC",
                "filter": {
                    "since": date_from,
                    "to": date_to,
                },
                "limit": limit,
                "offset": offset,
                "with": {
                    "analytics_data": True,
                    "financial_data": True,
                },
            },
        )

    # ============================================
    # ФИНАНСЫ
    # ============================================

    async def get_transactions(
        self,
        date_from: str,
        date_to: str,
        page: int = 1,
        page_size: int = 1000,
        transaction_type: str = "all",
    ) -> dict:
        """
        Получить финансовые транзакции.

        Endpoint: POST /v3/finance/transaction/list
        """
        return await self._request(
            "POST",
            "/v3/finance/transaction/list",
            json={
                "filter": {
                    "date": {
                        "from": date_from,
                        "to": date_to,
                    },
                    "transaction_type": transaction_type,
                },
                "page": page,
                "page_size": page_size,
            },
        )

    # ============================================
    # АНАЛИТИКА
    # ============================================

    async def get_analytics(
        self,
        date_from: str,
        date_to: str,
        dimension: list[str],
        metrics: list[str],
        limit: int = 1000,
        offset: int = 0,
    ) -> dict:
        """
        Получить аналитику.

        Endpoint: POST /v1/analytics/data
        Метрики: revenue, ordered_units, hits_view_search, conv_tocart, etc.
        """
        return await self._request(
            "POST",
            "/v1/analytics/data",
            json={
                "date_from": date_from,
                "date_to": date_to,
                "dimension": dimension,
                "metrics": metrics,
                "limit": limit,
                "offset": offset,
            },
        )

    async def test_credentials(self) -> bool:
        """
        Проверка что API ключи валидные.

        Использует лёгкий метод (sellerinfo).
        """
        try:
            await self._request("POST", "/v1/seller/info", json={})
            return True
        except OzonAuthError:
            return False
        except Exception:
            return False
