"""
Engine y sesión async de SQLAlchemy 2.0 (spec sección 1: asyncpg, no bloquear
el event loop). La dependencia `get_db_with_tenant_context` (que fija
`app.current_company_id` vía `set_config()` para RLS) se agrega en Fase 2
(Backend Lógica) junto con `get_current_company_id` — acá solo la base.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    # pool_pre_ping: antes de entregar una conexión del pool, hace un
    # SELECT 1 barato para confirmar que sigue viva.
    pool_pre_ping=True,
)

# Motor separado, rol con BYPASSRLS, usado EXCLUSIVAMENTE por el lookup
# pre-auth de login (ver app/config.py, database_url_auth_lookup) — nunca
# para escrituras ni para ninguna otra query del sistema.
auth_lookup_engine = create_async_engine(settings.database_url_auth_lookup, echo=False, future=True, pool_pre_ping=True)


def _session_scope_factory(bind_engine):
    """Fábrica de context managers de sesión, ligados a UNA conexión física
    durante todo su ciclo de vida.

    BUG REAL ENCONTRADO (Fase 1 de purchasing, tests de concurrencia):
    `async_sessionmaker(bind=engine)` por defecto hace que la sesión
    devuelva su conexión física al pool en cada `commit()` — la siguiente
    query de la MISMA sesión lógica puede reengancharse a una conexión
    FÍSICA DISTINTA del pool. Como `set_config('app.current_company_id',
    ..., false)` se fija sobre una conexión física concreta, cualquier
    servicio que haga más de un `commit()` (la mayoría) podía perder su
    contexto RLS a mitad de la sesión y fallar con "new row violates
    row-level security policy" — reproducido de forma determinística
    corriendo tests en cierto orden. Es, con alta probabilidad, también la
    explicación real de los 500 intermitentes ("invalid input syntax for
    bigint: ''") vistos antes en inventory, que nunca se pudieron
    reproducir vía curl directo (una sola request HTTP normalmente no
    alcanza a agotar tantas conexiones del pool como para exponer la
    carrera) pero sí bajo tests con múltiples requests concurrentes.

    Fix: `engine.connect()` hace un checkout explícito de UNA conexión que
    se retiene durante todo el `async with` — la sesión se liga a ESA
    conexión (`AsyncSession(bind=connection)`) y nunca la libera al pool
    hasta que el bloque completo termina, sin importar cuántos commits
    ocurran adentro.
    """

    @asynccontextmanager
    async def _scope() -> AsyncIterator[AsyncSession]:
        async with bind_engine.connect() as connection:
            async with AsyncSession(bind=connection, expire_on_commit=False, autoflush=False) as session:
                yield session

    return _scope


# Se mantienen los mismos nombres (AsyncSessionLocal, AuthLookupSessionLocal)
# y la misma sintaxis de uso (`async with AsyncSessionLocal() as session:`)
# que antes con async_sessionmaker — código existente (routers, servicios,
# tests, scripts) no necesita cambiar una sola línea.
AsyncSessionLocal = _session_scope_factory(engine)
AuthLookupSessionLocal = _session_scope_factory(auth_lookup_engine)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def get_auth_lookup_db() -> AsyncSession:
    async with AuthLookupSessionLocal() as session:
        yield session
