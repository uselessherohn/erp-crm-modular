"""
Tests HTTP reales (item 7 de la suite de calidad) — el sobre de error
uniforme (spec sección 7) ya tiene 3 bugs reales documentados y corregidos
en app/main.py (ver los comentarios de cada exception_handler ahí). Estos
tests los fijan como regresión permanente, ejercitando la capa HTTP real
(no llamando al service ni al handler directo) — es la única forma de
confirmar que el middleware/routing de FastAPI realmente entrega el sobre
correcto en la práctica, no solo que el handler en sí está bien escrito.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_undefined_route_returns_uniform_envelope_404(client: AsyncClient):
    """Bug real documentado en app/main.py: registrar el handler sobre
    fastapi.exceptions.HTTPException no alcanza para una ruta que no
    matchea ningún router — Starlette lanza su propia clase base
    directamente. El handler está registrado sobre
    starlette.exceptions.HTTPException a propósito."""
    response = await client.get("/esta-ruta-no-existe-en-ningun-lado")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "HTTP_ERROR"
    assert "message" in body["error"]
    assert "details" in body["error"]


@pytest.mark.asyncio
async def test_wrong_method_on_existing_route_returns_uniform_envelope_405(client: AsyncClient):
    """/auth/login existe, pero solo acepta POST — GET debe dar 405 con
    el mismo sobre uniforme, no el error nativo de Starlette."""
    response = await client.get("/auth/login")
    assert response.status_code == 405
    body = response.json()
    assert body["error"]["code"] == "HTTP_ERROR"


@pytest.mark.asyncio
async def test_malformed_body_returns_uniform_envelope_422(client: AsyncClient):
    """Bug real documentado: un 422 de Pydantic (falta el campo `password`
    en el login) usaba el formato nativo de FastAPI (`{"detail": [...]}`),
    no el sobre uniforme."""
    response = await client.post("/auth/login", json={"email": "sin-password@test.hn"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "errors" in body["error"]["details"]


@pytest.mark.asyncio
async def test_model_validator_failure_returns_uniform_envelope_422_not_500(client: AsyncClient, auth_headers: dict):
    """Bug real documentado (encontrado probando contacts end-to-end): un
    model_validator que falla (ContactCreate exige al menos un rol activo)
    trae un objeto Exception de Python dentro de `ctx.error`, no
    serializable por json.dumps — daba un 500 crudo en vez de un 422
    limpio. custom_encoder fuerza ese caso a texto."""
    response = await client.post(
        "/contacts",
        headers=auth_headers,
        json={"name": "Sin ningún rol activo"},  # is_customer/is_vendor/is_patient/is_lead todos False (default)
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    # Confirma que el body es JSON válido de punta a punta — si el
    # custom_encoder no capturara el objeto Exception interno, este
    # `.json()` de httpx ya habría fallado antes de llegar acá, o el
    # server habría respondido 500.


@pytest.mark.asyncio
async def test_domain_not_found_error_returns_uniform_envelope_404(client: AsyncClient, auth_headers: dict):
    """Un NotFoundError real de un service (no un 404 de ruta inexistente)
    — mismo sobre, código de dominio específico (NOT_FOUND, no el
    HTTP_ERROR genérico de arriba)."""
    response = await client.get("/contacts/999999999", headers=auth_headers)
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_missing_auth_header_returns_uniform_envelope_401_or_403(client: AsyncClient):
    """Ruta protegida sin ningún header de autorización — confirma el
    sobre uniforme también en el camino de auth, no solo en errores de
    validación/dominio."""
    response = await client.get("/contacts")
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "PERMISSION_DENIED"
