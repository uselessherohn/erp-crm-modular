#!/usr/bin/env python3
"""
03_alembic_downgrade.py — Confirma que TODAS las migraciones bajan limpio,
una por una, desde head hasta la base.

Nunca se había probado en esta regresión: `alembic upgrade head` se corrió
decenas de veces contra bases limpias, pero downgrade() de cada archivo es
código que nunca se ejercita en el flujo normal de desarrollo — es común
que quede roto o incompleto sin que nadie lo note hasta el día que hace
falta un rollback real en producción.

Corre downgrade uno por uno (no downgrade directo a base) porque un solo
downgrade masivo puede ocultar en qué migración específica falló.

REQUIERE una base ya limpia y migrada a head antes de correr esto (mismo
criterio que el resto de la suite de regresión — el orquestador
`run_quality_suite.py` se encarga de dejarla así antes de invocar este
script). No gestiona su propia base a propósito: mezclar "quién prepara la
base" con "qué migra/baja" complica el script sin necesidad.

Uso:
    python scripts/qa_suite/03_alembic_downgrade.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=BACKEND_ROOT, capture_output=True, text=True, **kwargs)


def alembic_history_revisions() -> list[str]:
    result = run([sys.executable, "-m", "alembic", "history"])
    if result.returncode != 0:
        print(result.stdout, result.stderr, file=sys.stderr)
        raise SystemExit("No se pudo leer el historial de alembic")
    revisions = []
    for line in result.stdout.splitlines():
        # formato: "<down> -> <rev>[ (head)], mensaje" o "<base> -> <rev>..."
        parts = line.split("->")
        if len(parts) < 2:
            continue
        rev = parts[1].strip().split(",")[0].split(" ")[0].strip()
        if rev:
            revisions.append(rev)
    return revisions


def main() -> int:
    print("=== alembic downgrade, migración por migración ===\n")

    revisions = alembic_history_revisions()
    print(f"{len(revisions)} migraciones en la cadena. Corriendo upgrade head -> downgrade uno por uno -> upgrade head.\n")

    # upgrade a head primero, para partir de un estado conocido.
    result = run([sys.executable, "-m", "alembic", "upgrade", "head"])
    if result.returncode != 0:
        print(result.stdout, result.stderr, file=sys.stderr)
        print("✗ alembic upgrade head falló antes de empezar — no se puede continuar.")
        return 1

    failures: list[tuple[str, str]] = []
    # Downgrade a un TARGET EXPLÍCITO por cada paso (no `-1` relativo).
    # Hallazgo real al escribir este script: `-1` es ambiguo en un punto
    # de merge del historial (este repo tiene uno real, `d016d0daa072` —
    # ramas paralelas de `pharmacy` y `website/ecommerce/reports`,
    # documentado en LOG_EJECUCION.md, sesión de `website`). Con un
    # target explícito por revisión (la que `alembic history` ya
    # resuelve a un orden lineal) no hay ambigüedad posible — cada
    # `downgrade <rev>` sabe exactamente a dónde ir, sea o no un punto de
    # merge.
    # revisions[0] es el head actual, revisions[-1] la más vieja.
    # targets[i] es a dónde bajar parados en revisions[i]:
    # revisions[i] -> revisions[i+1], y el último paso baja a "base".
    targets = [*revisions[1:], "base"]
    for from_rev, to_target in zip(revisions, targets, strict=True):
        result = run([sys.executable, "-m", "alembic", "downgrade", to_target])
        if result.returncode != 0:
            failures.append((from_rev, result.stdout + result.stderr))
            print(f"✗ downgrade a '{to_target}' falló (bajando desde {from_rev})")
            break
        else:
            print(f"✓ downgrade a '{to_target}' ok")

    # Siempre volver a head al final, haya fallado o no, para no dejar el
    # entorno a medias si esto corre como parte de una suite más larga.
    restore = run([sys.executable, "-m", "alembic", "upgrade", "head"])
    if restore.returncode != 0:
        print("\n✗ CRÍTICO: no se pudo volver a 'upgrade head' después del downgrade — la base quedó en un estado intermedio.")
        print(restore.stdout, restore.stderr, file=sys.stderr)
        return 2

    if failures:
        rev, output = failures[0]
        print(f"\n✗ {len(failures)} fallo(s). Primera migración con downgrade roto: {rev}")
        print("--- salida de alembic ---")
        print(output)
        return 1

    print(f"\n✓ Las {len(revisions)} migraciones bajan limpio, una por una, hasta la base.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
