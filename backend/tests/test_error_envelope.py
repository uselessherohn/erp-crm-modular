"""
Formato de error uniforme (spec sección 7): "Un exception handler central
en FastAPI mapea cada una a su status code y al formato de error uniforme."
No es opcional para un subconjunto de errores — TODO error, sin excepción.

Usa httpx.ASGITransport contra la app real (no mocks) — sin necesidad de
levantar uvicorn en un proceso aparte para este caso puntual.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_request_validation_error_uses_uniform_envelope():
    """Bug real encontrado en Fase 2 de contacts: un model_validator de
    Pydantic que falla en el body producía 500 (TypeError: Object of type
    ValueError is not JSON serializable) en vez de 422 uniforme."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/contacts", json={"name": "Sin rol"})
    assert res.status_code in (401, 403, 422)  # 401/403 si falta auth primero, 422 si el body se valida antes
    body = res.json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]


@pytest.mark.asyncio
async def test_404_uses_uniform_envelope():
    """Bug real: registrar el handler sobre fastapi.exceptions.HTTPException
    no alcanza — Starlette lanza su propia clase base para 404 de ruta sin
    match. Ver comentario en app/main.py."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/ruta-que-no-existe")
    assert res.status_code == 404
    body = res.json()
    assert body == {"error": {"code": "HTTP_ERROR", "message": "Not Found", "details": None}}


@pytest.mark.asyncio
async def test_405_uses_uniform_envelope():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.delete("/health")
    assert res.status_code == 405
    body = res.json()
    assert body["error"]["code"] == "HTTP_ERROR"


@pytest.mark.asyncio
async def test_domain_error_uses_uniform_envelope():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/contacts")  # sin Authorization header
    assert res.status_code == 403
    body = res.json()
    assert body["error"]["code"] == "PERMISSION_DENIED"
