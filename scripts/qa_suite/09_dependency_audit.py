#!/usr/bin/env python3
"""
09_dependency_audit.py — `pip-audit` sobre requirements.txt (producción) y
requirements-qa.txt (herramientas de esta misma suite), buscando CVEs
conocidos en las versiones exactas pineadas.

Nunca se había corrido en este proyecto — todas las versiones en
requirements.txt fueron elegidas por disponibilidad al momento de instalar
(pip install sin pin previo, luego congeladas), no por ausencia de
vulnerabilidades conocidas.

Uso:
    python scripts/qa_suite/09_dependency_audit.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"


def audit(requirements_file: str, *, ignore_vulns: list[str] | None = None) -> int:
    path = BACKEND_ROOT / requirements_file
    if not path.exists():
        print(f"! {requirements_file} no existe — omitido.")
        return 0

    print(f"--- {requirements_file} ---")
    cmd = [sys.executable, "-m", "pip_audit", "-r", str(path), "--desc"]
    for vuln_id in ignore_vulns or []:
        cmd += ["--ignore-vuln", vuln_id]
    result = subprocess.run(cmd, cwd=BACKEND_ROOT)
    return result.returncode


# Riesgos aceptados y documentados (ver STATE.md, sección "Riesgos
# aceptados") — NO usar esto para CVEs nuevos sin evaluar primero si hay
# una versión con fix real disponible.
#
# PYSEC-2026-1325 (ecdsa, timing attack Minerva sobre P-256): `ecdsa` es
# dependencia DURA de python-jose sin importar el extra instalado
# (confirmado: python-jose[cryptography] también la arrastra). Esta app
# firma JWT exclusivamente con HS256 (app/core/security.py) — la
# superficie ECDSA de `ecdsa` nunca se ejerce en runtime. Sin parche
# planeado por el proyecto upstream a la fecha de esta auditoría.
PROD_IGNORE_VULNS = ["PYSEC-2026-1325"]


def main() -> int:
    print("=== Auditoría de dependencias (pip-audit) ===\n")
    code_prod = audit("requirements.txt", ignore_vulns=PROD_IGNORE_VULNS)
    print()
    code_qa = audit("requirements-qa.txt")

    print()
    if code_prod == 0 and code_qa == 0:
        print("✓ Sin CVEs conocidos en las dependencias pineadas.")
        return 0
    print("✗ pip-audit encontró CVEs conocidos — ver el detalle arriba. Evaluar upgrade de la versión afectada.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
