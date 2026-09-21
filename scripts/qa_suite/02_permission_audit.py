#!/usr/bin/env python3
"""
02_permission_audit.py — Permisos "fantasma": usados en require_permission()
pero nunca sembrados en scripts/bootstrap_admin.py (nadie podría tenerlos
nunca, ni un admin — el endpoint queda inaccesible para siempre), y
permisos sembrados pero nunca usados en ningún require_permission() (código
muerto de RBAC, o un typo que dejó el código real sin protección real).

Corrida original manual: Fase 0 de la regresión QA externa (sep-2026, ver
STATE.md sección 0.1). Formalizada acá para poder re-correrla en cada
cambio, no solo una vez.

Uso:
    python scripts/qa_suite/02_permission_audit.py
"""
from __future__ import annotations

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"


def find_used_permissions() -> set[str]:
    """Un código de permiso se considera "usado" si aparece como string
    literal en cualquier lugar de app/ (fuera de bootstrap_admin.py) — no
    solo dentro de require_permission(...). Hallazgo real al escribir
    este script: varios códigos de medical/hr se chequean vía
    user_has_permission() (enmascarado "suave", DED-21) o pasados como
    kwarg a un helper propio (all_permission=/own_permission=, RBAC "own
    patients" de medical) — ninguno de los dos calza con el patrón
    estricto require_permission("...") que tenía la primera versión de
    este script, y eso generaba 16 falsos positivos de "sin uso"."""
    used: set[str] = set()
    pattern = re.compile(r'"([a-z_]+:[a-z_]+:[a-z_-]+)"')
    for f in (BACKEND_ROOT / "app").rglob("*.py"):
        if "__pycache__" in str(f):
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        used |= set(pattern.findall(text))
    return used


def find_seeded_permissions() -> set[str]:
    text = (BACKEND_ROOT / "scripts" / "bootstrap_admin.py").read_text(encoding="utf-8", errors="ignore")
    return set(re.findall(r'code\s*=\s*"([a-z_]+:[a-z_]+:[a-z_-]+)"', text))


def main() -> int:
    used = find_used_permissions()
    seeded = find_seeded_permissions()

    phantom = sorted(used - seeded)  # usados, nunca sembrados — inaccesibles para siempre
    unused = sorted(seeded - used)  # sembrados, nunca usados — código muerto o typo

    print("=== Auditoría de permisos RBAC ===\n")
    print(f"Permisos usados (string literal en app/): {len(used)}")
    print(f"Permisos sembrados en bootstrap_admin.py: {len(seeded)}\n")

    ok = True
    if phantom:
        ok = False
        print("✗ PERMISOS FANTASMA (usados, nunca sembrados — nadie puede tenerlos nunca):")
        for p in phantom:
            print(f"  - {p}")
    else:
        print("✓ Sin permisos fantasma.")

    print()
    if unused:
        # WARNING, no ERROR — código muerto no es tan grave como un endpoint
        # inaccesible, pero vale la pena revisarlo (¿typo real? ¿feature
        # a medio construir?).
        print("! Permisos sembrados pero nunca usados en require_permission() (revisar, no necesariamente un bug):")
        for p in unused:
            print(f"  - {p}")
    else:
        print("✓ Sin permisos sembrados sin uso.")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
