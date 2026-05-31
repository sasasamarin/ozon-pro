"""
Клиент Озон Seller API.

Особенности:
- Async (httpx)
- Token-bucket rate-limit (per-client = per-account)
- Retry-After parsing: если Ozon ответил 429 с заголовком, ждём ровно столько
- Шифрование API ключей в БД, расшифровка при создании клиента
"""
import asyncio
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
)

from app.core.config import settings
from app.core.logging import log


# ============================================================
# Rate-limit primitive: token bucket
# ============================================================


class TokenBucket:
    """Простой token-bucket с пополнением `rate` токенов/сек и `capacity` burst.

    async-safe (asyncio.Lock). На каждый запрос делается `await acquire()` —
    если токенов хватает, возвращается мгновенно; иначе спит ровно столько,
    сколько нужно для накопления.
    """

    __slots__ = ("rate", "capacity", "tokens", "_last", "_lock")

    def __init__(self, *, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, n: int = 1) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last
                self._last = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                if self.tokens >= n:
                    self.tokens -= n
                    return
                wait = (n - self.tokens) / self.rate
                # Освобождаем lock на время сна — не пользуемся им из-под себя.
                # На практике acquire вызывается из одной таски, конкурентных
                # acquire в рамках одного клиента обычно нет; для надёжности —
                # sleep ВНУТРИ lock'а, чтобы tokens не съели рядом.
                await asyncio.sleep(wait)


def _parse_retry_after(header: str | None) -> float | None:
    """Парсит заголовок Retry-After. Поддерживаем секунды (наиболее частый формат)."""
    if not header:
        return None
    s = header.strip()
    try:
        v = float(s)
        return v if v >= 0 else None
    except ValueError:
        # HTTP-date — редкость для rate-limit, не парсим
        return None


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
    """429 от Ozon. retry_after — сколько секунд просили подождать."""

    def __init__(
        self,
        message: str = "Превышен лимит запросов",
        *,
        retry_after: float | None = None,
        status_code: int | None = 429,
        response_data: dict | None = None,
    ):
        super().__init__(message, status_code=status_code, response_data=response_data)
        self.retry_after = retry_after


def _rate_limit_wait(retry_state) -> float:
    """tenacity-wait: если знаем Retry-After, ждём его; иначе exponential 2→30 сек.

    Защита от тонкой ситуации: Retry-After=0 → ждём минимум 1 секунду, чтобы
    не зацикливаться.
    """
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, OzonRateLimitError) and exc.retry_after is not None:
        return max(1.0, float(exc.retry_after))
    attempt = max(1, retry_state.attempt_number)
    # Экспоненциальный backoff: 2, 4, 8, 16, 30 (cap)
    return float(min(30, 2 ** attempt))


