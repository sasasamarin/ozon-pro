"""
Дерево категорий Ozon (description_category).

Источник — endpoint /v1/description-category/tree. Хранит весь каталог,
включая узлы без товаров — для UI разворачивания и для агрегатов
«сколько в этой ветке у меня SKU/выручки».

products.category_id ссылается на конечный узел (type или leaf category).
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class OzonCategoryTree(BaseModel):
    """
    Один узел дерева категорий Ozon.

    Узел может быть:
    - категорией (description_category, есть children)
    - типом (type, лист дерева — на нём заводятся товары)

    parent_id NULL → корневой узел.
    """

    __tablename__ = "ozon_category_tree"

    # description_category_id или type_id (они уникальны в одном пространстве)
    ozon_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ozon_category_tree.ozon_id"), nullable=True, index=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Полный путь от корня для быстрых LIKE-запросов: "Дом / Освещение / Бытовое освещение"
    full_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_type: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
