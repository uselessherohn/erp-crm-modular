"""
Servicios de `ecommerce`. `company_id` siempre inyectado desde el router
(nunca leído del payload del cliente) — mismo criterio anti-IDOR que el
resto del proyecto. En las rutas públicas, `company_id` viene de la URL
(ver `dependencies.py` y AMB-03 en STATE.md).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting import schemas as accounting_schemas
from app.accounting.services import InvoiceService
from app.contacts.models import Contact
from app.core.services import AuditService
from app.ecommerce import models, schemas
from app.inventory.models import Product
from app.inventory.services import ProductService, WarehouseService
from app.sales import schemas as sales_schemas
from app.sales.models import PriceList
from app.sales.services import PriceListService, SalesOrderService
from app.shared.exceptions import ConflictError, NotFoundError, ValidationError


class EcommerceSettingsService:
    @staticmethod
    async def get_or_none(db: AsyncSession, *, company_id: int) -> models.EcommerceSettings | None:
        result = await db.execute(
            select(models.EcommerceSettings).where(models.EcommerceSettings.company_id == company_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_raise(db: AsyncSession, *, company_id: int) -> models.EcommerceSettings:
        settings = await EcommerceSettingsService.get_or_none(db, company_id=company_id)
        if settings is None:
            raise ValidationError(
                "Ecommerce no tiene configuración inicial (almacén/lista de precios) — "
                "un administrador debe crearla primero en el panel"
            )
        return settings

    @staticmethod
    async def create(db: AsyncSession, *, company_id: int) -> models.EcommerceSettings:
        existing = await EcommerceSettingsService.get_or_none(db, company_id=company_id)
        if existing is not None:
            raise ValidationError("Ya existe configuración de ecommerce para esta compañía — usá 'actualizar'")

        settings = models.EcommerceSettings(company_id=company_id, webhook_secret=secrets.token_hex(32))
        db.add(settings)
        await db.flush()
        await AuditService.log_event(
            db, company_id=company_id, event="ecommerce.settings.created", entity_type="ecommerce_settings",
            entity_id=settings.id, user_id=None,
        )
        await db.commit()
        await db.refresh(settings)
        return settings

    @staticmethod
    async def update(
        db: AsyncSession, *, company_id: int, payload: schemas.EcommerceSettingsUpdate
    ) -> models.EcommerceSettings:
        settings = await EcommerceSettingsService.get_or_raise(db, company_id=company_id)

        if payload.default_warehouse_id is not None:
            await WarehouseService.get(db, company_id=company_id, warehouse_id=payload.default_warehouse_id)
            settings.default_warehouse_id = payload.default_warehouse_id
        if payload.default_price_list_id is not None:
            price_list = await db.get(PriceList, payload.default_price_list_id)
            if price_list is None or price_list.company_id != company_id:
                raise NotFoundError(f"Lista de precios {payload.default_price_list_id} no encontrada")
            settings.default_price_list_id = payload.default_price_list_id

        await db.flush()
        await AuditService.log_event(
            db, company_id=company_id, event="ecommerce.settings.updated", entity_type="ecommerce_settings",
            entity_id=settings.id, user_id=None,
        )
        await db.commit()
        await db.refresh(settings)
        return settings

    @staticmethod
    async def resolve_price_list_id(db: AsyncSession, *, company_id: int, settings: models.EcommerceSettings) -> int:
        if settings.default_price_list_id is not None:
            return settings.default_price_list_id
        result = await db.execute(
            select(PriceList).where(PriceList.company_id == company_id, PriceList.is_default.is_(True))
        )
        default_list = result.scalar_one_or_none()
        if default_list is None:
            raise ValidationError(
                "Ecommerce no tiene lista de precios configurada ni existe una lista marcada is_default=true"
            )
        return default_list.id


class CatalogService:
    @staticmethod
    async def list_catalog(db: AsyncSession, *, company_id: int) -> list[schemas.CatalogItem]:
        """Solo productos activos que tengan precio en la lista de precios
        resuelta (ver `EcommerceSettingsService.resolve_price_list_id`) —
        un producto sin entrada en esa lista simplemente no aparece en el
        catálogo público, no es un error (DEDUCIBLE, no confirmado por
        Roberto)."""
        settings = await EcommerceSettingsService.get_or_raise(db, company_id=company_id)
        price_list_id = await EcommerceSettingsService.resolve_price_list_id(db, company_id=company_id, settings=settings)

        result = await db.execute(select(Product).where(Product.company_id == company_id, Product.is_active.is_(True)))
        products = list(result.scalars().all())

        items: list[schemas.CatalogItem] = []
        for product in products:
            try:
                unit_price = await PriceListService.get_price(
                    db, company_id=company_id, price_list_id=price_list_id, product_id=product.id, quantity=Decimal(1)
                )
            except NotFoundError:
                continue
            items.append(schemas.CatalogItem(product_id=product.id, sku=product.sku, name=product.name, unit_price=unit_price))
        return items


class CartService:
    @staticmethod
    async def _serialize(db: AsyncSession, cart: models.Cart) -> schemas.CartRead:
        result = await db.execute(select(models.CartItem).where(models.CartItem.cart_id == cart.id))
        items = list(result.scalars().all())
        return schemas.CartRead(
            id=cart.id,
            status=cart.status,
            currency_code=cart.currency_code,
            sales_order_id=cart.sales_order_id,
            items=[schemas.CartItemRead.model_validate(i) for i in items],
        )

    @staticmethod
    async def create_cart(db: AsyncSession, *, company_id: int) -> tuple[models.Cart, str]:
        token = secrets.token_urlsafe(32)
        cart = models.Cart(company_id=company_id, session_token=token)
        db.add(cart)
        await db.commit()
        await db.refresh(cart)
        return cart, token

    @staticmethod
    async def _get_cart_row(
        db: AsyncSession, *, company_id: int, cart_id: int, session_token: str, for_update: bool = False
    ) -> models.Cart:
        stmt = select(models.Cart).where(models.Cart.company_id == company_id, models.Cart.id == cart_id)
        if for_update:
            # BUG REAL encontrado por scripts/qa_suite/11_concurrency_load.py
            # (escenario 2, concurrencia real): sin este lock, N checkouts
            # concurrentes del MISMO carrito pasaban TODOS el chequeo
            # `cart.status != "open"` (ninguno había comprometido su cambio
            # de estado todavía) y cada uno ejecutaba el flujo COMPLETO de
            # creación de orden — confirmado empíricamente: 20 checkouts
            # concurrentes con el mismo carrito crearon 15 SalesOrder reales
            # distintos (con su propia reserva de stock, factura y asientos
            # contables cada uno), pese a que la respuesta HTTP de las 20
            # llamadas mostraba, gracias a la capa de idempotencia, el MISMO
            # `sales_order_id` — la idempotencia estaba ocultando el
            # problema en vez de prevenirlo: el trabajo duplicado real ya
            # había ocurrido en la base antes de que la respuesta se
            # cacheara. `with_for_update()` serializa las N transacciones en
            # esta lectura — la primera en llegar mantiene el lock hasta su
            # commit (que dejó `status="checked_out"`), y cada una de las
            # siguientes, al desbloquear, ve el estado ya actualizado y
            # sale por `ConflictError` antes de crear nada.
            stmt = stmt.with_for_update()
        result = await db.execute(stmt)
        cart = result.scalar_one_or_none()
        # Mensaje deliberadamente genérico (no distingue "no existe" de
        # "token incorrecto") — anti-enumeración del mismo tipo que el
        # resto del proyecto aplica a login.
        if cart is None or not hmac.compare_digest(cart.session_token, session_token):
            raise NotFoundError("Carrito no encontrado o token inválido")
        return cart

    @staticmethod
    async def get_cart(db: AsyncSession, *, company_id: int, cart_id: int, session_token: str) -> schemas.CartRead:
        cart = await CartService._get_cart_row(db, company_id=company_id, cart_id=cart_id, session_token=session_token)
        return await CartService._serialize(db, cart)

    @staticmethod
    async def add_item(
        db: AsyncSession, *, company_id: int, cart_id: int, session_token: str, payload: schemas.AddCartItem
    ) -> schemas.CartRead:
        cart = await CartService._get_cart_row(db, company_id=company_id, cart_id=cart_id, session_token=session_token)
        if cart.status != "open":
            raise ConflictError(f"El carrito {cart_id} ya no admite cambios (estado: '{cart.status}')")

        product = await ProductService.get(db, company_id=company_id, product_id=payload.product_id)
        if not product.is_active:
            raise ValidationError(f"El producto '{product.name}' no está activo")

        settings = await EcommerceSettingsService.get_or_raise(db, company_id=company_id)
        price_list_id = await EcommerceSettingsService.resolve_price_list_id(db, company_id=company_id, settings=settings)
        unit_price = await PriceListService.get_price(
            db, company_id=company_id, price_list_id=price_list_id, product_id=product.id, quantity=payload.quantity
        )

        result = await db.execute(
            select(models.CartItem).where(models.CartItem.cart_id == cart.id, models.CartItem.product_id == product.id)
        )
        existing_item = result.scalar_one_or_none()
        if existing_item is not None:
            existing_item.quantity += payload.quantity
            existing_item.unit_price_snapshot = unit_price
        else:
            db.add(
                models.CartItem(
                    company_id=company_id, cart_id=cart.id, product_id=product.id,
                    quantity=payload.quantity, unit_price_snapshot=unit_price,
                )
            )

        await db.commit()
        await db.refresh(cart)
        return await CartService._serialize(db, cart)


class CheckoutService:
    @staticmethod
    async def _find_or_create_customer_contact(db: AsyncSession, *, company_id: int, name: str, email: str, phone: str | None) -> Contact:
        """Mismo criterio de reutilización por email que
        `website.FormSubmissionService` (módulo 22, DED-46) — reutiliza un
        `Contact` existente marcándolo `is_customer=true` si no lo era, en
        vez de duplicar.

        BUG REAL encontrado por scripts/qa_suite/11_concurrency_load.py
        (escenario 2, concurrencia real): esto era un SELECT-luego-INSERT
        (check-then-act) sin ningún lock — dos checkouts concurrentes con
        el MISMO email (ej. el mismo cliente haciendo doble clic, o el
        propio reintento del cliente ante un timeout) podían ver ambos "no
        existe todavía" y competir por el mismo INSERT. El perdedor de esa
        carrera contra el índice único parcial `ux_contacts_company_email`
        propagaba un `IntegrityError` crudo — ni siquiera un `DomainError`,
        así que ni `IdempotencyService.run_command` lo capturaba — como un
        500 real (confirmado: dominaba los 500 observados en el escenario
        2, más que la carrera de idempotencia en sí). Mismo patrón UPSERT
        que `StockService._get_or_create_lot` — un duplicado concurrente
        simplemente no inserta (`ON CONFLICT DO NOTHING` sobre el mismo
        índice parcial `(company_id, email) WHERE email IS NOT NULL`) y el
        SELECT posterior trae la fila real, sea la que insertamos nosotros
        o la que ganó la otra transacción."""
        stmt = (
            pg_insert(Contact)
            .values(company_id=company_id, name=name, email=email, phone=phone, is_customer=True)
            .on_conflict_do_nothing(index_elements=["company_id", "email"], index_where=text("email IS NOT NULL"))
        )
        await db.execute(stmt)
        result = await db.execute(select(Contact).where(Contact.company_id == company_id, Contact.email == email))
        contact = result.scalar_one()
        if not contact.is_customer:
            contact.is_customer = True
            await db.flush()
        return contact

    @staticmethod
    async def checkout(
        db: AsyncSession, *, company_id: int, cart_id: int, session_token: str, payload: schemas.CheckoutRequest
    ) -> schemas.CheckoutResult:
        cart = await CartService._get_cart_row(
            db, company_id=company_id, cart_id=cart_id, session_token=session_token, for_update=True
        )
        if cart.status != "open":
            raise ConflictError(f"El carrito {cart_id} ya fue procesado (estado: '{cart.status}')")

        result = await db.execute(select(models.CartItem).where(models.CartItem.cart_id == cart.id))
        cart_items = list(result.scalars().all())
        if not cart_items:
            raise ValidationError("El carrito está vacío")

        settings = await EcommerceSettingsService.get_or_raise(db, company_id=company_id)
        if settings.default_warehouse_id is None:
            raise ValidationError("Ecommerce no tiene almacén configurado — un administrador debe configurarlo primero")
        price_list_id = await EcommerceSettingsService.resolve_price_list_id(db, company_id=company_id, settings=settings)

        contact = await CheckoutService._find_or_create_customer_contact(
            db, company_id=company_id, name=payload.name, email=payload.email, phone=payload.phone
        )

        # Precio re-verificado al checkout, no copiado de
        # `unit_price_snapshot` (ver comentario en models.Cart) — un
        # carrito puede quedar abierto un buen rato antes de pagarse.
        lines = []
        for item in cart_items:
            fresh_price = await PriceListService.get_price(
                db, company_id=company_id, price_list_id=price_list_id, product_id=item.product_id, quantity=item.quantity
            )
            lines.append(sales_schemas.SalesOrderLineCreate(product_id=item.product_id, quantity=item.quantity, unit_price=fresh_price))

        so_payload = sales_schemas.SalesOrderCreate(
            customer_id=contact.id, warehouse_id=settings.default_warehouse_id,
            price_list_id=price_list_id, currency_code=cart.currency_code, lines=lines,
        )
        order = await SalesOrderService.create_draft(
            db, company_id=company_id, payload=so_payload, created_by=None, _skip_commit=True
        )

        cart.status = "checked_out"
        cart.contact_id = contact.id
        cart.sales_order_id = order.id
        await AuditService.log_event(
            db, company_id=company_id, event="ecommerce.checkout", entity_type="ecommerce_cart",
            entity_id=cart.id, user_id=None,
        )
        await db.commit()
        await db.refresh(order)

        return schemas.CheckoutResult(
            sales_order_id=order.id, sales_order_number=order.number, status=order.status, total_lines=len(order.lines)
        )


class WebhookService:
    @staticmethod
    def verify_signature(*, webhook_secret: str, raw_body: bytes, signature: str | None) -> bool:
        if not signature:
            return False
        expected = hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    async def handle_payment_event(
        db: AsyncSession, *, company_id: int, gateway: str, raw_body: bytes, payload: dict, signature: str | None
    ) -> dict:
        """Payload esperado (contrato PROPIO simplificado — no se integró
        ningún SDK de pasarela real, ver `EcommerceSettings.webhook_secret`):
        `{"event_id": str, "sales_order_id": int, "status": "paid"}`. Un
        adaptador real (Stripe/PayPal/MercadoPago) traduciría el webhook
        nativo de cada pasarela a esta forma antes de llegar acá — TODO
        explícito, fuera de alcance de este cierre."""
        settings = await EcommerceSettingsService.get_or_raise(db, company_id=company_id)
        if not WebhookService.verify_signature(webhook_secret=settings.webhook_secret, raw_body=raw_body, signature=signature):
            raise ValidationError("Firma de webhook inválida o ausente")

        event_id = payload.get("event_id")
        sales_order_id = payload.get("sales_order_id")
        status = payload.get("status")
        if not event_id or not sales_order_id or not status:
            raise ValidationError("Payload de webhook incompleto — se esperan 'event_id', 'sales_order_id' y 'status'")

        existing = await db.execute(
            select(models.PaymentGatewayEvent).where(
                models.PaymentGatewayEvent.company_id == company_id,
                models.PaymentGatewayEvent.gateway == gateway,
                models.PaymentGatewayEvent.event_id == str(event_id),
            )
        )
        if existing.scalar_one_or_none() is not None:
            # Ya procesado — responde 200 sin reprocesar (idempotencia por
            # event_id, spec 8.4).
            return {"status": "already_processed"}

        # LIMITACIÓN CONOCIDA (documentada, no un bug silencioso): los
        # pasos siguientes (confirmar orden, facturar, contabilizar) NO son
        # atómicos entre sí junto con el registro de este evento —
        # `SalesOrderService.confirm`/`InvoiceService.create_draft`/`.post`
        # hacen su propio commit interno, y no exponen `_skip_commit` para
        # componer una sola transacción como sí permite
        # `SalesOrderService.create_draft`. Si el proceso se cae entre
        # confirmar la orden y registrar `PaymentGatewayEvent`, un reintento
        # legítimo de la pasarela chocaría con `ConflictError` al intentar
        # confirmar una orden que ya no está en 'draft'. TODO explícito: dar
        # a esos servicios un modo `_skip_commit` para poder envolver todo
        # esto en una sola transacción, igual que se hizo en `checkout()`.
        if status == "paid":
            order = await SalesOrderService.confirm(db, company_id=company_id, order_id=int(sales_order_id), actor_id=None)

            invoice_lines = []
            for line in order.lines:
                product = await ProductService.get(db, company_id=company_id, product_id=line.product_id)
                invoice_lines.append(
                    accounting_schemas.InvoiceLineCreate(description=product.name, quantity=line.quantity, unit_price=line.unit_price)
                )
            invoice_payload = accounting_schemas.InvoiceCreate(
                direction=accounting_schemas.DirectionEnum.sale,
                contact_id=order.customer_id,
                currency_code=order.currency_code,
                issue_date=date.today(),
                source_document_type="sales_order",
                source_document_id=order.id,
                lines=invoice_lines,
            )
            invoice = await InvoiceService.create_draft(db, company_id=company_id, payload=invoice_payload, created_by=None)
            await InvoiceService.post(db, company_id=company_id, invoice_id=invoice.id, actor_id=None)

        db.add(
            models.PaymentGatewayEvent(
                company_id=company_id, gateway=gateway, event_id=str(event_id), payload_raw=payload,
                sales_order_id=int(sales_order_id), processed_at=datetime.now(UTC),
            )
        )
        await AuditService.log_event(
            db, company_id=company_id, event="ecommerce.payment_webhook_processed", entity_type="ecommerce_payment_event",
            entity_id=int(sales_order_id), user_id=None,
        )
        await db.commit()
        return {"status": "processed"}
