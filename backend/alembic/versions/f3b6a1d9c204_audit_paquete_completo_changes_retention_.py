"""audit: paquete completo (módulo 25) — audit.changes (diff) + audit_retention_policies

Revision ID: f3b6a1d9c204
Revises: a1c4f0e2b9d7
Create Date: 2026-09-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3b6a1d9c204'
down_revision: Union[str, Sequence[str], None] = 'a1c4f0e2b9d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Módulo 25 — audit completo (spec 8.1). Opera sobre la misma tabla
    `audit` creada en el módulo 1 (spec 8.0) — no la duplica.

    1. `audit.changes` (JSONB, nullable): "Control de Cambios (Diff)"
       [core]. Columna retroactiva, igual que otras agregadas en
       cierres posteriores al módulo dueño de la tabla original.
    2. `audit_retention_policies`: "Retención y Depuración" [core] — una
       fila opcional por compañía. NO se agrega ningún mecanismo de
       borrado automático en esta migración (ver AMB-07, STATE.md): el
       trigger `trg_audit_immutable` (módulo 1) bloquea DELETE/UPDATE
       sobre `audit` incondicionalmente, así que la "Depuración" real es
       un procedimiento de mantenimiento fuera de esta migración y fuera
       de la API HTTP — ver `scripts/purge_audit.py`.

    No requiere GRANT de secuencia nuevo aparte del estándar (la tabla
    nueva usa un `id` autoincremental normal, ya cubierto por el GRANT
    sistémico de `1d9a25acd918` para secuencias creadas hasta ese punto
    — para esta secuencia nueva, `erp_app` la obtiene por
    `ALTER DEFAULT PRIVILEGES` ya configurado en la migración inicial,
    igual que cualquier tabla nueva desde entonces).

    CORRECCIÓN (sesión de verificación externa, sep-2026): el párrafo de
    arriba es incorrecto y quedó así como registro histórico del error,
    no como guía — la migración inicial (1483b27d4cff) NUNCA usó
    `ALTER DEFAULT PRIVILEGES`; el patrón real de este proyecto (visible
    en toda migración posterior, ej. `465ce93341cd`) es que CADA
    migración con tabla nueva emite su propio
    `GRANT SELECT, INSERT, UPDATE, DELETE ON <tabla> TO erp_app`
    explícito, porque `GRANT ... ON ALL TABLES IN SCHEMA public` (spec,
    migración inicial) solo cubre las tablas que existen en el momento
    en que corre, no las creadas después — el mismo patrón de bug ya
    documentado para secuencias en `1d9a25acd918`, aquí para tablas.
    Esta migración originalmente omitía ese GRANT para
    `audit_retention_policies`, y `erp_app` (el rol de runtime real de
    la API, sin bypass de RLS) fallaba con
    `InsufficientPrivilegeError: permission denied for table
    audit_retention_policies` al primer INSERT/SELECT real — reproducido
    contra Postgres real en esta sesión de verificación, no detectado
    antes porque ningún cierre previo había insertado como `erp_app` en
    esta tabla. Corregido agregando el GRANT explícito más abajo.
    """
    op.add_column("audit", sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    op.create_table(
        "audit_retention_policies",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", name="uq_audit_retention_policies_company"),
    )
    op.create_index(
        op.f("ix_audit_retention_policies_company_id"), "audit_retention_policies", ["company_id"],
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON audit_retention_policies TO erp_app")
    op.execute("GRANT USAGE, SELECT ON audit_retention_policies_id_seq TO erp_app")
    # ^ Mismo motivo que el GRANT de tabla de arriba: `1d9a25acd918` solo
    # cubrió las secuencias que existían en ese momento, y esta migración
    # corre DESPUÉS de esa — la secuencia de esta tabla nueva nunca quedó
    # cubierta por ningún GRANT sistémico. Sin este GRANT explícito,
    # `erp_app` puede fallar al insertar (aunque el motivo exacto
    # verificado en esta sesión fue el permiso de tabla de arriba, no el
    # de secuencia — se agrega este también por el mismo razonamiento y
    # para no repetir el mismo patrón de bug).

    # RLS — mismo patrón que cualquier tabla multi-tenant del proyecto
    # (spec 3, "toda tabla con company_id lleva RLS", sin excepción).
    op.execute("ALTER TABLE audit_retention_policies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_retention_policies FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON audit_retention_policies
        USING (company_id = current_setting('app.current_company_id', true)::bigint)
        WITH CHECK (company_id = current_setting('app.current_company_id', true)::bigint)
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON audit_retention_policies")
    op.drop_index(op.f("ix_audit_retention_policies_company_id"), table_name="audit_retention_policies")
    op.drop_table("audit_retention_policies")
    op.drop_column("audit", "changes")
