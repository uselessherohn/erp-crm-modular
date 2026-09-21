#!/usr/bin/env python3
"""
15_secrets_audit.py — ¿hay algún secreto real commiteado, en el historial
completo de git o en el working tree actual?

Puro Python + `git log -p` — sin `gitleaks`/`trufflehog` ni ninguna
dependencia externa, para que un agente lo corra sin instalar nada más que
lo que ya trae el repo. Los patrones cubren las familias de secretos más
comunes (AWS, claves privadas PEM, tokens de GitHub/Slack/Stripe, JWT
HS256 con pinta de secreto real, URLs de conexión con password embebido,
genéricos "password/secret/api_key = <algo con pinta de secreto>") — no es
exhaustivo (ningún regex-scanner lo es), pero cubre el 90% de lo que
termina commiteado por accidente.

IMPORTANTE — falsos positivos esperados y cómo se filtran:
- Todo lo que vive en `.env.example`, fixtures de test, o el propio
  código de ESTE script se excluye — son valores de ejemplo/plantilla a
  propósito.
- Valores claramente de desarrollo (`ci_test_...`, `dev_pw`, `changeme`,
  `example`, `xxx`) se reportan aparte, en "posibles falsos positivos",
  no en la lista de hallazgos reales — pero SÍ se listan, para que un
  humano decida, nunca se descartan en silencio.

Uso:
    python scripts/qa_suite/15_secrets_audit.py
    python scripts/qa_suite/15_secrets_audit.py --skip-history   # solo working tree, más rápido
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# (nombre, regex, ¿el grupo 0 completo es el secreto o hay que usar un grupo?)
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("AWS Access Key ID", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    (
        "AWS Secret Access Key (heurística — 40 chars base64-like tras 'aws.{0,20}secret')",
        re.compile(r"aws.{0,20}secret.{0,5}[:=]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?", re.IGNORECASE),
    ),
    ("Clave privada PEM", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    (
        "Token de GitHub (ghp_/gho_/ghu_/ghs_/ghr_/github_pat_)",
        re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    ),
    ("Token de Slack (xox?-...)", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("Clave de Stripe (sk_live_/rk_live_)", re.compile(r"\b(sk|rk)_live_[0-9A-Za-z]{20,}\b")),
    (
        "JWT con pinta de secreto real (HS256, 3 segmentos base64url)",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ),
    (
        "URL de conexión con password embebido",
        re.compile(r"(postgres(ql)?|mysql|mongodb(\+srv)?|redis)://[^:\s]+:[^@\s]{3,}@"),
    ),
    (
        "Asignación genérica de secreto (password/secret/token/api_key = valor no trivial)",
        re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"]([^'\"\s]{8,})['\"]"),
    ),
]

# Sustrings que, si aparecen en el VALOR capturado, degradan el hallazgo a
# "posible falso positivo" en vez de hallazgo real — placeholders de
# desarrollo, no secretos de producción.
DEV_PLACEHOLDER_MARKERS = (
    "ci_test", "dev_pw", "changeme", "example", "placeholder", "xxxxx", "your_", "<", "todo", "fixme",
    "test_secret", "not_for_production", "dummy", "owner:pass", "@host", "user:pass",
)

# Rutas excluidas del escaneo del working tree — plantillas/ejemplos a
# propósito, y este mismo script (sus propios patrones matchean sus
# propios docstrings de ejemplo).
EXCLUDE_PATH_SUBSTRINGS = (
    "/node_modules/", "/.git/", "/dist/", "/__pycache__/", "/.pytest_cache/", "/.mypy_cache/", "/.ruff_cache/",
    "/.hypothesis/", ".env.example", "15_secrets_audit.py", "/htmlcov/",
)


def _is_dev_placeholder(matched_text: str) -> bool:
    lowered = matched_text.lower()
    return any(marker in lowered for marker in DEV_PLACEHOLDER_MARKERS)


# Patrones cuyo match NUNCA es legítimo en ningún archivo, ni siquiera de
# test — una clave privada PEM o un token real de GitHub no tiene versión
# "de mentira" que tenga sentido commitear.
_ALWAYS_REAL_PATTERN_NAMES = frozenset({
    "AWS Access Key ID",
    "Clave privada PEM",
    "Token de GitHub (ghp_/gho_/ghu_/ghs_/ghr_/github_pat_)",
    "Token de Slack (xox?-...)",
    "Clave de Stripe (sk_live_/rk_live_)",
})


def _looks_like_test_file(source: str) -> bool:
    lowered = source.lower()
    return "test" in lowered or "/tests/" in lowered or "conftest" in lowered or "qa_suite" in lowered


def _scan_text(source: str, text: str) -> tuple[list[str], list[str]]:
    """Devuelve (hallazgos_reales, posibles_falsos_positivos) como líneas
    de reporte ya formateadas con su origen."""
    real: list[str] = []
    maybe: list[str] = []
    for name, pattern in PATTERNS:
        for match in pattern.finditer(text):
            snippet = match.group(0)
            # Nunca imprimir el secreto completo en el reporte — ni
            # siquiera si termina siendo un falso positivo, por higiene:
            # el reporte mismo no debería convertirse en otro lugar donde
            # buscar secretos.
            redacted = snippet[:6] + "…" + snippet[-4:] if len(snippet) > 14 else "…"
            line = f"  [{name}] {source} — {redacted}"
            # Un password/token/secret "genérico" (el patrón más ruidoso,
            # y el único que produce falsos positivos en volumen) dentro
            # de un archivo de test es, casi siempre, una credencial de
            # fixture inventada a propósito (ej. "PasswordSalesTest1") —
            # se degrada a "posible falso positivo" en vez de real. Los
            # patrones de _ALWAYS_REAL_PATTERN_NAMES NUNCA se degradan así:
            # no existe una versión "de mentira" legítima de una clave PEM
            # o un token real de GitHub.
            is_placeholder = _is_dev_placeholder(snippet) or (
                name not in _ALWAYS_REAL_PATTERN_NAMES and _looks_like_test_file(source)
            )
            (maybe if is_placeholder else real).append(line)
    return real, maybe


def scan_working_tree() -> tuple[list[str], list[str]]:
    real_all: list[str] = []
    maybe_all: list[str] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        path_str = str(path)
        if any(s in path_str for s in EXCLUDE_PATH_SUBSTRINGS):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        real, maybe = _scan_text(str(path.relative_to(REPO_ROOT)), text)
        real_all += real
        maybe_all += maybe
    return real_all, maybe_all


def scan_git_history() -> tuple[list[str], list[str]]:
    """`git log -p` completo — encuentra secretos que se commitearon y
    DESPUÉS se borraron en un commit posterior (siguen en el historial,
    recuperables por cualquiera con `git log`/`git show`, aunque el
    working tree actual ya esté limpio).

    Se parsea línea por línea seteando el archivo "actual" en cada header
    `diff --git a/X b/Y` — así una línea agregada dentro de
    `tests/test_core_module.py` se identifica como tal (mismo criterio de
    "es un archivo de test" que en el working tree), en vez de perder ese
    contexto y quedar como un `passwo…123` genérico sin archivo, que sin
    esa pista se clasificaría como hallazgo real."""
    result = subprocess.run(
        ["git", "log", "-p", "--all", "--full-history"], cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"! No se pudo leer el historial de git: {result.stderr[:300]}")
        return [], []

    real_all: list[str] = []
    maybe_all: list[str] = []
    current_file = "(archivo desconocido en el historial)"
    diff_header = re.compile(r"^diff --git a/(.+?) b/(.+)$")
    buffer_by_file: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        header_match = diff_header.match(line)
        if header_match:
            current_file = header_match.group(2)
            continue
        if line.startswith("+") and not line.startswith("+++"):
            buffer_by_file.setdefault(current_file, []).append(line[1:])

    for file_path, added_lines in buffer_by_file.items():
        real, maybe = _scan_text(f"git-history:{file_path}", "\n".join(added_lines))
        real_all += real
        maybe_all += maybe
    return real_all, maybe_all


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-history", action="store_true",
        help="Solo escanea el working tree actual, sin el historial de git (más rápido)",
    )
    args = parser.parse_args()

    print("=== Auditoría de secretos ===\n")

    print("--- Working tree actual ---")
    wt_real, wt_maybe = scan_working_tree()
    print(f"{len(wt_real)} hallazgo(s) real(es), {len(wt_maybe)} posible(s) falso(s) positivo(s).\n")

    hist_real: list[str] = []
    hist_maybe: list[str] = []
    if not args.skip_history:
        print("--- Historial completo de git (git log -p --all) ---")
        hist_real, hist_maybe = scan_git_history()
        print(f"{len(hist_real)} hallazgo(s) real(es), {len(hist_maybe)} posible(s) falso(s) positivo(s).\n")
    else:
        print("--- Historial de git: omitido (--skip-history) ---\n")

    all_real = wt_real + hist_real
    all_maybe = wt_maybe + hist_maybe

    if all_real:
        print(f"✗ {len(all_real)} HALLAZGO(S) REAL(ES):")
        for line in all_real:
            print(line)
        print()
    if all_maybe:
        print(f"⚠ {len(all_maybe)} posible(s) falso(s) positivo(s) (placeholder de desarrollo por el valor, revisar de todos modos):")
        for line in all_maybe[:30]:
            print(line)
        if len(all_maybe) > 30:
            print(f"  ... y {len(all_maybe) - 30} más.")
        print()

    if all_real:
        print(
            "✗ Hay secretos reales commiteados — si están en el HISTORIAL (no solo el working\n"
            "  tree), borrar el archivo no alcanza: hace falta reescribir el historial\n"
            "  (git filter-repo / BFG) y ROTAR el secreto (asumir que ya está comprometido)."
        )
        return 1
    print("✓ Sin secretos reales detectados en working tree ni historial completo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
