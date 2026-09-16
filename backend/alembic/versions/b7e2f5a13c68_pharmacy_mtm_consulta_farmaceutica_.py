"""pharmacy: MTM / Consulta Farmacéutica (módulo 21) — pharmacy_mtm_sessions + pharmacy_mtm_billing_records

Revision ID: b7e2f5a13c68
Revises: a3f8c1d9e0b2
Create Date: 2026-09-15 16:30:00.000000

NOTA DE MERGE (sesión de verificación externa, sep-2026): esta migración
llegó con `down_revision = 'f3b6a1d9c204'` porque se escribió en paralelo,
ramificada de un estado del repo previo a los módulos 17 (interacciones)
y 18 (aseguradoras), que para cuando esto se integró ya estaban en
`main`. Sin conflicto real de esquema (tabla nueva, sin tocar nada de
esos dos módulos) — se reencadenó a `a3f8c1d9e0b2` (tip real de la
cadena de farmacia a esa altura: 17→18) para mantener una sola cadena
lineal, mismo criterio ya aplicado en el propio módulo 17 para su
reencadene sobre `f3b6a1d9c204`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2f5a13c68'
down_revision: Union[str, Sequence[str], None] = 'a3f8c1d9e0b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Módulo 21 — MTM / Consulta Farmacéutica (spec 8.3, "MTM / Consulta
    Farmacéutica [extendido]"). Dos tablas nuevas, mismo desacople
    clínico/financiero que `consultations`/`medical_billing_records`
    (módulos 9/13) — ver DED-62 en `app/pharmacy/models.py`.
    """
    op.create_table(
        "pharmacy_mtm_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("patient_contact_id", sa.BigInteger(), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("pharmacist_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("medication_review", sa.Text(), nullable=False),
        sa.Column("adherence_notes", sa.Text(), nullable=True),
        sa.Column("adverse_effects_notes", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column("fee_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="HNL"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.CheckConstraint("status IN ('open', 'closed', 'cancelled')", name="ck_pharmacy_mtm_sessions_status"),
        sa.CheckConstraint("fee_amount > 0", name="ck_pharmacy_mtm_sessions_fee_positive"),
    )
    op.create_index(op.f("ix_pharmacy_mtm_sessions_company_id"), "pharmacy_mtm_sessions", ["company_id"])
    op.create_index(op.f("ix_pharmacy_mtm_sessions_patient_contact_id"), "pharmacy_mtm_sessions", ["patient_contact_id"])
    op.create_index(op.f("ix_pharmacy_mtm_sessions_pharmacist_user_id"), "pharmacy_mtm_sessions", ["pharmacist_user_id"])

    op.create_table(
        "pharmacy_mtm_billing_records",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("pharmacy_mtm_sessions.id"), nullable=False, unique=True),
        sa.Column("billing_mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="issued"),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="HNL"),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("invoice_id", sa.BigInteger(), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("receipt_number", sa.String(50), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("billing_mode IN ('accounting_invoice', 'simple_receipt')", name="ck_pharmacy_mtm_billing_records_mode"),
        sa.CheckConstraint("status IN ('issued', 'cancelled')", name="ck_pharmacy_mtm_billing_records_status"),
        sa.CheckConstraint("amount > 0", name="ck_pharmacy_mtm_billing_records_amount_positive"),
    )
    op.create_index(op.f("ix_pharmacy_mtm_billing_records_company_id"), "pharmacy_mtm_billing_records", ["company_id"])
    op.create_index(op.f("ix_pharmacy_mtm_billing_records_session_id"), "pharmacy_mtm_billing_records", ["session_id"])

    # RLS — mismo patrón que cualquier tabla multi-tenant del proyecto.
    for table in ("pharmacy_mtm_sessions", "pharmacy_mtm_billing_records"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (company_id = current_setting('app.current_company_id', true)::bigint)
                WITH CHECK (company_id = current_setting('app.current_company_id', true)::bigint)
            """
        )
        # Bug sistémico ya documentado en 1d9a25acd918 y reencontrado en
        # f3b6a1d9c204 (módulo 25): el GRANT ON ALL TABLES de la migración
        # inicial solo cubre las tablas que existen en el momento en que
        # corre, nunca las creadas después — cada tabla nueva necesita su
        # propio GRANT explícito. Esta migración originalmente no lo
        # tenía (corregido en la sesión de verificación externa, sep-2026,
        # antes de correr contra Postgres real por primera vez, así que
        # nunca llegó a fallar en un pytest real).
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO erp_app")
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO erp_app")


def downgrade() -> None:
    """Downgrade schema."""
    for table in ("pharmacy_mtm_billing_records", "pharmacy_mtm_sessions"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.drop_index(op.f("ix_pharmacy_mtm_billing_records_session_id"), table_name="pharmacy_mtm_billing_records")
    op.drop_index(op.f("ix_pharmacy_mtm_billing_records_company_id"), table_name="pharmacy_mtm_billing_records")
    op.drop_table("pharmacy_mtm_billing_records")
    op.drop_index(op.f("ix_pharmacy_mtm_sessions_pharmacist_user_id"), table_name="pharmacy_mtm_sessions")
    op.drop_index(op.f("ix_pharmacy_mtm_sessions_patient_contact_id"), table_name="pharmacy_mtm_sessions")
    op.drop_index(op.f("ix_pharmacy_mtm_sessions_company_id"), table_name="pharmacy_mtm_sessions")
    op.drop_table("pharmacy_mtm_sessions")
