"""contacts: unicidad de email por compania, busqueda por email/tax_id

Revision ID: ea97b3b319d5
Revises: 6f6e78cc5e26
Create Date: 2026-09-18 05:21:44.693185

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea97b3b319d5'
down_revision: Union[str, Sequence[str], None] = '6f6e78cc5e26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


"""contacts: unicidad de email por compania, busqueda por email/tax_id

Revision ID: ea97b3b319d5
Revises: 6f6e78cc5e26
Create Date: 2026-09-18 05:21:44.693185

HALLAZGO REAL (regresión QA externa, sep-2026, catálogo módulo 2):
emails duplicados estaban permitidos dentro de la misma compañía, sin
ninguna decisión DEDUCIBLE/AMBIGUO registrada al respecto — a diferencia
de `users.email` (único global, AMB-01, migración 131bc488d5b7). DEDUCIBLE
nuevo: único POR COMPAÑÍA (no global como users — Contact representa
entidades externas, no identidades de login; dos compañías clientas de
este sistema pueden compartir el mismo proveedor con el mismo email sin
conflicto). Índice único parcial (WHERE email IS NOT NULL): el campo es
nullable y NULL no debe chocar consigo mismo (comportamiento estándar de
unicidad SQL, ya usado implícitamente en otros lados del proyecto).

También agrega índices btree en email/tax_id para la búsqueda nueva de
ContactService.list_contacts (antes solo cubría `name` vía pg_trgm).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea97b3b319d5'
down_revision: Union[str, Sequence[str], None] = '6f6e78cc5e26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "CREATE UNIQUE INDEX ux_contacts_company_email ON contacts (company_id, email) "
        "WHERE email IS NOT NULL"
    )
    op.create_index(op.f("ix_contacts_email"), "contacts", ["email"])
    op.create_index(op.f("ix_contacts_tax_id"), "contacts", ["tax_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_contacts_tax_id"), table_name="contacts")
    op.drop_index(op.f("ix_contacts_email"), table_name="contacts")
    op.execute("DROP INDEX IF EXISTS ux_contacts_company_email")

