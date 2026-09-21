"""
Registro de recursos para tests/security/test_tenant_isolation.py.

Cada entrada de RESOURCES describe UN recurso real de negocio: cómo crearlo
en una compañía (vía capa de servicio, directo contra Postgres — igual de
rápido y confiable que el resto de la suite), y qué rutas HTTP probar con su
id una vez creado.

Este registro es DELIBERADAMENTE curado, no automático — cubre un recurso
representativo de 7 módulos distintos, elegidos por sensibilidad de negocio
(datos clínicos, salarios, contactos con tax_id) o por ser cadenas de
creación no triviales (sales order con líneas reales). Para que un agente lo
extienda a otro módulo: agregar una entrada nueva a RESOURCES con su propia
factory async — el test ya la recorre automáticamente, no hace falta tocar
test_tenant_isolation.py.

test_route_crawler_no_crashes.py complementa esto con un crawler automático
sobre TODAS las rutas parametrizadas de la app (vía el schema OpenAPI) — más
superficial (no created el recurso "correcto", solo prueba con un id
inexistente) pero cubre módulos que este registro no cura a mano.
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import models_registry  # noqa: F401 — registra todos los modelos antes de tocar cualquier FK


@dataclass
class Resource:
    """Un recurso creado en una compañía, y las rutas HTTP que deberían
    volverse inaccesibles para un token de OTRA compañía."""

    name: str
    resource_id: int
    # (método, path) — path ya con el id interpolado.
    detail_routes: list[tuple[str, str]] = field(default_factory=list)
    # path de la ruta de listado que NO debería incluir este id.
    list_route: str | None = None
    # payload mínimo válido para un PATCH, si hay ruta de PATCH en detail_routes.
    patch_payload: dict | None = None


async def set_tenant_context(db: AsyncSession, company_id: int) -> None:
    await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)})


async def _make_contact(db: AsyncSession, company_id: int) -> Resource:
    from app.contacts import schemas as contacts_schemas
    from app.contacts.services import ContactService

    contact = await ContactService.create_contact(
        db, company_id=company_id,
        payload=contacts_schemas.ContactCreate(name=f"Contacto {uuid.uuid4().hex[:6]}", is_customer=True, tax_id="0801199912345"),
        created_by=None,
    )
    return Resource(
        name="contacts.contact",
        resource_id=contact.id,
        detail_routes=[("GET", f"/contacts/{contact.id}"), ("PATCH", f"/contacts/{contact.id}")],
        list_route="/contacts",
        patch_payload={"name": "Nombre pisado por tenant ajeno"},
    )


async def _make_product(db: AsyncSession, company_id: int) -> Resource:
    from app.inventory import schemas as inv_schemas
    from app.inventory.services import ProductService

    product = await ProductService.create(
        db, company_id=company_id, created_by=None,
        payload=inv_schemas.ProductCreate(
            sku=f"SKU-{uuid.uuid4().hex[:8]}", name="Producto de prueba",
            product_type=inv_schemas.ProductTypeEnum.facturable,
        ),
    )
    return Resource(
        name="inventory.product",
        resource_id=product.id,
        detail_routes=[("GET", f"/inventory/products/{product.id}")],
        list_route="/inventory/products",
    )


async def _make_employee(db: AsyncSession, company_id: int) -> Resource:
    from app.hr import schemas as hr_schemas
    from app.hr.services import DepartmentService, EmployeeService

    _dept = await DepartmentService.create(db, company_id=company_id, payload=hr_schemas.DepartmentCreate(name="Depto de prueba"))
    employee = await EmployeeService.create(
        db, company_id=company_id,
        payload=hr_schemas.EmployeeCreate(first_name="Emp", last_name=f"Leado{uuid.uuid4().hex[:6]}", hire_date=date(2026, 1, 1)),
        created_by=None,
    )
    return Resource(
        name="hr.employee — incluye salario, dato sensible",
        resource_id=employee.id,
        detail_routes=[("GET", f"/hr/employees/{employee.id}"), ("PATCH", f"/hr/employees/{employee.id}")],
        list_route="/hr/employees",
        patch_payload={"salary": "999999.00"},
    )


async def _make_opportunity(db: AsyncSession, company_id: int) -> Resource:
    from app.pipeline import schemas as pipeline_schemas
    from app.pipeline.services import OpportunityService, StageService

    stage = await StageService.create(db, company_id=company_id, payload=pipeline_schemas.StageCreate(name="Prospecto"))
    contact_resource = await _make_contact(db, company_id)
    opportunity = await OpportunityService.create(
        db, company_id=company_id,
        payload=pipeline_schemas.OpportunityCreate(contact_id=contact_resource.resource_id, stage_id=stage.id, name="Oportunidad de prueba"),
        created_by=None,
    )
    return Resource(
        name="pipeline.opportunity",
        resource_id=opportunity.id,
        detail_routes=[("GET", f"/pipeline/opportunities/{opportunity.id}")],
        list_route="/pipeline/opportunities",
    )


async def _make_sales_order(db: AsyncSession, company_id: int) -> Resource:
    from app.inventory import schemas as inv_schemas
    from app.inventory.services import WarehouseService
    from app.sales import schemas as sales_schemas
    from app.sales.services import SalesOrderService

    contact_resource = await _make_contact(db, company_id)
    product_resource = await _make_product(db, company_id)
    warehouse = await WarehouseService.create(db, company_id=company_id, payload=inv_schemas.WarehouseCreate(name="Almacén de prueba"))
    order = await SalesOrderService.create_draft(
        db, company_id=company_id, created_by=None,
        payload=sales_schemas.SalesOrderCreate(
            customer_id=contact_resource.resource_id, warehouse_id=warehouse.id,
            lines=[sales_schemas.SalesOrderLineCreate(product_id=product_resource.resource_id, quantity=1, unit_price=100)],
        ),
    )
    return Resource(
        name="sales.sales_order",
        resource_id=order.id,
        detail_routes=[("GET", f"/sales/sales-orders/{order.id}")],
        list_route="/sales/sales-orders",
    )


async def _make_clinical_record(db: AsyncSession, company_id: int) -> Resource:
    """El recurso más sensible del registro — expediente clínico cifrado
    (pgcrypto). Necesita un contacto con is_patient=True y un usuario
    "profesional" (cualquier usuario real sirve para el FK de autor)."""
    from app.contacts import schemas as contacts_schemas
    from app.contacts.services import ContactService
    from app.core import schemas as core_schemas
    from app.core.services import UserService
    from app.medical import schemas as medical_schemas
    from app.medical.services import ClinicalRecordService

    patient = await ContactService.create_contact(
        db, company_id=company_id,
        payload=contacts_schemas.ContactCreate(name=f"Paciente {uuid.uuid4().hex[:6]}", is_patient=True),
        created_by=None,
    )
    professional = await UserService.create_user(
        db, company_id=company_id,
        payload=core_schemas.UserCreate(email=f"dr.{uuid.uuid4().hex[:8]}@test.hn", full_name="Dr. Prueba", password="PasswordDrTest1"),
        created_by=None,
    )
    entry = await ClinicalRecordService.create_entry(
        db, company_id=company_id, author_user_id=professional.id,
        payload=medical_schemas.ClinicalRecordEntryCreate(
            patient_contact_id=patient.id, entry_type=medical_schemas.ClinicalRecordEntryTypeEnum.note,
            content="Dato clínico confidencial del tenant víctima — no debería ser legible por otro tenant.",
        ),
    )
    return Resource(
        name="medical.clinical_record_entry — dato clínico cifrado",
        resource_id=entry.id,
        detail_routes=[("GET", f"/medical/records/{entry.id}")],
        list_route=None,  # no hay listado global, solo por paciente — cubierto por el detail_route
    )


# Nombre -> factory. El test recorre esto en orden; agregar una entrada acá
# es la única extensión que hace falta para cubrir un módulo más.
FACTORIES: dict[str, Callable[[AsyncSession, int], Awaitable[Resource]]] = {
    "contacts.contact": _make_contact,
    "inventory.product": _make_product,
    "hr.employee": _make_employee,
    "pipeline.opportunity": _make_opportunity,
    "sales.sales_order": _make_sales_order,
    "medical.clinical_record_entry": _make_clinical_record,
}
