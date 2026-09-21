"""
tests/security/test_tenant_isolation.py — aislamiento multi-tenant vía HTTP real.

Para cada recurso en resource_factories.RESOURCES: se crea en tenant_b (la
"víctima"), y se intenta acceder/modificar/listar con el token real de
tenant_a (el "atacante"). El resultado correcto en los tres casos:

- GET detalle con el id de B -> nunca 200. 403 o 404 son ambos aceptables
  (algunos diseños devuelven 404 a propósito para no filtrar ni siquiera la
  existencia del recurso vía la diferencia 403 vs 404 — no se exige una
  convención sobre la otra, solo que nunca sea 200).
- PATCH detalle con el id de B -> nunca 200 (ni un 200 que "no cambió nada":
  si el status es 200, se asume que modificó datos ajenos).
- GET listado de A -> el id de B nunca debería aparecer entre los resultados.

Cualquier 200 acá es un hallazgo de severidad alta — reportado con el nombre
del recurso y la ruta exacta para que se pueda reproducir con curl.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from app.database import AsyncSessionLocal
from tests.security.resource_factories import FACTORIES, Resource, set_tenant_context


@pytest_asyncio.fixture(params=sorted(FACTORIES.keys()))
async def victim_resource(request, tenant_b: dict) -> Resource:
    """Crea el recurso parametrizado en tenant_b y lo devuelve ya con las
    rutas HTTP armadas."""
    factory = FACTORIES[request.param]
    async with AsyncSessionLocal() as db:
        await set_tenant_context(db, tenant_b["company_id"])
        resource = await factory(db, tenant_b["company_id"])
        await db.commit()
    return resource


@pytest.mark.asyncio
async def test_cross_tenant_detail_access_denied(client, tenant_a: dict, victim_resource: Resource):
    for method, path in victim_resource.detail_routes:
        if method == "GET":
            response = await client.get(path, headers=tenant_a["headers"])
        elif method == "PATCH":
            response = await client.patch(path, headers=tenant_a["headers"], json=victim_resource.patch_payload or {})
        else:
            continue
        assert response.status_code in (403, 404), (
            f"IDOR real: {method} {path} devolvió {response.status_code} (se esperaba 403/404) "
            f"para el recurso '{victim_resource.name}' de OTRO tenant. Body: {response.text[:500]}"
        )


@pytest.mark.asyncio
async def test_cross_tenant_list_does_not_leak(client, tenant_a: dict, victim_resource: Resource):
    if victim_resource.list_route is None:
        pytest.skip(f"{victim_resource.name} no tiene ruta de listado global (cubierto solo por detail_routes)")
    response = await client.get(victim_resource.list_route, headers=tenant_a["headers"])
    if response.status_code != 200:
        # 403 (por RBAC o por licenciamiento de paquete, ej. PACKAGE_NOT_LICENSED)
        # o 404 ya prueban por sí solos que no hay fuga — no hay body con
        # datos que inspeccionar.
        return
    body = response.json()
    items = body if isinstance(body, list) else body.get("items", body.get("results", []))
    leaked_ids = [item.get("id") for item in items if isinstance(item, dict) and item.get("id") == victim_resource.resource_id]
    assert not leaked_ids, (
        f"Fuga real: el listado {victim_resource.list_route} de tenant_a incluye el id "
        f"{victim_resource.resource_id} del recurso '{victim_resource.name}' que pertenece a tenant_b."
    )


@pytest.mark.asyncio
async def test_cross_tenant_foreign_key_reference_rejected(client, tenant_a: dict, tenant_b: dict):
    """El otro lado del mismo bug: usar el id de un recurso AJENO como FK al
    crear algo propio. Ej.: un SalesOrder de tenant_a con customer_id de un
    contacto de tenant_b — si el service solo valida "existe ese id" sin
    filtrar por company_id, esto pasaría silenciosamente (facturarle a un
    cliente ajeno, o peor, filtrar su nombre en la respuesta del pedido
    creado)."""
    async with AsyncSessionLocal() as db:
        await set_tenant_context(db, tenant_b["company_id"])
        victim_contact = await FACTORIES["contacts.contact"](db, tenant_b["company_id"])
        await db.commit()

    from app.inventory import schemas as inv_schemas
    from app.inventory.services import ProductService, WarehouseService

    async with AsyncSessionLocal() as db:
        await set_tenant_context(db, tenant_a["company_id"])
        warehouse = await WarehouseService.create(db, company_id=tenant_a["company_id"], payload=inv_schemas.WarehouseCreate(name="Almacén A"))
        product = await ProductService.create(
            db, company_id=tenant_a["company_id"], created_by=None,
            payload=inv_schemas.ProductCreate(sku="SKU-CROSS-TEST", name="Producto A", product_type=inv_schemas.ProductTypeEnum.facturable),
        )
        await db.commit()
        warehouse_id, product_id = warehouse.id, product.id

    response = await client.post(
        "/sales/sales-orders",
        headers=tenant_a["headers"],
        json={
            "customer_id": victim_contact.resource_id,  # contacto de tenant_b, usado desde tenant_a
            "warehouse_id": warehouse_id,
            "lines": [{"product_id": product_id, "quantity": 1, "unit_price": 100}],
        },
    )
    assert response.status_code in (403, 404, 422), (
        f"IDOR vía FK cruzada: crear un sales order en tenant_a usando el contact_id de tenant_b "
        f"devolvió {response.status_code} (se esperaba 403/404/422). Body: {response.text[:500]}"
    )
