"""pharmacy: Reposición a Droguerías (módulo 20) — pharmacy_reorder_points

Revision ID: c4d8b3f61a97
Revises: b7e2f5a13c68
Create Date: 2026-09-16 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d8b3f61a97'
down_revision: Union[str, Sequence[str], None] = 'b7e2f5a13c68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Módulo 20 — Reposición a Droguerías (spec 8.3, "[extendido]"). Una
    sola tabla nueva — la sugerencia de reorden en sí NO se persiste
    (se calcula al vuelo comparando esto contra `stock_levels`, ver
    DED-65 en `app/pharmacy/models.py`); generar la PO reutiliza
    `purchase_orders`/`purchase_order_lines` ya existentes (módulo 4),
    sin tabla nueva de por medio.
    """
    op.create_table(
        "pharmacy_reorder_points",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("company_id", sa.BigInteger(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("product_id", sa.BigInteger(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("warehouse_id", sa.BigInteger(), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("reorder_point", sa.Numeric(14, 4), nullable=False),
        sa.Column("reorder_quantity", sa.Numeric(14, 4), nullable=False),
        sa.Column("preferred_vendor_id", sa.BigInteger(), sa.ForeignKey("contacts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("company_id", "product_id", "warehouse_id", name="uq_pharmacy_reorder_points_product_warehouse"),
        sa.CheckConstraint("reorder_point >= 0", name="ck_pharmacy_reorder_points_point_nonneg"),
        sa.CheckConstraint("reorder_quantity > 0", name="ck_pharmacy_reorder_points_quantity_positive"),
    )
    op.create_index(op.f("ix_pharmacy_reorder_points_company_id"), "pharmacy_reorder_points", ["company_id"])
    op.create_index(op.f("ix_pharmacy_reorder_points_product_id"), "pharmacy_reorder_points", ["product_id"])
    op.create_index(op.f("ix_pharmacy_reorder_points_warehouse_id"), "pharmacy_reorder_points", ["warehouse_id"])

    op.execute("ALTER TABLE pharmacy_reorder_points ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE pharmacy_reorder_points FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON pharmacy_reorder_points
            USING (company_id = current_setting('app.current_company_id', true)::bigint)
            WITH CHECK (company_id = current_setting('app.current_company_id', true)::bigint)
        """
    )
    # Bug sistémico ya documentado en 1d9a25acd918 y reencontrado en
    # f3b6a1d9c204 (módulo 25) y b7e2f5a13c68 (módulo 21, esta misma
    # sesión): cada tabla nueva necesita su propio GRANT explícito.
    # Corregido antes de correr esta migración contra Postgres real por
    # primera vez (sesión de verificación externa, sep-2026).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON pharmacy_reorder_points TO erp_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE pharmacy_reorder_points_id_seq TO erp_app")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON pharmacy_reorder_points")
    op.drop_index(op.f("ix_pharmacy_reorder_points_warehouse_id"), table_name="pharmacy_reorder_points")
    op.drop_index(op.f("ix_pharmacy_reorder_points_product_id"), table_name="pharmacy_reorder_points")
    op.drop_index(op.f("ix_pharmacy_reorder_points_company_id"), table_name="pharmacy_reorder_points")
    op.drop_table("pharmacy_reorder_points")
