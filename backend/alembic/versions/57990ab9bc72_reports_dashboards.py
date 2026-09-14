"""reports: dashboards

Revision ID: 57990ab9bc72
Revises: 355c2d2ae36f
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '57990ab9bc72'
down_revision: Union[str, Sequence[str], None] = '355c2d2ae36f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'report_dashboards',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('owner_user_id', sa.BigInteger(), nullable=True),
        sa.Column('widgets', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'name', name='uq_report_dashboards_company_name'),
    )
    op.create_index(op.f('ix_report_dashboards_company_id'), 'report_dashboards', ['company_id'], unique=False)

    op.execute("ALTER TABLE report_dashboards ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE report_dashboards FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON report_dashboards
            USING (company_id = current_setting('app.current_company_id', true)::bigint)
            WITH CHECK (company_id = current_setting('app.current_company_id', true)::bigint)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON report_dashboards TO erp_app")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON report_dashboards")
    op.execute("ALTER TABLE report_dashboards NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE report_dashboards DISABLE ROW LEVEL SECURITY")
    op.drop_index(op.f('ix_report_dashboards_company_id'), table_name='report_dashboards')
    op.drop_table('report_dashboards')
