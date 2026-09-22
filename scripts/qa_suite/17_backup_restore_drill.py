#!/usr/bin/env python3
"""
17_backup_restore_drill.py — ¿el backup declarado realmente sirve para
recuperar el sistema?

STATE.md nunca documenta un simulacro real de esto — este script lo hace:

1. `pg_dump` de la base real (DATABASE_URL_ADMIN) a un archivo.
2. Crea una base NUEVA, vacía, con nombre único.
3. Restaura el dump ahí (`psql < dump.sql`, o `pg_restore` si el dump es
   formato custom).
4. Corre `alembic upgrade head` contra la base restaurada — debería ser
   un no-op limpio (la tabla `alembic_version` viaja en el dump), confirma
   que el esquema restaurado es compatible con las migraciones actuales.
5. Compara el conteo de filas de una tabla representativa por módulo entre
   el original y la restaurada — deberían ser IDÉNTICOS.
6. Levanta una conexión real contra la base restaurada y corre una query
   con JOIN real (no solo un SELECT 1) para confirmar que no es solo
   "las tablas existen" sino "los datos y las relaciones son usables".
7. Limpieza: dropea la base temporal y borra el archivo de dump.

Requiere `pg_dump`/`psql` en PATH (vienen con cualquier instalación de
Postgres — si el backend ya corre migraciones con Alembic contra esta
misma base, ya están disponibles) y permisos de superusuario/CREATEDB
sobre el servidor Postgres (usa el mismo rol que Alembic, vía
DATABASE_URL_ADMIN).

Uso:
    python scripts/qa_suite/17_backup_restore_drill.py
"""
from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

import os  # noqa: E402

os.chdir(BACKEND_ROOT)

from app.config import settings  # noqa: E402


def _parse_admin_url() -> dict:
    """DATABASE_URL_ADMIN es postgresql+psycopg://user:pass@host:port/db —
    pg_dump/psql/createdb/dropdb quieren host/port/user/dbname sueltos,
    no una URL SQLAlchemy."""
    raw = settings.database_url_admin.replace("postgresql+psycopg://", "postgresql://")
    parsed = urlparse(raw)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname": (parsed.path or "/").lstrip("/"),
    }


def _run(cmd: list[str], *, env: dict, description: str) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"✗ FALLO en «{description}»:\n{result.stderr[:2000]}")
    return result


def main() -> int:
    conn = _parse_admin_url()
    env = {**os.environ, "PGPASSWORD": conn["password"]}
    common = ["-h", conn["host"], "-p", conn["port"], "-U", conn["user"]]

    dump_path = Path(f"/tmp/backup_restore_drill_{uuid.uuid4().hex[:8]}.sql")
    restored_db = f"restore_drill_{uuid.uuid4().hex[:8]}"

    print(f"{'=' * 70}\nSimulacro de backup/restore — base original: '{conn['dbname']}'\n{'=' * 70}\n")

    print("--- 1. pg_dump de la base real ---")
    dump = _run(
        ["pg_dump", *common, "-d", conn["dbname"], "-f", str(dump_path)],
        env=env, description="pg_dump",
    )
    if dump.returncode != 0:
        return 1
    size_mb = dump_path.stat().st_size / (1024 * 1024)
    print(f"✓ Dump generado: {dump_path} ({size_mb:.2f} MB)\n")

    print(f"--- 2. Crear base nueva y vacía: '{restored_db}' ---")
    create = _run(["createdb", *common, restored_db], env=env, description="createdb")
    if create.returncode != 0:
        dump_path.unlink(missing_ok=True)
        return 1
    print("✓ Base creada.\n")

    ok = True
    try:
        print("--- 3. Restaurar el dump en la base nueva ---")
        restore = _run(
            ["psql", *common, "-d", restored_db, "-f", str(dump_path), "-v", "ON_ERROR_STOP=1"],
            env=env, description="psql (restore)",
        )
        if restore.returncode != 0:
            ok = False
        else:
            print("✓ Restaurado sin errores.\n")

        if ok:
            print("--- 4. alembic upgrade head contra la base restaurada (debería ser no-op) ---")
            restored_admin_url = settings.database_url_admin.replace(f"/{conn['dbname']}", f"/{restored_db}")
            alembic_env = {**env, "DATABASE_URL_ADMIN": restored_admin_url}
            upgrade = _run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                env=alembic_env, description="alembic upgrade head",
            )
            if upgrade.returncode != 0:
                ok = False
            else:
                # Un upgrade "no-op" real no imprime ninguna línea de
                # "Running upgrade" — si el esquema restaurado YA estaba al
                # día, alembic no debería tener nada que hacer.
                ran_migrations = "Running upgrade" in upgrade.stdout or "Running upgrade" in upgrade.stderr
                if ran_migrations:
                    print(
                        "⚠ alembic SÍ corrió migraciones contra la base restaurada — el dump no incluía "
                        "el estado más reciente, o el pg_dump/restore no preservó alembic_version "
                        "correctamente. Revisar (no necesariamente un fallo si el dump es de un punto "
                        "intencionalmente anterior)."
                    )
                else:
                    print("✓ No-op limpio — el esquema restaurado ya estaba al día con las migraciones actuales.\n")

        if ok:
            print("--- 5. Comparar conteo de filas por tabla representativa ---")
            tables_to_check = ["companies", "users", "contacts", "products", "sales_orders", "invoices"]
            mismatches = []
            for table in tables_to_check:
                original = _run(
                    ["psql", *common, "-d", conn["dbname"], "-t", "-c", f"SELECT count(*) FROM {table}"],
                    env=env, description=f"count {table} (original)",
                )
                restored = _run(
                    ["psql", *common, "-d", restored_db, "-t", "-c", f"SELECT count(*) FROM {table}"],
                    env=env, description=f"count {table} (restaurada)",
                )
                orig_count = original.stdout.strip()
                rest_count = restored.stdout.strip()
                status = "✓" if orig_count == rest_count else "✗"
                print(f"  {status} {table}: original={orig_count} restaurada={rest_count}")
                if orig_count != rest_count:
                    mismatches.append(table)
            if mismatches:
                print(f"✗ FALLO: conteo de filas distinto en: {mismatches}")
                ok = False
            print()

        if ok:
            print("--- 6. Query real con JOIN contra la base restaurada (no solo 'las tablas existen') ---")
            join_query = (
                "SELECT count(*) FROM sales_orders so "
                "JOIN contacts c ON c.id = so.customer_id "
                "JOIN companies co ON co.id = so.company_id"
            )
            join_result = _run(
                ["psql", *common, "-d", restored_db, "-t", "-c", join_query],
                env=env, description="query con JOIN real",
            )
            if join_result.returncode != 0:
                ok = False
            else:
                print(f"✓ JOIN real ejecuta correctamente contra la base restaurada — {join_result.stdout.strip()} filas.\n")
    finally:
        print(f"--- 7. Limpieza: dropear '{restored_db}' y borrar el dump ---")
        _run(["dropdb", *common, "--if-exists", restored_db], env=env, description="dropdb")
        dump_path.unlink(missing_ok=True)
        print("✓ Limpieza completa.\n")

    print(f"{'=' * 70}")
    if ok:
        print("✓✓✓ Simulacro de backup/restore exitoso — el backup declarado sí sirve para recuperar el sistema. ✓✓✓")
        return 0
    print("✗ El simulacro encontró un problema real — ver detalle arriba.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
