"""
tests/security/test_route_crawler_no_crashes.py — cobertura amplia pero
superficial, complementaria a test_tenant_isolation.py.

test_tenant_isolation.py cura 6 recursos a mano y prueba el caso fuerte: un
id que SÍ existe (de otro tenant). Este archivo hace lo opuesto — recorre
TODAS las rutas parametrizadas de la app (vía app.openapi(), sin curar nada
a mano) y prueba con un id que NO existe para nadie. Es un check más débil
(no puede distinguir "no lo veo porque es de otro tenant" de "no lo veo
porque no existe"), pero cubre automáticamente los ~40+ endpoints que
test_tenant_isolation.py no tiene tiempo de curar a mano uno por uno —
sirve sobre todo para atrapar dos cosas baratas de romper accidentalmente:

1. Un endpoint que devuelve 500 en vez de 404/403 ante un id inexistente
   (normalmente un NotFoundError que se escapa sin capturar, o un intento de
   acceder a un atributo de `None`).
2. Un endpoint que devuelve 200 CON DATOS REALES para un id que no existe
   para nadie — una fuga real. (Una lista vacía o `null` en 200 para un
   "listar por padre inexistente" es una convención REST válida, no se
   cuenta como fuga.)

Para extender la cobertura FUERTE (con datos reales de otro tenant) a un
módulo que este archivo no cura, agregar una entrada al registro en
resource_factories.py en vez de tocar este archivo.
"""
from __future__ import annotations

import re

import pytest

from app.main import app

# Id que no existe para NADIE — asumiendo que ningún test corrido antes
# llegó a crear 2 mil millones de filas en una sola tabla (asunción segura:
# ningún módulo tiene autoincrement compartido entre corridas, cada test usa
# una base fresca o un rango bajo de ids).
NONEXISTENT_ID = 2_000_000_000

# Rutas a excluir del crawler — casos con semántica propia donde 200/404 no
# aplican tal cual:
_EXCLUDE_PATH_SUBSTRINGS = (
    "/internal/",  # requiere X-Internal-Api-Key, no un Bearer token — fuera de alcance de este crawler
)


def _discover_parameterized_routes() -> list[tuple[str, str]]:
    """(método, path_template) para cada ruta GET/PATCH/PUT/DELETE con al
    menos un parámetro de path, vía el schema OpenAPI real de la app — la
    misma fuente de verdad que /docs."""
    schema = app.openapi()
    routes: list[tuple[str, str]] = []
    for path, methods in schema["paths"].items():
        if "{" not in path or any(s in path for s in _EXCLUDE_PATH_SUBSTRINGS):
            continue
        for method, _spec in methods.items():
            if method.upper() not in ("GET", "PATCH", "PUT", "DELETE"):
                continue
            # Ruta con más de un {param} (ej. /medical/patients/{id}/records) —
            # solo el ÚLTIMO se reemplaza por el id inexistente; los
            # anteriores se rellenan con NONEXISTENT_ID también, ya que un
            # id de path inexistente en CUALQUIER posición debería resultar
            # en 404, nunca en 500.
            routes.append((method.upper(), path))
    return routes


def _fill_path(template: str) -> str:
    return re.sub(r"\{[^}]+\}", str(NONEXISTENT_ID), template)


PARAMETERIZED_ROUTES = _discover_parameterized_routes()


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path_template", PARAMETERIZED_ROUTES, ids=[f"{m}:{p}" for m, p in PARAMETERIZED_ROUTES])
async def test_nonexistent_id_never_crashes_or_leaks(client, tenant_a: dict, method: str, path_template: str):
    path = _fill_path(path_template)
    if method == "GET":
        response = await client.get(path, headers=tenant_a["headers"])
    elif method == "PATCH":
        response = await client.patch(path, headers=tenant_a["headers"], json={})
    elif method == "PUT":
        response = await client.put(path, headers=tenant_a["headers"], json={})
    elif method == "DELETE":
        response = await client.delete(path, headers=tenant_a["headers"])
    else:  # pragma: no cover — no debería llegar acá dado el filtro de arriba
        pytest.skip(f"método {method} no cubierto por el crawler")

    assert response.status_code < 500, (
        f"{method} {path} (id inexistente) devolvió {response.status_code} — un id "
        f"inexistente NUNCA debería producir un error 5xx (normalmente una excepción "
        f"NotFoundError/ValidationError sin capturar). Body: {response.text[:500]}"
    )
    if response.status_code == 200:
        # Algunas rutas "listar por padre" (ej. /medical/patients/{id}/records)
        # devuelven 200 con una lista/valor vacío a propósito cuando el padre
        # no existe, en vez de 404 — es una convención REST válida, no una
        # fuga. Lo que NO es válido bajo ningún diseño es un 200 con datos
        # reales para un id que no existe para nadie.
        body = response.json()
        is_empty = body in (None, [], {}) or (isinstance(body, dict) and not any(body.values()))
        assert is_empty, (
            f"{method} {path} devolvió 200 CON DATOS ({str(body)[:300]}) para un id que "
            f"no existe para nadie ({NONEXISTENT_ID}) — posible fuga real."
        )
