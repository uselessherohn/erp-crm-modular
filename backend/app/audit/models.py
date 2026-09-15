"""
Módulo 25 — audit (spec sección 8.1), paquete `audit` COMPLETO
(transversal, postergable). Opera sobre la misma tabla `audit` creada en
`app/core/models.py` (`AuditLog`, spec 8.0) — no la duplica. Este
paquete solo agrega:

1. Registro de Actividad [core] y Control de Cambios (Diff) [core]: no
   requieren tabla nueva — el diff vive en la columna `AuditLog.changes`
   (JSONB, agregada retroactivamente por la migración de este módulo,
   mismo criterio que otras columnas retroactivas del proyecto). La UI
   de consulta/reportería es `AuditQueryService` (`app/audit/services.py`).
2. Retención y Depuración [core]: SÍ requiere una tabla nueva —
   `AuditRetentionPolicy`, una fila opcional por compañía con el número
   de días de retención configurado (spec: "rotación estándar, ej. 90
   días" — ese es el default cuando no hay fila).

LEÍDO CON CUIDADO (AMB-07, ver STATE.md): la tabla `audit` tiene un
trigger `BEFORE UPDATE OR DELETE` (`trg_audit_immutable`, creado en el
módulo 1, spec 8.0) que bloquea CUALQUIER `UPDATE`/`DELETE` sobre esta
tabla incondicionalmente — no distingue entre eventos operativos
generales y eventos clínicos, ni entre el rol de runtime de la API
(`erp_app`) y cualquier otro. Esto significa que la "Depuración" real
(borrado físico de filas vencidas) **no puede ejecutarse desde la capa
de aplicación** tal como está construida hoy — ni siquiera con
`erp_app`, que sí tiene el GRANT de `DELETE` pero no puede desactivar el
trigger (no es owner de la tabla). Se documenta como una tensión real
entre este módulo y el módulo 1, no se resuelve en silencio: ver
`scripts/purge_audit.py` (fuera de la API HTTP, requiere credenciales
elevadas) y la nota AMB-07 en `STATE.md` para la decisión completa.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditRetentionPolicy(Base):
    __tablename__ = "audit_retention_policies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="90")
    """Spec 8.1: "rotación estándar, ej. 90 días" — aplica solo a eventos
    operativos generales. NUNCA a eventos `medical.*` (ver
    `AuditQueryService.MEDICAL_EVENT_PREFIX` en services.py), que quedan
    protegidos por el trigger de inmutabilidad de `audit` sin importar
    si este paquete está o no licenciado (spec 8.1, nota explícita)."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("company_id", name="uq_audit_retention_policies_company"),
    )
