"""
Módulo 1 — core (spec sección 8.0).

Entidades: Company, User, Role, Permission, UserRole, RolePermission,
UserSession, Attachment, CompanyPackage, AuditLog, IdempotencyKey.

Convenciones aplicadas (spec sección 5):
- snake_case plural, todo en inglés.
- PK BigInteger.
- created_at/updated_at UTC con server_default=func.now().
- Soft delete (is_active) solo en catálogos maestros; ninguna entidad de
  este módulo es documento transaccional con flujo de estados, así que no
  aplica la variante de estados explícitos acá.
- Dinero: no aplica en este módulo (sin entidades financieras en core).
- company_id indexado en toda tabla de negocio — excepto Company (raíz del
  tenant) y Permission (catálogo global del sistema, no por tenant).
- Row-Level Security (nuevo v10.4): ENABLE + FORCE + policy tenant_isolation
  en toda tabla con company_id — se aplica en la migración, no acá (DDL puro
  de SQLAlchemy no expresa RLS; ver migración Alembic).
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PackageEnum(str, enum.Enum):
    administrative = "administrative"
    medical = "medical"
    pharmacy = "pharmacy"
    web = "web"


class PackageStatusEnum(str, enum.Enum):
    active = "active"
    suspended = "suspended"
    deactivated = "deactivated"


# ---------------------------------------------------------------------------
# Company — raíz del tenant, no lleva company_id (es el propio tenant)
# ---------------------------------------------------------------------------
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Defaults de fábrica por mercado objetivo — PYME hondureña (spec 8.0, v10.3)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, server_default="America/Tegucigalpa")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, server_default="HNL")
    locale: Mapped[str] = mapped_column(String(10), nullable=False, server_default="es-HN")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[list["User"]] = relationship(back_populates="company", lazy="selectin")
    packages: Mapped[list["CompanyPackage"]] = relationship(back_populates="company", lazy="selectin")


# ---------------------------------------------------------------------------
# RBAC — Permission es catálogo global del sistema (no company_id);
# Role sí es una tabla de negocio con company_id (permite roles a medida por
# empresa, además de los roles de fábrica que se seedean por compañía).
# ---------------------------------------------------------------------------
class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Formato modulo:accion (ej. sales:create); modulo:entidad:accion solo si
    # una entidad concreta lo justifica (spec sección 1).
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_roles_company_name"),
    )

    # Bug real encontrado en el cierre del módulo 8 (hr): esta relación
    # apuntaba a `RolePermission` (la tabla de asociación) en vez de a
    # `Permission`, así que `RoleRead.model_validate(role)` fallaba con
    # AttributeError en cualquier rol con 1+ permisos (RolePermission no
    # tiene los campos `id`/`code`/`description` que espera
    # `PermissionRead`) — nunca se disparó antes porque ningún test ni uso
    # manual había creado un rol con permission_ids no vacío. `viewonly`
    # porque `RoleService.create_role` gestiona la tabla de asociación
    # insertando `RolePermission` directamente, no a través de esta
    # colección.
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="role_permissions", lazy="selectin", viewonly=True
    )


class RolePermission(Base):
    """Tabla de asociación — sin company_id propio: el aislamiento de tenant
    se hereda de `Role` (que sí tiene RLS). No es objeto de RLS directo
    (spec 5: RLS aplica a tablas de negocio *con* company_id)."""
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("permissions.id"), primary_key=True)
    permission: Mapped["Permission"] = relationship(lazy="selectin")


class UserRole(Base):
    """Tabla de asociación — mismo criterio que RolePermission: sin
    company_id propio, hereda aislamiento de `User`/`Role`."""
    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("roles.id"), primary_key=True)

    role: Mapped["Role"] = relationship(lazy="selectin")


# ---------------------------------------------------------------------------
# User — tabla de negocio central, company_id obligatorio
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    locale: Mapped[str | None] = mapped_column(String(10), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # Autenticación y seguridad [core]: bloqueo por intentos
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Sucursal activa (spec 5, get_current_warehouse_id). FK real agregada
    # en el módulo 3 (inventory, migración ccd8a2f53a05) — actualizado acá
    # también en el modelo ORM (antes solo existía como DDL crudo vía
    # op.create_foreign_key, sin reflejarse en Base.metadata; Alembic
    # autogenerate lo detectaba como "FK no declarada, a eliminar" al
    # generar la siguiente migración — corregido en el mismo cierre donde
    # se encontró, ver STATE.md).
    active_warehouse_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    # AMBIGUO — Fase 2 del Módulo 1: la spec no dice cómo el cliente indica
    # su company_id antes de autenticarse. Default DEDUCIBLE adoptado: email
    # único globalmente (no solo por compañía) — cambiado desde
    # uq_users_company_email en la migración 131bc488d5b7. Ver STATE.md.
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
    )

    company: Mapped["Company"] = relationship(back_populates="users", lazy="selectin")
    roles: Mapped[list["UserRole"]] = relationship(lazy="selectin")


class UserSession(Base):
    """Sesiones activas / refresh tokens (Autenticación y Seguridad [core])."""
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)

    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Adjuntos — capacidad genérica desde core (spec sección 4)
# ---------------------------------------------------------------------------
class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)

    uploaded_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_attachments_entity", "entity_type", "entity_id"),
    )


# ---------------------------------------------------------------------------
# Registro de paquetes y feature flags (spec sección 2.4)
# ---------------------------------------------------------------------------
class CompanyPackage(Base):
    __tablename__ = "company_packages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    package: Mapped[PackageEnum] = mapped_column(
        String(20), nullable=False
    )  # enum aplicado a nivel de app + CHECK constraint en migración
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # v10.3: reemplaza al booleano viejo (el que combinaba "solo
    # dependencias mínimas" en un único flag sí/no — ver changelog_decisiones
    # para el nombre original del campo retirado).
    # None/lista vacía = compra directa del Administrativo completo, no arrastre.
    minimal_modules: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[PackageStatusEnum] = mapped_column(String(20), nullable=False, server_default="active")
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)

    company: Mapped["Company"] = relationship(back_populates="packages", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("company_id", "package", name="uq_company_packages_company_package"),
    )


# ---------------------------------------------------------------------------
# Audit mínimo [core] — spec 8.0, trigger de inmutabilidad en la migración
# ---------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    event: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Idempotencia (spec sección 7, TTL por dominio corregido en v10.4)
# ---------------------------------------------------------------------------
class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Solo se escribe ante 2xx o 4xx definitivo — nunca ante 5xx (v10.4).
    response_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    response_status_code: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "company_id", "idempotency_key", "endpoint",
            name="uq_idempotency_keys_company_key_endpoint",
        ),
    )


# ---------------------------------------------------------------------------
# Numeración atómica de documentos (spec sección 5/Concurrencia):
# "nunca MAX(number)+1 en la app — secuencia de PostgreSQL por
# empresa+tipo, o SELECT ... FOR UPDATE sobre tabla de contadores."
# Se elige la tabla de contadores (no una secuencia de Postgres por
# empresa+tipo) porque las secuencias son objetos DDL — crear una por cada
# combinación empresa×tipo_de_documento requeriría DDL dinámico en
# runtime, frágil y difícil de versionar en Alembic. Una tabla de filas es
# el mismo patrón de concurrencia (SELECT FOR UPDATE) sin ese problema.
# ---------------------------------------------------------------------------
class DocumentCounter(Base):
    __tablename__ = "document_counters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    current_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        UniqueConstraint("company_id", "doc_type", "year", name="uq_document_counters_company_type_year"),
    )
