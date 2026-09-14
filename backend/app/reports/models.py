"""
Módulo 24 — reports (spec sección 8.1), subset [core]: Dashboards
Interactivos, Reportes Cruzados, Exportación de Datos (PDF/XLSX/CSV).

[extendido] fuera de este cierre: Report Builder (consultas ad-hoc
configurables por el usuario), Programación de Reportes (envío periódico
automático — dependería de un scheduler que no existe en el proyecto).

DEDUCIBLE, no confirmado por Roberto: "Dashboards Interactivos" se modela
como UNA tabla (`Dashboard`) con los widgets embebidos en una columna
JSONB, no como una tabla `DashboardWidget` separada — spec no especifica
la granularidad, y esto alcanza para "dashboards con varios widgets" sin
el costo de un CRUD anidado completo. Cada widget referencia una métrica
del registro whitelisted en `metrics.py` (`metric_key`) — nunca SQL
arbitrario desde el cliente, ni siquiera desde el panel interno (spec 5:
las tablas de auditoría/reportes no exponen consultas libres).

Depende de "los módulos ya construidos que quiera cruzar, no de una lista
fija" (`modulos_erp_crm_v10_4.json`, nota explícita) — en este cierre,
únicamente de `sales`, `accounting` e `inventory` (los tres módulos
técnicos garantizados si `administrative` está activo). Cruzar con
`medical`/`pharmacy` queda fuera de este cierre — TODO explícito, ver
`metrics.py`.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Dashboard(Base):
    __tablename__ = "report_dashboards"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Lista de widgets: [{"widget_type": "table"|"metric", "metric_key":
    # str, "title": str}, ...] — validado contra el whitelist de
    # `metrics.py` en el service, no a nivel de columna.
    widgets: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_report_dashboards_company_name"),)
