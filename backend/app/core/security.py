"""
Безопасность: JWT, пароли, шифрование чувствительных данных.

ВАЖНО: API ключи Озона хранятся в БД ЗАШИФРОВАННЫМИ.
Расшифровываются только в памяти при обращении к Озон API.
"""
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# --- ПАРОЛИ (bcrypt) ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Захэшировать пароль (bcrypt)."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверить пароль."""
    return pwd_context.verify(plain_password, hashed_password)


# --- JWT ТОКЕНЫ ---
def create_access_token(
    subject: str | int,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Создать JWT access token.

    Args:
        subject: ID пользователя (или email)
        extra_claims: доп. данные в токене (company_id, role и т.д.)
        expires_delta: срок жизни (по умолчанию из настроек)
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.now(UTC) + expires_delta
    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "access",
    }
    if extra_claims:
        to_encode.update(extra_claims)

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | int) -> str:
    """Создать refresh token (долгоживущий, для обновления access)."""
    expire = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "refresh",
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Декодировать JWT токен.

    Raises:
        JWTError: если токен невалиден или просрочен
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# --- ШИФРОВАНИЕ API КЛЮЧЕЙ ОЗОНА ---
# Используем Fernet (симметричное шифрование AES-128)
_fernet = Fernet(settings.ENCRYPTION_KEY.encode())


def encrypt_secret(plain_text: str) -> str:
    """
    Зашифровать чувствительные данные (API ключи Озона).

    Используется при сохранении в БД.
    Возвращает base64-строку которую можно хранить в TEXT поле.
    """
    if not plain_text:
        return ""
    return _fernet.encrypt(plain_text.encode()).decode()


def decrypt_secret(encrypted_text: str) -> str:
    """
    Расшифровать данные из БД.

    Используется только в памяти, например когда нужно вызвать Озон API.
    """
    if not encrypted_text:
        return ""
    return _fernet.decrypt(encrypted_text.encode()).decode()


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "encrypt_secret",
    "decrypt_secret",
    "JWTError",
]
