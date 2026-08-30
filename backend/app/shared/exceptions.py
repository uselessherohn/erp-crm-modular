"""
Jerarquía base de excepciones de dominio (spec sección 4).
Ningún módulo inventa su propio esquema de errores — todos heredan de acá.
"""
from __future__ import annotations


class DomainError(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundError(DomainError):
    status_code = 404
    error_code = "NOT_FOUND"


class ValidationError(DomainError):
    status_code = 422
    error_code = "VALIDATION_ERROR"


class ConflictError(DomainError):
    status_code = 409
    error_code = "CONFLICT"


class PermissionDeniedError(DomainError):
    status_code = 403
    error_code = "PERMISSION_DENIED"


class PackageNotLicensedError(PermissionDeniedError):
    error_code = "PACKAGE_NOT_LICENSED"


class PackageSuspendedError(PermissionDeniedError):
    error_code = "PACKAGE_SUSPENDED"


class IdempotencyConflictError(ConflictError):
    error_code = "IDEMPOTENCY_KEY_CONFLICT"
