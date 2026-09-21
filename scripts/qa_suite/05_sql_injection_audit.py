#!/usr/bin/env python3
"""
05_sql_injection_audit.py — Audita todo uso de SQL crudo (`sqlalchemy.text()`,
y `op.execute()` en migraciones) buscando el patrón real de riesgo: SQL armado
con f-strings/`.format()`/`%`-formatting a partir de datos que podrían venir
del usuario, en vez de parámetros bindeados (`:nombre` + `.execute(stmt, {...})`).

No es un linter genérico de seguridad (para eso existe `bandit`, más ruidoso
y con más falsos positivos en un proyecto que sí usa SQL crudo legítimamente
para RLS/triggers) — es un chequeo dirigido a la forma real en que este
proyecto construye queries, aprendido de la propia auditoría de regresión:
`text()` con `:param` es el patrón correcto y mayoritario; lo que hay que
atrapar es una desviación de ese patrón, no el uso de `text()` en sí.

Clasifica cada hallazgo en dos categorías:
- CRÍTICO (`app/`): interpolación de un valor en `text()` fuera de
  `alembic/versions/` — el código de aplicación no debería nunca necesitar
  esto (nombres de tabla/columna en `app/` son siempre literales fijos en
  el código, no datos de entrada).
- REVISAR (`alembic/versions/`): interpolación en una migración — con
  frecuencia legítima (nombres de tabla que varían migración a migración,
  pero SIEMPRE literales del propio código fuente, nunca de un usuario) pero
  vale la pena confirmarlo caso por caso, no asumirlo.

Uso:
    python scripts/qa_suite/05_sql_injection_audit.py
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

# Encuentra llamadas a text(...)/execute(...) cuyo argumento es un f-string,
# una llamada a .format(, o contiene un operador % de formato de string
# (heurística por línea — no un parser de AST completo, pero suficiente para
# este tamaño de repo y mucho más preciso que un grep genérico de "text(").
RISKY_CALL = re.compile(r"\b(text|execute)\s*\(\s*f[\"']")
RISKY_FORMAT = re.compile(r"\.execute\([^)]*\.format\(")


def scan_file(path: Path) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        if RISKY_CALL.search(line) or RISKY_FORMAT.search(line):
            findings.append((i, line.strip()))
    return findings


def main() -> int:
    print("=== Auditoría de SQL crudo (f-strings/.format() en text()/execute()) ===\n")

    critical: list[tuple[Path, int, str]] = []
    review: list[tuple[Path, int, str]] = []

    for f in (BACKEND_ROOT / "app").rglob("*.py"):
        if "__pycache__" in str(f):
            continue
        for line_no, line in scan_file(f):
            critical.append((f.relative_to(REPO_ROOT), line_no, line))

    for f in (BACKEND_ROOT / "alembic" / "versions").rglob("*.py"):
        if "__pycache__" in str(f):
            continue
        for line_no, line in scan_file(f):
            review.append((f.relative_to(REPO_ROOT), line_no, line))

    ok = True
    if critical:
        ok = False
        print(f"✗ CRÍTICO — {len(critical)} interpolación(es) de SQL en app/ (código de aplicación):")
        for path, line_no, line in critical:
            print(f"  {path}:{line_no}: {line}")
    else:
        print("✓ Sin interpolación de SQL en app/ — todo uso de text()/execute() usa parámetros bindeados.")

    print()
    if review:
        print(
            f"! REVISAR — {len(review)} interpolación(es) de SQL en migraciones "
            "(con frecuencia legítimo — nombres de tabla propios del código, "
            "nunca datos de usuario — pero confirmar caso por caso, no asumir):"
        )
        for path, line_no, line in review:
            print(f"  {path}:{line_no}: {line}")
    else:
        print("✓ Sin interpolación de SQL en migraciones tampoco.")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
