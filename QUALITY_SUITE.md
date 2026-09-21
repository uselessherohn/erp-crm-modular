# Suite de calidad — más allá de la regresión funcional

La regresión QA externa (sep-2026, ver `LOG_EJECUCION.md` y `STATE.md`)
cubrió los 26 módulos contra el catálogo de casos
(`catalogo_casos_regresion_erp_crm_v1.md`): comportamiento funcional,
multi-tenant, RBAC, casos límite. Esta suite cubre lo que esa regresión
**no** mide — la integridad del código y del proceso en sí, no el
comportamiento de negocio.

No reemplaza `pytest tests/` (los 248 tests funcionales) — lo complementa.
Vive en `scripts/qa_suite/` + `backend/tests/http/` +
`backend/tests/property/`.

> **Nota (sep-2026, segunda sesión)**: este documento describe la corrida
> *original* de la suite, hecha antes de que `scripts/qa_suite/` se
> integrara al repo — sus fixes (StrEnum, etc.) nunca llegaron a `main`.
> Al integrar la suite y correrla de nuevo contra `main` real, `ruff`
> volvió a marcar 171 hallazgos y `mypy` 28 (ver `LOG_EJECUCION.md`,
> sección "SEGUNDA REGRESIÓN QA EXTERNA"). Esta segunda pasada además
> encontró 2 bugs reales de comportamiento (no solo de lint/types) vía
> `tests/http/` y `tests/property/`, un bug de tipos real en columnas
> `Numeric` mal declaradas `float`, y activó el plugin `pydantic.mypy`
> (no configurado hasta entonces) — todo cerrado y confirmado con la
> suite completa (268/268: 248 funcionales + 20 http/property).

## Las 6 etapas

Cada etapa es un punto natural de commit/push — mismo ritmo que la
regresión por módulo: correr, confirmar en verde, commitear, seguir. El
orquestador se detiene en la primera etapa que falle.

```bash
cd backend
python ../scripts/qa_suite/run_quality_suite.py --list        # ver las etapas
python ../scripts/qa_suite/run_quality_suite.py                # todas, en orden
python ../scripts/qa_suite/run_quality_suite.py --stage baseline   # una sola
```

Requiere una base Postgres limpia y migrada a `head` (mismo setup que el
resto de la suite de regresión — `DROP/CREATE DATABASE`, grants a
`erp_app`/`erp_auth_lookup`, `alembic upgrade head`) antes de correr
cualquier etapa que toque la base (todas menos `sql-audit` y
`deps-audit`).

### 1. `baseline` — cobertura, permisos, downgrade, lint/types

Todo local, sin red, minutos.

- **`01_coverage.py`** — cobertura real de la suite (`pytest-cov`).
  Primera corrida: **87%**. Los puntos bajos son todos `routers.py`
  (48-75%) — la etapa `http` (más abajo) es lo que existe para mejorar
  justamente eso. Umbral fijado en **85%**, no en el número exacto de hoy
  (deja margen, sube con el tiempo a medida que se cierran huecos reales
  — no es una meta artificial de 100%).
- **`02_permission_audit.py`** — formaliza la auditoría manual de la Fase
  0 de la regresión QA (permisos usados en RBAC vs. sembrados en
  `bootstrap_admin.py`). Primer intento del script tuvo 16 falsos
  positivos: el regex original solo buscaba `require_permission(...)`,
  sin contemplar `user_has_permission(...)` (enmascarado "suave", DED-21)
  ni el patrón `all_permission=`/`own_permission=` propio de `medical`
  ("own patients"). Corregido a un escaneo de string literal en todo
  `app/` — **149/149 sin fantasmas ni código muerto**, confirmado.
