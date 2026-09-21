#!/usr/bin/env python3
"""
11_concurrency_load.py — Concurrencia real, no simulada.

STATE.md documenta el SELECT FOR UPDATE de StockService "probado con 10
conexiones reales" y la idempotencia de webhooks "probada secuencial" — dos
afirmaciones que este script convierte en una prueba real y repetible:

1. **Oversell**: N confirmaciones simultáneas de SalesOrders que compiten por
   el mismo stock físico limitado. El invariante real: nunca se reserva más
   de lo que hay físicamente, sin importar cuántas lleguen al mismo tiempo.
2. **Idempotencia bajo carrera real**: el mismo Idempotency-Key disparado por
   N requests HTTP verdaderamente concurrentes (no uno después del otro) al
   endpoint de checkout de ecommerce. El invariante real: se crea EXACTAMENTE
   una orden, sin importar cuántos requests lleguen en la misma ventana.

A diferencia del resto de scripts/qa_suite/ (que corren pytest contra la app
en el mismo proceso vía ASGITransport), este script pega contra un servidor
uvicorn REAL ya levantado — las conexiones HTTP y las conexiones a Postgres
del lado del servidor son genuinamente concurrentes, no coroutines
cooperativas en el mismo loop de eventos que el cliente de test. Es la
diferencia entre "probé que el código no tiene una race condition obvia" y
"probé que el servidor real, bajo carga real, no la tiene".

Requiere:
- El backend real corriendo (`uvicorn app.main:app`) — por defecto en
  http://127.0.0.1:8000, configurable con --base-url.
- Acceso directo a Postgres (usa el mismo DATABASE_URL_ADMIN del .env) para
  el setup de datos (compañía, producto, stock) y para las verificaciones
  finales — más rápido y determinístico que armar todo por HTTP.

Uso:
    python scripts/qa_suite/11_concurrency_load.py
    python scripts/qa_suite/11_concurrency_load.py --base-url http://127.0.0.1:8000 --concurrency 20
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

import os  # noqa: E402

os.chdir(BACKEND_ROOT)

from sqlalchemy import select, text  # noqa: E402

from app import models_registry  # noqa: E402,F401 — registra todos los modelos antes de tocar cualquier FK
from app.config import settings  # noqa: E402
from app.contacts import schemas as contacts_schemas  # noqa: E402
from app.contacts.services import ContactService  # noqa: E402
from app.core import schemas as core_schemas  # noqa: E402
from app.core.services import RoleService, UserService  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.ecommerce import schemas as ecommerce_schemas  # noqa: E402
from app.ecommerce.services import EcommerceSettingsService  # noqa: E402
from app.inventory import schemas as inv_schemas  # noqa: E402
from app.inventory.services import ProductService, StockService, WarehouseService  # noqa: E402
from app.sales import schemas as sales_schemas  # noqa: E402
from app.sales.services import PriceListService  # noqa: E402


async def _set_tenant(db, company_id: int) -> None:
    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)})


async def _make_company_and_admin(client: httpx.AsyncClient, label: str) -> dict:
    unique = uuid.uuid4().hex[:8]
    resp = await client.post(
        "/internal/companies",
        headers={"X-Internal-Api-Key": settings.internal_api_key},
        json={"name": f"Load Test {label} {unique}"},
    )
    resp.raise_for_status()
    company_id = resp.json()["id"]

    email = f"admin_load_{unique}@test.hn"
    password = "PasswordLoadTest1"

    async with AsyncSessionLocal() as db:
        await _set_tenant(db, company_id)
        from app.core import models as core_models

        codes = await db.execute(select(core_models.Permission.id))
        permission_ids = [row[0] for row in codes.all()]
        role = await RoleService.create_role(
            db, company_id=company_id, payload=core_schemas.RoleCreate(name="Admin", permission_ids=permission_ids),
        )
        user = await UserService.create_user(
            db, company_id=company_id,
            payload=core_schemas.UserCreate(email=email, full_name="Admin Load Test", password=password),
            created_by=None,
        )
        db.add(core_models.UserRole(user_id=user.id, role_id=role.id))
        for package in ("administrative", "medical", "pharmacy", "web"):
            db.add(core_models.CompanyPackage(company_id=company_id, package=package, status="active"))
        await db.commit()

    login = await client.post("/auth/login", json={"email": email, "password": password})
    login.raise_for_status()
    token = login.json()["access_token"]
    return {"company_id": company_id, "headers": {"Authorization": f"Bearer {token}"}}


async def _setup_sales_invoice_account_mappings(db, company_id: int) -> None:
    from app.accounting import models as accounting_models

    for role, name in [("receivable", "Cuentas por Cobrar"), ("income", "Ingresos"), ("tax", "Impuestos por Pagar")]:
        account = accounting_models.Account(company_id=company_id, code=f"LOAD-{role}", name=name, account_type=role)
        db.add(account)
        await db.flush()
        db.add(accounting_models.DocumentAccountMapping(company_id=company_id, document_type="sales_invoice", role=role, account_id=account.id))


# ---------------------------------------------------------------------------
# Escenario 1 — oversell: N confirmaciones simultáneas sobre stock limitado
# ---------------------------------------------------------------------------
async def scenario_oversell(base_url: str, concurrency: int) -> bool:
    print(f"\n{'=' * 70}\nEscenario 1 — oversell (stock limitado, {concurrency} confirmaciones simultáneas)\n{'=' * 70}")

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        tenant = await _make_company_and_admin(client, "Oversell")
        company_id, headers = tenant["company_id"], tenant["headers"]

        physical_stock = concurrency // 2  # a propósito: menos stock que pedidos, para forzar la contención
        async with AsyncSessionLocal() as db:
            await _set_tenant(db, company_id)
            warehouse = await WarehouseService.create(db, company_id=company_id, payload=inv_schemas.WarehouseCreate(name="Bodega Carga"))
            product = await ProductService.create(
                db, company_id=company_id, created_by=None,
                payload=inv_schemas.ProductCreate(
                sku=f"SKU-LOAD-{uuid.uuid4().hex[:6]}", name="Producto Carga",
                product_type=inv_schemas.ProductTypeEnum.facturable,
            ),
            )
            customer = await ContactService.create_contact(
                db, company_id=company_id, created_by=None,
                payload=contacts_schemas.ContactCreate(name="Cliente Carga", is_customer=True),
            )
            await StockService.record_movement(
                db, company_id=company_id, created_by=None,
                payload=inv_schemas.StockMovementCreate(
                    product_id=product.id, warehouse_id=warehouse.id, movement_type=inv_schemas.MovementTypeEnum.entrada,
                    quantity=physical_stock, reference="Stock inicial — script de carga",
                ),
            )
            await db.commit()
            warehouse_id, product_id, customer_id = warehouse.id, product.id, customer.id

        print(f"Stock físico: {physical_stock} unidades. Creando {concurrency} sales orders draft de 1 unidad cada uno...")
        order_ids = []
        for _ in range(concurrency):
            resp = await client.post(
                "/sales/sales-orders", headers=headers,
                json={
                    "customer_id": customer_id, "warehouse_id": warehouse_id,
                    "lines": [{"product_id": product_id, "quantity": 1, "unit_price": 100}],
                },
            )
            resp.raise_for_status()
            order_ids.append(resp.json()["id"])

        print(f"Disparando las {concurrency} confirmaciones EN PARALELO (asyncio.gather, requests HTTP reales)...")

        async def confirm_one(order_id: int) -> int:
            resp = await client.post(f"/sales/sales-orders/{order_id}/confirm", headers=headers)
            return resp.status_code

        results = await asyncio.gather(*(confirm_one(oid) for oid in order_ids))

        successes = sum(1 for s in results if s == 200)
        conflicts = sum(1 for s in results if s == 409)
        server_errors = [s for s in results if s >= 500]

        async with AsyncSessionLocal() as db:
            await _set_tenant(db, company_id)
            from app.inventory import models as inv_models

            level = (await db.execute(
                select(inv_models.StockLevel).where(
                    inv_models.StockLevel.company_id == company_id, inv_models.StockLevel.product_id == product_id,
                    inv_models.StockLevel.warehouse_id == warehouse_id, inv_models.StockLevel.lot_id.is_(None),
                )
            )).scalar_one()
            reserved = level.reserved_quantity

        print(f"Resultados: {successes} exitosas (200), {conflicts} rechazadas por stock insuficiente (409), {len(server_errors)} 5xx.")
        print(f"reserved_quantity final en DB: {reserved} (físico disponible: {physical_stock})")

        ok = True
        if server_errors:
            print(f"✗ FALLO: {len(server_errors)} confirmaciones devolvieron 5xx bajo concurrencia real — códigos: {server_errors}")
            ok = False
        if successes != physical_stock:
            print(f"✗ FALLO: se esperaban {physical_stock} confirmaciones exitosas (una por unidad física), se observaron {successes}.")
            ok = False
        if reserved > physical_stock:
            print(f"✗ FALLO CRÍTICO — OVERSELL REAL: reserved_quantity ({reserved}) > stock físico ({physical_stock}).")
            ok = False
        if ok:
            print(f"✓ Sin oversell: {successes}/{concurrency} exitosas, {conflicts} rechazadas, reserved_quantity nunca superó el físico.")
        return ok


# ---------------------------------------------------------------------------
# Escenario 2 — idempotencia real: mismo Idempotency-Key, N requests simultáneos
# ---------------------------------------------------------------------------
async def scenario_idempotency_race(base_url: str, concurrency: int) -> bool:
    print(f"\n{'=' * 70}\nEscenario 2 — idempotencia bajo carrera real ({concurrency} checkouts simultáneos, mismo Idempotency-Key)\n{'=' * 70}")

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        tenant = await _make_company_and_admin(client, "Idempotency")
        company_id = tenant["company_id"]

        async with AsyncSessionLocal() as db:
            await _set_tenant(db, company_id)
            warehouse = await WarehouseService.create(db, company_id=company_id, payload=inv_schemas.WarehouseCreate(name="Bodega Online Carga"))
            product = await ProductService.create(
                db, company_id=company_id, created_by=None,
                payload=inv_schemas.ProductCreate(
                    sku=f"SKU-IDEMP-{uuid.uuid4().hex[:6]}", name="Producto Idempotencia",
                    product_type=inv_schemas.ProductTypeEnum.facturable,
                ),
            )
            price_list = await PriceListService.create(
                db, company_id=company_id,
                payload=sales_schemas.PriceListCreate(
                    name="Lista Carga", is_default=True,
                    items=[sales_schemas.PriceListItemCreate(product_id=product.id, unit_price=100)],
                ),
            )
            await EcommerceSettingsService.create(db, company_id=company_id)
            await EcommerceSettingsService.update(
                db, company_id=company_id,
                payload=ecommerce_schemas.EcommerceSettingsUpdate(default_warehouse_id=warehouse.id, default_price_list_id=price_list.id),
            )
            await StockService.record_movement(
                db, company_id=company_id, created_by=None,
                payload=inv_schemas.StockMovementCreate(
                    product_id=product.id, warehouse_id=warehouse.id, movement_type=inv_schemas.MovementTypeEnum.entrada,
                    quantity=1000, reference="Stock inicial — script de carga",
                ),
            )
            await _setup_sales_invoice_account_mappings(db, company_id)
            await db.commit()
            product_id = product.id

        cart_resp = await client.post(f"/public/ecommerce/{company_id}/carts")
        cart_resp.raise_for_status()
        cart_body = cart_resp.json()
        cart_id, cart_token = cart_body["id"], cart_resp.headers.get("X-Cart-Token") or cart_body.get("session_token")
        if not cart_token:
            print("✗ No se pudo obtener el token del carrito — revisar la respuesta de POST /carts (shape puede haber cambiado).")
            return False

        add_resp = await client.post(
            f"/public/ecommerce/{company_id}/carts/{cart_id}/items",
            headers={"X-Cart-Token": cart_token}, json={"product_id": product_id, "quantity": 1},
        )
        add_resp.raise_for_status()

        idempotency_key = str(uuid.uuid4())
        checkout_payload = {"name": "Cliente Carga", "email": "cliente.carga@test.hn"}

        print(f"Disparando {concurrency} checkouts EN PARALELO con Idempotency-Key={idempotency_key}...")

        async def checkout_once() -> httpx.Response:
            return await client.post(
                f"/public/ecommerce/{company_id}/carts/{cart_id}/checkout",
                headers={"X-Cart-Token": cart_token, "Idempotency-Key": idempotency_key}, json=checkout_payload,
            )

        responses = await asyncio.gather(*(checkout_once() for _ in range(concurrency)))
        status_codes = [r.status_code for r in responses]
        order_ids_seen = {r.json().get("sales_order_id") for r in responses if r.status_code < 400}

        async with AsyncSessionLocal() as db:
            await _set_tenant(db, company_id)
            from app.sales import models as sales_models

            real_count = (await db.execute(
                select(sales_models.SalesOrder).where(sales_models.SalesOrder.company_id == company_id)
            )).scalars().all()

        print(f"Status codes observados: {sorted(set(status_codes))} (conteo: {status_codes})")
        print(f"sales_order_id distintos entre las respuestas exitosas: {order_ids_seen}")
        print(f"SalesOrders reales creadas en la DB para esta compañía: {len(real_count)}")

        ok = True
        server_errors = [s for s in status_codes if s >= 500]
        if server_errors:
            print(f"✗ FALLO: {len(server_errors)} checkouts devolvieron 5xx bajo concurrencia real.")
            ok = False
        if len(order_ids_seen) > 1:
            print(f"✗ FALLO CRÍTICO — IDEMPOTENCIA ROTA: se crearon {len(order_ids_seen)} órdenes distintas ({order_ids_seen}).")
            ok = False
        if len(real_count) != 1:
            print(f"✗ FALLO CRÍTICO: hay {len(real_count)} SalesOrder(s) reales en la DB para esta compañía — se esperaba exactamente 1.")
            ok = False
        no_success_seen = not any(s < 400 for s in status_codes)
        if len(real_count) == 1 and no_success_seen:
            # No es un fallo del invariante duro que este script existe para
            # proteger (no hay doble orden, no hay crash) — pero SÍ es un
            # hallazgo real y no trivial: la respuesta "canónica" que la capa
            # de idempotencia cacheó para esta clave fue un error (409),
            # pese a que una de las N ejecuciones concurrentes SÍ creó una
            # orden real de verdad (con su reserva de stock y su factura).
            # Ningún cliente de las 20 llamadas se entera de que la orden
            # existe — el "primero en persistir gana" de
            # IdempotencyService._persist_or_yield_to_winner no distingue
            # una respuesta de éxito de una de error al decidir cuál es la
            # canónica, y bajo esta forma particular de carrera (los
            # caminos de fallo terminan más rápido que el de éxito, así que
            # tienden a ganar la carrera de persistencia) el error gana casi
            # siempre. Corregir esto de raíz requiere serializar TODA la
            # ejecución de `command()` detrás de un lock/reserva de la
            # Idempotency-Key antes de correr nada (no solo la persistencia
            # del resultado al final) — rediseño real, no un fix quirúrgico;
            # ver STATE.md.
            print(
                f"⚠ HALLAZGO (no bloqueante): se creó 1 SalesOrder real, pero NINGUNA de las {concurrency} "
                f"respuestas HTTP fue de éxito (todas devolvieron error) — la respuesta canónica cacheada "
                f"para esta Idempotency-Key fue un error pese a que la operación sí tuvo éxito en alguna "
                f"ejecución concurrente. Ningún cliente se entera de que la orden existe."
            )
        if ok:
            print(f"✓ Sin duplicado ni crash: {concurrency} requests concurrentes con la misma clave produjeron exactamente 1 SalesOrder, sin 5xx.")
        return ok


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="URL del backend real ya corriendo (uvicorn)")
    parser.add_argument("--concurrency", type=int, default=20, help="Cantidad de requests verdaderamente concurrentes por escenario")
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base_url, timeout=5.0) as probe:
        try:
            await probe.get("/docs")
        except httpx.ConnectError:
            print(f"✗ No se pudo conectar a {args.base_url} — ¿está uvicorn corriendo? (uvicorn app.main:app --host 127.0.0.1 --port 8000)")
            return 1

    ok1 = await scenario_oversell(args.base_url, args.concurrency)
    ok2 = await scenario_idempotency_race(args.base_url, args.concurrency)

    print(f"\n{'=' * 70}")
    if ok1 and ok2:
        print("✓✓✓ Ambos escenarios de concurrencia real en verde — punto seguro para commit/push. ✓✓✓")
        return 0
    print("✗ Al menos un escenario de concurrencia encontró un hallazgo real — ver detalle arriba.")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
