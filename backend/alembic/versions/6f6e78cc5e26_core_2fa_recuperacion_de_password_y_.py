"""core: 2FA, recuperacion de password, y activar/desactivar usuario (spec 8.0 core, gaps reales)

Revision ID: 6f6e78cc5e26
Revises: c4d8b3f61a97
Create Date: 2026-09-17 23:23:35.458614

HALLAZGO REAL (regresión QA externa, sep-2026): spec_erp_crm_v10_4.md
sección 8.0 marca "Autenticación y Seguridad [core]: login, 2FA,
recuperación de contraseña, sesiones activas, JWT/OAuth2, política de
contraseñas, bloqueo por intentos" — [core], no [extendido]. Al cierre
original del módulo 1 se construyó login/JWT/bloqueo/sesiones, pero 2FA y
recuperación de contraseña nunca se construyeron, y esa omisión no quedó
registrada en STATE.md ni como TODO ni como decisión (ver sección 0.1/0.2
de STATE.md para el detalle completo). Esta migración cierra ese gap.
También se corrige un gap relacionado, no explícitamente [core] en la
spec pero sí implícito en "Gestión de Usuarios [core]: perfiles,
**estados**...": no existía ninguna forma de desactivar/reactivar un
usuario (sin UserUpdate, sin endpoint PATCH sobre /users).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f6e78cc5e26'
down_revision: Union[str, Sequence[str], None] = 'c4d8b3f61a97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # pgcrypto: la necesita totp_secret_encrypted (pgp_sym_encrypt, mismo
    # patrón que medical/1669f8fbbc6b — ver ese archivo para el precedente
    # y la corrección real que dejó documentada). IF NOT EXISTS: idempotente
    # aunque medical la haya habilitado antes en la cadena (no es el caso
    # acá — core es el módulo 1, corre primero — pero lo sería en cualquier
    # reordenamiento futuro).
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # -----------------------------------------------------------------
    # 2FA (TOTP) — columnas en users, no tabla aparte: es 1:1 con el
    # usuario, sin historial que justifique una tabla propia.
    # -----------------------------------------------------------------
    op.add_column("users", sa.Column("totp_secret_encrypted", sa.LargeBinary(), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )

    # -----------------------------------------------------------------
    # Recuperación de contraseña — mismo patrón que UserSession/refresh
    # token (spec 8.0): token de un solo uso, hasheado en reposo
    # (sha256, nunca se persiste el valor plano), resoluble sin conocer
    # company_id de antemano (rol erp_auth_lookup, BYPASSRLS, columnas
    # concretas) porque el flujo empieza solo con el email.
    # -----------------------------------------------------------------
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_password_reset_tokens_company_id"), "password_reset_tokens", ["company_id"])
    op.create_index(op.f("ix_password_reset_tokens_user_id"), "password_reset_tokens", ["user_id"])

    op.execute("ALTER TABLE password_reset_tokens ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE password_reset_tokens FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON password_reset_tokens
            USING (company_id = current_setting('app.current_company_id', true)::bigint)
            WITH CHECK (company_id = current_setting('app.current_company_id', true)::bigint)
        """
    )
    # Bug sistémico ya documentado en 1d9a25acd918/f3b6a1d9c204/b7e2f5a13c68:
    # el GRANT ON ALL TABLES de la migración inicial solo cubre las tablas
    # que existían en ese momento — cada tabla nueva necesita su propio
    # GRANT explícito, o falla en el primer INSERT real contra Postgres.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_tokens TO erp_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE password_reset_tokens_id_seq TO erp_app")

    # Lookup pre-auth: el flujo de "olvidé mi contraseña" empieza solo con
    # el email (no se conoce company_id), y el de "confirmar con el token"
    # empieza solo con el token — mismo problema que login/refresh,
    # resuelto igual (columnas concretas, BYPASSRLS, nunca se escribe con
    # este rol).
    op.execute(
        "GRANT SELECT (id, company_id, user_id, token_hash, expires_at, used_at) "
        "ON password_reset_tokens TO erp_auth_lookup"
    )

    # -----------------------------------------------------------------
    # Desactivar/reactivar usuario: sin cambio de esquema (is_active ya
    # existe desde 1483b27d4cff) — el gap era solo de capa de
    # servicio/API (UserService.set_active + PATCH /users/{id}/status),
    # no de modelo. Documentado acá para que el historial de migraciones
    # explique por qué este cierre no toca `users.is_active`.
    # -----------------------------------------------------------------


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("REVOKE SELECT ON password_reset_tokens FROM erp_auth_lookup")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON password_reset_tokens")
    op.drop_index(op.f("ix_password_reset_tokens_user_id"), table_name="password_reset_tokens")
    op.drop_index(op.f("ix_password_reset_tokens_company_id"), table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret_encrypted")
