"""
Fixtures compartidos para tests/security/ — aislamiento multi-tenant.

A diferencia de tests/test_medical_module.py::test_rls_blocks_cross_tenant_*
(que llama a la capa de servicio directo con el `company_id` "correcto" pasado
a mano, probando que RLS bloquea la fila una vez que ese `company_id` es
confiable), esta suite ataca la capa HTTP real: un usuario autenticado de la
compañía A, con un token real, intentando llegar a un recurso de la compañía
B por su id. Esto prueba algo distinto y complementario: que cada router
efectivamente deriva `company_id` del token (vía `get_current_company_id`) y
nunca de un parámetro que el cliente controle — RLS es la última línea de
defensa, no la única, y un bug real sería un endpoint que confíe en un
`company_id` que no venga del token.

Reutiliza el mismo patrón que tests/http/conftest.py (compañía real vía
`/internal/companies`, admin real con TODOS los permisos vía
`RoleService`/`UserService`), pero por duplicado — una compañía "A" (el
atacante, cuyo token se usa en cada intento) y una "B" (la víctima, dueña de
los recursos que A no debería poder tocar).
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.config import settings
from app.core import schemas as core_schemas
from app.core.services import RoleService, UserService
from app.database import AsyncSessionLocal
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _all_permission_ids(db) -> list[int]:
    """Idéntico a tests/http/conftest.py::_all_permission_ids — duplicado a
    propósito en vez de importado, para que tests/security/ sea un paquete
    autocontenido que un agente pueda copiar/correr aislado sin arrastrar el
    resto de tests/http/."""
    import re
    from pathlib import Path

    from sqlalchemy import select

    from app.core import models as core_models

    backend_root = Path(__file__).resolve().parents[2]
    pattern = re.compile(r'"([a-z_]+:[a-z_]+:[a-z_-]+)"')
    codes: set[str] = set()
    for f in (backend_root / "app").rglob("*.py"):
        if "__pycache__" in str(f):
            continue
        codes |= set(pattern.findall(f.read_text(encoding="utf-8", errors="ignore")))

    ids: list[int] = []
    for code in sorted(codes):
        existing = (await db.execute(select(core_models.Permission).where(core_models.Permission.code == code))).scalar_one_or_none()
        if existing is None:
            existing = core_models.Permission(code=code, description=code)
            db.add(existing)
            await db.flush()
        ids.append(existing.id)
    return ids


async def _make_tenant(client: AsyncClient, *, label: str) -> dict:
    """Crea una compañía real + un admin real con TODOS los permisos, loguea
    por HTTP, y devuelve todo lo que un test necesita: company_id, headers
    de auth, y el email/password por si hace falta volver a loguear."""
    unique = uuid.uuid4().hex[:8]
    company_name = f"Tenant {label} {unique}"

    response = await client.post(
        "/internal/companies",
        headers={"X-Internal-Api-Key": settings.internal_api_key},
        json={"name": company_name},
    )
    assert response.status_code == 201, response.text
    company_id = response.json()["id"]

    email = f"admin_{label.lower()}_{unique}@test.hn"
    password = "PasswordTenantTest1"

    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)})
        role = await RoleService.create_role(
            db, company_id=company_id,
            payload=core_schemas.RoleCreate(name=f"Admin {label}", permission_ids=await _all_permission_ids(db)),
        )
        from app.core import models as core_models

        user = await UserService.create_user(
            db, company_id=company_id,
            payload=core_schemas.UserCreate(email=email, full_name=f"Admin {label}", password=password),
            created_by=None,
        )
        db.add(core_models.UserRole(user_id=user.id, role_id=role.id))
        # Licencia TODOS los paquetes (mismo criterio que scripts/bootstrap_admin.py)
        # — sin esto, rutas gateadas por `require_package` (pipeline, medical,
        # pharmacy, website) devuelven 403 PACKAGE_NOT_LICENSED para CUALQUIER
        # tenant, propio o ajeno, lo que haría que un intento de acceso cruzado
        # "pase" el test por la razón equivocada (licenciamiento, no
        # aislamiento real). Ambos tenants necesitan todo licenciado para que
        # el 403/404 que se observe se deba de verdad al filtro de company_id.
        for package in ("administrative", "medical", "pharmacy", "web"):
            db.add(core_models.CompanyPackage(company_id=company_id, package=package, status="active"))
        await db.commit()
        user_id = user.id

    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    return {
        "company_id": company_id,
        "user_id": user_id,
        "email": email,
        "password": password,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest_asyncio.fixture
async def tenant_a(client: AsyncClient) -> dict:
    """El "atacante" — el token que se usa en cada intento de la suite."""
    return await _make_tenant(client, label="A")


@pytest_asyncio.fixture
async def tenant_b(client: AsyncClient) -> dict:
    """La "víctima" — dueña de los recursos que tenant_a no debería poder tocar."""
    return await _make_tenant(client, label="B")
