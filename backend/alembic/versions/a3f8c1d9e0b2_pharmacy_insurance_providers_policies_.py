"""pharmacy: insurance_providers, patient_insurance_policies, insurance_claims

Revision ID: a3f8c1d9e0b2
Revises: 67040fb9b867
Create Date: 2026-09-15 20:10:00.000000

NOTA: escrita a mano, mismo motivo que 67040fb9b867 — el autogenerate
crudo de Alembic trae drops espurios de tablas de website/ecommerce/
reports que sí existen (falso positivo documentado desde `purchasing`).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f8c1d9e0b2'
down_revision: Union[str, Sequence[str], None] = '67040fb9b867'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'insurance_providers',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('contact_id', sa.BigInteger(), nullable=False),
        sa.Column('default_coverage_percentage', sa.Numeric(5, 2), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            'default_coverage_percentage IS NULL OR (default_coverage_percentage >= 0 AND default_coverage_percentage <= 100)',
            name='ck_insurance_providers_coverage_range',
        ),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'contact_id', name='uq_insurance_providers_company_contact'),
    )
    op.create_index(op.f('ix_insurance_providers_company_id'), 'insurance_providers', ['company_id'], unique=False)
    op.create_index(op.f('ix_insurance_providers_contact_id'), 'insurance_providers', ['contact_id'], unique=False)

    op.create_table(
        'patient_insurance_policies',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('patient_contact_id', sa.BigInteger(), nullable=False),
        sa.Column('insurance_provider_id', sa.BigInteger(), nullable=False),
        sa.Column('policy_number', sa.String(length=100), nullable=False),
        sa.Column('coverage_percentage', sa.Numeric(5, 2), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('coverage_percentage >= 0 AND coverage_percentage <= 100', name='ck_patient_insurance_policies_coverage_range'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['insurance_provider_id'], ['insurance_providers.id']),
        sa.ForeignKeyConstraint(['patient_contact_id'], ['contacts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'company_id', 'patient_contact_id', 'insurance_provider_id',
            name='uq_patient_insurance_policies_company_patient_provider',
        ),
    )
    op.create_index(op.f('ix_patient_insurance_policies_company_id'), 'patient_insurance_policies', ['company_id'], unique=False)
    op.create_index(op.f('ix_patient_insurance_policies_insurance_provider_id'), 'patient_insurance_policies', ['insurance_provider_id'], unique=False)
    op.create_index(op.f('ix_patient_insurance_policies_patient_contact_id'), 'patient_insurance_policies', ['patient_contact_id'], unique=False)

    op.create_table(
        'insurance_claims',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('dispensation_order_id', sa.BigInteger(), nullable=False),
        sa.Column('insurance_provider_id', sa.BigInteger(), nullable=False),
        sa.Column('patient_contact_id', sa.BigInteger(), nullable=False),
        sa.Column('claim_number', sa.String(length=50), nullable=False),
        sa.Column('amount_total', sa.Numeric(18, 2), nullable=False),
        sa.Column('amount_patient_copay', sa.Numeric(18, 2), nullable=False),
        sa.Column('amount_claimed_insurer', sa.Numeric(18, 2), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('billing_mode', sa.String(length=20), nullable=True),
        sa.Column('invoice_id', sa.BigInteger(), nullable=True),
        sa.Column('payment_id', sa.BigInteger(), nullable=True),
        sa.Column('rejection_reason', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'submitted', 'approved', 'paid', 'rejected')", name='ck_insurance_claims_status'),
        sa.CheckConstraint('amount_total = amount_patient_copay + amount_claimed_insurer', name='ck_insurance_claims_amounts_sum'),
        sa.CheckConstraint('amount_patient_copay >= 0 AND amount_claimed_insurer >= 0', name='ck_insurance_claims_amounts_nonneg'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['dispensation_order_id'], ['dispensation_orders.id']),
        sa.ForeignKeyConstraint(['insurance_provider_id'], ['insurance_providers.id']),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
        sa.ForeignKeyConstraint(['patient_contact_id'], ['contacts.id']),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'claim_number', name='uq_insurance_claims_company_claim_number'),
        sa.UniqueConstraint('company_id', 'dispensation_order_id', name='uq_insurance_claims_company_dispensation'),
    )
    op.create_index(op.f('ix_insurance_claims_company_id'), 'insurance_claims', ['company_id'], unique=False)
    op.create_index(op.f('ix_insurance_claims_dispensation_order_id'), 'insurance_claims', ['dispensation_order_id'], unique=False)
    op.create_index(op.f('ix_insurance_claims_insurance_provider_id'), 'insurance_claims', ['insurance_provider_id'], unique=False)
    op.create_index(op.f('ix_insurance_claims_patient_contact_id'), 'insurance_claims', ['patient_contact_id'], unique=False)

    for table in ('insurance_providers', 'patient_insurance_policies', 'insurance_claims'):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (company_id = current_setting('app.current_company_id', true)::bigint)
                WITH CHECK (company_id = current_setting('app.current_company_id', true)::bigint)
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO erp_app")
        # Bug sistémico ya documentado en 1d9a25acd918 — el GRANT sobre la
        # tabla no cubre la secuencia del id autoincremental.
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO erp_app")


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('insurance_claims', 'patient_insurance_policies', 'insurance_providers'):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f('ix_insurance_claims_patient_contact_id'), table_name='insurance_claims')
    op.drop_index(op.f('ix_insurance_claims_insurance_provider_id'), table_name='insurance_claims')
    op.drop_index(op.f('ix_insurance_claims_dispensation_order_id'), table_name='insurance_claims')
    op.drop_index(op.f('ix_insurance_claims_company_id'), table_name='insurance_claims')
    op.drop_table('insurance_claims')

    op.drop_index(op.f('ix_patient_insurance_policies_patient_contact_id'), table_name='patient_insurance_policies')
    op.drop_index(op.f('ix_patient_insurance_policies_insurance_provider_id'), table_name='patient_insurance_policies')
    op.drop_index(op.f('ix_patient_insurance_policies_company_id'), table_name='patient_insurance_policies')
    op.drop_table('patient_insurance_policies')

    op.drop_index(op.f('ix_insurance_providers_contact_id'), table_name='insurance_providers')
    op.drop_index(op.f('ix_insurance_providers_company_id'), table_name='insurance_providers')
    op.drop_table('insurance_providers')
