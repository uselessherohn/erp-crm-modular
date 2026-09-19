"""
Tests de integración del módulo reports — contra PostgreSQL real, mismo
patrón que el resto de `tests/test_*_module.py`.

NOTA DE ESTE CIERRE: escritos y revisados estáticamente, NO ejecutados —
mismo motivo que los demás módulos de este cierre (sin Postgres/red en
este entorno). `to_xlsx`/`to_pdf` además dependen de `openpyxl`/
`reportlab`, agregados a `requirements.txt` pero tampoco instalados aquí
— sus dos tests correspondientes son, por lo tanto, doblemente no
verificados (ni el flujo en general ni la disponibilidad del paquete).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.accounting import schemas as accounting_schemas
from app.accounting.services import InvoiceService
from app.core import models as core_models
from app.database import AsyncSessionLocal
from app.inventory import models as inventory_models
from app.inventory import schemas as inventory_schemas
from app.inventory.services import ProductService, WarehouseService
from app.reports import schemas as reports_schemas
from app.reports.services import DashboardService, ExportService, MetricService
from app.sales import schemas as sales_schemas
from app.sales.services import SalesOrderService
from app.shared.exceptions import NotFoundError, ValidationError


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def company(db):
    unique = uuid.uuid4().hex[:8]
    c = core_models.Company(name=f"Test Co {unique}", tax_id=unique)
    db.add(c)
    await db.flush()
    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(c.id)})
    await db.commit()
    return c


@pytest_asyncio.fixture
async def sales_fixture(db, company):
    """Un cliente + un producto + una orden de venta (draft) + una factura
    contabilizada — suficiente para ejercitar las 4 métricas del módulo."""
    from app.contacts.models import Contact

    customer = Contact(company_id=company.id, name="Cliente Reportes", is_customer=True)
    db.add(customer)
    await db.flush()
    await db.commit()

    warehouse = await WarehouseService.create(db, company_id=company.id, payload=inventory_schemas.WarehouseCreate(name="Bodega Reportes"))
    product = await ProductService.create(
        db, company_id=company.id, created_by=None,
        payload=inventory_schemas.ProductCreate(sku=f"SKU-{uuid.uuid4().hex[:6]}", name="Producto Reportes", product_type="facturable"),
    )

    order = await SalesOrderService.create_draft(
        db, company_id=company.id, created_by=None,
        payload=sales_schemas.SalesOrderCreate(
            customer_id=customer.id, warehouse_id=warehouse.id,
            lines=[sales_schemas.SalesOrderLineCreate(product_id=product.id, quantity=Decimal("3"), unit_price=Decimal("50.00"))],
        ),
    )

    await _setup_sales_invoice_account_mappings(db, company)

    invoice = await InvoiceService.create_draft(
        db, company_id=company.id, created_by=None,
        payload=accounting_schemas.InvoiceCreate(
            direction=accounting_schemas.DirectionEnum.sale, contact_id=customer.id, issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            lines=[accounting_schemas.InvoiceLineCreate(description="Producto Reportes", quantity=Decimal("3"), unit_price=Decimal("50.00"))],
        ),
    )
    await InvoiceService.post(db, company_id=company.id, invoice_id=invoice.id, actor_id=None)

    stock = inventory_models.StockLevel(company_id=company.id, product_id=product.id, warehouse_id=warehouse.id, quantity=Decimal("100"))
    db.add(stock)
    await db.commit()

    return {"customer": customer, "product": product, "warehouse": warehouse, "order": order}


async def _setup_sales_invoice_account_mappings(db, company):
    """Fixture mínima real del motor de asientos (mismo patrón que
    tests/test_medical_module.py::_setup_sales_invoice_account_mappings) —
    sin esto, `InvoiceService.post` no tiene a qué cuentas resolver
    `sales_invoice`, y las 4 métricas que dependen de una factura
    contabilizada nunca llegan a ejercitarse."""
    from app.accounting import models as accounting_models

    for role, name in [("receivable", "Cuentas por Cobrar"), ("income", "Ingresos"), ("tax", "Impuestos por Pagar")]:
        account = accounting_models.Account(
            company_id=company.id, code=f"TEST-{role}", name=name, account_type=role,
        )
        db.add(account)
        await db.flush()
        db.add(accounting_models.DocumentAccountMapping(
            company_id=company.id, document_type="sales_invoice", role=role, account_id=account.id,
        ))
    await db.commit()


@pytest.mark.asyncio
async def test_sales_by_customer_metric(db, company, sales_fixture):
    result = await MetricService.run(
        db, company_id=company.id, metric_key="sales_by_customer",
        date_from=date.today() - timedelta(days=1), date_to=date.today() + timedelta(days=1),
    )
    assert len(result.rows) == 1
    assert result.rows[0]["cliente"] == "Cliente Reportes"
    assert Decimal(str(result.rows[0]["total"])) == Decimal("150.00")


@pytest.mark.asyncio
async def test_top_products_by_revenue_metric(db, company, sales_fixture):
    result = await MetricService.run(
        db, company_id=company.id, metric_key="top_products_by_revenue",
        date_from=date.today() - timedelta(days=1), date_to=date.today() + timedelta(days=1),
    )
    assert len(result.rows) == 1
    assert result.rows[0]["producto"] == "Producto Reportes"


@pytest.mark.asyncio
async def test_accounts_receivable_open_metric(db, company, sales_fixture):
    result = await MetricService.run(
        db, company_id=company.id, metric_key="accounts_receivable_open",
        date_from=date.today() - timedelta(days=1), date_to=date.today() + timedelta(days=1),
    )
    assert len(result.rows) == 1
    assert Decimal(str(result.rows[0]["saldo_pendiente"])) == Decimal("150.00")


@pytest.mark.asyncio
async def test_stock_by_warehouse_metric(db, company, sales_fixture):
    # Rango de fechas irrelevante para esta métrica (foto del estado
    # actual) — se pasa uno cualquiera, ver docstring de `_stock_by_warehouse`.
    result = await MetricService.run(
        db, company_id=company.id, metric_key="stock_by_warehouse", date_from=date.today(), date_to=date.today(),
    )
    assert len(result.rows) == 1
    assert Decimal(str(result.rows[0]["cantidad_disponible"])) == Decimal("100")


@pytest.mark.asyncio
async def test_unknown_metric_raises_not_found(db, company):
    with pytest.raises(NotFoundError):
        await MetricService.run(db, company_id=company.id, metric_key="no_existe", date_from=date.today(), date_to=date.today())


@pytest.mark.asyncio
async def test_dashboard_rejects_widget_with_unknown_metric(db, company):
    with pytest.raises(ValidationError):
        await DashboardService.create(
            db, company_id=company.id, owner_user_id=None,
            payload=reports_schemas.DashboardCreate(
                name="Dashboard Inválido",
                widgets=[reports_schemas.DashboardWidget(metric_key="no_existe", title="Widget")],
            ),
        )


@pytest.mark.asyncio
async def test_dashboard_crud(db, company):
    dashboard = await DashboardService.create(
        db, company_id=company.id, owner_user_id=None,
        payload=reports_schemas.DashboardCreate(
            name="Ventas",
            widgets=[reports_schemas.DashboardWidget(metric_key="sales_by_customer", title="Top clientes")],
        ),
    )
    assert len(dashboard.widgets) == 1

    fetched = await DashboardService.get(db, company_id=company.id, dashboard_id=dashboard.id)
    assert fetched.name == "Ventas"

    updated = await DashboardService.update(
        db, company_id=company.id, dashboard_id=dashboard.id, actor_id=None,
        payload=reports_schemas.DashboardUpdate(name="Ventas (editado)"),
    )
    assert updated.name == "Ventas (editado)"

    await DashboardService.delete(db, company_id=company.id, dashboard_id=dashboard.id, actor_id=None)
    with pytest.raises(NotFoundError):
        await DashboardService.get(db, company_id=company.id, dashboard_id=dashboard.id)


def test_export_csv_contains_header_and_rows():
    content = ExportService.to_csv(columns=["a", "b"], rows=[{"a": "1", "b": "2"}])
    text_content = content.decode("utf-8-sig")
    assert "a,b" in text_content
    assert "1,2" in text_content


def test_export_xlsx_produces_nonempty_bytes():
    content = ExportService.to_xlsx(title="Test", columns=["a", "b"], rows=[{"a": 1, "b": 2}])
    assert len(content) > 0
    assert content[:2] == b"PK"  # XLSX es un ZIP — firma de archivo ZIP


def test_export_pdf_produces_nonempty_bytes():
    content = ExportService.to_pdf(title="Test", columns=["a", "b"], rows=[{"a": 1, "b": 2}])
    assert len(content) > 0
    assert content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_medical_originated_invoice_missing_from_sales_metrics_but_present_in_ar(db, company):
    """Catálogo módulo 24 — 'el caso más importante de este módulo': una
    factura originada en medical/pharmacy (no en sales), ¿aparece igual
    que una de sales en las métricas correspondientes?

    Respuesta real confirmada, NO es una sorpresa — coincide con el TODO
    explícito ya declarado en la cabecera de app/reports/metrics.py
    ('métricas que crucen medical/pharmacy... requeriría validar el
    paquete de origen de cada dominio... fuera de alcance de este
    cierre'):

    - `accounts_receivable_open` SÍ la incluye — consulta la tabla
      genérica `invoices`, sin acoplarse al origen.
    - `sales_by_customer`/`top_products_by_revenue` NO la incluyen —
      consultan `sales_orders`/`sales_order_lines` directo, y una
      factura de medical/pharmacy nunca tiene un `sales_order`
      asociado. `top_products_by_revenue` en particular es
      estructuralmente imposible de corregir sin tocar el modelo:
      `InvoiceLine` no tiene `product_id` (solo `description` libre),
      así que ni siquiera hay con qué vincular una línea de factura de
      pharmacy a un producto para esa métrica específica."""
    from app.contacts.models import Contact

    customer = Contact(company_id=company.id, name="Paciente Facturado", is_customer=True, is_patient=True)
    db.add(customer)
    await db.flush()
    await db.commit()
    await _setup_sales_invoice_account_mappings(db, company)

    # Factura creada DIRECTO (sin sales_order) — mismo patrón que
    # medical/pharmacy: InvoiceService.create_draft llamado directo.
    invoice = await InvoiceService.create_draft(
        db, company_id=company.id, created_by=None,
        payload=accounting_schemas.InvoiceCreate(
            direction=accounting_schemas.DirectionEnum.sale, contact_id=customer.id, issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            lines=[accounting_schemas.InvoiceLineCreate(description="Consulta médica", quantity=Decimal("1"), unit_price=Decimal("500.00"))],
        ),
    )
    await InvoiceService.post(db, company_id=company.id, invoice_id=invoice.id, actor_id=None)

    date_from, date_to = date.today() - timedelta(days=1), date.today() + timedelta(days=1)

    ar = await MetricService.run(db, company_id=company.id, metric_key="accounts_receivable_open", date_from=date_from, date_to=date_to)
    assert any(row["factura"] == invoice.number for row in ar.rows), "accounts_receivable_open debería incluirla — consulta la tabla genérica invoices"

    sbc = await MetricService.run(db, company_id=company.id, metric_key="sales_by_customer", date_from=date_from, date_to=date_to)
    assert not any(row["cliente"] == "Paciente Facturado" for row in sbc.rows), (
        "sales_by_customer NO debería incluirla todavía — confirma el TODO explícito ya declarado "
        "en metrics.py, no una sorpresa. Si este assert falla, el TODO se resolvió y hay que "
        "actualizar STATE.md/este test."
    )
