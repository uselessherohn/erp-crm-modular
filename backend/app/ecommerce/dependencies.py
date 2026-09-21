"""
Mismo criterio que `website/dependencies.py` (módulo 22) para las rutas
públicas del storefront (sin JWT). Se duplica aquí en vez de importar
desde `website` porque son paquetes de dominio distintos — TODO no
bloqueante: si aparece un tercer módulo con rutas públicas, mover
`get_public_db_context` a `app/core/dependencies.py` como utilidad
compartida en vez de seguir duplicándolo.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_active_packages
from app.core.models import PackageStatusEnum
from app.database import AsyncSessionLocal
from app.shared.exceptions import PackageNotLicensedError


async def get_public_db_context(company_id: int) -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)}
        )
        yield session


async def ensure_ecommerce_active(db: AsyncSession, *, company_id: int) -> None:
    """Gating real de `ecommerce` (spec 2.2/2.4, ver
    `diseno_modulos_22_25_erp_crm.md` sección 2.1): requiere el paquete
    `web` con `ecommerce` incluido en `minimal_modules` (o compra completa
    de `web`, `minimal_modules` vacío/None — misma semántica que el fix de
    `require_package` en `core/dependencies.py`) Y el arrastre técnico
    `inventory+sales+accounting` sobre `administrative` (se valida
    contra `sales` como representante del trío — spec 2.2 garantiza que
    los tres siempre se conceden juntos, nunca un subconjunto)."""
    packages = await get_active_packages(company_id, db)

    web_row = packages.get("web")
    if web_row is None or web_row.status == PackageStatusEnum.deactivated:
        raise PackageNotLicensedError("Paquete 'web' no contratado")
    web_modules = web_row.minimal_modules
    if web_modules and "ecommerce" not in web_modules:
        raise PackageNotLicensedError("El paquete 'web' contratado no incluye 'ecommerce'")

    admin_row = packages.get("administrative")
    if admin_row is None or admin_row.status == PackageStatusEnum.deactivated:
        raise PackageNotLicensedError("Ecommerce requiere el mínimo técnico de 'administrative' (inventory+sales+accounting)")
    admin_modules = admin_row.minimal_modules
    if admin_modules and "sales" not in admin_modules:
        raise PackageNotLicensedError("El arrastre de 'administrative' no incluye 'sales'")
