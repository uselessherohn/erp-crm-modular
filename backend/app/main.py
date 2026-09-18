from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.routers import auth, companies, roles, users
from app.contacts import routers as contacts_routers
from app.inventory import routers as inventory_routers
from app.purchasing import routers as purchasing_routers
from app.sales import routers as sales_routers
from app.accounting import routers as accounting_routers
from app.pipeline import routers as pipeline_routers
from app.hr import routers as hr_routers
from app.medical import routers as medical_routers
from app.notifications import routers as notifications_routers
from app.website import routers as website_routers
from app.ecommerce import routers as ecommerce_routers
from app.reports import routers as reports_routers
from app.pharmacy import routers as pharmacy_routers
from app.audit import routers as audit_routers
from app.shared.exceptions import DomainError, ValidationError as DomainValidationError

# HALLAZGO REAL (regresión QA externa, sep-2026): sin esto, el logger raíz
# de Python queda en WARNING sin ningún handler — cualquier logger.info()
# de la app se descarta en silencio, nunca llega a ningún lado (ni
# siquiera a stderr). Afectaba a notifications.LoggingEmailSender (nunca
# detectado porque tests/test_notifications_module.py inyecta un
# _FakeEmailSender de test, no ejercita el logger real) y al nuevo stub
# de password-reset de core (ver PasswordResetService._send_reset_email).
# Nivel INFO: visibilidad de estos "envíos" simulados en dev/sandbox sin
# volverse demasiado ruidoso (no DEBUG).
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

app = FastAPI(title="ERP/CRM Modular — Núcleo", version="10.4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Formato de error uniforme (spec sección 7) — todo DomainError, sea
    cual sea el módulo que lo lance, responde con la misma envoltura."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Bug real encontrado al probar contacts end-to-end: los 422 que genera
    FastAPI/Pydantic ANTES de llegar a mi código (body malformado, un
    model_validator de un schema que falla) usaban el formato nativo de
    FastAPI (`{"detail": [...]}`), no el sobre uniforme que exige la spec
    ("Un exception handler central... mapea cada una... al formato de error
    uniforme" — sección 7). Se normaliza acá para que TODO error, sin
    excepción, tenga la misma forma."""
    domain_exc = DomainValidationError("Error de validación en la solicitud", details={"errors": exc.errors()})
    return JSONResponse(
        status_code=domain_exc.status_code,
        content=jsonable_encoder(
            {
                "error": {
                    "code": domain_exc.error_code,
                    "message": domain_exc.message,
                    "details": domain_exc.details,
                }
            },
            # exc.errors() trae objetos no serializables (ej. la excepción
            # Python original dentro de ctx.error de un model_validator) —
            # bug real encontrado al probar contacts end-to-end (500 en vez
            # de 422). exclude=... no alcanza porque el problema está
            # anidado; se fuerza a texto lo que jsonable_encoder no pueda
            # convertir, en vez de dejar que json.dumps reviente.
            custom_encoder={Exception: lambda e: str(e)},
        ),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Cubre HTTPException nativas (404 de ruta inexistente, 405, etc.) con
    el mismo sobre uniforme. Bug real: registrar esto sobre
    fastapi.exceptions.HTTPException NO alcanza — Starlette lanza su propia
    clase base directamente para 404 de "sin ruta que matchee", y el
    dispatcher de excepciones busca por la clase exacta primero. Se registra
    sobre starlette.exceptions.HTTPException (la base real) para cubrir
    ambos casos."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail), "details": None}},
    )


app.include_router(companies.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(roles.router)
app.include_router(contacts_routers.router)
app.include_router(inventory_routers.router)
app.include_router(purchasing_routers.router)
app.include_router(sales_routers.router)
app.include_router(accounting_routers.router)
app.include_router(pipeline_routers.router)
app.include_router(hr_routers.router)
app.include_router(medical_routers.router)
app.include_router(medical_routers.public_router)
app.include_router(notifications_routers.router)
app.include_router(website_routers.router)
app.include_router(website_routers.public_router)
app.include_router(ecommerce_routers.router)
app.include_router(ecommerce_routers.public_router)
app.include_router(reports_routers.router)
app.include_router(pharmacy_routers.router)
app.include_router(audit_routers.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
