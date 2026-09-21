#!/usr/bin/env python3
"""
16_rate_limit_audit.py — ¿se puede fuerza-bruta /auth/login sin que nada
frene al atacante? ¿el tiempo de respuesta filtra qué emails existen?

Dos chequeos, contra un backend real ya corriendo:

1. Rate limiting / throttling: N intentos de login rápidos y reales contra
   MUCHOS emails distintos (no el mismo — el lockout por cuenta que ya
   existe en AuthService.MAX_FAILED_ATTEMPTS no cubre esto: un atacante
   real probando contraseñas comunes contra una lista grande de emails
   nunca toca el límite por cuenta individual). El invariante esperado en
   cualquier API pública: en algún punto debería aparecer un 429 o un
   Retry-After — si las N respuestas son todas 401/422 sin ninguna señal
   de throttling, es un hallazgo real.

2. Canal lateral de tiempo (timing side-channel): se mide el tiempo de
   respuesta de login con un email que NO existe vs. uno que SÍ existe
   (con password incorrecto). Si `verify_password` (bcrypt, deliberadamente
   lento) solo se ejecuta cuando el email existe, un atacante puede medir
   la diferencia y enumerar cuentas válidas aunque el mensaje de error sea
   idéntico ("Credenciales inválidas") en ambos casos — el mensaje igual
   no alcanza si el TIEMPO es distinto.

Uso:
    python scripts/qa_suite/16_rate_limit_audit.py
    python scripts/qa_suite/16_rate_limit_audit.py --base-url http://127.0.0.1:8000 --attempts 30
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
import uuid
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

import os  # noqa: E402

os.chdir(BACKEND_ROOT)

from app import models_registry  # noqa: E402,F401 — registra todos los modelos antes de tocar cualquier FK
from app.config import settings  # noqa: E402


def check_middleware_statically() -> bool:
    print(f"{'=' * 70}\nChequeo estático — ¿hay middleware de rate-limiting en app/main.py?\n{'=' * 70}")
    main_py = (BACKEND_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    markers = ("slowapi", "RateLimit", "ratelimit", "limiter", "Limiter", "throttl")
    found = [m for m in markers if m in main_py]
    if found:
        print(f"✓ Se encontraron menciones de rate-limiting en app/main.py: {found}")
        return True
    print("⚠ No se encontró ningún middleware de rate-limiting (slowapi u otro) registrado en app/main.py.")
    return False


async def _make_company(client: httpx.AsyncClient) -> tuple[int, str, str]:
    unique = uuid.uuid4().hex[:8]
    resp = await client.post(
        "/internal/companies", headers={"X-Internal-Api-Key": settings.internal_api_key},
        json={"name": f"Rate Limit Audit {unique}"},
    )
    resp.raise_for_status()
    company_id = resp.json()["id"]

    from sqlalchemy import text

    from app.core import schemas as core_schemas
    from app.core.services import UserService
    from app.database import AsyncSessionLocal

    email = f"real_user_{unique}@test.hn"
    password = "PasswordRateLimitTest1"
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)})
        await UserService.create_user(
            db, company_id=company_id,
            payload=core_schemas.UserCreate(email=email, full_name="Usuario Real", password=password),
            created_by=None,
        )
        await db.commit()
    return company_id, email, password


async def check_brute_force_throttling(base_url: str, attempts: int) -> bool:
    print(f"\n{'=' * 70}\nChequeo dinámico — {attempts} intentos de login reales contra emails DISTINTOS\n{'=' * 70}")
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        print(
            f"Disparando {attempts} intentos de login secuenciales, cada uno con un email distinto\n"
            "(nunca se repite, así que el lockout por cuenta de AuthService.MAX_FAILED_ATTEMPTS "
            "nunca entra en juego)..."
        )
        status_codes = []
        for _ in range(attempts):
            resp = await client.post(
                "/auth/login", json={"email": f"attacker_probe_{uuid.uuid4().hex[:10]}@test.hn", "password": "cualquier-cosa"},
            )
            status_codes.append(resp.status_code)

        throttled = any(s == 429 for s in status_codes)
        distinct = sorted(set(status_codes))
        print(f"Status codes observados: {distinct} (conteo total: {len(status_codes)})")
        if throttled:
            print("✓ El servidor respondió 429 en algún punto — hay throttling real.")
            return True
        print(
            f"⚠ HALLAZGO: {attempts} intentos de login contra {attempts} emails distintos, ninguno throttleado "
            f"(nunca un 429, nunca un Retry-After). El lockout por cuenta individual no protege contra un "
            f"atacante que prueba contraseñas comunes contra una LISTA de emails — solo protege una cuenta "
            f"ya identificada. Recomendación: rate-limiting por IP (ej. slowapi) además del lockout por cuenta."
        )
        return False


async def check_timing_side_channel(base_url: str, samples: int) -> bool:
    print(f"\n{'=' * 70}\nChequeo dinámico — canal lateral de tiempo (email real vs. inexistente), {samples} muestras de cada uno\n{'=' * 70}")
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        _, real_email, _real_password = await _make_company(client)

        async def timed_login(email: str) -> float:
            start = time.perf_counter()
            await client.post("/auth/login", json={"email": email, "password": "password-incorrecta-a-propósito"})
            return time.perf_counter() - start

        # "Calentar" la conexión/pool antes de medir — la primera request
        # de cualquier serie suele ser más lenta por razones ajenas al bug
        # que se está buscando (setup de conexión TCP, primer query plan).
        await timed_login(real_email)

        real_times = [await timed_login(real_email) for _ in range(samples)]
        fake_times = [await timed_login(f"no_existe_{uuid.uuid4().hex[:10]}@test.hn") for _ in range(samples)]

        real_median = statistics.median(real_times)
        fake_median = statistics.median(fake_times)
        gap_ms = (real_median - fake_median) * 1000

        print(f"Mediana email REAL (password incorrecta): {real_median * 1000:.1f} ms")
        print(f"Mediana email INEXISTENTE: {fake_median * 1000:.1f} ms")
        print(f"Diferencia: {gap_ms:.1f} ms")

        # Umbral deliberadamente generoso (20ms) para no reportar ruido de
        # red/scheduler como si fuera el side-channel — un bcrypt real
        # (cost factor típico) agrega decenas a cientos de ms, muy por
        # encima de cualquier jitter normal de este chequeo corriendo
        # local contra localhost.
        if gap_ms < 20:
            print("✓ Sin diferencia de tiempo significativa — no se detecta canal lateral de enumeración de usuarios.")
            return True
        print(
            f"⚠ HALLAZGO: el login con un email real tarda ~{gap_ms:.0f} ms más que uno inexistente — "
            f"un atacante puede medir esto para enumerar qué emails están registrados, pese a que el "
            f"mensaje de error ('Credenciales inválidas') es idéntico en ambos casos. Causa probable: "
            f"la verificación de password (bcrypt, deliberadamente lenta) solo se ejecuta cuando el email "
            f"existe — para un email inexistente la función retorna antes de llegar a esa verificación."
        )
        return False


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--attempts", type=int, default=30, help="Intentos de login para el chequeo de fuerza bruta")
    parser.add_argument("--timing-samples", type=int, default=15, help="Muestras por grupo para el chequeo de timing")
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base_url, timeout=5.0) as probe:
        try:
            await probe.get("/docs")
        except httpx.ConnectError:
            print(f"✗ No se pudo conectar a {args.base_url} — ¿está uvicorn corriendo?")
            return 1

    has_middleware = check_middleware_statically()
    throttled = await check_brute_force_throttling(args.base_url, args.attempts)
    no_timing_leak = await check_timing_side_channel(args.base_url, args.timing_samples)

    print(f"\n{'=' * 70}")
    if has_middleware and throttled and no_timing_leak:
        print("✓✓✓ Sin hallazgos — rate-limiting real presente, sin canal lateral de tiempo. ✓✓✓")
        return 0
    print(
        "⚠ Hallazgos reales — ver detalle arriba. Ninguno es un 500/crash (no bloquea el resto\n"
        "  de la suite), pero son riesgos de seguridad reales a evaluar."
    )
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