- **`03_alembic_downgrade.py`** — nunca se había probado en toda la
  regresión. Primer intento (`downgrade -1` repetido) chocó con un
  "Ambiguous walk" real: el historial de migraciones tiene un punto de
  merge genuino (`d016d0daa072`, ramas paralelas de `pharmacy` y
  `website/ecommerce/reports`, documentado en `LOG_EJECUCION.md` — sesión
  de `website`), y `-1` es ambiguo en un fork. Reescrito para bajar a
  **targets explícitos** (que `alembic history` ya linealiza) en vez de
  pasos relativos — con eso, **las 31 migraciones bajan limpio hasta la
  base y vuelven a subir**, confirmado con la suite completa (248/248)
  después del ciclo completo.
- **`04_lint_and_types.py`** — `ruff` + `mypy`, nunca corridos antes.
  Primera pasada: 693 hallazgos, de los cuales **589 eran
  `Depends(...)`** — el patrón estándar y obligatorio de FastAPI, no
  bugs; ruff los marca por default (`B008`,
  function-call-in-default-argument). Configurado en `backend/pyproject.toml`
  (`extend-immutable-calls`) para exceptuar `Depends`/`Query`/etc. **y**
  las fábricas de dependencias paramétricas propias del proyecto
  (`require_permission("...")`, `require_package("...")` — el patrón
  aparece un nivel más adentro de `Depends(...)` y necesita su propia
  excepción). Con eso, 387 hallazgos reales; aplicados los fixes seguros
  automáticos (imports, comillas de anotaciones, `Decimal("1.0")` →
  `Decimal("1")`) y un refactor mecánico pero real (`class X(str,
  enum.Enum)` → `class X(enum.StrEnum)`, 67 clases en 47 archivos,
  verificado con la suite completa + un smoke test real del servidor —
  OpenAPI sigue generando las mismas rutas). Quedaron 8 hallazgos triviales,
  corregidos a mano uno por uno. `line-length` calibrado a **150** (el
  máximo real encontrado en el repo fue 146) — medir el estándar real del
  proyecto en vez de imponer un default genérico que nunca se siguió
  porque ningún linter había corrido antes. `DTZ011`
  (`date.today()` sin timezone) **ignorado explícitamente**, no por
  pereza: los 7 usos reales son `date.today()` poblando columnas
  `Date` (no `DateTime`) — la zona horaria no aplica, confirmado uno por
  uno antes de decidir el ignore.

### 2. `sql-audit` — SQL crudo / inyección

`05_sql_injection_audit.py`: no es `bandit` genérico (mucho ruido en un
proyecto que usa SQL crudo legítimo para RLS/triggers) — busca
específicamente `text()`/`execute()` armados con f-strings/`.format()` en
vez de parámetros bindeados (`:nombre`). Distingue `app/` (crítico — el
código de aplicación nunca debería necesitar interpolar SQL, los nombres
de tabla/columna son literales fijos) de `alembic/versions/` (a
revisar caso por caso — con frecuencia legítimo para nombres de tabla que
varían migración a migración, pero siempre literales del propio código,
nunca datos de un usuario).

### 3. `frontend` — build + vitest

Nunca se corrió en toda esta regresión — fue 100% backend. `npm run
build` + `npx vitest run` sobre `frontend/`. Si no hay `frontend/package.json`
en el checkout, la etapa se omite sin fallar (nada que correr).

### 4. `http` — tests a nivel HTTP real

`backend/tests/http/` — a diferencia del resto de la suite (248 tests que
llaman servicios directo), estos pegan contra la app real vía
`httpx.ASGITransport` (in-process, sin abrir un socket, pero ejercitando
el mismo código que un request real: routing, middleware, exception
handlers — lo único que no pasa es la capa TCP en sí).

- **`test_error_envelope_http.py`** — fija como regresión permanente los
  3 bugs reales que `app/main.py` ya documenta en sus propios
  comentarios (encontrados en una sesión anterior, verificados a mano
  con `curl`, nunca antes con un test que quede corriendo): 404 de ruta
  inexistente (Starlette lanza su excepción base directo, no la de
  FastAPI), 405 de método no permitido, 422 de validación de Pydantic
  (formato nativo vs. sobre uniforme), y el caso más sutil — un
  `model_validator` que falla mete un objeto `Exception` de Python
  dentro de `ctx.error`, no serializable por `json.dumps` sin el
  `custom_encoder` explícito (daba 500 crudo en vez de 422 limpio).
  También el camino de dominio (`NotFoundError` real de un service) y la
  falta de header `Authorization`.
