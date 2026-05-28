"""
Клиент Ozon Performance API (реклама).

Особенности:
- OAuth client_credentials: POST /api/client/token → access_token живёт ~30 минут
- Токен кэшируется в OzonAccount.perf_access_token_encrypted (+ expires_at)
- Если кэшированный токен жив — используем его, иначе запрашиваем новый
- При 401 на запросе токен сбрасывается и запрашивается заново (один раз)
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import asyncio

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
)

from app.core.config import settings
from app.core.logging import log
from app.core.security import decrypt_secret, encrypt_secret
from app.models import OzonAccount
from app.services.ozon_client import (
    OzonAPIError,
    OzonAuthError,
    OzonRateLimitError,
    TokenBucket,
    _parse_retry_after,
    _rate_limit_wait,
)

# Safety margin — refresh token этот промежуток времени до фактической истечения
_TOKEN_REFRESH_MARGIN = timedelta(seconds=60)


class OzonPerfNotConfigured(OzonAPIError):
    """Performance API ключи не заполнены — кабинет работает только по Seller API."""


class OzonPerformanceClient:
    """
    Клиент для Ozon Performance API.

    Использование:
        async with OzonPerformanceClient(account, db) as client:
            campaigns = await client.get_campaigns()

    Внутри клиент сам управляет access-токеном: читает кэш из account,
    запрашивает новый при необходимости, и сохраняет обновлённый токен
    в account (flush, не commit — это ответственность вызывающего).
    """

    # Performance API лимиты строже, чем Seller — берём 40 RPS с burst 10.
    DEFAULT_RATE = 40.0
    DEFAULT_BURST = 10
    DEFAULT_CONCURRENCY = 4

    def __init__(
        self,
        account: OzonAccount,
        db: AsyncSession,
        base_url: str | None = None,
        timeout: float = 60.0,
        *,
        rate: float | None = None,
        burst: int | None = None,
        concurrency: int | None = None,
    ):
        self.account = account
        self.db = db
        self.base_url = base_url or settings.OZON_PERFORMANCE_API_BASE_URL
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._bucket = TokenBucket(
            rate=rate or self.DEFAULT_RATE,
            capacity=burst or self.DEFAULT_BURST,
        )
        self._sema = asyncio.Semaphore(concurrency or self.DEFAULT_CONCURRENCY)

    async def __aenter__(self) -> OzonPerformanceClient:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"Content-Type": "application/json"},
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    # ------------------------------------------------------------
    # Токен
    # ------------------------------------------------------------

    def _cached_token_valid(self) -> str | None:
        """Возвращает кэшированный токен, если он ещё валиден (с запасом)."""
        if not self.account.perf_access_token_encrypted:
            return None
        if not self.account.perf_token_expires_at:
            return None
        if self.account.perf_token_expires_at <= datetime.now(UTC) + _TOKEN_REFRESH_MARGIN:
            return None
        try:
            return decrypt_secret(self.account.perf_access_token_encrypted)
        except Exception:  # noqa: BLE001 — порченый кэш → запросим новый
            return None

    async def _request_new_token(self) -> str:
        """Запросить свежий access_token через client_credentials и сохранить в БД."""
        assert self._client is not None, "use as async context manager"

        if not self.account.perf_client_id_encrypted or not self.account.perf_client_secret_encrypted:
            raise OzonPerfNotConfigured(
                "Performance API ключи не настроены для этого кабинета"
            )

        client_id = decrypt_secret(self.account.perf_client_id_encrypted)
        client_secret = decrypt_secret(self.account.perf_client_secret_encrypted)

        log.info("ozon_perf_token_request", account_id=str(self.account.id))
        res = await self._client.post(
            "/api/client/token",
            json={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
        )

        if res.status_code == 401 or res.status_code == 403:
            raise OzonAuthError(
                "Performance API: неверные client_id/client_secret",
                status_code=res.status_code,
                response_data=res.json() if res.content else {},
            )
        if res.status_code == 429:
            raise OzonRateLimitError(
                "Performance API: rate limit на токен", status_code=429
            )
        res.raise_for_status()

        data = res.json()
        token = data["access_token"]
        expires_in = int(data.get("expires_in", 1800))

        self.account.perf_access_token_encrypted = encrypt_secret(token)
        self.account.perf_token_expires_at = datetime.now(UTC) + timedelta(
            seconds=expires_in
        )
        await self.db.flush()

        log.info(
            "ozon_perf_token_received",
            account_id=str(self.account.id),
            expires_in=expires_in,
        )
        return token

    async def _ensure_token(self) -> str:
        cached = self._cached_token_valid()
        if cached:
            return cached
        return await self._request_new_token()

    # ------------------------------------------------------------
    # Запросы
    # ------------------------------------------------------------

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
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        assert self._client is not None, "use as async context manager"

        async with self._sema:
            await self._bucket.acquire()

            token = await self._ensure_token()
            headers = {"Authorization": f"Bearer {token}"}

            log.info(
                "ozon_perf_request",
                method=method,
                endpoint=endpoint,
                account_id=str(self.account.id),
            )

            async def _do_request(_token: str) -> httpx.Response:
                return await self._client.request(  # type: ignore[union-attr]
                    method=method,
                    url=endpoint,
                    json=json,
                    params=params,
                    headers={"Authorization": f"Bearer {_token}"},
                )

            response = await _do_request(token)

            # 401 — токен мог просто истечь между ensure_token и запросом. Один retry.
            if response.status_code == 401:
                log.warning("ozon_perf_token_invalid", account_id=str(self.account.id))
                self.account.perf_access_token_encrypted = None
                self.account.perf_token_expires_at = None
                await self.db.flush()
                token = await self._ensure_token()
                response = await _do_request(token)

            if response.status_code == 429:
                ra = _parse_retry_after(response.headers.get("Retry-After"))
                log.warning(
                    "ozon_perf_rate_limited",
                    endpoint=endpoint,
                    retry_after=ra,
                )
                raise OzonRateLimitError(
                    f"Performance API 429, Retry-After={ra}",
                    retry_after=ra,
                )

            if response.status_code >= 400:
                raise OzonAPIError(
                    f"Ozon Performance {response.status_code}: {response.text[:300]}",
                    status_code=response.status_code,
                    response_data=response.json() if response.content else {},
                )

            return response.json()

    # ------------------------------------------------------------
    # Эндпоинты
    # ------------------------------------------------------------

    async def get_campaigns(self) -> list[dict]:
        """
        Список рекламных кампаний.

        Endpoint: GET /api/client/campaign
        Response: {"list": [{id, title, type, state, ...}, ...]}
        """
        data = await self._request("GET", "/api/client/campaign")
        return data.get("list", [])

    async def get_daily_stats(
        self,
        date_from: str,  # YYYY-MM-DD
        date_to: str,  # YYYY-MM-DD
        campaign_ids: list[str] | None = None,
    ) -> dict:
        """
        Ежедневная агрегированная статистика по кампаниям.

        Endpoint: POST /api/client/statistics/daily/json
        Возвращает агрегаты impressions/clicks/orders/revenue/money_spent
        для каждой пары (campaign, date) в указанном диапазоне.
        """
        payload: dict[str, Any] = {
            "dateFrom": date_from,
            "dateTo": date_to,
        }
        if campaign_ids:
            payload["campaigns"] = campaign_ids
        return await self._request(
            "POST", "/api/client/statistics/daily/json", json=payload
        )
