"""
Общий фильтр продуктов по category_id (с потомками) и tags.

Используется в Dashboard / P&L / Economics / Funnel / Heatmap, чтобы единый
выбор юзера в Topbar (CategoryPickerGlobal + TagPickerGlobal) применялся
ко всем разделам одинаково.

Логика:
- category_id: рекурсивный CTE по ozon_category_tree (один SQL на каждый
  запрос — кеш бы не помешал, но 9550 узлов в памяти Postgres мгновенно).
  Возвращает список ozon_id (включая корневой выбранный + все потомки).
- tags: PostgreSQL ARRAY оверлап `p.tags && :tags`.
"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def category_descendants(
    db: AsyncSession, *, category_id: int,
) -> list[int]:
    """
    Возвращает [category_id] + все ozon_id потомков из ozon_category_tree.

    Если category_id не существует в дереве — возвращает просто [category_id]
    (защита от race condition: дерево не синкнуто, а товар уже в БД).
    """
    rows = (await db.execute(text("""
        WITH RECURSIVE descendants AS (
            SELECT ozon_id FROM ozon_category_tree WHERE ozon_id = :cid
            UNION ALL
            SELECT t.ozon_id FROM ozon_category_tree t
            JOIN descendants d ON t.parent_id = d.ozon_id
        )
        SELECT ozon_id FROM descendants
    """), {"cid": category_id})).scalars().all()
    if not rows:
        # Дерево пустое или нет такого id — фильтр по самому id
        return [category_id]
    return list(rows)


def build_product_filter_sql(
    *, category_ids: Sequence[int] | None,
    tags: Sequence[str] | None,
    p_alias: str = "p",
) -> tuple[str, dict]:
    """
    Возвращает (sql_fragment, params) для добавления в WHERE-блок запроса.

    Пример:
        sql_extra, extra_params = build_product_filter_sql(
            category_ids=desc, tags=tags, p_alias="p")
        sql = f"SELECT ... FROM products p WHERE p.deleted_at IS NULL {sql_extra}"
        params.update(extra_params)

    Если category_ids и tags пусты — вернёт пустую строку.
    """
    parts: list[str] = []
    params: dict = {}

    if category_ids:
        parts.append(f"AND {p_alias}.category_id = ANY(:cat_ids)")
        params["cat_ids"] = list(category_ids)

    if tags:
        # ARRAY overlap: товар должен иметь ХОТЯ БЫ ОДИН из выбранных тегов
        parts.append(f"AND {p_alias}.tags && CAST(:tag_filter AS text[])")
        params["tag_filter"] = list(tags)

    return (" ".join(parts), params)