- **`test_cors_http.py`** — nunca se había confirmado que
  `cors_allowed_origins` realmente se aplica en la práctica (la config
  podría estar bien y el middleware mal registrado, o al revés).
- **`test_auth_flow_http.py`** — flujo completo real: crear compañía →
  usuario → login → usar el JWT en una ruta protegida → refresh → usar
  el token nuevo. Y el mensaje genérico de login fallido (DED de core),
  confirmado a nivel HTTP, no solo de servicio.

### 5. `property` — property-based testing (hypothesis)

`backend/tests/property/` — en vez de valores puntuales elegidos a mano,
genera cientos de combinaciones y verifica una propiedad matemática que
debe sostenerse siempre.

- **`test_accounting_compute_lines_properties.py`** — el corazón
  numérico del motor de asientos (`_compute_lines`): `total == subtotal +
  tax_amount` siempre; el agregado es exactamente la suma de las líneas
  (no una aproximación — redondear por línea y sumar da un resultado
  distinto a sumar y redondear el agregado, y este código hace lo
  primero, a propósito); montos nunca negativos para inputs no negativos;
  todo monto redondeado a 2 decimales sin excepción (incluyendo el caso
  clásico `0.03 × 0.07`, que en aritmética exacta da más de 2 decimales);
  y con una tasa de impuesto real, `tax_amount` dentro de una tolerancia
  de redondeo acumulado explicada (no un número mágico).
- **`test_security_properties.py`** — `hash_password`/`verify_password`:
  roundtrip siempre verifica, contraseñas distintas nunca verifican entre
  sí (con la generación de contraseñas acotada a ASCII a propósito —
  bcrypt trunca a 72 *bytes*, no caracteres, y un generador con
  caracteres multi-byte podría producir dos contraseñas "distintas" para
  Python que colisionan en bytes truncados, un falso fallo de test, no un
  bug real de la app — encontrado y corregido antes de correr el test
  por primera vez), el hash nunca contiene la contraseña en texto plano,
  y nunca es determinístico entre llamadas (el salt de bcrypt).

### 6. `deps-audit` — dependencias vulnerables

`09_dependency_audit.py`: `pip-audit` sobre `requirements.txt` y
`requirements-qa.txt`. Nunca se había corrido — todas las versiones
fueron elegidas por disponibilidad al instalar, no por ausencia de CVEs
conocidos.

## Dependencias de la suite

`backend/requirements-qa.txt` — separado de `requirements.txt` a
propósito: la app en producción nunca importa `pytest-cov`/`ruff`/`mypy`/
`pip-audit`/`hypothesis`. Instalar con:

```bash
pip install -r requirements-qa.txt --break-system-packages
```

## Qué falta (fuera de alcance de esta primera versión)

- El umbral de cobertura (85%) y el de `mypy` (sin `--strict` todavía)
  son puntos de partida, no el techo. Subir con el tiempo.
- `UP042` (StrEnum) ya se corrigió en la primera pasada de esta suite —
  si aparece de nuevo en el futuro (una clase nueva con `class X(str,
  enum.Enum)`), es una regresión de estilo, no algo a re-decidir.
- Property-based testing quedó acotado a dos objetivos de alto valor
  (cálculos financieros, hashing de contraseñas) — no es exhaustivo de
  toda la base de código. Buenos candidatos futuros: la lógica de
  redondeo de `StockService` (inventory), la comparación de
  `CreditControlService.get_credit_status` (¿es monótona? ¿subir el
  límite de crédito nunca puede volver a bloquear a alguien que antes no
  lo estaba?).
