#!/usr/bin/env python3
"""
04_lint_and_types.py — ruff (lint + estilo) y mypy (chequeo de tipos)
sobre app/ y scripts/. No incluye tests/ a propósito: los tests de este
proyecto usan patrones (fixtures, imports condicionales dentro de
funciones) que generan ruido de tipos sin valor real — el código que
importa que esté bien tipado es el de la aplicación.

Ninguna corrida previa de este proyecto pasó por lint/types — primera vez
que se ejecutan. Es normal (y esperable) que la primera corrida encuentre
una cantidad no trivial de avisos; el objetivo de esta primera pasada es
tener el baseline real, no llegar a cero en un solo commit.

Uso:
    python scripts/qa_suite/04_lint_and_types.py [--fix]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="Deja que ruff aplique los fixes automáticos seguros")
    args = parser.parse_args()

    print("=== ruff (lint) ===\n")
    ruff_cmd = [sys.executable, "-m", "ruff", "check", "app", "scripts"]
    if args.fix:
        ruff_cmd.append("--fix")
    ruff_result = subprocess.run(ruff_cmd, cwd=BACKEND_ROOT)

    print("\n=== mypy (chequeo de tipos) ===\n")
    mypy_result = subprocess.run(
        [sys.executable, "-m", "mypy", "app", "../scripts/qa_suite"],
        cwd=BACKEND_ROOT,
    )
    # Sin --ignore-missing-imports ni --no-error-summary por CLI: ya están
    # en backend/pyproject.toml ([tool.mypy]) — un solo lugar de verdad
    # para la config, no duplicada entre el script y el archivo.

    print()
    if ruff_result.returncode == 0:
        print("✓ ruff sin hallazgos.")
    else:
        print("✗ ruff encontró hallazgos — ver arriba (--fix aplica los seguros automáticamente).")

    if mypy_result.returncode == 0:
        print("✓ mypy sin errores de tipos.")
    else:
        print("✗ mypy encontró errores de tipos — ver arriba.")

    return 0 if (ruff_result.returncode == 0 and mypy_result.returncode == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