class OzonSellerClient:
    """
    Клиент для Озон Seller API.

    Использование:
        client = OzonSellerClient(client_id="123", api_key="abc")
        products = await client.get_products()
    """

    # Default-лимиты для Seller API. Документация Ozon — около 100 RPS на seller,
    # некоторые endpoint'ы строже. Берём 80 с запасом + burst 20 + 8 concurrent.
    DEFAULT_RATE = 80.0
    DEFAULT_BURST = 20
    DEFAULT_CONCURRENCY = 8

    def __init__(
        self,
        client_id: str,
        api_key: str,
        base_url: str | None = None,
        timeout: float = 60.0,
        *,
        rate: float | None = None,
        burst: int | None = None,
        concurrency: int | None = None,
    ):
        self.client_id = client_id
        self.api_key = api_key
        self.base_url = base_url or settings.OZON_API_BASE_URL
        self.timeout = timeout

        self._client: httpx.AsyncClient | None = None
        self._bucket = TokenBucket(
            rate=rate or self.DEFAULT_RATE,
            capacity=burst or self.DEFAULT_BURST,
        )
        self._sema = asyncio.Semaphore(concurrency or self.DEFAULT_CONCURRENCY)

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
        stop=stop_after_attempt(5),
        wait=_rate_limit_wait,
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
        """Сделать запрос к Озон API с rate-limit + retry."""
        if not self._client:
            raise RuntimeError("Client must be used as async context manager")

        async with self._sema:
            await self._bucket.acquire()

            log.info(
                "ozon_api_request",
                method=method,
                endpoint=endpoint,
                client_id=self.client_id[:8] + "...",
            )

            try:
                response = await self._client.request(
                    method=method,
                    url=endpoint,
                    json=json,
                    params=params,
                )

                if response.status_code == 401:
                    raise OzonAuthError(
                        "Неверные API ключи",
                        status_code=401,
                        response_data=response.json() if response.content else {},
                    )

                if response.status_code == 429:
                    ra = _parse_retry_after(response.headers.get("Retry-After"))
                    log.warning(
                        "ozon_api_rate_limited",
                        endpoint=endpoint,
                        retry_after=ra,
                    )
                    raise OzonRateLimitError(
                        f"429 от Ozon, Retry-After={ra}",
                        retry_after=ra,
                    )

                # 5xx gateway-ошибки от Ozon — transient, ретраим через тот же канал.
                if response.status_code in (502, 503, 504):
                    ra = _parse_retry_after(response.headers.get("Retry-After"))
                    log.warning(
                        "ozon_api_gateway_error",
                        endpoint=endpoint,
                        status=response.status_code,
                    )
                    raise OzonRateLimitError(
                        f"{response.status_code} gateway",
                        retry_after=ra or 5.0,
                        status_code=response.status_code,
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

        По умолчанию фильтр пустой → Ozon берёт visibility=VISIBLE, отдаст
        только видимые товары. Передай {"visibility": "ALL"} чтобы вытянуть
        ВСЁ (включая архивные/невидимые) — нужно для синка.
        """
        payload = {
            "limit": limit,
            "last_id": last_id,
            "filter": filter_params or {},
        }
        return await self._request("POST", "/v3/product/list", json=payload)

    async def get_product_info(
        self,
        *,
        offer_ids: list[str] | None = None,
        product_ids: list[int] | None = None,
        sku: list[int] | None = None,
    ) -> dict:
        """
        Получить детальную информацию о товарах (батч).

        Endpoint: POST /v3/product/info/list

        Передай ОДИН из массивов (offer_ids / product_ids / sku) — макс 1000
        элементов за запрос. Возвращает name, primary_image, images, barcode,
        category и др. — используется для enrichment'а после /v3/product/list.

        Ozon принимает имя поля product_id (camelCase в payload — нет, snake_case).
        """
        payload: dict[str, Any] = {}
        if offer_ids:
            payload["offer_id"] = offer_ids
        if product_ids:
            payload["product_id"] = product_ids
        if sku:
            payload["sku"] = sku
        return await self._request(
            "POST",
            "/v3/product/info/list",
            json=payload,
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

    # ============================================
    # ВОЗВРАТЫ / ОТМЕНЫ / РЕАЛИЗАЦИЯ / СКЛАДЫ
    # ============================================

    async def get_fbo_returns(
        self,
        *,
        offset: int = 0,
        limit: int = 1000,
    ) -> dict:
        """Возвраты FBO. Endpoint: POST /v1/returns/list

        Ozon ждёт return_schema STRING ("Fbo"/"Fbs"), не массив — раньше слали
        ["FBO"] и получали 400 «invalid value for string field return_schema».
        """
        return await self._request(
            "POST",
            "/v1/returns/list",
            json={
                "filter": {"return_schema": "Fbo"},
                "limit": limit,
                "offset": offset,
            },
        )

    async def get_fbs_returns(
        self,
        *,
        offset: int = 0,
        limit: int = 1000,
    ) -> dict:
        """Возвраты FBS. Endpoint: POST /v1/returns/list"""
        return await self._request(
            "POST",
            "/v1/returns/list",
            json={
                "filter": {"return_schema": "Fbs"},
                "limit": limit,
                "offset": offset,
            },
        )

    async def get_realization(self, *, month: int, year: int) -> dict:
        """Отчёт о реализации Ozon за месяц.

        Endpoint: POST /v2/finance/realization
        Требует premium_plus или premium_pro.
        """
        return await self._request(
            "POST",
            "/v2/finance/realization",
            json={"month": str(month), "year": str(year), "language": "RU"},
        )

    async def get_stock_on_warehouses(
        self,
        *,
        limit: int = 1000,
        offset: int = 0,
        warehouse_type: str = "ALL",
    ) -> dict:
        """Остатки по складам Ozon (FBO).

        Endpoint: POST /v2/analytics/stock_on_warehouses
        warehouse_type: ALL / FULFILLMENT / CROSSDOCK
        """
        return await self._request(
            "POST",
            "/v2/analytics/stock_on_warehouses",
            json={"limit": limit, "offset": offset, "warehouse_type": warehouse_type},
        )

    # ============================================
    # ОТЗЫВЫ / ВОПРОСЫ / ЧАТЫ — premium_pro only
    # ============================================

    async def get_reviews(
        self,
        *,
        last_id: str = "",
        limit: int = 100,
        status: str = "ALL",
        sort_dir: str = "DESC",
    ) -> dict:
        """Список отзывов. Требует premium_pro.

        Endpoint: POST /v1/review/list
        """
        return await self._request(
            "POST",
            "/v1/review/list",
            json={
                "last_id": last_id,
                "limit": limit,
                "sort_dir": sort_dir,
                "status": status,
            },
        )

    async def get_questions(
        self,
        *,
        last_id: str = "",
        limit: int = 100,
    ) -> dict:
        """Список вопросов о товарах. Требует premium_pro.

        Endpoint: POST /v1/question/list
        """
        return await self._request(
            "POST",
            "/v1/question/list",
            json={"last_id": last_id, "limit": limit},
        )

    async def get_chats(
        self,
        *,
        from_id: str = "",
        limit: int = 100,
        filter_: dict | None = None,
    ) -> dict:
        """Список чатов. Endpoint: POST /v3/chat/list

        Ozon v3 chat внутренне зовёт устаревший RPC, который требует поле
        `cursor` всегда (даже пустую строку); без него отдаёт «Cursor value is
        incorrect». Передаём `cursor` всегда + базовый filter.
        """
        eff_filter = filter_ or {"chat_status": "All"}
        payload: dict[str, Any] = {
            "limit": limit,
            "filter": eff_filter,
            "cursor": from_id or "",
        }
        return await self._request("POST", "/v3/chat/list", json=payload)

    async def get_chat_history(
        self,
        *,
        chat_id: str,
        from_message_id: str = "",
        limit: int = 100,
    ) -> dict:
        """История сообщений в чате.

        Endpoint: POST /v3/chat/history
        """
        payload: dict[str, Any] = {"chat_id": chat_id, "limit": limit, "direction": "Forward"}
        if from_message_id:
            payload["from_message_id"] = from_message_id
        return await self._request("POST", "/v3/chat/history", json=payload)

    # ============================================
    # БАЛАНС
    # ============================================

    async def get_payouts_total(self) -> dict:
        """Сумма выплат за всё время + следующая ожидаемая выплата.

        Endpoint: GET /v1/finance/payouts/total (или POST в зависимости от версии)
        """
        return await self._request("GET", "/v1/finance/payouts/total")

    # ============================================
    # КАТЕГОРИИ
    # ============================================

    async def get_description_category_tree(self, language: str = "DEFAULT") -> dict:
        """Полное дерево категорий каталога Ozon.

        Endpoint: POST /v1/description-category/tree.
        Возвращает вложенную структуру: description_category → children + types (листья).
        Глобальный справочник (один на весь Ozon), не зависит от кабинета.
        """
        return await self._request(
            "POST", "/v1/description-category/tree", json={"language": language}
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
