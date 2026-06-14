"""
Зонд Performance API: найти НОВЫЙ безлимитный метод «Статистика по товарам
в Оплате за клик» эмпирически (живой вызов → смотрим payload), не угадывая
поля в код (правило CLAUDE.md).

Запуск на проде:
    docker exec ozon_worker python -m app.scripts.probe_perf_product_stats

Скрипт:
  1) берёт первый кабинет с Performance-ключами;
  2) подтверждает OAuth-токен (список кампаний);
  3) перебирает кандидатов endpoint'ов (GET и POST) за ВЧЕРА и печатает
     HTTP-статус + начало тела по каждому.
Ничего не пишет в БД — только читает.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.db.session import AsyncSessionLocal
from app.services.ozon_perf_client import OzonPerformanceClient
from app.workers.tasks._helpers import get_active_accounts

# Вчера по UTC — данные за этот день уже зафиксированы Ozon (фиксация в 3:00 мск).
_Y = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()

# Кандидаты нового per-товар метода. dateFrom/dateTo/campaignId подставляются.
# Перебираем оба HTTP-метода — какой ответит 200 с товарными строками, тот наш.
_CANDIDATES = [
    ("GET", "/api/client/statistics/products/json"),
    ("POST", "/api/client/statistics/products/json"),
    ("GET", "/api/client/statistics/product/json"),
    ("GET", "/api/client/statistics/campaign/product/json"),
    ("GET", "/api/client/statistics/orders/json"),
    ("GET", "/api/client/statistics/attribution"),
    ("GET", "/api/client/statistics/expense/json"),
    ("POST", "/api/client/statistics/products"),
    ("GET", "/api/client/statistics/products"),
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        accounts = await get_active_accounts(db)
        eligible = [a for a in accounts if a.perf_client_id_encrypted]
        if not eligible:
            print("НЕТ кабинетов с Performance-ключами")
            return
        account = eligible[0]
        print(f"Кабинет: {account.name} ({account.id})")

        async with OzonPerformanceClient(account, db) as client:
            token = await client._ensure_token()
            assert client._client is not None
            http = client._client
            auth = {"Authorization": f"Bearer {token}"}

            # 1) Подтверждаем токен + берём campaignId для параметров.
            camp_resp = await http.get("/api/client/campaign", headers=auth)
            print(f"\n[campaign] GET /api/client/campaign -> {camp_resp.status_code}")
            campaign_id = None
            try:
                clist = camp_resp.json().get("list", [])
                print(f"  кампаний: {len(clist)}")
                if clist:
                    campaign_id = clist[0].get("id") or clist[0].get("campaignId")
                    print(f"  пример campaign_id={campaign_id}")
            except Exception as e:
                print(f"  не распарсил список кампаний: {e}")

            print(f"\nДаты зонда: dateFrom={_Y} dateTo={_Y} (вчера)\n")

            # 2) Перебор кандидатов.
            for method, path in _CANDIDATES:
                params = {"dateFrom": _Y, "dateTo": _Y, "date": _Y}
                if campaign_id:
                    params["campaignId"] = campaign_id
                    params["campaignIds"] = [campaign_id]
                    params["campaigns"] = [campaign_id]
                try:
                    if method == "GET":
                        r = await http.get(path, params=params, headers=auth)
                    else:
                        body = {
                            "dateFrom": _Y, "dateTo": _Y, "date": _Y,
                            "campaignId": campaign_id,
                            "campaigns": [campaign_id] if campaign_id else [],
                        }
                        r = await http.post(path, json=body, headers=auth)
                    snippet = r.text[:600].replace("\n", " ")
                    print(f"[{r.status_code}] {method} {path}")
                    print(f"      {snippet}\n")
                except Exception as e:
                    print(f"[ERR] {method} {path} -> {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
