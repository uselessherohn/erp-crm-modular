"""merge pharmacy y website/ecommerce/reports (trabajo en paralelo desde 370fd33db300)

Revision ID: d016d0daa072
Revises: 465ce93341cd, 57990ab9bc72
Create Date: 2026-09-14 11:38:06.506899

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd016d0daa072'
down_revision: Union[str, Sequence[str], None] = ('465ce93341cd', '57990ab9bc72')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
