#!/usr/bin/env python3
"""
tests/e2e/seed_invoice_ready_to_pay.py — crea, dentro de "El Roble" (la
misma compañía que bootstrap_admin.py), un cliente + producto + orden de
venta confirmada + enviada + facturada, lista para que el spec de
Playwright (critical-flow.spec.ts) la pague desde la UI real.

Reimplementar esta cadena (draft -> confirm -> ship -> invoice, con
warehouse/stock/producto/cliente de por medio) en TypeScript vía fetch()
sería mucho más frágil que llamar a la capa de servicio de Python
directamente, que es exactamente lo que ya hace el resto de la suite
(11_concurrency_load.py, tests/security/). Invocado como subproceso desde
el spec — imprime un único JSON por stdout con lo que el spec necesita
para interactuar con la UI (nombre del contacto tal como aparece en el
selector de la UI, y número de factura).

Uso:
    python tests/e2e/seed_invoice_ready_to_pay.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

import os  # noqa: E402

os.chdir(BACKEND_ROOT)

from sqlalchemy import select, text  # noqa: E402

from app import models_registry  # noqa: E402,F401 — registra todos los modelos antes de tocar cualquier FK
from app.accounting import models as accounting_models  # noqa: E402
from app.contacts import schemas as contacts_schemas  # noqa: E402
from app.contacts.services import ContactService  # noqa: E402
from app.core import models as core_models  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.inventory import schemas as inv_schemas  # noqa: E402
from app.inventory.services import ProductService, StockService, WarehouseService  # noqa: E402
from app.sales import schemas as sales_schemas  # noqa: E402
from app.sales.services import SalesOrderService  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as db:
        company_id = (await db.execute(select(core_models.Company.id).where(core_models.Company.name == "El Roble"))).scalar_one()
        await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)})

        # Mismo patrón que backend/tests/test_ecommerce_module.py /
        # 11_concurrency_load.py: sin un DocumentAccountMapping para
        # sales_invoice, InvoiceService.post() no puede contabilizar.
        has_mapping = (await db.execute(
            select(accounting_models.DocumentAccountMapping).where(
                accounting_models.DocumentAccountMapping.company_id == company_id,
                accounting_models.DocumentAccountMapping.document_type == "sales_invoice",
            )
        )).first()
        if has_mapping is None:
            for role, name in [("receivable", "Cuentas por Cobrar E2E"), ("income", "Ingresos E2E"), ("tax", "Impuestos por Pagar E2E")]:
                account = accounting_models.Account(company_id=company_id, code=f"E2E-{role}", name=name, account_type=role)
                db.add(account)
                await db.flush()
                db.add(accounting_models.DocumentAccountMapping(
                    company_id=company_id, document_type="sales_invoice", role=role, account_id=account.id,
                ))

        unique = uuid.uuid4().hex[:6]
        contact_name = f"Cliente E2E {unique}"
        customer = await ContactService.create_contact(
            db, company_id=company_id, created_by=None,
            payload=contacts_schemas.ContactCreate(name=contact_name, is_customer=True),
        )
        warehouse = await WarehouseService.create(db, company_id=company_id, payload=inv_schemas.WarehouseCreate(name=f"Bodega E2E {unique}"))
        product = await ProductService.create(
            db, company_id=company_id, created_by=None,
            payload=inv_schemas.ProductCreate(sku=f"SKU-E2E-{unique}", name="Producto E2E", product_type=inv_schemas.ProductTypeEnum.facturable),
        )
        await StockService.record_movement(
            db, company_id=company_id, created_by=None,
            payload=inv_schemas.StockMovementCreate(
                product_id=product.id, warehouse_id=warehouse.id, movement_type=inv_schemas.MovementTypeEnum.entrada,
                quantity=Decimal(10), reference="Stock inicial — seed E2E Playwright",
            ),
        )
        order = await SalesOrderService.create_draft(
            db, company_id=company_id, created_by=None,
            payload=sales_schemas.SalesOrderCreate(
                customer_id=customer.id, warehouse_id=warehouse.id,
                lines=[sales_schemas.SalesOrderLineCreate(product_id=product.id, quantity=Decimal(1), unit_price=Decimal(500))],
            ),
        )
        await db.commit()

        order = await SalesOrderService.confirm(db, company_id=company_id, order_id=order.id, actor_id=None)
        await db.commit()
        full_line = order.lines[0]
        order = await SalesOrderService.ship(
            db, company_id=company_id, order_id=order.id, actor_id=None,
            payload=sales_schemas.ShipSalesOrder(lines=[sales_schemas.ShipLineItem(line_id=full_line.id, quantity=full_line.quantity)]),
        )
        await db.commit()
        order = await SalesOrderService.invoice(db, company_id=company_id, order_id=order.id, actor_id=None)
        await db.commit()

        # BUG/CARACTERÍSTICA REAL descubierta armando este seed:
        # SalesOrderService.invoice() SOLO cambia order.status a
        # 'facturado' — no crea ninguna fila en accounting.Invoice. La
        # factura real es una acción MANUAL separada (InvoiceService.
        # create_draft(), típicamente disparada desde la página de
        # Facturación referenciando la orden vía source_document_type/
        # source_document_id) — nunca automática al invocar
        # /sales-orders/{id}/invoice. Documentado como hallazgo en
        # STATE.md; acá se reproduce el mismo paso manual que la UI real
        # necesitaría, para poder sembrar una factura de verdad.
        from datetime import date

        from app.accounting import schemas as accounting_schemas
        from app.accounting.services import InvoiceService

        invoice = await InvoiceService.create_draft(
            db, company_id=company_id, created_by=None,
            payload=accounting_schemas.InvoiceCreate(
                direction=accounting_schemas.DirectionEnum.sale, contact_id=customer.id, issue_date=date.today(),
                source_document_type="sales_order", source_document_id=order.id,
                lines=[accounting_schemas.InvoiceLineCreate(description="Producto E2E", quantity=Decimal(1), unit_price=Decimal(500))],
            ),
        )
        await db.commit()
        invoice = await InvoiceService.post(db, company_id=company_id, invoice_id=invoice.id, actor_id=None)
        await db.commit()

        print(json.dumps({
            "contact_name": contact_name,
            "invoice_number": invoice.number,
            "invoice_total": str(invoice.total),
        }))


if __name__ == "__main__":
    asyncio.run(main())
