"""
Property-based testing sobre app.core.security — puro (sin DB), así que
corre con muchos más ejemplos y mucho más rápido que los de accounting.
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.security import hash_password, verify_password

# Contraseñas realistas: al menos 8 caracteres (spec 8.0, política de
# contraseñas), ASCII imprimible. Acotado a ASCII a propósito, no solo por
# realismo: bcrypt trunca a 72 BYTES (ver _BCRYPT_MAX_BYTES en
# app/core/security.py), y con caracteres multi-byte (unicode fuera de
# ASCII) 72 CARACTERES podrían superar los 72 bytes — dos contraseñas
# "distintas" para Python (!=) podrían truncarse al mismo valor de bytes
# y verificar como si fueran la misma, lo cual sería un falso fallo de
# test_different_password_never_verifies, no un bug real de la app (el
# truncamiento a 72 bytes es una limitación conocida y documentada de
# bcrypt, aplicada consistentemente en hash y en verify). Con ASCII,
# 1 carácter = 1 byte siempre, así que el límite de 72 caracteres
# garantiza <= 72 bytes sin ambigüedad.
passwords = st.text(min_size=8, max_size=72, alphabet=st.characters(min_codepoint=32, max_codepoint=126))


@settings(max_examples=200, deadline=None)
@given(password=passwords)
def test_hash_roundtrip_always_verifies(password: str):
    """La propiedad más básica y más importante: cualquier contraseña,
    hasheada y luego verificada contra su propio hash, siempre da True."""
    hashed = hash_password(password)
    assert verify_password(password, hashed)


@settings(max_examples=200, deadline=None)
@given(password=passwords, wrong_password=passwords)
def test_different_password_never_verifies(password: str, wrong_password: str):
    """Dos contraseñas distintas nunca deberían verificar entre sí — con
    la salvedad real y documentada arriba del límite de 72 bytes de
    bcrypt, por eso ambos generadores están acotados a esa longitud."""
    if password == wrong_password:
        return  # hypothesis puede generar el mismo valor para ambos — no es el caso que prueba esta propiedad
    hashed = hash_password(password)
    assert not verify_password(wrong_password, hashed)


@settings(max_examples=100, deadline=None)
@given(password=passwords)
def test_hash_never_contains_the_plaintext_password(password: str):
    """El hash nunca debe contener la contraseña en texto plano — chequeo
    barato pero real contra un "hasheo" que en realidad sea una
    codificación reversible (base64, etc.) en vez de un hash real."""
    hashed = hash_password(password)
    assert password not in hashed


@settings(max_examples=100, deadline=None)
@given(password=passwords)
def test_hash_is_never_deterministic_across_calls(password: str):
    """bcrypt incluye un salt aleatorio — la MISMA contraseña, hasheada
    dos veces, debe dar hashes DISTINTOS (si no, dos usuarios con la
    misma contraseña serían detectables comparando hashes — una fuga de
    información real, aunque nadie pueda revertir el hash)."""
    hashed_once = hash_password(password)
    hashed_twice = hash_password(password)
    assert hashed_once != hashed_twice
    # pero ambos siguen verificando la contraseña original — el salt
    # cambia el hash, no la capacidad de verificar.
    assert verify_password(password, hashed_once)
    assert verify_password(password, hashed_twice)
