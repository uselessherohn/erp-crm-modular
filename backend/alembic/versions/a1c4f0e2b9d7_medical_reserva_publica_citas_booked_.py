"""medical: reserva pública de citas (módulo 15) — booked_via_public_widget en appointments

Revision ID: a1c4f0e2b9d7
Revises: 1d9a25acd918
Create Date: 2026-09-14 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4f0e2b9d7'
down_revision: Union[str, Sequence[str], None] = '1d9a25acd918'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Módulo 15 (reserva pública de citas, spec 8.2/8.4) no agrega tablas
    nuevas — reutiliza `Appointment` (módulo 9) por completo. Única
    adición: un flag informativo para distinguir una cita creada por el
    widget público de una creada por personal de recepción (mismo
    criterio retroactivo que `reserved_quantity`/`credit_limit` en
    cierres anteriores). No requiere GRANT de secuencia nuevo (la tabla
    `appointments` ya existe desde el módulo 9, y el fix sistémico de
    `1d9a25acd918` ya cubrió todas las secuencias existentes a esa
    fecha).
    """
    op.add_column(
        "appointments",
        sa.Column("booked_via_public_widget", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("appointments", "booked_via_public_widget")
