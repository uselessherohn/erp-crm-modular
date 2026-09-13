"""
Dependencias propias de `website` para sus rutas públicas (storefront, sin
JWT — spec 10: `storefront/` es un frontend separado del panel interno).

AMBIGUO, no confirmado por Roberto (ver `diseno_modulos_22_25_erp_crm.md`
sección 2.4): en producción el storefront necesita resolver `company_id`
por subdominio o dominio propio, no por un id explícito en la URL. Aquí se
implementa la variante explícita (`company_id` como path param) porque es
funcionalmente correcta y suficiente para levantar el módulo — cambiar la
resolución a subdominio/dominio el día que se confirme NO debería tocar
`services.py` ni los modelos, solo esta dependencia y el router público.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_active_packages
from app.core.models import PackageStatusEnum
from app.database import AsyncSessionLocal
from app.shared.exceptions import PackageNotLicensedError


async def get_public_db_context(company_id: int) -> AsyncSession:
    """Igual que `get_db_with_tenant_context`, pero sin pasar por
    `get_current_user` (no hay JWT en una request anónima del storefront).
    RLS sigue aplicando normal — se fija `app.current_company_id` con el
    valor de la URL en vez de con el de un token firmado."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)}
        )
        yield session


async def ensure_web_package_active(db: AsyncSession, *, company_id: int) -> None:
    """Equivalente público de `require_package("web")` — no puede
    reutilizarse la dependencia FastAPI original porque esa depende de
    `get_current_company_id`/JWT. Misma función de dominio
    (`get_active_packages`) por debajo, mismo criterio de error
    (`PACKAGE_NOT_LICENSED`, nunca un 404 silencioso — spec 2.4)."""
    packages = await get_active_packages(company_id, db)
    row = packages.get("web")
    if row is None or row.status == PackageStatusEnum.deactivated:
        raise PackageNotLicensedError("Paquete 'web' no contratado")
