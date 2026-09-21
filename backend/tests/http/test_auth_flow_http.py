"""
Tests HTTP reales del flujo de autenticación de punta a punta — a
diferencia de test_core_module.py (que llama AuthService.login directo),
esto ejercita también el router (parseo del header Authorization,
inyección de company_id vía get_current_company_id, RLS vía
get_db_with_tenant_context) para un caso real y completo: crear compañía →
crear usuario → login → usar el token en una ruta protegida → refresh →
usar el token nuevo.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_http_flow_create_company_user_login_use_token_refresh(client: AsyncClient, company_and_admin):
    company_id, email, password = company_and_admin

    login = await client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert tokens["token_type"] == "bearer"
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Ruta protegida real, con el JWT real — no solo que login() devuelva
    # un token, sino que ESE token efectivamente autentica en otra ruta.
    me = await client.get("/users/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200, me.text
    assert me.json()["email"] == email
    assert me.json()["company_id"] == company_id

    # Token inválido/mal armado — rechazado limpio, no un 500.
    bad = await client.get("/users/me", headers={"Authorization": "Bearer esto-no-es-un-jwt-real"})
    assert bad.status_code in (401, 403, 422)

    # Refresh real: el nuevo access_token también funciona.
    refreshed = await client.post("/auth/refresh", params={"raw_refresh_token": refresh_token})
    assert refreshed.status_code == 200, refreshed.text
    new_access_token = refreshed.json()["access_token"]
    assert new_access_token != access_token

    me_again = await client.get("/users/me", headers={"Authorization": f"Bearer {new_access_token}"})
    assert me_again.status_code == 200


@pytest.mark.asyncio
async def test_wrong_password_returns_generic_message_via_http(client: AsyncClient, company_and_admin):
    """DED de core (spec 8.0): el mensaje de login fallido nunca debe
    distinguir 'email no existe' de 'password incorrecta' — confirmado acá
    a nivel HTTP, no solo a nivel de servicio."""
    _, email, _ = company_and_admin

    wrong_password = await client.post("/auth/login", json={"email": email, "password": "esto-esta-mal"})
    nonexistent_email = await client.post("/auth/login", json={"email": "no-existe-para-nada@test.hn", "password": "cualquiera"})

    assert wrong_password.status_code == nonexistent_email.status_code == 422
    assert wrong_password.json()["error"]["message"] == nonexistent_email.json()["error"]["message"]
