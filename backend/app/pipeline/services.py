"""
Servicios de pipeline — Fase 2.

`StageService` es CRUD simple (sin máquina de estados propia). `Opportunity`
tiene el único comportamiento no trivial del módulo: movimiento libre entre
etapas no terminales (kanban), y comandos explícitos `close_won`/`close_lost`
para alcanzar una etapa terminal (DED-18). `ActivityService` es CRUD simple
con un comando `complete` para marcar `completed_at`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contacts.services import ContactService
from app.core.services import AuditService
from app.pipeline import models, schemas
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


class StageService:
    @staticmethod
    async def create(db: AsyncSession, *, company_id: int, payload: schemas.StageCreate) -> models.Stage:
        if payload.is_won and payload.is_lost:
            raise ValidationError("Una etapa no puede ser 'ganada' y 'perdida' a la vez")
        stage = models.Stage(
            company_id=company_id,
            name=payload.name,
            sort_order=payload.sort_order,
            is_won=payload.is_won,
            is_lost=payload.is_lost,
        )
        db.add(stage)
        await db.commit()
        await db.refresh(stage)
        return stage

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, stage_id: int) -> models.Stage:
        result = await db.execute(
            select(models.Stage).where(models.Stage.company_id == company_id, models.Stage.id == stage_id)
        )
        stage = result.scalar_one_or_none()
        if stage is None:
            raise NotFoundError(f"Etapa {stage_id} no encontrada")
        return stage

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Stage]:
        result = await db.execute(
            select(models.Stage).where(models.Stage.company_id == company_id).order_by(models.Stage.sort_order)
        )
        return list(result.scalars().all())


class OpportunityService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.OpportunityCreate, created_by: int | None
    ) -> models.Opportunity:
        await ContactService.get_contact(db, company_id=company_id, contact_id=payload.contact_id)
        stage = await StageService.get(db, company_id=company_id, stage_id=payload.stage_id)
        if stage.is_won or stage.is_lost:
            raise ValidationError("No se puede crear una oportunidad directamente en una etapa terminal")

        opportunity = models.Opportunity(
            company_id=company_id,
            contact_id=payload.contact_id,
            stage_id=payload.stage_id,
            owner_user_id=payload.owner_user_id,
            name=payload.name,
            amount=payload.amount,
            currency_code=payload.currency_code,
            expected_close_date=payload.expected_close_date,
            created_by=created_by,
        )
        db.add(opportunity)
        await db.flush()
        await AuditService.log_event(
            db, company_id=company_id, event="opportunity.created", entity_type="opportunity",
            entity_id=opportunity.id, user_id=created_by,
        )
        await db.commit()
        await db.refresh(opportunity)
        return opportunity

    @staticmethod
    async def _get_locked(db: AsyncSession, *, company_id: int, opportunity_id: int) -> models.Opportunity:
        result = await db.execute(
            select(models.Opportunity)
            .where(models.Opportunity.company_id == company_id, models.Opportunity.id == opportunity_id)
            .with_for_update()
        )
        opportunity = result.scalar_one_or_none()
        if opportunity is None:
            raise NotFoundError(f"Oportunidad {opportunity_id} no encontrada")
        return opportunity

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, opportunity_id: int) -> models.Opportunity:
        result = await db.execute(
            select(models.Opportunity).where(
                models.Opportunity.company_id == company_id, models.Opportunity.id == opportunity_id
            )
        )
        opportunity = result.scalar_one_or_none()
        if opportunity is None:
            raise NotFoundError(f"Oportunidad {opportunity_id} no encontrada")
        return opportunity

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Opportunity]:
        result = await db.execute(select(models.Opportunity).where(models.Opportunity.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def move_stage(
        db: AsyncSession, *, company_id: int, opportunity_id: int, payload: schemas.OpportunityMoveStage,
        actor_id: int | None,
    ) -> models.Opportunity:
        """Movimiento libre de kanban entre etapas NO terminales (DED-18).
        Alcanzar una etapa terminal requiere los comandos explícitos
        `close_won`/`close_lost`, no este endpoint genérico."""
        opportunity = await OpportunityService._get_locked(db, company_id=company_id, opportunity_id=opportunity_id)
        if opportunity.status != "open":
            raise ConflictError(
                f"No se puede mover una oportunidad '{opportunity.status}' — reabrila primero"
            )
        target_stage = await StageService.get(db, company_id=company_id, stage_id=payload.stage_id)
        if target_stage.is_won or target_stage.is_lost:
            raise ValidationError(
                "No se puede mover directamente a una etapa terminal — usá cerrar ganada/perdida"
            )
        opportunity.stage_id = payload.stage_id
        opportunity.version += 1
        await db.commit()
        await db.refresh(opportunity)
        return opportunity

    @staticmethod
    async def close_won(
        db: AsyncSession, *, company_id: int, opportunity_id: int, actor_id: int | None
    ) -> models.Opportunity:
        opportunity = await OpportunityService._get_locked(db, company_id=company_id, opportunity_id=opportunity_id)
        if opportunity.status != "open":
            raise ConflictError(f"Solo se puede cerrar como ganada una oportunidad 'open' (actual: '{opportunity.status}')")
        won_stage = await OpportunityService._get_terminal_stage(db, company_id=company_id, is_won=True)
        opportunity.stage_id = won_stage.id
        opportunity.status = "won"
        opportunity.closed_at = datetime.now(timezone.utc)
        opportunity.version += 1
        await AuditService.log_event(
            db, company_id=company_id, event="opportunity.won", entity_type="opportunity",
            entity_id=opportunity.id, user_id=actor_id,
        )
        await db.commit()
        await db.refresh(opportunity)
        return opportunity

    @staticmethod
    async def close_lost(
        db: AsyncSession, *, company_id: int, opportunity_id: int, payload: schemas.OpportunityCloseLost,
        actor_id: int | None,
    ) -> models.Opportunity:
        opportunity = await OpportunityService._get_locked(db, company_id=company_id, opportunity_id=opportunity_id)
        if opportunity.status != "open":
            raise ConflictError(f"Solo se puede cerrar como perdida una oportunidad 'open' (actual: '{opportunity.status}')")
        lost_stage = await OpportunityService._get_terminal_stage(db, company_id=company_id, is_won=False)
        opportunity.stage_id = lost_stage.id
        opportunity.status = "lost"
        opportunity.closed_at = datetime.now(timezone.utc)
        opportunity.lost_reason = payload.lost_reason
        opportunity.version += 1
        await AuditService.log_event(
            db, company_id=company_id, event="opportunity.lost", entity_type="opportunity",
            entity_id=opportunity.id, user_id=actor_id,
        )
        await db.commit()
        await db.refresh(opportunity)
        return opportunity

    @staticmethod
    async def reopen(db: AsyncSession, *, company_id: int, opportunity_id: int, actor_id: int | None) -> models.Opportunity:
        opportunity = await OpportunityService._get_locked(db, company_id=company_id, opportunity_id=opportunity_id)
        if opportunity.status == "open":
            raise ConflictError("La oportunidad ya está abierta")
        # Reabrir no reconstruye la etapa anterior (no se registra en el
        # modelo mínimo) — vuelve a la primera etapa no terminal configurada,
        # que el usuario puede mover de inmediato si no es la deseada.
        stages = await StageService.list(db, company_id=company_id)
        first_open_stage = next((s for s in stages if not s.is_won and not s.is_lost), None)
        if first_open_stage is None:
            raise ValidationError("No hay ninguna etapa no terminal configurada para reabrir la oportunidad")
        opportunity.stage_id = first_open_stage.id
        opportunity.status = "open"
        opportunity.closed_at = None
        opportunity.lost_reason = None
        opportunity.version += 1
        await db.commit()
        await db.refresh(opportunity)
        return opportunity

    @staticmethod
    async def _get_terminal_stage(db: AsyncSession, *, company_id: int, is_won: bool) -> models.Stage:
        stages = await StageService.list(db, company_id=company_id)
        matches = [s for s in stages if (s.is_won if is_won else s.is_lost)]
        if not matches:
            label = "ganada" if is_won else "perdida"
            raise ValidationError(
                f"No hay ninguna etapa marcada como '{label}' configurada — creá una antes de cerrar oportunidades"
            )
        return matches[0]


class ActivityService:
    @staticmethod
    async def create(
        db: AsyncSession, *, company_id: int, payload: schemas.ActivityCreate, created_by: int | None
    ) -> models.Activity:
        await ContactService.get_contact(db, company_id=company_id, contact_id=payload.contact_id)
        if payload.opportunity_id is not None:
            opportunity = await OpportunityService.get(db, company_id=company_id, opportunity_id=payload.opportunity_id)
            if opportunity.contact_id != payload.contact_id:
                raise ValidationError("La oportunidad referenciada pertenece a otro contacto")

        activity = models.Activity(
            company_id=company_id,
            contact_id=payload.contact_id,
            opportunity_id=payload.opportunity_id,
            activity_type=payload.activity_type.value,
            subject=payload.subject,
            notes=payload.notes,
            due_date=payload.due_date,
            created_by=created_by,
        )
        db.add(activity)
        await db.commit()
        await db.refresh(activity)
        return activity

    @staticmethod
    async def get(db: AsyncSession, *, company_id: int, activity_id: int) -> models.Activity:
        result = await db.execute(
            select(models.Activity).where(
                models.Activity.company_id == company_id, models.Activity.id == activity_id
            )
        )
        activity = result.scalar_one_or_none()
        if activity is None:
            raise NotFoundError(f"Actividad {activity_id} no encontrada")
        return activity

    @staticmethod
    async def list(db: AsyncSession, *, company_id: int) -> list[models.Activity]:
        result = await db.execute(select(models.Activity).where(models.Activity.company_id == company_id))
        return list(result.scalars().all())

    @staticmethod
    async def complete(db: AsyncSession, *, company_id: int, activity_id: int) -> models.Activity:
        activity = await ActivityService.get(db, company_id=company_id, activity_id=activity_id)
        if activity.completed_at is not None:
            raise ConflictError("La actividad ya está completada")
        activity.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(activity)
        return activity
