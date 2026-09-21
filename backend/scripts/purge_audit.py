#!/usr/bin/env python3
"""
purge_audit.py — Depuración física real de `audit` (módulo 25, spec 8.1)

## Por qué este script existe fuera de la API HTTP (AMB-07, ver STATE.md)

La tabla `audit` tiene un trigger `BEFORE UPDATE OR DELETE`
(`trg_audit_immutable`, creado en el módulo 1, spec 8.0) que bloquea
CUALQUIER UPDATE/DELETE sobre esa tabla incondicionalmente — no importa
el rol, no importa si la fila es de un evento "operativo general" o de
un evento clínico. Esto es deliberado: ni siquiera `erp_app` (el rol de
runtime de la API, que sí tiene el GRANT de DELETE) puede borrar una
fila de `audit` a través de la aplicación. Es la garantía real de
"audit es append-only" — un admin de la compañía comprometido no puede
usar la API para borrar su propio rastro.

`AuditRetentionService.count_purge_eligible` (endpoint
`GET /audit/retention-policy/purge-eligible`) por eso SOLO cuenta filas
vencidas — nunca las borra. El borrado físico real, cuando de verdad
hace falta por una obligación de retención (spec 8.1: "rotación
estándar, ej. 90 días" para eventos operativos generales — nunca para
eventos `medical.*`, protegidos aparte por regulación, spec 8.2), es
this operación de mantenimiento explícita, ejecutada por alguien con
credenciales de base de datos elevadas (dueño de la tabla o superusuario
— NO las credenciales normales de `erp_app`), fuera de cualquier sesión
de usuario de la aplicación.

## Qué hace

Por cada compañía (o una sola, si se pasa `--company-id`):
1. Lee su `AuditRetentionPolicy.retention_days` (90 si no tiene fila).
2. Desactiva `trg_audit_immutable` (requiere ser dueño de la tabla).
3. Borra las filas de `audit` de esa compañía con `created_at` más
   viejo que `retention_days`, EXCLUYENDO cualquier evento que empiece
   con `medical.` (mismo criterio que `AuditQueryService.MEDICAL_EVENT_PREFIX`
   — ver `app/audit/services.py`).
4. Reactiva el trigger.
5. Todo dentro de una transacción — si el paso 3 falla, el trigger
   nunca queda desactivado más tiempo del necesario.

## Corrección real (sesión de verificación externa, sep-2026)

Al ejecutarlo por primera vez contra Postgres real con `--company-id`,
falló con `psycopg.errors.AmbiguousColumn: column reference
"company_id" is ambiguous` — el filtro `company_filter` usaba
`company_id` sin calificar, y las 3 consultas donde se interpola
mezclan `audit a` con `audit_retention_policies p` (ambas tienen esa
columna). Corregido calificando como `a.company_id` en las 3.
Verificado real: `--dry-run` reporta el mismo conteo que
`GET /audit/retention-policy/purge-eligible`, el borrado real excluye
correctamente eventos `medical.*`, y el trigger de inmutabilidad queda
reactivado al final (confirmado con un intento de `DELETE` manual
posterior, que vuelve a fallar como debe).

## NO EJECUTADO — sin Postgres disponible en el entorno donde se escribió

Igual que el resto de scripts nuevos de este proyecto en sesiones sin
Postgres/red (`verify_state.py`, `validate_modules.py`), este script se
escribió por inspección de la spec y el esquema, no se corrió contra una
base real. Antes de usarlo en producción: probarlo primero contra un
respaldo/staging, y confirmar que el DSN pasado en `--db-url` tiene
privilegios de owner sobre `audit` (si no, el `ALTER TABLE ... DISABLE
TRIGGER` del paso 2 fallará con un error de permisos claro, no con un
borrado a medias).

Uso:
    python scripts/purge_audit.py --db-url postgresql://OWNER:pass@host/db
    python scripts/purge_audit.py --db-url ... --company-id 3
    python scripts/purge_audit.py --db-url ... --dry-run
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Depuración física de audit — módulo 25 (v10.4)")
    parser.add_argument("--db-url", required=True, help="DSN de PostgreSQL con privilegios de OWNER sobre 'audit' (no erp_app)")
    parser.add_argument("--company-id", type=int, default=None, help="Limitar a una sola compañía (default: todas)")
    parser.add_argument("--dry-run", action="store_true", help="Solo reporta cuántas filas se borrarían, sin tocar nada")
    args = parser.parse_args()

    try:
        import psycopg  # type: ignore
    except ImportError:
        print("ERROR: psycopg no instalado — pip install 'psycopg[binary]'", file=sys.stderr)
        return 2

    with psycopg.connect(args.db_url, connect_timeout=5) as conn, conn.cursor() as cur:
        company_filter = "AND a.company_id = %(company_id)s" if args.company_id is not None else ""
        params = {"company_id": args.company_id} if args.company_id is not None else {}

        cur.execute(
            f"""
                SELECT a.company_id,
                       COALESCE(p.retention_days, 90) AS retention_days,
                       count(*) FILTER (
                           WHERE a.created_at < now() - (COALESCE(p.retention_days, 90) || ' days')::interval
                             AND a.event NOT LIKE 'medical.%%'
                       ) AS eligible
                FROM audit a
                LEFT JOIN audit_retention_policies p ON p.company_id = a.company_id
                WHERE 1=1 {company_filter}
                GROUP BY a.company_id, p.retention_days
                """,
            params,
        )
        rows = cur.fetchall()

        if not rows:
            print("Nada que evaluar — sin filas en 'audit' que coincidan con el filtro.")
            return 0

        total_eligible = 0
        for company_id, retention_days, eligible in rows:
            print(f"company_id={company_id} retention_days={retention_days} elegibles_para_borrar={eligible}")
            total_eligible += eligible

        if args.dry_run:
            print(f"\n--dry-run: {total_eligible} fila(s) se borrarían. Nada fue modificado.")
            return 0

        if total_eligible == 0:
            print("\nSin filas elegibles — no se desactiva el trigger.")
            return 0

        confirm = input(f"\nSe van a borrar {total_eligible} fila(s) de 'audit' (excluyendo 'medical.*'). Escribir 'BORRAR' para confirmar: ")
        if confirm != "BORRAR":
            print("Cancelado — no se modificó nada.")
            return 1

        cur.execute("ALTER TABLE audit DISABLE TRIGGER trg_audit_immutable")
        try:
            cur.execute(
                f"""
                    DELETE FROM audit a
                    USING audit_retention_policies p
                    WHERE a.company_id = p.company_id
                      AND a.created_at < now() - (p.retention_days || ' days')::interval
                      AND a.event NOT LIKE 'medical.%%'
                      {company_filter}
                    """,
                params,
            )
            deleted_with_policy = cur.rowcount
            cur.execute(
                f"""
                    DELETE FROM audit a
                    WHERE NOT EXISTS (SELECT 1 FROM audit_retention_policies p WHERE p.company_id = a.company_id)
                      AND a.created_at < now() - interval '90 days'
                      AND a.event NOT LIKE 'medical.%%'
                      {company_filter}
                    """,
                params,
            )
            deleted_default = cur.rowcount
        finally:
            cur.execute("ALTER TABLE audit ENABLE TRIGGER trg_audit_immutable")

        conn.commit()
        print(f"\nBorradas {deleted_with_policy + deleted_default} fila(s). Trigger de inmutabilidad reactivado.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
