"""
Whitelist de métricas para "Reportes Cruzados" [core] (spec 8.1). Cada
entrada es una consulta de solo lectura predefinida — el cliente (panel
interno o un widget de `Dashboard`) solo puede referenciar una por
`metric_key`, nunca enviar SQL propio (spec 5: sin consultas libres desde
el cliente, ni siquiera para reportería).

Todas las consultas ya filtran por `company_id` explícito (nunca confían
solo en RLS para reportería agregada — un `GROUP BY` que accidentalmente
cruce compañías por un JOIN mal filtrado sería un fallo silencioso mucho
más difícil de notar que en una consulta de un solo registro). RLS sigue
activo como segunda capa, no la única.

TODO explícito, fuera de alcance de este cierre: métricas que crucen
`medical`/`pharmacy` — requeriría validar el paquete de origen de cada
dominio tocado antes de exponer el resultado (ver
`diseno_modulos_22_25_erp_crm.md` sección 3.1), no solo el paquete
`administrative` que gatea el router de `reports` en general.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    columns: list[str]
    # Todas reciben (db, company_id, date_from, date_to) aunque algunas
    # (fotos del estado actual, ej. stock) ignoren el rango de fechas —
    # firma uniforme para que el router no necesite saber cuáles sí lo usan.
    query: Callable[[AsyncSession, int, date, date], Awaitable[list[dict]]]


async def _sales_by_customer(db: AsyncSession, company_id: int, date_from: date, date_to: date) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT c.name AS cliente, SUM(sol.quantity * sol.unit_price) AS total
            FROM sales_orders so
            JOIN contacts c ON c.id = so.customer_id
            JOIN sales_order_lines sol ON sol.sales_order_id = so.id
            WHERE so.company_id = :company_id AND so.status != 'cancelado'
              AND so.created_at >= :date_from AND so.created_at < :date_to
            GROUP BY c.name
            ORDER BY total DESC
            """
        ),
        {"company_id": company_id, "date_from": date_from, "date_to": date_to},
    )
    return [dict(row) for row in result.mappings().all()]


async def _top_products_by_revenue(db: AsyncSession, company_id: int, date_from: date, date_to: date) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT p.sku AS sku, p.name AS producto,
                   SUM(sol.quantity) AS cantidad_vendida,
                   SUM(sol.quantity * sol.unit_price) AS ingresos
            FROM sales_order_lines sol
            JOIN sales_orders so ON so.id = sol.sales_order_id
            JOIN products p ON p.id = sol.product_id
            WHERE so.company_id = :company_id AND so.status != 'cancelado'
              AND so.created_at >= :date_from AND so.created_at < :date_to
            GROUP BY p.sku, p.name
            ORDER BY ingresos DESC
            LIMIT 50
            """
        ),
        {"company_id": company_id, "date_from": date_from, "date_to": date_to},
    )
    return [dict(row) for row in result.mappings().all()]


async def _accounts_receivable_open(db: AsyncSession, company_id: int, date_from: date, date_to: date) -> list[dict]:
    """Foto del estado actual de cuentas por cobrar abiertas, filtrada por
    `issue_date` en el rango (no por fecha de vencimiento) — DEDUCIBLE, no
    confirmado por Roberto."""
    result = await db.execute(
        text(
            """
            SELECT c.name AS cliente, i.number AS factura, i.issue_date AS fecha_emision,
                   i.due_date AS fecha_vencimiento, i.balance_due AS saldo_pendiente
            FROM invoices i
            JOIN contacts c ON c.id = i.contact_id
            WHERE i.company_id = :company_id AND i.direction = 'sale' AND i.status = 'posted'
              AND i.balance_due > 0
              AND i.issue_date >= :date_from AND i.issue_date < :date_to
            ORDER BY i.due_date ASC NULLS LAST
            """
        ),
        {"company_id": company_id, "date_from": date_from, "date_to": date_to},
    )
    return [dict(row) for row in result.mappings().all()]


async def _stock_by_warehouse(db: AsyncSession, company_id: int, date_from: date, date_to: date) -> list[dict]:
    """Foto del stock actual — ignora `date_from`/`date_to` (no hay
    histórico de saldos, solo el saldo materializado actual)."""
    result = await db.execute(
        text(
            """
            SELECT w.name AS almacen, p.sku AS sku, p.name AS producto,
                   SUM(sl.quantity) AS cantidad_disponible, SUM(sl.reserved_quantity) AS cantidad_reservada
            FROM stock_levels sl
            JOIN warehouses w ON w.id = sl.warehouse_id
            JOIN products p ON p.id = sl.product_id
            WHERE sl.company_id = :company_id
            GROUP BY w.name, p.sku, p.name
            ORDER BY w.name, p.name
            """
        ),
        {"company_id": company_id},
    )
    return [dict(row) for row in result.mappings().all()]


METRICS: dict[str, MetricDefinition] = {
    "sales_by_customer": MetricDefinition(
        key="sales_by_customer", label="Ventas por cliente",
        columns=["cliente", "total"], query=_sales_by_customer,
    ),
    "top_products_by_revenue": MetricDefinition(
        key="top_products_by_revenue", label="Productos más vendidos (por ingresos)",
        columns=["sku", "producto", "cantidad_vendida", "ingresos"], query=_top_products_by_revenue,
    ),
    "accounts_receivable_open": MetricDefinition(
        key="accounts_receivable_open", label="Cuentas por cobrar abiertas",
        columns=["cliente", "factura", "fecha_emision", "fecha_vencimiento", "saldo_pendiente"],
        query=_accounts_receivable_open,
    ),
    "stock_by_warehouse": MetricDefinition(
        key="stock_by_warehouse", label="Stock actual por almacén",
        columns=["almacen", "sku", "producto", "cantidad_disponible", "cantidad_reservada"],
        query=_stock_by_warehouse,
    ),
}
