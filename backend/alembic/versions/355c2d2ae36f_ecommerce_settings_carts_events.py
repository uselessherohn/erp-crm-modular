"""ecommerce: settings, carts, cart_items, payment_gateway_events

Revision ID: 355c2d2ae36f
Revises: be79a5e3b927
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '355c2d2ae36f'
down_revision: Union[str, Sequence[str], None] = 'be79a5e3b927'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'ecommerce_settings',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('default_warehouse_id', sa.BigInteger(), nullable=True),
        sa.Column('default_price_list_id', sa.BigInteger(), nullable=True),
        sa.Column('webhook_secret', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
        sa.ForeignKeyConstraint(['default_warehouse_id'], ['warehouses.id'], ),
        sa.ForeignKeyConstraint(['default_price_list_id'], ['price_lists.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id'),
    )

    op.create_table(
        'ecommerce_carts',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('session_token', sa.String(length=64), nullable=False),
        sa.Column('contact_id', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='open', nullable=False),
        sa.Column('currency_code', sa.String(length=3), server_default='HNL', nullable=False),
        sa.Column('sales_order_id', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ),
        sa.ForeignKeyConstraint(['sales_order_id'], ['sales_orders.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'session_token', name='uq_ecommerce_carts_company_token'),
    )
    op.create_index(op.f('ix_ecommerce_carts_company_id'), 'ecommerce_carts', ['company_id'], unique=False)

    op.create_table(
        'ecommerce_cart_items',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('cart_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('unit_price_snapshot', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
        sa.ForeignKeyConstraint(['cart_id'], ['ecommerce_carts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cart_id', 'product_id', name='uq_ecommerce_cart_items_cart_product'),
    )
    op.create_index(op.f('ix_ecommerce_cart_items_company_id'), 'ecommerce_cart_items', ['company_id'], unique=False)
    op.create_index(op.f('ix_ecommerce_cart_items_cart_id'), 'ecommerce_cart_items', ['cart_id'], unique=False)

    op.create_table(
        'ecommerce_payment_gateway_events',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('gateway', sa.String(length=30), nullable=False),
        sa.Column('event_id', sa.String(length=150), nullable=False),
        sa.Column('payload_raw', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('sales_order_id', sa.BigInteger(), nullable=True),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
        sa.ForeignKeyConstraint(['sales_order_id'], ['sales_orders.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'gateway', 'event_id', name='uq_ecommerce_payment_events_company_gateway_event'),
    )
    op.create_index(
        op.f('ix_ecommerce_payment_gateway_events_company_id'), 'ecommerce_payment_gateway_events', ['company_id'], unique=False
    )

    # Row-Level Security (spec 5/DoD) — las cuatro tablas tienen company_id.
    for table in ('ecommerce_settings', 'ecommerce_carts', 'ecommerce_cart_items', 'ecommerce_payment_gateway_events'):
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


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('ecommerce_payment_gateway_events', 'ecommerce_cart_items', 'ecommerce_carts', 'ecommerce_settings'):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f('ix_ecommerce_payment_gateway_events_company_id'), table_name='ecommerce_payment_gateway_events')
    op.drop_table('ecommerce_payment_gateway_events')
    op.drop_index(op.f('ix_ecommerce_cart_items_cart_id'), table_name='ecommerce_cart_items')
    op.drop_index(op.f('ix_ecommerce_cart_items_company_id'), table_name='ecommerce_cart_items')
    op.drop_table('ecommerce_cart_items')
    op.drop_index(op.f('ix_ecommerce_carts_company_id'), table_name='ecommerce_carts')
    op.drop_table('ecommerce_carts')
    op.drop_table('ecommerce_settings')
