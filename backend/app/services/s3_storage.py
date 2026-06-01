"""
S3-хранилище через aioboto3 + Selectel S3-compatible.

Использование:
    from app.services.s3_storage import upload_bytes, generate_presigned_url

    key = await upload_bytes(content=b"...", key="supplies/...", mime="application/pdf")
    url = await generate_presigned_url(key, expires=3600)

Bucket, ключи и регион берутся из settings (S3_BUCKET / S3_ENDPOINT_URL / S3_REGION
/ S3_ACCESS_KEY / S3_SECRET_KEY).
"""
from __future__ import annotations

import aioboto3

from app.core.config import settings


def _session() -> aioboto3.Session:
    return aioboto3.Session(
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
    )


async def upload_bytes(*, content: bytes, key: str, mime: str | None = None) -> str:
    """Кладёт байты в bucket по ключу. Возвращает key."""
    extra = {"ContentType": mime} if mime else {}
    async with _session().client("s3", endpoint_url=settings.S3_ENDPOINT_URL) as s3:
        await s3.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=content, **extra)
    return key


async def generate_presigned_url(key: str, *, expires: int = 3600) -> str:
    """Создаёт временную ссылку на скачивание (по умолчанию 1 час)."""
    async with _session().client("s3", endpoint_url=settings.S3_ENDPOINT_URL) as s3:
        return await s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": key},
            ExpiresIn=expires,
        )


async def delete_object(key: str) -> None:
    """Удаляет объект из bucket."""
    async with _session().client("s3", endpoint_url=settings.S3_ENDPOINT_URL) as s3:
        await s3.delete_object(Bucket=settings.S3_BUCKET, Key=key)
