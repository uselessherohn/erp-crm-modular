"""pharmacy: product_active_ingredients, drug_interaction_reference_entries

Revision ID: 67040fb9b867
Revises: f3b6a1d9c204
Create Date: 2026-09-15 04:04:35.969075

NOTA: se escribió a mano en vez de usar el autogenerate crudo — el diff
automático contra la base traía drops espurios de tablas de website/
ecommerce/reports que sí existen (mismo falso positivo ya documentado en
cada migración desde `purchasing`), no relacionados con este cambio.

NOTA DE MERGE (sesión de verificación externa, sep-2026): esta migración
llegó con `down_revision = '1d9a25acd918'` porque se escribió en paralelo,
ramificada de un estado del repo previo a los módulos 15
(`a1c4f0e2b9d7`) y 25 (`f3b6a1d9c204`), que para cuando esto se integró
ya estaban en `main`. Sin conflicto real de esquema (tablas y columnas
enteramente nuevas, sin tocar nada de esos dos módulos) — se reencadenó
a `f3b6a1d9c204` para mantener una sola cadena lineal, en vez de agregar
una migración de merge aparte (esa alternativa se reserva para cuando sí
hay cambios en las mismas tablas, como ya pasó una vez con `d016d0daa072`).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67040fb9b867'
down_revision: Union[str, Sequence[str], None] = 'f3b6a1d9c204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Seed pequeño a mano (DED-51, pedido explícito de Roberto): 15 pares
# conocidos y reales, severidad clínicamente alta salvo 3 casos
# 'moderate' incluidos a propósito para ejercitar ambas severidades.
# Siempre en orden alfabético (ingredient_a < ingredient_b) por el check
# constraint. Fuente: interacciones de referencia de dominio público
# (no una API externa — DED-51 documenta por qué).
_SEED_PAIRS = [
    ("amiodarone", "warfarin", "major", "Amiodarona inhibe el metabolismo de warfarina — potencia el efecto anticoagulante, riesgo de sangrado."),
    ("amoxicillin", "methotrexate", "moderate", "Penicilinas pueden reducir la excreción renal de metotrexato, aumentando su toxicidad."),
    ("aspirin", "warfarin", "major", "Combinación con alto riesgo de sangrado — efecto antiplaquetario más anticoagulante."),
    ("carbamazepine", "ethinylestradiol", "moderate", "Carbamazepina induce el metabolismo del estrógeno — reduce la eficacia anticonceptiva."),
    ("ciprofloxacin", "theophylline", "moderate", "Ciprofloxacina inhibe el metabolismo de teofilina — riesgo de niveles tóxicos."),
    ("clarithromycin", "simvastatin", "major", "Inhibición de CYP3A4 — riesgo elevado de miopatía/rabdomiólisis."),
    ("clopidogrel", "omeprazole", "moderate", "Omeprazol inhibe CYP2C19 — reduce la activación y el efecto antiplaquetario de clopidogrel."),
    ("digoxin", "furosemide", "moderate", "Furosemida puede causar hipokalemia, que aumenta el riesgo de toxicidad por digoxina."),
    ("fluoxetine", "tramadol", "major", "Riesgo de síndrome serotoninérgico por combinación de agentes serotoninérgicos."),
    ("hydrochlorothiazide", "lithium", "major", "Diuréticos tiazídicos reducen el aclaramiento renal de litio — riesgo de toxicidad."),
    ("ibuprofen", "methotrexate", "major", "AINEs reducen el aclaramiento renal de metotrexato — riesgo de toxicidad severa."),
    ("ibuprofen", "warfarin", "major", "AINE + anticoagulante — riesgo elevado de sangrado gastrointestinal."),
    ("lisinopril", "spironolactone", "major", "IECA + diurético ahorrador de potasio — riesgo de hiperkalemia severa."),
    ("metronidazole", "warfarin", "major", "Metronidazol inhibe el metabolismo de warfarina — potencia el efecto anticoagulante."),
    ("nitroglycerin", "sildenafil", "major", "Combinación contraindicada — riesgo de hipotensión severa y potencialmente mortal."),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'drug_interaction_reference_entries',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('ingredient_a', sa.String(length=200), nullable=False),
        sa.Column('ingredient_b', sa.String(length=200), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("severity IN ('moderate', 'major')", name='ck_drug_interaction_reference_severity'),
        sa.CheckConstraint('ingredient_a < ingredient_b', name='ck_drug_interaction_reference_alpha_order'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ingredient_a', 'ingredient_b', name='uq_drug_interaction_reference_pair'),
    )
    op.create_index(op.f('ix_drug_interaction_reference_entries_ingredient_a'), 'drug_interaction_reference_entries', ['ingredient_a'], unique=False)
    op.create_index(op.f('ix_drug_interaction_reference_entries_ingredient_b'), 'drug_interaction_reference_entries', ['ingredient_b'], unique=False)

    op.create_table(
        'product_active_ingredients',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=False),
        sa.Column('active_ingredient', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'product_id', name='uq_product_active_ingredients_company_product'),
    )
    op.create_index(op.f('ix_product_active_ingredients_active_ingredient'), 'product_active_ingredients', ['active_ingredient'], unique=False)
    op.create_index(op.f('ix_product_active_ingredients_company_id'), 'product_active_ingredients', ['company_id'], unique=False)
    op.create_index(op.f('ix_product_active_ingredients_product_id'), 'product_active_ingredients', ['product_id'], unique=False)

    # RLS: solo `product_active_ingredients` es multi-tenant (DED-52).
    # `drug_interaction_reference_entries` es un catálogo GLOBAL (DED-53,
    # mismo criterio que `permissions`) — sin company_id, sin RLS.
    op.execute("ALTER TABLE product_active_ingredients ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE product_active_ingredients FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON product_active_ingredients
            USING (company_id = current_setting('app.current_company_id', true)::bigint)
            WITH CHECK (company_id = current_setting('app.current_company_id', true)::bigint)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON product_active_ingredients TO erp_app")
    # Bug sistémico ya documentado en 1d9a25acd918 — el GRANT sobre la
    # tabla no cubre la secuencia del id autoincremental.
    op.execute("GRANT USAGE, SELECT ON SEQUENCE product_active_ingredients_id_seq TO erp_app")
    # Catálogo global: SELECT para erp_app (todas las compañías lo leen),
    # sin INSERT/UPDATE/DELETE por API — se administra por seed/migración,
    # igual que `permissions` no tiene endpoint de escritura pública.
    op.execute("GRANT SELECT ON drug_interaction_reference_entries TO erp_app")

    seed_table = sa.table(
        'drug_interaction_reference_entries',
        sa.column('ingredient_a', sa.String),
        sa.column('ingredient_b', sa.String),
        sa.column('severity', sa.String),
        sa.column('description', sa.String),
    )
    op.bulk_insert(
        seed_table,
        [
            {"ingredient_a": a, "ingredient_b": b, "severity": sev, "description": desc}
            for a, b, sev, desc in _SEED_PAIRS
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON product_active_ingredients")
    op.execute("ALTER TABLE product_active_ingredients NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE product_active_ingredients DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f('ix_product_active_ingredients_product_id'), table_name='product_active_ingredients')
    op.drop_index(op.f('ix_product_active_ingredients_company_id'), table_name='product_active_ingredients')
    op.drop_index(op.f('ix_product_active_ingredients_active_ingredient'), table_name='product_active_ingredients')
    op.drop_table('product_active_ingredients')
    op.drop_index(op.f('ix_drug_interaction_reference_entries_ingredient_b'), table_name='drug_interaction_reference_entries')
    op.drop_index(op.f('ix_drug_interaction_reference_entries_ingredient_a'), table_name='drug_interaction_reference_entries')
    op.drop_table('drug_interaction_reference_entries')
