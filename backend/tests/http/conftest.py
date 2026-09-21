"""
Fixtures compartidos para tests/http/ — a diferencia del resto de la suite
(que llama servicios directo), estos tests pegan contra la app real, capa
HTTP incluida: middleware, exception handlers, serialización de
FastAPI/Pydantic. `httpx.ASGITransport` corre la app en el mismo proceso
sin abrir un socket real — más rápido y determinístico que levantar
uvicorn, pero ejercitando exactamente el mismo código que un request real
por la red (routing, middleware, exception handlers; lo único que no pasa
es la capa TCP/HTTP en sí, que no es responsabilidad de esta app).
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def company_and_admin(client: AsyncClient):
    """Crea una compañía real vía el endpoint interno + un admin real vía
    scripts.bootstrap_admin (mismo camino que usa el operador real), y
    devuelve (company_id, email, password) para loguear en el test."""
    from app import models_registry  # noqa: F401 — mismo motivo que el resto de la suite: registra todos los modelos antes de tocar User
    from app.core import schemas as core_schemas
    from app.core.services import RoleService, UserService
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    unique = uuid.uuid4().hex[:8]
    company_name = f"HTTP Test {unique}"

    response = await client.post(
        "/internal/companies",
        headers={"X-Internal-Api-Key": settings.internal_api_key},
        json={"name": company_name},
    )
    assert response.status_code == 201, response.text
    company_id = response.json()["id"]

    email = f"admin_http_{unique}@test.hn"
    password = "PasswordHttpTest1"

    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)})
        role = await RoleService.create_role(
            db, company_id=company_id,
            payload=core_schemas.RoleCreate(name="Admin HTTP", permission_ids=await _all_permission_ids(db)),
        )
        from app.core import models as core_models

        user = await UserService.create_user(
            db, company_id=company_id,
            payload=core_schemas.UserCreate(email=email, full_name="Admin HTTP", password=password),
            created_by=None,
        )
        db.add(core_models.UserRole(user_id=user.id, role_id=role.id))
        await db.commit()

    return company_id, email, password


async def _all_permission_ids(db) -> list[int]:
    """Sembrado idempotente de TODOS los códigos de permiso reales del
    repo (mismo criterio de escaneo que scripts/qa_suite/
    02_permission_audit.py) — los tests HTTP no pueden asumir que
    scripts/bootstrap_admin.py ya corrió contra esta base (son
    autocontenidos, cada uno arranca de una base limpia). Sin esto, una
    compañía nueva no tiene NINGÚN Permission sembrado (es una tabla
    global, no se crea con la compañía) y el admin de test no podría
    tener ningún permiso real para pasar los `require_permission(...)`
    de las rutas que se van a probar."""
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


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, company_and_admin):
    _, email, password = company_and_admin
    response = await client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
