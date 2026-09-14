from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services import AuditService
from app.reports import models, schemas
from app.reports.metrics import METRICS
from app.shared.exceptions import NotFoundError, ValidationError


class MetricService:
    @staticmethod
    def list_metrics() -> list[schemas.MetricInfo]:
        return [schemas.MetricInfo(key=m.key, label=m.label, columns=m.columns) for m in METRICS.values()]

    @staticmethod
    async def run(db: AsyncSession, *, company_id: int, metric_key: str, date_from: date, date_to: date) -> schemas.MetricDataResult:
        definition = METRICS.get(metric_key)
        if definition is None:
            raise NotFoundError(f"Métrica '{metric_key}' no existe — ver GET /reports/metrics para las disponibles")
        rows = await definition.query(db, company_id, date_from, date_to)
        return schemas.MetricDataResult(key=metric_key, columns=definition.columns, rows=rows)


class DashboardService:
    @staticmethod
    def _validate_widgets(widgets: list[schemas.DashboardWidget]) -> None:
        for widget in widgets:
            if widget.metric_key not in METRICS:
                raise ValidationError(f"El widget referencia la métrica '{widget.metric_key}', que no existe")

    @staticmethod
    async def create(db: AsyncSession, *, company_id: int, payload: schemas.DashboardCreate, owner_user_id: int | None) -> models.Dashboard:
        DashboardService._validate_widgets(payload.widgets)
        dashboard = models.Dashboard(
            company_id=company_id, name=payload.name, owner_user_id=owner_user_id,
            widgets=[w.model_dump() for w in payload.widgets],
        )
        db.add(dashboard)
        await db.flush()
        await AuditService.log_event(
            db, company_id=company_id, event="reports.dashboard.created", entity_type="report_dashboard",
            entity_id=dashboard.id, user_id=owner_user_id,
        )
        await db.commit()
        await db.refresh(dashboard)
        return dashboard

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, dashboard_id: int) -> models.Dashboard:
        result = await db.execute(
            select(models.Dashboard).where(models.Dashboard.company_id == company_id, models.Dashboard.id == dashboard_id)
        )
        dashboard = result.scalar_one_or_none()
        if dashboard is None:
            raise NotFoundError(f"Dashboard {dashboard_id} no encontrado")
        return dashboard

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Dashboard]:
        result = await db.execute(select(models.Dashboard).where(models.Dashboard.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def update(
        db: AsyncSession, *, company_id: int, dashboard_id: int, payload: schemas.DashboardUpdate, actor_id: int | None
    ) -> models.Dashboard:
        dashboard = await DashboardService.get(db, company_id=company_id, dashboard_id=dashboard_id)
        if payload.name is not None:
            dashboard.name = payload.name
        if payload.widgets is not None:
            DashboardService._validate_widgets(payload.widgets)
            dashboard.widgets = [w.model_dump() for w in payload.widgets]
        await db.flush()
        await AuditService.log_event(
            db, company_id=company_id, event="reports.dashboard.updated", entity_type="report_dashboard",
            entity_id=dashboard.id, user_id=actor_id,
        )
        await db.commit()
        await db.refresh(dashboard)
        return dashboard

    @staticmethod
    async def delete(db: AsyncSession, *, company_id: int, dashboard_id: int, actor_id: int | None) -> None:
        dashboard = await DashboardService.get(db, company_id=company_id, dashboard_id=dashboard_id)
        await db.delete(dashboard)
        await AuditService.log_event(
            db, company_id=company_id, event="reports.dashboard.deleted", entity_type="report_dashboard",
            entity_id=dashboard_id, user_id=actor_id,
        )
        await db.commit()


class ExportService:
    """DEDUCIBLE: los tres formatos generan el archivo completo en memoria
    (`io.BytesIO`) antes de responder — sin streaming — porque las
    métricas de este cierre están acotadas (`LIMIT 50` en la más grande,
    ver `metrics.py`). Si algún día una métrica puede devolver miles de
    filas, esto necesita revisarse (streaming real o paginación) — no es
    un problema hoy, pero tampoco escala indefinidamente."""

    @staticmethod
    def to_csv(*, columns: list[str], rows: list[dict]) -> bytes:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})
        return buffer.getvalue().encode("utf-8-sig")  # BOM: Excel abre UTF-8 con tildes sin corromper

    @staticmethod
    def to_xlsx(*, title: str, columns: list[str], rows: list[dict]) -> bytes:
        # openpyxl no está en requirements.txt previo a este cierre — se
        # agregó como dependencia nueva (ver STATE.md). Import perezoso
        # para que el resto del módulo funcione igual si alguien corre
        # solo los tests de CSV sin haber instalado esto todavía.
        from openpyxl import Workbook
        from openpyxl.styles import Font

        wb = Workbook()
        ws = wb.active
        ws.title = title[:31] or "Reporte"  # límite real de Excel para nombres de hoja
        ws.append(columns)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append([row.get(col, "") for col in columns])

        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def to_pdf(*, title: str, columns: list[str], rows: list[dict]) -> bytes:
        # reportlab tampoco estaba en requirements.txt — mismo criterio de
        # import perezoso que to_xlsx.
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = [Paragraph(title, styles["Title"])]

        table_data = [columns] + [[str(row.get(col, "")) for col in columns] for row in rows]
        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(table)
        doc.build(elements)
        return buffer.getvalue()
