"""
Property-based testing (item 8 de la suite de calidad) sobre
`accounting._compute_lines` — el corazón numérico del motor de asientos
(spec 8.1): a partir de líneas (cantidad, precio unitario, tasa de
impuesto) calcula subtotal/tax_amount/total por línea y agregado. Todos
los tests manuales de la regresión QA probaron valores puntuales elegidos
a mano (1500, 15%, etc.) — `hypothesis` genera cientos de combinaciones,
incluyendo bordes que nadie pensaría a mano (cantidades muy grandes,
decimales con muchos dígitos, cero).

Invariantes verificadas, no valores puntuales — el objetivo de
property-based testing es la propiedad matemática que debe sostenerse
SIEMPRE, no un caso de ejemplo más.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from app.accounting import schemas as accounting_schemas
from app.accounting.services import TaxRateService, _compute_lines
from app.core import models as core_models
from app.database import AsyncSessionLocal

# Cantidades/precios realistas: positivos, hasta 2 decimales (como
# realmente los ingresaría un usuario — un precio con más de 2 decimales
# no tiene sentido de negocio, aunque Decimal lo permita matemáticamente),
# y acotados para no generar sumas que se salgan del NUMERIC de la
# columna real (spec: no hay un límite explícito documentado, así que se
# acota a un rango generoso pero realista).
quantities = st.decimals(min_value="0.01", max_value="100000", places=2)
prices = st.decimals(min_value="0", max_value="1000000", places=2)


class _FakeLine:
    def __init__(self, quantity: Decimal, unit_price: Decimal, tax_rate_id: int | None = None):
        self.description = "línea de test"
        self.quantity = quantity
        self.unit_price = unit_price
        self.tax_rate_id = tax_rate_id


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def company(db):
    unique = uuid.uuid4().hex[:8]
    c = core_models.Company(name=f"Property Test {unique}", tax_id=unique)
    db.add(c)
    await db.flush()
    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(c.id)})
    await db.commit()
    return c


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(lines=st.lists(st.tuples(quantities, prices), min_size=1, max_size=10))
@pytest.mark.asyncio
async def test_total_always_equals_subtotal_plus_tax_without_tax_rate(db, company, lines):
    """Sin tasa de impuesto (tax_rate_id=None → rate=0): total debe ser
    EXACTAMENTE igual al subtotal, tax_amount EXACTAMENTE cero — sin
    importar cuántas líneas ni qué valores, mientras sean válidos."""
    raw_lines = [_FakeLine(q, p) for q, p in lines]
    subtotal, tax_amount, total, line_dicts = await _compute_lines(db, company_id=company.id, raw_lines=raw_lines)

    assert tax_amount == Decimal("0.00")
    assert total == subtotal
    assert total == subtotal + tax_amount  # la identidad fundamental, siempre


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(lines=st.lists(st.tuples(quantities, prices), min_size=1, max_size=10))
@pytest.mark.asyncio
async def test_subtotal_equals_sum_of_line_subtotals(db, company, lines):
    """El agregado siempre es exactamente la suma de las líneas — no una
    aproximación, no un redondeo del agregado distinto de la suma de
    redondeos por línea (un error clásico de sistemas financieros: sumar
    primero y redondear después da un resultado distinto a redondear cada
    línea y sumar después; este código hace lo segundo, a propósito)."""
    raw_lines = [_FakeLine(q, p) for q, p in lines]
    subtotal, tax_amount, total, line_dicts = await _compute_lines(db, company_id=company.id, raw_lines=raw_lines)

    assert subtotal == sum((d["line_subtotal"] for d in line_dicts), Decimal("0"))
    assert tax_amount == sum((d["line_tax"] for d in line_dicts), Decimal("0"))


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(lines=st.lists(st.tuples(quantities, prices), min_size=1, max_size=10))
@pytest.mark.asyncio
async def test_amounts_never_negative_for_non_negative_inputs(db, company, lines):
    """Cantidad y precio siempre >= 0 (spec de negocio: no hay líneas de
    "cantidad negativa" en una factura — eso es lo que existen las notas
    de crédito/débito para) — subtotal/tax/total nunca deberían dar
    negativo si los inputs no lo son."""
    raw_lines = [_FakeLine(q, p) for q, p in lines]
    subtotal, tax_amount, total, line_dicts = await _compute_lines(db, company_id=company.id, raw_lines=raw_lines)

    assert subtotal >= 0
    assert tax_amount >= 0
    assert total >= 0
    for d in line_dicts:
        assert d["line_subtotal"] >= 0
        assert d["line_total"] >= 0


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(lines=st.lists(st.tuples(quantities, prices), min_size=1, max_size=10))
@pytest.mark.asyncio
async def test_line_amounts_always_rounded_to_2_decimals(db, company, lines):
    """`_round2` (spec: montos monetarios siempre a 2 decimales) —
    confirmado que NINGÚN monto de línea ni agregado sale con más
    precisión que centavos, sin importar la combinación de cantidad ×
    precio que genere la multiplicación (ej. 0.03 × 0.07 da más de 2
    decimales en aritmética exacta si no se redondea)."""
    raw_lines = [_FakeLine(q, p) for q, p in lines]
    subtotal, tax_amount, total, line_dicts = await _compute_lines(db, company_id=company.id, raw_lines=raw_lines)

    def _has_at_most_2_decimals(value: Decimal) -> bool:
        return value.as_tuple().exponent >= -2

    assert _has_at_most_2_decimals(subtotal)
    assert _has_at_most_2_decimals(tax_amount)
    assert _has_at_most_2_decimals(total)
    for d in line_dicts:
        assert _has_at_most_2_decimals(d["line_subtotal"])
        assert _has_at_most_2_decimals(d["line_tax"])
        assert _has_at_most_2_decimals(d["line_total"])


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    lines=st.lists(st.tuples(quantities, prices), min_size=1, max_size=5),
    rate=st.decimals(min_value="0", max_value="50", places=2),
)
@pytest.mark.asyncio
async def test_tax_amount_matches_rate_within_rounding_tolerance(db, company, lines, rate):
    """Con una tasa real (creada una vez por ejemplo — 30 ejemplos, no 100,
    porque cada uno hace un INSERT/DELETE real de TaxRate y esto sí toca
    la base de verdad): tax_amount debe estar cerca de subtotal * rate/100
    — "cerca" porque el redondeo es POR LÍNEA, no sobre el agregado, así
    que con muchas líneas la diferencia acumulada de redondeo puede llegar
    a unos pocos centavos, nunca más que (cantidad de líneas × 0.01)."""
    # BUG REAL DEL TEST encontrado por la suite de calidad externa
    # (sep-2026): `company` es un fixture function-scoped pero @given
    # ejecuta hasta 30 ejemplos dentro de la MISMA invocación del test
    # (por eso el suppress_health_check de function_scoped_fixture),
    # reutilizando la misma compañía para todos. Nombrar la tasa como
    # f"Tasa {rate}%" sin más choca con `uq_tax_rates_company_name` en
    # cuanto Hypothesis genera el mismo `rate` dos veces (algo casi
    # garantizado en 30 sorteos sobre ~5000 valores posibles, y más
    # probable todavía porque Hypothesis prioriza bordes como 0.00) —
    # 100% reproducible en 5/5 corridas aisladas. Un sufijo único por
    # ejemplo evita la colisión sin depender de aislar la sesión/transacción
    # entre ejemplos.
    tax_rate = await TaxRateService.create(
        db,
        company_id=company.id,
        payload=accounting_schemas.TaxRateCreate(name=f"Tasa {rate}% {uuid.uuid4().hex[:8]}", rate=rate),
    )
    raw_lines = [_FakeLine(q, p, tax_rate_id=tax_rate.id) for q, p in lines]
    subtotal, tax_amount, total, line_dicts = await _compute_lines(db, company_id=company.id, raw_lines=raw_lines)

    expected_tax_approx = subtotal * rate / Decimal(100)
    tolerance = Decimal("0.01") * len(lines)
    assert abs(tax_amount - expected_tax_approx) <= tolerance
    assert total == subtotal + tax_amount  # la identidad fundamental se sostiene igual, con o sin impuesto
