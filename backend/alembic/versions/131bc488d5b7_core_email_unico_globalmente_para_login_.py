"""core: email unico globalmente para login pre-auth (AMBIGUO Fase 2)

Revision ID: 131bc488d5b7
Revises: 1483b27d4cff
Create Date: 2026-08-19 11:16:47.957136

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '131bc488d5b7'
down_revision: Union[str, Sequence[str], None] = '1483b27d4cff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("uq_users_company_email", "users", type_="unique")
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    # Rol de solo lectura con BYPASSRLS, exclusivo para el lookup pre-auth
    # de login (app/database.py: auth_lookup_engine). Se crea vía DDL puro
    # en vez de asumir que ya existe fuera de la migración, para que
    # `alembic upgrade head` sea reproducible en cualquier entorno nuevo.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'erp_auth_lookup') THEN
                CREATE ROLE erp_auth_lookup LOGIN PASSWORD 'erp_auth_lookup_dev_pw'
                    NOSUPERUSER BYPASSRLS;
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('GRANT CONNECT ON DATABASE %I TO erp_auth_lookup', current_database());
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO erp_auth_lookup")
    op.execute(
        "GRANT SELECT (id, company_id, email, hashed_password, failed_login_attempts, "
        "locked_until, is_active) ON users TO erp_auth_lookup"
    )
    # También necesario para /auth/refresh (mismo patrón que login: el
    # access token ya expiró, se resuelve company_id desde
    # refresh_token_hash, que es único globalmente).
    op.execute(
        "GRANT SELECT (id, company_id, refresh_token_hash) ON user_sessions TO erp_auth_lookup"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("REVOKE SELECT ON users FROM erp_auth_lookup")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.create_unique_constraint("uq_users_company_email", "users", ["company_id", "email"])
