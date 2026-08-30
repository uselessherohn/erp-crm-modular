"""
Configuración global vía pydantic-settings (spec sección 4: "Configuración y
secretos" — toda config vía variables de entorno, nunca hardcodeada).
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base de datos — el rol de aplicación NUNCA es superusuario ni tiene
    # BYPASSRLS (spec sección 5, defensa en profundidad RLS).
    database_url: str = (
        "postgresql+asyncpg://erp_app:erp_app_dev_pw@localhost:5432/erp_crm_dev"
    )
    # Rol de solo lectura con BYPASSRLS — exclusivamente para el lookup
    # pre-auth de login (AuthService.login), el único caso legítimamente
    # cross-tenant del sistema (spec sección 5: "scripts administrativos que
    # necesitan acceso cross-tenant legítimo usan un rol separado con
    # BYPASSRLS, nunca el rol de la aplicación" — mismo criterio aplicado
    # acá a un caso de aplicación, no solo administrativo). AMBIGUO
    # registrado en el cierre del Módulo 1 Fase 2: la spec no especifica
    # cómo el cliente identifica su company_id antes de autenticarse.
    database_url_auth_lookup: str = (
        "postgresql+asyncpg://erp_auth_lookup:erp_auth_lookup_dev_pw@localhost:5432/erp_crm_dev"
    )
    # Usado solo por Alembic (DDL) y scripts administrativos — dueño de las
    # tablas, no el rol de runtime de la API.
    database_url_admin: str = (
        "postgresql+psycopg://postgres:postgres_dev_pw@localhost:5432/erp_crm_dev"
    )

    # JWT / Auth
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_ENV"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 30

    # Default de fábrica por mercado objetivo — PYME hondureña (spec 8.0, v10.3)
    default_timezone: str = "America/Tegucigalpa"
    default_currency_code: str = "HNL"
    default_locale: str = "es-HN"

    # Gestión de clave pgcrypto (spec 1.1) — DEDUCIBLE con default declarado:
    # variable de entorno vía pydantic-settings, sin rotación programada.
    # Se usa por primera vez en el módulo `medical` (módulo 9), no en `core`.
    pgcrypto_key: str = "CHANGE_ME_IN_PRODUCTION_ENV"

    # Idempotencia — TTL por dominio en horas (spec 7, corregido en v10.4)
    idempotency_ttl_hours_sales: int = 24
    idempotency_ttl_hours_accounting: int = 72
    idempotency_ttl_hours_medical_billing: int = 72
    idempotency_ttl_hours_pharmacy: int = 24 * 7

    # Onboarding de compañías (POST /internal/companies): no hay ningún
    # usuario todavía en la primera empresa, así que no puede protegerse
    # con el RBAC normal. DEDUCIBLE temporal: header estático de servicio,
    # no expuesto en el router público. TODO real: reemplazar por un panel
    # de superadmin propio cuando exista (fuera de alcance de core v1).
    internal_api_key: str = "CHANGE_ME_IN_PRODUCTION_ENV"

    # CORS (hallazgo de Fase 3: el frontend en otro origen necesita esto
    # para hablar con la API) — orígenes explícitos, nunca "*" porque las
    # rutas autenticadas usan Authorization header con credenciales reales.
    cors_allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]


settings = Settings()
