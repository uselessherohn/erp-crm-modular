#!/usr/bin/env python3
"""
validate_modules.py — Consistencia estructural de modulos_erp_crm_v10_4.json

Deliberadamente simple: sin dependencias, sin máquina de estados, sin
compilador de contexto — solo lo que hace falta para atrapar el tipo de
error que ya pasó una vez (dependencia incorrecta del módulo 15 en v10.1)
antes de que llegue a la tabla markdown.

Uso:
    python scripts/validate_modules.py modulos_erp_crm_v10_4.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    modulos = data.get("modulos", [])
    ids = {m["id"] for m in modulos}

    # 1. Toda dependencia declarada debe existir como módulo
    for m in modulos:
        for dep in m.get("depende_de", []):
            if dep not in ids:
                errors.append(f"Módulo {m['id']} ({m['nombre']}) depende de {dep}, que no existe")
        for dep in m.get("depende_opcional_de", []):
            if dep not in ids:
                errors.append(f"Módulo {m['id']} ({m['nombre']}) depende opcionalmente de {dep}, que no existe")

    # 2. Sin ciclos (orden topológico de Kahn)
    indeg = {m["id"]: 0 for m in modulos}
    adj: dict[int, list[int]] = {m["id"]: [] for m in modulos}
    for m in modulos:
        for dep in m.get("depende_de", []):
            if dep in adj:
                adj[dep].append(m["id"])
                indeg[m["id"]] += 1
    queue = [i for i, deg in indeg.items() if deg == 0]
    visited = 0
    while queue:
        n = queue.pop()
        visited += 1
        for nb in adj.get(n, []):
            indeg[nb] -= 1
            if indeg[nb] == 0:
                queue.append(nb)
    if visited != len(modulos):
        errors.append("Ciclo detectado en las dependencias obligatorias de la tabla de módulos")

    # 3. IDs únicos y consecutivos (facilita detectar huecos por error de edición)
    sorted_ids = sorted(ids)
    if sorted_ids != list(range(1, len(sorted_ids) + 1)):
        errors.append(f"IDs de módulo no son consecutivos desde 1: {sorted_ids}")

    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Uso: python scripts/validate_modules.py <ruta al JSON>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(data)

    if errors:
        print(f"✗ {len(errors)} error(es) de consistencia en {path.name}:\n")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"✓ {path.name} consistente: {len(data.get('modulos', []))} módulos, sin ciclos, sin dependencias huérfanas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
