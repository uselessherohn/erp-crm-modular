"""
Módulo 22 — website (spec sección 8.4).

Alcance [core] construido en este cierre: CMS de Páginas Públicas,
Formularios de Captación (crean `Contact` con `is_lead=true` directo sobre
el Núcleo — spec 8.4/9, "siempre funciona, no depende de Administrativo").

Fuera de alcance [extendido], no construido aquí: SEO, Multi-idioma, Widget
de Reserva Pública de Citas (bloqueado además porque integra con Médico y
con el módulo 15 de la tabla, que sigue TODO-24 en STATE.md).

Depende solo de Núcleo (1, 2) — spec 8.4 y `modulos_erp_crm_v10_4.json`
(`depende_de: [1, 2]`, sin `inventory`). `ecommerce` (módulo 23) declara a
este módulo como dependencia en el JSON, pero a nivel de código no hay
ningún import cruzado real — ver nota de secuencia en el documento de
diseño (`diseno_modulos_22_25_erp_crm.md`, sección 1).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Page(Base):
    __tablename__ = "website_pages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    # Único por compañía, no global — dos compañías del mismo SaaS pueden
    # tener cada una su propia página "quienes-somos" (constraint compuesta
    # en la migración).
    slug: Mapped[str] = mapped_column(String(150), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # DEDUCIBLE, no confirmado por Roberto: dos estados alcanzan para el
    # alcance [core] (landing, quienes somos, términos) — sin flujo de
    # aprobación/revisión editorial. Si se necesita un tercer estado
    # (ej. "in_review"), es una extensión aditiva sobre este mismo campo,
    # no un rediseño.
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="draft")  # draft|published
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    __table_args__ = (UniqueConstraint("company_id", "slug", name="uq_website_pages_company_slug"),)


class FormSubmission(Base):
    __tablename__ = "website_form_submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("companies.id"), nullable=False, index=True)

    page_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("website_pages.id"), nullable=True)
    form_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Payload crudo del formulario — los formularios de captación no tienen
    # un esquema fijo de campos (spec 8.4 no lo especifica), así que se
    # guarda tal cual se recibió además de los campos normalizados que sí
    # alimentan el Contact (name/email/phone, ver schemas.py).
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # spec 8.4/9: todo formulario crea (o reutiliza) un Contact con
    # is_lead=true directo sobre el Núcleo — nunca queda un envío huérfano
    # sin Contact asociado.
    contact_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("contacts.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
