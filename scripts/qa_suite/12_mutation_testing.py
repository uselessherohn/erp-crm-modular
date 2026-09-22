#!/usr/bin/env python3
"""
12_mutation_testing.py — ¿la suite de tests realmente detecta bugs, o solo
da cobertura de vanidad?

Cobertura de línea (01_coverage.py) mide qué código SE EJECUTA durante los
tests — no si algún test fallaría si ese código estuviera mal. Mutation
testing cambia el código a propósito (invierte un `if`, cambia `>` por
`>=`, etc.) y corre la suite contra cada mutante: si NINGÚN test falla, el
"mutante sobrevive" — señal de que esa línea, pese a tener cobertura, no
está realmente puesta a prueba.

Configurado en pyproject.toml, [tool.mutmut] — deliberadamente acotado a
`app/core/security.py` (hashing de passwords + JWT) contra un subconjunto
RÁPIDO y ya identificado de tests (`tests/property/test_security_properties.py`
+ los tests de token/login/refresh de tests/test_core_module.py, ~5
segundos en total) — NO la suite completa. Mutar los 92 archivos de app/
y correr los 350s de la suite completa por cada mutante es, literalmente,
cómputo de días; esto es deliberado y necesario para que un agente pueda
correrlo en minutos, no para "cubrir todo".

Para extender esto a otro módulo: agregar su path a `source_paths`/
`only_mutate` en pyproject.toml, y una selección de tests RÁPIDA y
específica a `pytest_add_cli_args_test_selection` — si no existe un
archivo de tests rápido y aislado (sin DB) para ese módulo, escribir uno
primero (mismo criterio que tests/property/test_security_properties.py)
es más valioso que dejar que mutmut corra la suite completa por mutante.

Uso:
    python scripts/qa_suite/12_mutation_testing.py
    python scripts/qa_suite/12_mutation_testing.py --max-mutants 20   # muestra rápida
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-mutants", type=int, default=None, help="Limitar cuántos mutantes correr (muestra rápida en vez de todos)")
    args = parser.parse_args()

    print(f"{'=' * 70}\nMutation testing — app/core/security.py\n{'=' * 70}\n")
    print(
        "Este comando puede tardar varios minutos incluso acotado — cada mutante corre una\n"
        "suite completa de tests, aunque sea la versión rápida (~5s).\n"
    )

    run_cmd = [sys.executable, "-m", "mutmut", "run"]
    if args.max_mutants:
        run_cmd += ["--max-children", str(args.max_mutants)]
    result = subprocess.run(run_cmd, cwd=BACKEND_ROOT)

    print(f"\n{'=' * 70}\nResultados\n{'=' * 70}")
    subprocess.run([sys.executable, "-m", "mutmut", "results"], cwd=BACKEND_ROOT)

    print(
        "\nPara ver el código exacto de un mutante que sobrevivió (test insuficiente):\n"
        "  python -m mutmut show <id>\n"
        "Un mutante sobreviviente no es automáticamente un 'fallo' de este script — es una "
        "SEÑAL para revisar si ese caso merece un test nuevo. El script no falla el exit code "
        "por mutantes sobrevivientes (a diferencia de las otras etapas): es una herramienta de "
        "exploración, no un gate binario pasa/no-pasa."
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
