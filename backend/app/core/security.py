"""
Seguridad: hashing de contraseñas (bcrypt directo — no passlib, que está sin
mantenimiento desde 2020 y es incompatible con bcrypt>=4.1 por un cambio de
API interna que rompe la detección de backend; bug real encontrado al
probar el bootstrap end-to-end, no un problema hipotético) y JWT
(python-jose).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import settings

_BCRYPT_MAX_BYTES = 72  # límite duro del algoritmo bcrypt


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def create_access_token(*, user_id: int, company_id: int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    # `jti` (JWT ID, RFC 7519 §4.1.7) — nonce aleatorio de un solo uso.
    # BUG REAL encontrado por la suite de calidad externa (sep-2026,
    # test_full_http_flow_create_company_user_login_use_token_refresh):
    # sin esto, dos tokens emitidos para el mismo usuario+compañía dentro
    # del mismo segundo son byte-por-byte idénticos — `exp` solo tiene
    # resolución de segundo y la firma HS256 es determinística sobre un
    # payload idéntico. Reproducible 100% de las veces en un refresh
    # inmediato tras el login (flujo normal de cualquier cliente rápido,
    # no solo de tests). El `jti` garantiza unicidad sin cambiar la
    # semántica de expiración.
    payload = {
        "sub": str(user_id),
        "company_id": company_id,
        "type": "access",
        "exp": expire,
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Token inválido o expirado") from exc


def generate_refresh_token() -> tuple[str, str]:
    """Devuelve (token_plano_para_el_cliente, hash_para_persistir).
    Nunca se persiste el token plano — mismo criterio que una contraseña."""
    raw = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def generate_password_reset_token() -> tuple[str, str]:
    """Mismo mecanismo que generate_refresh_token (token de un solo uso,
    hasheado en reposo) — separado como función propia porque semántica y
    tabla son distintas (password_reset_tokens, no user_sessions), aunque
    la implementación criptográfica sea idéntica."""
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


def hash_password_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()
