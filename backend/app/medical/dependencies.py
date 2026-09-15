"""
Dependencias propias de `medical` para su única ruta pública (widget de
reserva de citas, módulo 15, sin JWT).

Spec 8.2 ("Reserva Pública de Citas"): "Requiere el paquete Web activo".
Spec 8.4 (`website`, "Widget de Reserva Pública de Citas"): "Requiere
Médico activo; sin él, la ruta del widget no se expone
(PACKAGE_NOT_LICENSED)". Las dos secciones describen la misma
integración desde lados distintos — el gating real exige AMBOS paquetes
activos, no uno u otro.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_active_packages
from app.core.models import PackageStatusEnum
from app.database import AsyncSessionLocal
from app.shared.exceptions import PackageNotLicensedError, PackageSuspendedError


async def get_public_db_context(company_id: int) -> AsyncSession:
    """Idéntico en propósito a `website.dependencies.get_public_db_context`
    (sin JWT, RLS fijado con el `company_id` explícito de la URL) —
    duplicado en vez de importado desde `website` para no crear una
    dependencia de código de `medical` hacia `website` por una función de
    3 líneas sin lógica de dominio; ambos ya comparten la dependencia
    real y declarada de la tabla de módulos (`depende_de: [9, 22]`)."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)}
        )
        yield session


async def ensure_public_booking_active(db: AsyncSession, *, company_id: int) -> None:
    """Equivalente público de `require_package("medical")` +
    `require_package("web")` combinados — ninguna de las dos dependencias
    FastAPI originales sirve acá porque ambas dependen de JWT
    (`get_current_company_id`), que una request anónima del widget no
    tiene. Mismo criterio de error que el resto del proyecto
    (`PACKAGE_NOT_LICENSED`, nunca un 404 silencioso — spec 2.4).

    Crear una cita es una escritura, no solo lectura — a diferencia de
    `website.ensure_web_package_active` (que solo bloquea `deactivated`,
    porque sus rutas públicas incluyen lectura de páginas ya publicadas),
    acá también se bloquea `suspended` en CUALQUIERA de los dos paquetes,
    mismo criterio que `require_package_writable` (spec 13, punto 2)."""
    packages = await get_active_packages(company_id, db)

    for package in ("web", "medical"):
        row = packages.get(package)
        if row is None or row.status == PackageStatusEnum.deactivated:
            raise PackageNotLicensedError(f"Paquete '{package}' no contratado")
        if row.status == PackageStatusEnum.suspended:
            raise PackageSuspendedError(f"Paquete '{package}' suspendido")
