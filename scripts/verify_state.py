#!/usr/bin/env python3
"""
verify_state.py — Verificación externa del DoD (nuevo en v10.4)

No reemplaza los tests del módulo (Fase 4) ni el Definition of Done
(spec sección 11) — es una segunda opinión que no depende de que el mismo
agente que escribió el código sea también quien confirma que está bien
escrito. Ver "Verificación externa del DoD" en
plantilla_modulos_erp_crm_v10_4.md.

Uso:
    python scripts/verify_state.py --state STATE.md --repo .
    python scripts/verify_state.py --state STATE.md --repo . --db-url postgresql://user:pass@host/db

Sin --db-url, se omiten las verificaciones de Nivel 1 (trigger de audit,
tabla idempotency_keys) y se reporta como "no verificable en este entorno"
en vez de fallar — el script nunca inventa un resultado que no pudo
comprobar.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


class Finding:
    def __init__(self, level: str, message: str):
        self.level = level  # "ERROR" | "WARNING" | "OK" | "SKIP"
        self.message = message

    def __str__(self) -> str:
        symbol = {"ERROR": "✗", "WARNING": "!", "OK": "✓", "SKIP": "·"}[self.level]
        return f"{symbol} [{self.level}] {self.message}"


def check_modules_exist_on_disk(state_text: str, repo_root: Path) -> list[Finding]:
    """Sección 1 de STATE.md: cada módulo marcado (✓) debería tener rastro
    real en el repo. Heurística deliberadamente simple — no reemplaza
    revisión humana, solo atrapa el caso obvio de STATE.md desincronizado
    del código (cierre que actualizó STATE.md pero no llegó a escribir
    archivos, o viceversa)."""
    findings: list[Finding] = []
    section1 = _extract_section(state_text, "1. Paquetes y módulos completados")
    if section1 is None:
        findings.append(Finding("WARNING", "No se encontró la sección 1 de STATE.md"))
        return findings

    # ej. "- Núcleo: core (✓), contacts (—)" — acepta guiones/guiones bajos
    # por si el repo real usa slugs compuestos en vez de nombres simples
    pattern = re.compile(r"([a-zA-Z_][\w/-]*)\s*\(✓\)")
    modules_marked_done = pattern.findall(section1)

    if not modules_marked_done:
        findings.append(Finding("SKIP", "Ningún módulo marcado (✓) todavía en STATE.md §1"))
        return findings

    for module_name in modules_marked_done:
        candidates = [
            repo_root / module_name,
            repo_root / "app" / module_name,
            repo_root / "backend" / "app" / module_name,
            repo_root / "src" / module_name,
        ]
        if any(c.exists() for c in candidates):
            findings.append(Finding("OK", f"Módulo '{module_name}' marcado (✓) tiene rastro en el repo"))
        else:
            findings.append(Finding(
                "ERROR",
                f"STATE.md marca '{module_name}' como (✓) pero no se encontró carpeta/archivo "
                f"correspondiente en ninguna de: {[str(c) for c in candidates]}",
            ))
    return findings


def check_pgcrypto_amb_key(state_text: str) -> list[Finding]:
    """Confirma que si existe declaración AMB-KEY (gestión de clave pgcrypto,
    spec 1.1), los cinco campos obligatorios están presentes — sea el caso
    DEDUCIBLE con default o el caso AMBIGUO (v10.4)."""
    findings: list[Finding] = []
    if "AMB-KEY" not in state_text:
        findings.append(Finding("SKIP", "Sin declaración AMB-KEY todavía — ok si aún no hay módulo medical con pgcrypto"))
        return findings

    required_fields = ["key_location", "rotation_period_days", "owner", "rekey_plan", "backup_policy"]
    amb_key_block = _extract_after_marker(state_text, "AMB-KEY:")
    missing = [f for f in required_fields if f"{f}=" not in amb_key_block]

    if missing:
        findings.append(Finding(
            "ERROR",
            f"AMB-KEY incompleto — faltan campos obligatorios (spec 1.1, plantilla de 5 campos): {missing}",
        ))
    else:
        findings.append(Finding("OK", "AMB-KEY tiene los cinco campos obligatorios completos"))
    return findings


def check_no_legacy_boolean_field(repo_root: Path, state_text: str) -> list[Finding]:
    """Regresión del hallazgo de v10.3: minimal_dependencies_only (bool) debía
    reemplazarse por minimal_modules (list[str] | None)."""
    findings: list[Finding] = []
    if "minimal_dependencies_only" in state_text:
        findings.append(Finding(
            "ERROR",
            "STATE.md todavía usa 'minimal_dependencies_only' (booleano viejo) — "
            "debe ser 'minimal_modules: list[str] | None' (v10.3, spec 2.4)",
        ))
    else:
        findings.append(Finding("OK", "STATE.md no usa el booleano viejo minimal_dependencies_only"))

    # Búsqueda heurística de código real, si el repo está disponible
    hits: list[str] = []
    if repo_root.exists():
        for py_file in repo_root.rglob("*.py"):
            try:
                if "minimal_dependencies_only" in py_file.read_text(encoding="utf-8", errors="ignore"):
                    hits.append(str(py_file))
            except OSError:
                continue
    if hits:
        findings.append(Finding(
            "ERROR",
            f"Código fuente todavía referencia 'minimal_dependencies_only' en: {hits}",
        ))
    return findings


def check_db_invariants(db_url: str) -> list[Finding]:
    """Verificaciones de Nivel 1 (requieren conexión real a PostgreSQL):
    trigger de inmutabilidad sobre audit + tabla idempotency_keys con su
    índice único."""
    findings: list[Finding] = []
    try:
        import psycopg  # type: ignore
    except ImportError:
        findings.append(Finding(
            "WARNING",
            "psycopg no instalado — no se pueden correr verificaciones de Nivel 1. "
            "pip install 'psycopg[binary]'",
        ))
        return findings

    try:
        with psycopg.connect(db_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT trigger_name FROM information_schema.triggers
                    WHERE event_object_table = 'audit'
                      AND action_timing = 'BEFORE'
                      AND (event_manipulation ILIKE '%UPDATE%' OR event_manipulation ILIKE '%DELETE%');
                    """
                )
                rows = cur.fetchall()
                if rows:
                    findings.append(Finding("OK", f"Trigger de inmutabilidad presente en 'audit': {[r[0] for r in rows]}"))
                else:
                    findings.append(Finding("ERROR", "No se encontró trigger BEFORE UPDATE/DELETE sobre 'audit' (spec 8.0/8.2)"))

                cur.execute("SELECT to_regclass('public.idempotency_keys') IS NOT NULL;")
                exists = cur.fetchone()[0]
                if not exists:
                    findings.append(Finding("ERROR", "Tabla 'idempotency_keys' no existe (spec 7)"))
                else:
                    cur.execute(
                        """
                        SELECT indexname FROM pg_indexes
                        WHERE tablename = 'idempotency_keys'
                          AND indexdef ILIKE '%(company_id, idempotency_key, endpoint)%';
                        """
                    )
                    idx = cur.fetchall()
                    if idx:
                        findings.append(Finding("OK", "Índice único (company_id, idempotency_key, endpoint) presente en idempotency_keys"))
                    else:
                        findings.append(Finding("ERROR", "Falta índice único (company_id, idempotency_key, endpoint) en idempotency_keys (spec 7)"))
    except Exception as exc:  # noqa: BLE001 — reportamos cualquier fallo de conexión, no lo escondemos
        findings.append(Finding("ERROR", f"No se pudo conectar/consultar la base: {exc}"))

    return findings


