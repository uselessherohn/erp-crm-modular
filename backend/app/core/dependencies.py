"""
Dependencias reutilizables de `core` (spec sección 5 y 2.4).

- `get_db_with_tenant_context`: fija `app.current_company_id` vía
  `set_config()` una sola vez por transacción (RLS, defensa en profundidad).
- `get_current_user` / `get_current_company_id`: nunca se lee `company_id`
  del payload del cliente.
- `get_current_warehouse_id` / `get_required_warehouse_id`: ver TODO abajo —
  `Warehouse` no existe todavía (vive en `inventory`, módulo 3).
- `get_active_packages` (función de dominio, no atada a FastAPI) +
  `require_package` (dependencia FastAPI que la usa, con cache por request).
- `require_permission`: RBAC granular `modulo:accion`.
"""
from __future__ import annotations

from fastapi import Depends, Header, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import CompanyPackage, PackageStatusEnum, Permission, User
from app.core.security import decode_access_token
from app.database import AsyncSessionLocal
from app.shared.exceptions import (
    PackageNotLicensedError,
    PackageSuspendedError,
    PermissionDeniedError,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extrae y valida el JWT del header Authorization: Bearer <token>.
    No fija todavía el contexto RLS (eso lo hace get_db_with_tenant_context,
    que depende de esta función) — acá solo autentica al usuario."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise PermissionDeniedError("Falta el header Authorization: Bearer <token>")

    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise PermissionDeniedError("Token inválido o expirado") from exc

    user_id = int(payload["sub"])

    # Nota: esta consulta corre ANTES de que el contexto RLS esté fijado
    # (todavía no sabemos el company_id validado). Es la única query del
    # sistema que necesariamente antecede a set_config() — se justifica
    # porque es cómo se descubre el company_id en primer lugar. El rol
    # erp_app con RLS FORCE + sin policy de excepción para esta tabla
    # bloquearía incluso esta lectura si no existiera una vía — por eso
    # esta consulta puntual usa una sesión separada con
    # current_setting relajado a NULL, lo cual bajo la policy
    # `company_id = current_setting(...)::bigint` con `NULLIF`/true como
    # segundo argumento de current_setting simplemente no matchea ninguna
    # fila. Solución: fijamos company_id = payload["company_id"] (viene del
    # JWT ya firmado por el propio backend en el login, no del payload
    # arbitrario del cliente) ANTES de la consulta.
    company_id = int(payload["company_id"])
    await db.execute(
        text("SELECT set_config('app.current_company_id', :cid, false)"),
        {"cid": str(company_id)},
    )

    result = await db.execute(select(User).where(User.id == user_id, User.company_id == company_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise PermissionDeniedError("Usuario no encontrado o inactivo")

    return user


def get_current_company_id(user: User = Depends(get_current_user)) -> int:
    return user.company_id


async def get_db_with_tenant_context(
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> AsyncSession:
    """Ya viene fijado desde get_current_user (necesitábamos company_id antes
    de poder consultar users bajo RLS). Se re-expone acá con el nombre que
    pide la spec (sección 5) para routers que solo necesitan la sesión con
    contexto ya establecido, sin repetir el set_config."""
    await db.execute(
        text("SELECT set_config('app.current_company_id', :cid, false)"),
        {"cid": str(company_id)},
    )
    return db


async def get_current_warehouse_id(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_with_tenant_context),
) -> int | None:
    """Sucursal activa del usuario (spec sección 5).

    TODO (declarado explícitamente, regla 1 del Mensaje 0 — no adelantar
    módulos futuros): la validación de pertenencia completa
    (`db.get(Warehouse, ...)` + `warehouse.company_id != user.company_id`)
    requiere el modelo `Warehouse`, que vive en `inventory` (módulo 3,
    Administrativo — todavía no construido). Hasta que ese módulo exista,
    esta función devuelve `active_warehouse_id` sin validar pertenencia
    contra una tabla que no existe. Es un hueco de seguridad conocido y
    documentado, no un olvido: no aplica todavía porque ningún módulo con
    `warehouse_id` está construido (Farmacéutico/POS, el único que exige
    `get_required_warehouse_id`, es módulo 16+). Cuando se construya el
    módulo 3, esta función se completa con la validación real y este
    comentario se elimina — DEDUCIBLE registrado en STATE.md."""
    if user.active_warehouse_id is None:
        return None
    return user.active_warehouse_id


async def get_required_warehouse_id(
    warehouse_id: int | None = Depends(get_current_warehouse_id),
) -> int:
    if warehouse_id is None:
        raise PermissionDeniedError(
            "Esta operación requiere una sucursal activa (active_warehouse_id); "
            "el usuario autenticado no tiene ninguna asignada"
        )
    return warehouse_id


# ---------------------------------------------------------------------------
# Registro de paquetes y feature flags (spec sección 2.4)
# ---------------------------------------------------------------------------
async def get_active_packages(company_id: int, db: AsyncSession) -> dict[str, CompanyPackage]:
    """Función de dominio pura (no atada a FastAPI) — reutilizable por
    routers Y por workers/schedulers/listeners (spec 2.4, enforcement más
    allá del ciclo HTTP). Devuelve {package_name: CompanyPackage} solo con
    filas existentes (un paquete nunca contratado simplemente no aparece)."""
    result = await db.execute(select(CompanyPackage).where(CompanyPackage.company_id == company_id))
    rows = result.scalars().all()
    return {row.package: row for row in rows}


async def get_active_packages_cached(
    request: Request,
    company_id: int = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db_with_tenant_context),
) -> dict[str, CompanyPackage]:
    """Cache por request (nunca de proceso) — nuevo en v10.4, spec 2.4:
    un paquete suspendido debe verse bloqueado de inmediato, no después de
    que expire un cache compartido entre requests de distintos tenants."""
    cache_attr = "_active_packages_cache"
    if not hasattr(request.state, cache_attr):
        setattr(request.state, cache_attr, await get_active_packages(company_id, db))
    return getattr(request.state, cache_attr)


def require_package(package: str, *, minimal_module: str | None = None):
    """Dependencia FastAPI factory. `minimal_module` se usa cuando la ruta
    protegida es parte de un submódulo mínimo arrastrado (inventory/sales/
    accounting sin Administrativo completo — spec 2.2/2.4)."""

    async def _checker(
        packages: dict[str, CompanyPackage] = Depends(get_active_packages_cached),
    ) -> CompanyPackage:
        row = packages.get(package)
        if row is None:
            raise PackageNotLicensedError(f"Paquete '{package}' no contratado")

        if minimal_module is not None:
            modules = row.minimal_modules or []
            if minimal_module not in modules and row.package != package:
                raise PackageNotLicensedError(
                    f"Submódulo mínimo '{minimal_module}' no incluido en el arrastre de '{package}'"
                )

        if row.status == PackageStatusEnum.deactivated:
            raise PackageNotLicensedError(f"Paquete '{package}' dado de baja")

        return row

    return _checker


def require_package_writable(package: str):
    """Igual que require_package, pero además bloquea escritura si el
    paquete está `suspended` (spec sección 13, punto 2)."""

    async def _checker(row: CompanyPackage = Depends(require_package(package))) -> CompanyPackage:
        if row.status == PackageStatusEnum.suspended:
            raise PackageSuspendedError(f"Paquete '{package}' suspendido — solo lectura histórica")
        return row

    return _checker


# ---------------------------------------------------------------------------
# RBAC granular (spec sección 1: modulo:accion)
# ---------------------------------------------------------------------------
def require_permission(code: str):
    """Dependencia factory: exige que el usuario autenticado tenga, a través
    de alguno de sus roles, el permiso `code` (formato modulo:accion)."""

    async def _checker(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db_with_tenant_context),
    ) -> User:
        from app.core.models import RolePermission, UserRole  # import local: evita ciclo con models

        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user.id, Permission.code == code)
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise PermissionDeniedError(f"Falta el permiso requerido: {code}")
        return user

    return _checker


async def user_has_permission(db: AsyncSession, *, user_id: int, code: str) -> bool:
    """Chequeo "suave" de permiso — a diferencia de `require_permission`,
    NO bloquea la request si falta; devuelve un bool para que el caller
    decida qué hacer (ej. enmascarar un campo sensible en vez de negar
    acceso al recurso completo — hr módulo 8, DED-21: `salary` visible
    solo con `hr:employee:read-sensitive`, sin bloquear el resto del
    legajo si falta ese permiso puntual)."""
    from app.core.models import RolePermission, UserRole  # import local: evita ciclo con models

    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id, Permission.code == code)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None
