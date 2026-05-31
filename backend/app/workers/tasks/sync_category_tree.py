"""
Синхронизация полного дерева категорий Ozon.

Endpoint: POST /v1/description-category/tree (один на весь Ozon, не per-account).
Достаточно дёргать раз в неделю — каталог меняется редко.

Структура ответа Ozon (упрощённо):
{
  "result": [
    {
      "description_category_id": 17027949,
      "category_name": "Дом",
      "disabled": false,
      "children": [
        { "description_category_id": ..., "category_name": ..., "children": [...], "type_id": 0 },
        ...
      ],
      "type_id": 0  // 0 = это категория, не тип
    },
    ...
  ]
}

Лист (type) приходит с type_id > 0 и без children. Для лист-узлов используем
type_id (это и есть products.category_id).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import log
from app.core.security import decrypt_secret
from app.models import OzonAccount, OzonCategoryTree
from app.services.ozon_client import OzonSellerClient
from app.workers.celery_app import celery_app
from app.workers.tasks._helpers import run_celery_async


@celery_app.task(name="app.workers.tasks.sync_category_tree.sync_category_tree",
                 bind=True, autoretry_for=(Exception,),
                 retry_kwargs={"max_retries": 2, "countdown": 300})
def sync_category_tree(self) -> dict:
    """Синкает полное дерево категорий Ozon. Один раз в неделю достаточно."""
    return run_celery_async(_sync_category_tree_async)


async def _sync_category_tree_async(SessionLocal: async_sessionmaker[AsyncSession]) -> dict:
    async with SessionLocal() as db:
        # Берём любой активный кабинет — этого хватит для запроса tree
        # (запрос требует валидных Client-Id/Api-Key, но возвращает глобальный каталог).
        account = (await db.execute(
            select(OzonAccount).where(OzonAccount.deleted_at.is_(None))
        )).scalars().first()
        if not account:
            log.warning("category_tree_no_account")
            return {"status": "skipped", "reason": "no active ozon account"}

        client_id = account.client_id
        api_key = decrypt_secret(account.api_key_encrypted)

        async with OzonSellerClient(client_id, api_key) as client:
            data = await client.get_description_category_tree()

        nodes: list[dict] = []
        _flatten(data.get("result", []), parent_id=None, level=0, path="", out=nodes)
        log.info("category_tree_flattened", count=len(nodes))

        if not nodes:
            return {"status": "empty"}

        # Upsert батчем — TimescaleDB на это норм
        batch_size = 500
        for i in range(0, len(nodes), batch_size):
            chunk = nodes[i:i + batch_size]
            stmt = pg_insert(OzonCategoryTree).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ozon_id"],
                set_={
                    "name": stmt.excluded.name,
                    "parent_id": stmt.excluded.parent_id,
                    "level": stmt.excluded.level,
                    "full_path": stmt.excluded.full_path,
                    "is_type": stmt.excluded.is_type,
                    "is_disabled": stmt.excluded.is_disabled,
                },
            )
            await db.execute(stmt)
        await db.commit()
        log.info("category_tree_synced", total=len(nodes))
        return {"status": "ok", "nodes_total": len(nodes)}


def _flatten(items: list[dict], *, parent_id: int | None, level: int,
             path: str, out: list[dict]) -> None:
    """Рекурсивно разворачивает вложенное дерево Ozon в плоский список upsert-рядов."""
    for item in items:
        # Узлы дерева бывают двух типов: категория (description_category_id, type_id=0)
        # и лист (type_id > 0). У листа нет своего description_category_id, но он
        # уникален по type_id.
        cat_id = item.get("description_category_id")
        type_id = item.get("type_id") or 0
        name = (item.get("category_name") or item.get("type_name") or "").strip()
        disabled = bool(item.get("disabled", False))

        if type_id > 0 and not item.get("children"):
            # Это лист (type)
            ozon_id = type_id
            is_type = True
        elif cat_id:
            ozon_id = cat_id
            is_type = False
        else:
            # Странный узел без id — скип
            continue

        full_path = f"{path} / {name}" if path else name

        out.append({
            "ozon_id": ozon_id,
            "name": name[:500] if name else f"#{ozon_id}",
            "parent_id": parent_id,
            "level": level,
            "full_path": full_path[:1000],
            "is_type": is_type,
            "is_disabled": disabled,
        })

        children = item.get("children") or []
        if children:
            _flatten(children, parent_id=ozon_id, level=level + 1, path=full_path, out=out)