def _extract_section(text: str, header_fragment: str) -> str | None:
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if header_fragment in line:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "\n".join(lines[start:end])


def _extract_after_marker(text: str, marker: str) -> str:
    idx = text.find(marker)
    if idx == -1:
        return ""
    return text[idx: idx + 800]  # ventana suficiente para los 5 campos


def main() -> int:
    parser = argparse.ArgumentParser(description="Verificación externa del DoD — v10.4")
    parser.add_argument("--state", required=True, type=Path, help="Ruta a STATE.md")
    parser.add_argument("--repo", required=True, type=Path, help="Raíz del repo del proyecto")
    parser.add_argument("--db-url", default=None, help="DSN de PostgreSQL para verificaciones de Nivel 1 (opcional)")
    args = parser.parse_args()

    if not args.state.exists():
        print(f"ERROR: {args.state} no existe", file=sys.stderr)
        return 2

    state_text = args.state.read_text(encoding="utf-8")

    all_findings: list[Finding] = []
    all_findings += check_modules_exist_on_disk(state_text, args.repo)
    all_findings += check_pgcrypto_amb_key(state_text)
    all_findings += check_no_legacy_boolean_field(args.repo, state_text)

    if args.db_url:
        all_findings += check_db_invariants(args.db_url)
    else:
        all_findings.append(Finding("SKIP", "Sin --db-url: se omiten verificaciones de Nivel 1 (trigger audit, idempotency_keys)"))

    print("=== Verificación externa del DoD — v10.4 ===\n")
    for f in all_findings:
        print(f)

    n_errors = sum(1 for f in all_findings if f.level == "ERROR")
    print(f"\n{n_errors} error(es) encontrados." if n_errors else "\nSin errores detectados.")
    return 1 if n_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
