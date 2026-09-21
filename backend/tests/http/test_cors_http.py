"""
Tests HTTP reales del middleware CORS — nunca se había probado que los
headers configurados en app.config.settings.cors_allowed_origins realmente
se apliquen en la práctica (la config podría estar bien escrita y el
middleware mal registrado, o al revés, y ningún test lo notaría sin pegarle
a la capa HTTP real).
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.config import settings


@pytest.mark.asyncio
async def test_cors_headers_present_for_allowed_origin(client: AsyncClient):
    allowed_origin = settings.cors_allowed_origins[0]
    response = await client.get("/health", headers={"Origin": allowed_origin})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == allowed_origin


@pytest.mark.asyncio
async def test_cors_preflight_allows_credentials_for_allowed_origin(client: AsyncClient):
    allowed_origin = settings.cors_allowed_origins[0]
    response = await client.options(
        "/contacts",
        headers={
            "Origin": allowed_origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == allowed_origin
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_headers_absent_for_disallowed_origin(client: AsyncClient):
    """Config real (app/config.py, DED explícito): nunca '*' porque las
    rutas autenticadas usan Authorization con credenciales reales — un
    origen no configurado no debería recibir el header de vuelta."""
    response = await client.get("/health", headers={"Origin": "https://sitio-no-autorizado.evil"})
    assert response.status_code == 200  # el request en sí no se bloquea del lado del server
    assert response.headers.get("access-control-allow-origin") != "https://sitio-no-autorizado.evil"
