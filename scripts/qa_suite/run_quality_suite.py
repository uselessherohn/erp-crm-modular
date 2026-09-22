#!/usr/bin/env python3
"""
run_quality_suite.py — Orquestador de la suite de calidad. Corre etapas en
orden; cada etapa completa (todos sus scripts en verde) es un punto natural
de commit/push — mismo ritmo que la regresión QA por módulo: avanzar,
confirmar en verde, commitear, seguir.

Etapas (ver QUALITY_SUITE.md para el detalle de qué cubre cada una y por
qué están agrupadas así):

  1  baseline          — cobertura, auditoría de permisos, downgrade de
                          alembic, lint + types. Todo local, sin red, minutos.
  2  sql-audit         — auditoría de SQL crudo / posible inyección.
  3  frontend          — build + vitest del frontend.
  4  http              — tests a nivel HTTP real (servidor real + httpx).
  5  property          — property-based testing (hypothesis) sobre
                          cálculos financieros y la máquina de estados de
                          SalesOrder.
  6  deps-audit        — pip-audit sobre requirements.txt (CVEs conocidos).
  7  security          — aislamiento multi-tenant (IDOR), HTTP real.
  8  concurrency       — concurrencia real contra un backend ya levantado
                          (oversell de stock, idempotencia bajo carrera real).
  9  secrets-audit     — secretos en el working tree y el historial completo
                          de git.
  10 rate-limit-audit  — fuerza bruta / timing side-channel en /auth/login,
                          contra un backend ya levantado.
  11 backup-restore    — simulacro real de pg_dump + restore + verificación.

  (opcional, no corre en el orden por defecto — ver --stage mutation)
  12 mutation          — mutation testing (mutmut) sobre app/core/security.py.

Uso:
    python scripts/qa_suite/run_quality_suite.py --stage baseline
    python scripts/qa_suite/run_quality_suite.py --stage security
    python scripts/qa_suite/run_quality_suite.py --stage mutation
    python scripts/qa_suite/run_quality_suite.py --list

Por defecto corre TODAS las etapas en orden y se detiene en la primera que
falle — así el punto de corte para "hasta acá se puede pushear" es
inequívoco: la última etapa impresa como ✓ es hasta donde se llegó limpio.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

QA_SUITE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = QA_SUITE_ROOT.parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
FRONTEND_ROOT = REPO_ROOT / "frontend"


class Stage:
    def __init__(self, key: str, label: str, run):
        self.key = key
        self.label = label
        self.run = run


def _py(script: str, *args: str) -> int:
    return subprocess.run([sys.executable, str(QA_SUITE_ROOT / script), *args]).returncode


def _pytest(*args: str) -> int:
    return subprocess.run([sys.executable, "-m", "pytest", *args], cwd=BACKEND_ROOT).returncode


def stage_baseline() -> int:
    steps = [
        ("Cobertura de código", lambda: _py("01_coverage.py")),
        ("Auditoría de permisos", lambda: _py("02_permission_audit.py")),
        ("alembic downgrade", lambda: _py("03_alembic_downgrade.py")),
        ("Lint + types", lambda: _py("04_lint_and_types.py")),
    ]
    return _run_steps(steps)


def stage_sql_audit() -> int:
    return _py("05_sql_injection_audit.py")


def stage_frontend() -> int:
    if not (FRONTEND_ROOT / "package.json").exists():
        print("! No hay frontend/package.json — etapa omitida (nada que correr).")
        return 0
    steps = [
        ("npm run build", lambda: subprocess.run(["npm", "run", "build"], cwd=FRONTEND_ROOT).returncode),
        ("npx vitest run", lambda: subprocess.run(["npx", "vitest", "run"], cwd=FRONTEND_ROOT).returncode),
    ]
    return _run_steps(steps)


def stage_http() -> int:
    return _pytest("tests/http/", "-v")


def stage_property() -> int:
    return _pytest("tests/property/", "-v")


def stage_deps_audit() -> int:
    return _py("09_dependency_audit.py")


def stage_security() -> int:
    return _pytest("tests/security/", "-v")


def stage_concurrency() -> int:
    print("! Requiere un backend real ya corriendo en http://127.0.0.1:8000 (uvicorn app.main:app) — no lo levanta esta etapa.")
    return _py("11_concurrency_load.py")


def stage_secrets_audit() -> int:
    return _py("15_secrets_audit.py")


def stage_rate_limit_audit() -> int:
    print("! Requiere un backend real ya corriendo en http://127.0.0.1:8000 (uvicorn app.main:app) — no lo levanta esta etapa.")
    return _py("16_rate_limit_audit.py")


def stage_backup_restore() -> int:
    return _py("17_backup_restore_drill.py")


def stage_mutation() -> int:
    print("! Exploratoria, no bloqueante — tarda varios minutos incluso acotada. Ver scripts/qa_suite/12_mutation_testing.py.")
    return _py("12_mutation_testing.py")


def _run_steps(steps: list[tuple[str, Callable[[], int]]]) -> int:
    for label, fn in steps:
        print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
        code = fn()
        if code != 0:
            print(f"\n✗ Falló: {label}")
            return code
    return 0


STAGES = [
    Stage("baseline", "1. Baseline (cobertura, permisos, downgrade, lint/types)", stage_baseline),
    Stage("sql-audit", "2. Auditoría de SQL crudo", stage_sql_audit),
    Stage("frontend", "3. Frontend (build + vitest)", stage_frontend),
    Stage("http", "4. Tests a nivel HTTP real", stage_http),
    Stage("property", "5. Property-based testing (hypothesis) — incluye la máquina de estados de SalesOrder", stage_property),
    Stage("deps-audit", "6. Auditoría de dependencias (CVEs)", stage_deps_audit),
    Stage("security", "7. Aislamiento multi-tenant (IDOR)", stage_security),
    Stage("concurrency", "8. Concurrencia real (requiere backend levantado)", stage_concurrency),
    Stage("secrets-audit", "9. Auditoría de secretos (working tree + historial de git)", stage_secrets_audit),
    Stage("rate-limit-audit", "10. Rate-limiting / timing side-channel en login (requiere backend levantado)", stage_rate_limit_audit),
    Stage("backup-restore", "11. Simulacro de backup/restore", stage_backup_restore),
]

# Excluida del "correr todas las etapas" por defecto — exploratoria, no un
# gate binario pasa/no-pasa (ver 12_mutation_testing.py), y tarda minutos
# incluso acotada. Se corre a propósito con --stage mutation.
OPTIONAL_STAGES = [
    Stage("mutation", "12. Mutation testing (mutmut, exploratoria — no bloqueante)", stage_mutation),
]

ALL_STAGE_KEYS = [s.key for s in STAGES] + [s.key for s in OPTIONAL_STAGES]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", choices=ALL_STAGE_KEYS, help="Correr solo esta etapa (incluye las opcionales, ej. mutation)")
    parser.add_argument("--list", action="store_true", help="Listar etapas y salir")
    args = parser.parse_args()

    if args.list:
        for s in STAGES + OPTIONAL_STAGES:
            suffix = "  (opcional, no corre por defecto)" if s in OPTIONAL_STAGES else ""
            print(f"{s.key:18} {s.label}{suffix}")
        return 0

    all_defined = STAGES + OPTIONAL_STAGES
    stages_to_run = [s for s in all_defined if s.key == args.stage] if args.stage else STAGES

    for stage in stages_to_run:
        print(f"\n{'#' * 70}\n# {stage.label}\n{'#' * 70}")
        code = stage.run()
        if code != 0:
            print(f"\n{'!' * 70}\n! Etapa '{stage.key}' terminó con errores — corregir antes de pushear más allá de acá.\n{'!' * 70}")
            return code
        print(f"\n✓✓✓ Etapa '{stage.key}' completa en verde — punto seguro para commit/push. ✓✓✓")

    if args.stage:
        print(f"\n🎉 Etapa '{args.stage}' terminó en verde.")
    else:
        print(f"\n🎉 Las {len(STAGES)} etapas de la suite de calidad terminaron en verde.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
