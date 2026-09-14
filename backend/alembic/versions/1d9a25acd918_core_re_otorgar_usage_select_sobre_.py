"""core: re-otorgar USAGE,SELECT sobre todas las secuencias a erp_app (bug sistemico desde modulo hr)

Revision ID: 1d9a25acd918
Revises: d016d0daa072
Create Date: 2026-09-14 22:14:22.213130

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1d9a25acd918'
down_revision: Union[str, Sequence[str], None] = 'd016d0daa072'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    BUG REAL, sistémico (encontrado durante la verificación externa del
    cierre de pharmacy+website/ecommerce/reports en CI, reproducido en
    local: `bootstrap_admin.py` fallaba con
    'permission denied for sequence ecommerce_settings_id_seq').

    La migración inicial (1483b27d4cff, módulo core) otorga
    `GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO erp_app`,
    pero ese GRANT en Postgres solo cubre las secuencias que EXISTEN en
    el momento en que se ejecuta — no las que se crean después (eso
    requeriría `ALTER DEFAULT PRIVILEGES`, que no se usó). Cada
    migración desde entonces solo repite
    `GRANT SELECT, INSERT, UPDATE, DELETE ON <tabla> TO erp_app` para
    sus tablas nuevas, sin el USAGE sobre la secuencia del `id`
    autoincremental de esas mismas tablas.

    Nunca se detectó antes porque ningún test de `pytest` ni ningún
    cierre previo había insertado una fila, como `erp_app` real (no
    superusuario), en una tabla creada por una migración posterior a
    `hr` (módulo 8) — el primer caso real fue `bootstrap_admin.py`
    insertando en `ecommerce_settings`. Afecta potencialmente a TODAS
    las tablas creadas desde `hr` en adelante (hr, medical, recetas,
    laboratorio, teleconsulta, facturación médica, portal/mensajería,
    notifications, website, ecommerce, reports, pharmacy) — cualquier
    INSERT vía la app real (no vía pytest, que hasta ahora no lo había
    ejercitado en este camino) podría fallar igual. Ver STATE.md.
    """
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO erp_app")


def downgrade() -> None:
    """Downgrade schema."""
    # No revierte el GRANT original de 1483b27d4cff (correcto: esa migración
    # sigue siendo dueña de la intención "erp_app puede usar secuencias").
    pass
