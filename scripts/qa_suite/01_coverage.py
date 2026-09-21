#!/usr/bin/env python3
"""
01_coverage.py — Cobertura de código real de la suite de tests.

No es un gate de "todo o nada": el umbral (--min-percent) es deliberadamente
bajo al principio — lo que importa es tener el número real y el reporte de
líneas/ramas nunca ejercitadas, no perseguir un 100% artificial forzando
tests sin valor. Sube el umbral con el tiempo, a medida que se cierran los
huecos reales que este reporte encuentra.

Requiere una base Postgres limpia y migrada (mismo setup que el resto de la
suite de regresión) — ver README de qa_suite para el procedimiento.

Uso:
    python scripts/qa_suite/01_coverage.py [--min-percent 60] [--html]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-percent", type=int, default=85, help="Umbral mínimo de cobertura de líneas (--cov-fail-under)")
    parser.add_argument("--html", action="store_true", help="También genera reporte HTML en htmlcov/")
    args = parser.parse_args()

    cmd = [
        sys.executable, "-m", "pytest", "tests/",
        "--cov=app",
        "--cov-report=term-missing",
        f"--cov-fail-under={args.min_percent}",
        "-q",
    ]
    if args.html:
        cmd.append("--cov-report=html")

    print(f"=== Cobertura de código (umbral: {args.min_percent}%) ===\n")
    result = subprocess.run(cmd, cwd=BACKEND_ROOT)

    if result.returncode == 0:
        print(f"\n✓ Cobertura por encima del {args.min_percent}%.")
    else:
        print(f"\n✗ Cobertura por debajo del {args.min_percent}%, o algún test falló — ver 'Missing' arriba para las líneas sin ejercitar.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
