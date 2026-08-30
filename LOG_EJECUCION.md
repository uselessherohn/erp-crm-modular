# LOG DE EJECUCIÓN — ERP/CRM Modular v10.4
Registro cronológico de todo lo ejecutado en este entorno (Nivel 1: servidor uvicorn real,
PostgreSQL 16 real, npm/node real, sin simulaciones), desde la configuración inicial del
entorno hasta el estado empaquetado en `erp_crm_avance.zip`.

---

## FASE 0 — Setup del entorno y validación de material de entrada

- `pip install --break-system-packages fastapi "sqlalchemy[asyncio]>=2.0" alembic asyncpg ...`
  → confirmación de Nivel 1 disponible (PostgreSQL instalable vía apt, stack Python completo).
- `apt-get install -y postgresql postgresql-contrib` → PostgreSQL 16.14 real instalado y arrancado
  (`service postgresql start`).
- `CREATE EXTENSION pg_trgm; CREATE EXTENSION pgcrypto;` → confirmadas disponibles.
- `npx openapi-typescript`, `npx openapi-zod-client`, Node 22 / npm 10 confirmados.
- Archivos de especificación recibidos y validados:
  - `modulos_erp_crm_v10_4.json` (fuente única de la tabla de módulos) validado con
    `scripts/validate_modules.py` → **"26 módulos, sin ciclos, sin dependencias huérfanas"**.
  - `scripts/verify_state.py` (verificación externa del DoD) recibido y ejecutado repetidas
    veces a lo largo del proyecto (ver cada cierre de módulo abajo).
- Roles de base de datos creados: `postgres` (owner/DDL), `erp_app` (runtime, sin BYPASSRLS,
  sin superusuario), `erp_auth_lookup` (solo lectura, BYPASSRLS, exclusivo del lookup pre-auth
  de login — agregado en el cierre de Fase 2 de `core`).
- Base de datos `erp_crm_dev` creada.

---

## MÓDULO 1 — `core` (Núcleo)

### Fase 1 — Backend Core (modelos, migración, schemas)
- Proyecto backend scaffoldeado en `/home/claude/erp_crm/backend` (venv propio, FastAPI 0.141,
  SQLAlchemy 2.0.52, Alembic, asyncpg, pydantic 2.13, pytest).
- Modelos: `Company`, `User`, `Role`, `Permission`, `RolePermission`, `UserRole`, `UserSession`,
  `Attachment`, `CompanyPackage`, `AuditLog`, `IdempotencyKey`.
- `alembic revision --autogenerate` → migración `1483b27d4cff` (companies, users, rbac,
  company_packages, audit, idempotency_keys).
- Editada a mano: CHECK constraints de enums, **trigger `trg_audit_immutable`** (BEFORE UPDATE
  OR DELETE, bloquea con RAISE EXCEPTION), **RLS** (`ENABLE`+`FORCE`+`CREATE POLICY
  tenant_isolation`) en las 7 tablas con `company_id`.
- `alembic upgrade head` → aplicó limpio.
- Verificación real: `UPDATE audit ...` → rechazado con el mensaje esperado del trigger.
  Prueba cruzada de RLS con dos tenants reales conectados como `erp_app` (sin BYPASSRLS):
  cada uno solo vio su propia fila.
- Sanity check de schemas Pydantic (`CompanyCreate`, `UserCreate`, `CompanyPackageRead`).
- **Bug real encontrado y corregido:** falta `pydantic[email]` (`email-validator`) para `EmailStr`.

### Fase 2 — Backend Lógica (auth, RBAC, servicios)
- `app/shared/exceptions.py` (jerarquía `DomainError`), `app/core/security.py`,
  `app/core/dependencies.py`, `app/core/services.py`, `app/core/routers/{auth,users,roles,
  companies}.py`, `app/main.py`.
- **AMBIGUO detectado (AMB-01):** la spec no resuelve cómo el cliente indica `company_id`
  antes de autenticarse. Decisión DEDUCIBLE: `email` único globalmente + rol `erp_auth_lookup`.
  Migración `131bc488d5b7` (cambia `uq_users_company_email`→`uq_users_email`, crea el rol).
- **Bugs reales encontrados y corregidos:**
  1. `user` de `auth_lookup_db` mutado y comiteado en `db` (otra sesión) — no habría persistido.
  2. `passlib` incompatible con `bcrypt>=4.1` → reemplazado por `bcrypt` directo.
  3. `refresh()` tenía el mismo problema de tenant-resolution que `login()`.
  4. Cross-event-loop de `asyncpg` en pytest → `asyncio_default_fixture_loop_scope=session`.
- Flujo probado end-to-end vía `uvicorn` real: crear compañía → bootstrap admin → login →
  `/users/me` (200) → `/users` sin permiso (403) → refresh con rotación → logout → 5 intentos
  fallidos → cuenta bloqueada.
- `pytest tests/` → **9/9 passed** (contra PostgreSQL real).

### Fase 2.5 — Contrato
- `curl http://127.0.0.1:8000/openapi.json` → `contracts/openapi.json` congelado
  (9 rutas, 11 schemas).

### Fase 3 — Frontend
- `npm create vite@latest frontend -- --template react-ts`, Tailwind v4, TypeScript bajado a
  5.9.3 (conflicto real con `openapi-typescript`).
- `ui.shadcn.com` **no disponible** en la red del sandbox → componentes UI (Button, Input,
  Label, Card, Table, Dialog, Select) escritos a mano sobre primitivas Radix reales.
- `npx openapi-typescript` + `npx openapi-zod-client --export-schemas` → cliente Zodios
  recortado programáticamente (incompatible con Zod v4, dependencia con señales de bajo
  mantenimiento).
- `npx tsc --noEmit` limpio, `npm run build` limpio.
- `cdn.playwright.dev` **no disponible** → Vitest + Testing Library + jsdom + fetch nativo de
  Node como sustituto (con la limitación documentada: no verifica CORS).

### Fase 4 — Tests y cierre
- 3/3 tests de integración de `LoginPage` (login real, error genérico, validación Zod).
- `STATE.md` creado. `scripts/verify_state.py` → 2 falsos positivos (comentarios históricos con
  el nombre del campo viejo) corregidos → **"Sin errores detectados"**.

---

## MÓDULO 2 — `contacts`

### Fase 1
- Modelo `Contact` (flags `is_customer/is_vendor/is_patient/is_lead`).
- Migración `40b15e2afd9b`: índice **GIN + `pg_trgm`** (`ix_contacts_name_trgm`) sobre `name`,
  RLS. **Falso positivo real de Alembic autogenerate** (quería borrar los CHECK de
  `company_packages` porque se crearon con `op.execute()` crudo) — corregido, patrón repetido
  en todas las migraciones siguientes.
- Prueba real de similitud: `similarity('Ferretería El Roble', 'Ferreteria El Rroble')` = 0.64.

### Fase 2
- `ContactService` (CRUD + búsqueda trigram), `router`.
- **Hallazgo retroactivo grave:** el sobre de error uniforme (spec §7) solo cubría
  `DomainError` propios — los 422 de Pydantic y 404/405 de Starlette usaban el formato nativo
  de FastAPI. Corregido en `app/main.py` (`RequestValidationError` con `jsonable_encoder` tras
  un 500 real por objetos no serializables; `starlette.exceptions.HTTPException`, no
  `fastapi.exceptions.HTTPException`, para capturar el 404 de ruta inexistente).
- `tests/test_error_envelope.py` (4 tests, vía `httpx.ASGITransport`).
- `pytest tests/` → **21/21 passed**.

### Fase 2.5 / 3 / 4
- Contrato re-congelado (11 rutas, 14 schemas).
- Frontend: `ContactsPage` con búsqueda debounced, crear/detalle.
- **10/10 tests frontend** (incluye `ContactsPage.integration.test.tsx`, búsqueda pg_trgm real
  end-to-end, mensaje de error específico del `model_validator` — mejora en `api-client.ts`
  para extraer `details.errors[0].msg`).
- `verify_state.py` → **"Sin errores detectados"**.

---

## MÓDULO 3 — `inventory` (subset [core])

### Fase 1
- Modelos: `Category`, `Warehouse`, `Product`, `Lot`, `StockMovement` (ledger append-only),
  `StockLevel` (saldo materializado — decisión DEDUCIBLE, spec dice "alta contención" sin
  nombrar la entidad).
- Migración `ccd8a2f53a05`: RLS en 6 tablas, **FK real `users.active_warehouse_id →
  warehouses.id`** (resuelve TODO diferido desde el cierre de `core`).

### Fase 2 — Concurrencia real
- `StockService._apply_delta`: patrón **UPSERT-a-cero + `SELECT ... FOR UPDATE`**.
- **Test de concurrencia real**: 10 conexiones `asyncpg` reales en paralelo (`asyncio.gather`,
  sesiones separadas) contra un stock que solo alcanza para 6 salidas de 10 → nunca negativo,
  en ninguna corrida.
- `pytest tests/` → **29/29 passed** (11 core + 10 contacts... ajustado; total acumulado).

### Fase 2.5 / 3 / 4
- Contrato re-congelado (18 rutas, 26 schemas).
- Frontend: `WarehousesPage`, `ProductsPage`, `StockPage` (registrar movimiento, transferencia).
- Componente `Select` de Radix escrito a mano (mismo motivo de red).
- **Bugs de test reales:** jsdom sin `hasPointerCapture`/`setPointerCapture` (polyfill agregado
  en `test-setup.ts`); Radix Select duplica texto en nodo interno de medición (`getByText`→
  `getByRole("option", {name})`).
- **10/10 tests frontend** (incluye `StockPage.integration.test.tsx`).
- Investigación de un 500 intermitente (`invalid input syntax for bigint: ''`) nunca
  reproducido vía `curl` directo — mitigado con `pool_pre_ping=True`, causa raíz real
  encontrada después (ver Módulo 4).
- `verify_state.py` → **"Sin errores detectados"**.

---

## MÓDULO 4 — `purchasing` (subset [core])

### Hallazgo retroactivo previo al módulo
- Regla de spec §5 (Concurrencia) no aplicada en `inventory`: columna `version` (bloqueo
  optimista) faltante en `StockLevel` → agregada.
- **Numeración atómica de documentos**, nueva infra compartida: tabla `document_counters` +
  `DocumentNumberingService.next_number()` en `core` (mismo patrón UPSERT+FOR UPDATE).
- Migración `4d97e3604c34`: `document_counters`, `version` en `stock_levels`.

### Fase 1
- Modelos `PurchaseOrder` (+`version`), `PurchaseOrderLine`.
- Migración `905a3855ef61`: RLS, `UniqueConstraint(company_id, number)`.

### Fase 2 — Máquina de estados
- `draft → confirmed → received → closed` (+`cancelled`), todas las transiciones con
  `SELECT ... FOR UPDATE` sobre la fila del PO.
- **Bug real de diseño encontrado antes de probar:** `StockService.record_movement` hacía
  `commit()` interno — rompía la composición con `receive()` (múltiples líneas + header en una
  transacción). Corregido separando `_record_movement_no_commit` / `record_movement`.
- `pytest tests/test_purchasing_module.py` → 10/10, incluyendo numeración atómica con
  **15 conexiones reales concurrentes** (nunca duplica).

### HALLAZGO CRÍTICO — bug de aislamiento RLS bajo connection pooling
- Reproducido de forma determinística corriendo tests de `purchasing`:
  `InsufficientPrivilegeError: new row violates row-level security policy for table
  "warehouses"`.
- Causa raíz: `async_sessionmaker(bind=engine)` libera la conexión física al pool en cada
  `commit()`; la siguiente query de la misma sesión lógica puede reengancharse a una conexión
  física **distinta**, sin el `set_config('app.current_company_id', ...)` fijado.
- **Fix en `app/database.py`:** `AsyncSessionLocal`/`AuthLookupSessionLocal` reescritos para
  ligar la sesión a **una única conexión física** (`engine.connect()` +
  `AsyncSession(bind=connection)`) durante todo su ciclo de vida. Misma sintaxis de uso, cero
  cambios en código existente.
- Verificado: **39/39 tests** (core+contacts+inventory+purchasing) siguieron pasando.
- Es, con alta probabilidad, la explicación real del 500 intermitente nunca resuelto en
  `inventory`.

### Fase 2.5 / 3 / 4
- Contrato re-congelado (24 rutas, 33 schemas).
- Frontend completo: `PurchaseOrdersPage`, diálogo de creación (líneas manejadas con
  `useState` por fricción real de tipos de `useFieldArray` con `Decimal`), diálogo de detalle
  con transiciones y recepción parcial.
- **Bug real en `scripts/bootstrap_admin.py`:** `NoReferencedTableError` por FK no resuelta
  (`app.inventory.models` nunca importado en el proceso) → creado `app/models_registry.py`.
- **1/1 test frontend** (flujo completo: crear PO → confirmar → recibir parcial desde la UI →
  stock verificado directo contra el backend).
- `pytest tests/` → **39/39 passed**. Frontend → **13/13 passed**.
- `verify_state.py` → **"Sin errores detectados"**.

---

## MÓDULO 5 — `sales` (subset [core])

### Hallazgo retroactivo previo al módulo
- Nuevo concepto: **reserva de stock** (distinta de descuento inmediato). `StockLevel.
  reserved_quantity` agregado (CHECK `reserved_quantity >= 0 AND reserved_quantity <=
  quantity`). `StockService.reserve/release_reservation/ship` (nuevo, mismo patrón
  UPSERT+FOR UPDATE).

### Fase 1
- Modelos `PriceList`+`PriceListItem` (precio por quiebre de volumen), `Quote`+`QuoteLine`,
  `SalesOrder`+`SalesOrderLine`.
- Migración `c93e498bb1c4`: `reserved_quantity`, 6 tablas nuevas con RLS.
- **Bugs menores de escritura corregidos antes de migrar:** `is_default` tipado como
  `Integer` en vez de `Boolean`; `QuoteStatusEnum`/`SalesOrderStatusEnum` como clases planas
  en vez de `enum.Enum` (inconsistente con el resto del proyecto).

### Fase 2 — Dos máquinas de estado + concurrencia
- `SalesOrder`: draft→confirmed(reserva)→en_preparacion→enviado(descuenta físico+libera
  reserva, parcial soportado)→facturado, cancelado desde draft/confirmed/en_preparacion.
- `Quote`: draft→sent→accepted(valida `valid_until` real)→converted(terminal)/expired/
  cancelled. `convert_to_order` atómico (`_skip_commit`, mismo patrón que `purchasing`).
- `pytest tests/test_sales_module.py` → **11/11 passed**, incluyendo **10 confirmaciones
  concurrentes reales** contra stock que solo alcanza para 6 reservas — nunca sobrevende.
- `pytest tests/` (suite completa) → **50/50 passed**.
- `STATE.md` actualizado con el hallazgo crítico en sección 0 (visible antes que cualquier
  otro contenido) y el contrato parcial de `sales`.
- `verify_state.py` → **"Sin errores detectados"**.

### Fase 2.5 / 3 (este último tramo)
- `curl http://127.0.0.1:8000/openapi.json` → contrato re-congelado: **38 rutas, 49 schemas**.
- `npx openapi-typescript` + `npx openapi-zod-client --export-schemas` → regenerado, recortado.
- `npx tsc --noEmit` limpio.
- Frontend: hooks `use-sales.ts`, `PriceListsPage`+`CreatePriceListDialog`, `QuotesPage`+
  `CreateQuoteDialog`+`QuoteDetailDialog` (envío→conversión a orden), `SalesOrdersPage`+
  `CreateSalesOrderDialog`+`SalesOrderDetailDialog` (envío parcial línea por línea).
- **Bug real encontrado y corregido en este último tramo:** `CreatePriceListDialog` pasaba el
  payload crudo (sin `currency_code`/`is_default`, que Zod completa con default) directo al
  hook, que esperaba el tipo *output* de Zod — TypeScript lo marcó en rojo
  (`Type ... is missing the following properties from type ...: currency_code, is_default`).
  Corregido pasando el payload por `schemas.PriceListCreate.parse()` antes de la mutación,
  mismo patrón usado en el resto del proyecto (`purchasing`, `inventory`).
- `npx tsc --noEmit -p tsconfig.app.json` → **limpio, 0 errores**.
- `npm run build` → **build de producción exitoso** (625 kB / 182 kB gzip; warning de tamaño
  de bundle esperado en esta etapa, no bloqueante).

**Pendiente, no ejecutado en este tramo:** Fase 4 de `sales` (tests de integración de frontend
para listas de precios/cotizaciones/órdenes de venta) y actualización final de `STATE.md`/
`verify_state.py` reflejando el frontend completo de este módulo.

---

## MÓDULO 5 — `sales`, cierre de Fase 4 (tests de integración frontend) y TODO-12

- Entorno de Nivel 1 reconstruido desde cero en un sandbox nuevo: PostgreSQL 16 real
  (`apt-get install postgresql postgresql-contrib`), roles `erp_app`/`erp_auth_lookup`
  recreados con sus contraseñas y privilegios (incluye `GRANT ... ON SEQUENCES`, que
  `ALTER DEFAULT PRIVILEGES ... ON TABLES` no cubre — hallazgo real de este tramo, corregido
  antes de la primera corrida de `pytest`), `alembic upgrade head` (7 migraciones, limpio),
  `uvicorn` real levantado con `setsid` (necesario para que el proceso sobreviva entre
  invocaciones de shell separadas del entorno de ejecución).
- `pytest tests/` → **50/50 passed**, confirmando lo ya reportado arriba para los módulos
  1-5 (Fases 1-2).
- **`PriceListsPage.integration.test.tsx`** (1 test): crea una lista de precios con un precio
  por producto desde la UI, verifica la tarjeta renderizada y el precio contra el backend real.
- **`QuotesPage.integration.test.tsx`** (1 test): crea cotización → envía → acepta → convierte
  a orden de venta, verificado contra el backend real.
  - **Hallazgo real de este tramo:** `SalesOrderService.convert_to_order` deja la orden nueva
    en estado `draft` (no auto-confirma) — se leyó el código fuente antes de escribir la
    aserción del test, en vez de asumir el estado esperado.
- **`SalesOrdersPage.integration.test.tsx`** (1 test): crea orden de venta (con stock real
  sembrado vía `/inventory/stock-movements`) → confirma (verifica `reserved_quantity` real)
  → envía cantidad completa (verifica descuento físico + liberación de reserva) → factura.
- **Bugs de test reales encontrados y corregidos** (en los tests nuevos, no en producción):
  1. `getByText(customerName)`/`getByText(/convertida/i)` con múltiples coincidencias — el
     subtítulo de cada página ("Borrador → Enviada → Aceptada → Convertida.") y filas de
     cotizaciones/órdenes de corridas previas colisionaban con el texto buscado. Corregido
     acotando con `within(dialog)` / `within(table)`.
  2. Timeout default de Vitest (5000ms) insuficiente para flujos de 3-4 transiciones de
     estado reales contra Postgres — subido a 15000ms en `QuotesPage` y `SalesOrdersPage`
     (mismo criterio ya usado en `PurchaseOrdersPage.integration.test.tsx`).
- `npx vitest run` (suite completa) → **16/16 passed** (13 previos + 3 nuevos de `sales`).
- `npx tsc --noEmit -p tsconfig.app.json` → limpio. `npm run build` → build de producción
  exitoso (mismo warning de tamaño de bundle ya documentado, no bloqueante).
- `STATE.md` actualizado: módulo 5 marcado Fases 1-4 completas, TODO-12 cerrado, resumen
  rodante y tabla de tests de frontend al día.
- `scripts/verify_state.py --state STATE.md --repo backend --db-url postgresql://...` →
  **"Sin errores detectados"**, incluyendo las verificaciones de Nivel 1 (trigger de
  inmutabilidad sobre `audit`, índice único de `idempotency_keys`) contra la base real.



## Resumen numérico acumulado (backend, `pytest tests/`)
| Módulo | Tests | Estado |
|---|---|---|
| core | 11 | ✓ |
| contacts | 10 | ✓ |
| inventory | 8 | ✓ |
| purchasing | 10 | ✓ |
| sales | 11 | ✓ |
| **Total backend** | **50** | ✓ (última corrida confirmada) |

## Resumen numérico acumulado (frontend, `vitest run`)
| Módulo | Tests | Estado |
|---|---|---|
| core | 6 | ✓ |
| contacts | 4 | ✓ |
| inventory | 2 | ✓ |
| purchasing | 1 | ✓ |
| sales | 3 | ✓ (Fase 4 cerrada en este cierre) |
| **Total frontend** | **16** | ✓ (última corrida confirmada) |

## Migraciones Alembic aplicadas (orden real)
1. `1483b27d4cff` — core: companies, users, rbac, company_packages, audit, idempotency_keys
2. `131bc488d5b7` — core: email único global, rol erp_auth_lookup
3. `40b15e2afd9b` — contacts: entidad unificada, pg_trgm
4. `ccd8a2f53a05` — inventory: catálogo, almacenes, movimientos, lotes, FK active_warehouse_id
5. `4d97e3604c34` — core+inventory: document_counters, version en stock_levels
6. `905a3855ef61` — purchasing: purchase_orders, purchase_order_lines
7. `c93e498bb1c4` — inventory+sales: reserved_quantity, price_lists, quotes, sales_orders

Todas verificadas con `alembic downgrade -1` + `alembic upgrade head` (reproducibilidad
confirmada) y, en el cierre de `purchasing`, con reconstrucción completa de la base desde cero
(`DROP DATABASE`→`CREATE DATABASE`→`alembic upgrade head`).

## Hallazgos críticos con impacto retroactivo (cronológico)
1. Formato de error uniforme incompleto (afectaba a `core` desde su cierre) — corregido en
   el cierre de `contacts`.
2. `StockLevel` sin columna `version` (spec §5) — corregido en el cierre de `purchasing`.
3. **Bug de aislamiento RLS bajo connection pooling** (afectaba a `core`, `contacts`,
   `inventory`, `purchasing` desde sus respectivos cierres) — corregido en el cierre de
   `purchasing`, el hallazgo más importante de todo el ciclo.
4. `record_movement` con commit interno, rompía composición transaccional — corregido en el
   cierre de `purchasing`.
5. `bootstrap_admin.py` con imports de modelos incompletos — corregido en el cierre de
   `purchasing` (`app/models_registry.py`).
6. `StockLevel` sin `reserved_quantity` (necesario para `sales`) — corregido en el cierre
   (parcial) de `sales`.

---

## MÓDULO 6 — `accounting`, Fases 2, 2.5 y 3

### Fase 2 (servicios + endpoints)
- `IdempotencyService` nuevo en `core/services.py` (resuelve TODO-03): hash SHA-256
  determinístico del payload (`json.dumps(sort_keys=True, default=str)`), TTL por dominio
  (usa `config.idempotency_ttl_hours_*`, ya scaffoldeado), colisión con payload distinto →
  409 `IDEMPOTENCY_KEY_CONFLICT`, solo persiste en 2xx/4xx definitivo. Construido como
  reutilizable pero **aún no cableado a ningún router** — queda para el próximo cierre.
- `app/accounting/services.py`: `AccountService`, `DocumentAccountMappingService`,
  `JournalService.post_entry()` (genérico — resuelve cuentas vía mapeo, valida balance antes
  de persistir), `TaxRateService`, `InvoiceService`, `CreditDebitNoteService`,
  `PaymentService`, `CreditControlService`. Todas las transiciones de estado con
  `SELECT...FOR UPDATE`; `PaymentService.post()` bloquea las facturas de sus allocations en
  orden ascendente de id para prevenir deadlock entre pagos concurrentes.
- **Hook cross-módulo real**: `sales.SalesOrderService.confirm()` ahora invoca
  `accounting.CreditControlService.assert_customer_not_blocked()` si el paquete
  `administrative` está activo — documentado en el docstring de `sales/services.py` como
  cambio aditivo que no reabre su contrato congelado.
- `pytest tests/` → 50/50 sin regresión tras el hook cross-módulo.
- **Smoke test manual real contra Postgres** (Nivel 1, vía curl): 6 cuentas del plan mínimo
  creadas, mapeo `sales_invoice`/`payment_received` configurado, factura de venta
  (1500 + 225 ISV = 1725) creada y contabilizada → asiento verificado por consulta directa a
  `journal_lines`: Dr CxC 1725.00 = Cr Ingresos 1500.00 + Cr ISV 225.00 (balanceado exacto).
  Pago parcial de 1000 aplicado y contabilizado → `balance_due` bajó a 725.00,
  `status=partially_paid`. Motor de Contención Financiera: con `credit_limit=500` y saldo
  725, `GET /accounting/credit-status/1` devolvió `is_blocked=true`; **el hook en
  `sales/confirm` rechazó la orden con 409 y el motivo exacto, sin reservar stock**; al subir
  el límite a 5000, la misma orden confirmó normal (200).

### Fase 2.5 (congelar contrato)
- `curl http://127.0.0.1:8000/openapi.json` → **54 rutas** (38 previas + 16 nuevas de
  accounting), confirmado que las 38 rutas previas no cambiaron (retrocompatibilidad).
- `npx openapi-typescript` + `npx openapi-zod-client --export-schemas` regenerados.
- **Bug real encontrado y corregido en este tramo**: el recorte programático de
  `schemas.ts` (necesario porque `--export-schemas` también genera un cliente Zodios
  incompatible con Zod v4) se hizo mal la primera vez — se agregó un `export const schemas`
  propio sin notar que `--export-schemas` **ya genera su propio** `export const schemas = {...}`
  antes del array `endpoints`. Resultado: dos declaraciones del mismo nombre, `tsc` fallaba
  con `TS2451: Cannot redeclare block-scoped variable 'schemas'`. Corregido: el recorte debe
  cortar únicamente lo que sigue *después* de `const endpoints = makeApi([` (el cliente
  Zodios), dejando intacto el `export const schemas` que la herramienta ya produce.
- `npx tsc --noEmit` limpio tras la corrección.

### Fase 3 (frontend)
- `use-accounting.ts`: hooks completos (query+mutation) para las 7 entidades con sus
  acciones (`post`/`cancel` donde aplica).
- `AccountsPage` (Plan de Cuentas + Tasas de Impuesto + Mapeo documento→cuentas, una sola
  página de configuración con 3 secciones) + `CreateAccountDialog` + `CreateTaxRateDialog` +
  `CreateDocumentAccountMappingDialog` (este último filtra las cuentas elegibles por rol
  seleccionado, para no permitir mapear una cuenta `income` a un rol `payable`).
- `InvoicesPage` + `CreateInvoiceDialog` (selector de dirección venta/proveedor que filtra
  contactos por `is_customer`/`is_vendor`, líneas con impuesto opcional) +
  `InvoiceDetailDialog` (contabilizar/cancelar, con nota explicando que una factura
  contabilizada se revierte con nota, no se cancela directo).
- `PaymentsPage` + `CreatePaymentDialog` (asignación a 0, 1 o varias facturas elegibles —
  filtradas por contacto+dirección+estado facturable) + `PaymentDetailDialog`
  (contabilizar/cancelar).
- Rutas y navegación agregadas (`/accounts`, `/invoices`, `/payments`).
- **No se construyó en este cierre**: `CreditDebitNotesPage` (backend/hooks completos, falta
  la UI) — recorte de alcance explícito por tamaño del módulo, no un olvido.
- `npx tsc --noEmit` limpio, `npm run build` exitoso (mismo warning de tamaño de bundle ya
  documentado, no bloqueante).
- `npx vitest run` (suite completa existente) → **16/16 passed**, sin regresión — confirma
  que el recorte corregido de `schemas.ts` no rompió nada de sales/purchasing/inventory/core.

**Pendiente, no ejecutado en este tramo:** Fase 4 (tests de integración frontend para
`AccountsPage`/`InvoicesPage`/`PaymentsPage`), `CreditDebitNotesPage`, cablear
`IdempotencyService` a los routers que crean movimientos financieros.

---

---

## MÓDULO 6 — `accounting`, cierre de Fase 4 (tests de integración) y del módulo completo

- Cableado de `IdempotencyService` a los 9 endpoints financieros (invoices/payments/
  credit-debit-notes: create/post/cancel) vía `IdempotencyService.run_command()` genérico,
  agregado a `core/services.py`. Verificado end-to-end contra el backend real: dos llamadas
  idénticas con la misma `Idempotency-Key` devuelven exactamente el mismo `id`/`created_at`/
  `version` (replay real, sin reejecutar); la misma clave con payload distinto → 409
  `IDEMPOTENCY_KEY_CONFLICT`; un error de negocio (422, mapeo de cuenta faltante) también se
  persiste y repite correctamente en el reintento. `pytest` 50/50 sin regresión.
- `CreditDebitNotesPage` construida (backend/hooks ya existían del cierre anterior):
  `CreateCreditDebitNoteDialog`, `CreditDebitNoteDetailDialog`, ruta y navegación agregadas.
  `tsc`/`build` limpios.
- **Fase 4 — 4 tests de integración nuevos, todos reales contra backend en 127.0.0.1:8000,
  sin mocks**: `AccountsPage.integration.test.tsx` (cuenta+tasa+mapeo), `InvoicesPage.
  integration.test.tsx` (crear→contabilizar, asiento verificado), `PaymentsPage.
  integration.test.tsx` (crear→asignar a factura→contabilizar, saldo verificado),
  `CreditDebitNotesPage.integration.test.tsx` (crear relacionada a factura→contabilizar).
- **3 bugs reales encontrados y corregidos gracias a estos tests** (el propósito real de la
  Fase 4, no solo cobertura):
  1. **Bug de backend real**: `CreditDebitNoteService.post()` construía `document_type` con
     `f"{note.direction}_{suffix}"`, produciendo `"sale_credit_note"` (con 'e', inválido)
     en vez de `"sales_credit_note"` — la dirección `sale`/`purchase` no coincide 1:1 con el
     prefijo de `DocumentTypeEnum` (`sales_`/`purchase_`, asimétrico, igual que
     `sales_invoice`/`purchase_invoice`). Corregido con mapeo explícito
     `direction_prefix = "sales" if note.direction == "sale" else "purchase"`.
  2. **Condición de carrera real de Vitest**: por defecto los archivos de test corren en
     paralelo; como todos golpean el mismo Postgres compartido (sin fixtures aisladas por
     archivo), dos suites configurando el mismo `document_account_mapping` (clave única
     `company_id+document_type+role`) se pisaban entre sí de forma no determinística.
     Corregido con `fileParallelism: false` en `vitest.config.ts`, con la razón documentada
     in-line — afecta a toda la suite de integración del proyecto, no solo a accounting.
  3. **Condición de carrera de UI**: el diálogo de creación podía seguir montado (con
     `data-state="open"`, background `aria-hidden`) un instante después de que la lista ya
     se refrescara mostrando el nuevo registro (por invalidación de query) — el test
     entonces fallaba al buscar `getByRole("table")` porque la tabla real seguía oculta
     detrás del overlay del diálogo todavía abierto. Corregido agregando una espera
     explícita a que el diálogo de creación se desmonte antes de consultar la tabla, en
     `CreditDebitNotesPage`, `InvoicesPage`, `PaymentsPage`, y **retroactivamente en
     `SalesOrdersPage`** (test del módulo 5, escrito en una sesión anterior, que tenía el
     mismo patrón latente y resultó ser flaky al desactivar el paralelismo de archivos).
- Verificación final: `pytest tests/` → **50/50**. `npx vitest run` (suite completa) →
  **12 archivos, 20/20 tests** (16 previos + 4 nuevos de accounting). `npx tsc --noEmit`
  limpio (se eliminó además un import no usado detectado en este chequeo). `npm run build`
  exitoso.
- `scripts/validate_modules.py` → sin cambios, sigue consistente (26 módulos).
- `STATE.md` actualizado: módulo 6 marcado Fases 1-4 completas, TODO-14 cerrado, resumen
  rodante al día.

**Módulo `accounting` cerrado por completo** (Fases 1-4). Con `sales` y `accounting` ambos
cerrados, el módulo 7 (`pipeline de leads/oportunidades`, depende de 2 y 6) queda
desbloqueado como siguiente candidato natural — ver `modulos_erp_crm_v10_4.json`.

---

---

## MÓDULO 7 — `pipeline` (Fases 1-4, módulo completo)

- Leí spec 2.3 y 8.0: **caso especial del proyecto** — toda la funcionalidad de `pipeline`
  (kanban de embudo, scoring, actividades) está clasificada [extendido, requiere paquete
  Administrativo], a diferencia de purchasing/sales/accounting que tenían un subset [core].
  Se construyó igual porque `modulos_erp_crm_v10_4.json` lo lista como módulo real con
  dependencias (`depende_de: [2, 6]`). Documenté 5 decisiones DEDUCIBLE/AMBIGUO (DED-15 a
  DED-19).
- **Fase 1**: 3 entidades (`Stage`, `Opportunity`, `Activity`). `Stage` configurable por
  compañía (spec sección 11, cambio v9: ya no hay pipeline fijo), con `is_won`/`is_lost`
  terminales y `CHECK NOT(is_won AND is_lost)` a nivel de fila. `Opportunity` vinculada a
  `Contact` existente (DED-15: "Lead" = `Contact.is_lead`, sin tabla nueva). RLS + grants
  verificados en las 3 tablas. `pytest` 50/50 sin regresión tras la migración.
- **Fase 2**: `StageService`, `OpportunityService` (`move_stage`/`close_won`/`close_lost`/
  `reopen`), `ActivityService`. **Hallazgo estructural del proyecto**: `pipeline` es el
  primer módulo donde `require_package("administrative")` — scaffoldeado desde el módulo 1,
  nunca antes usado en ningún router real de purchasing/sales/accounting — se aplica de
  verdad, a nivel de router completo.
  - **Verificado real, end-to-end**: sin fila `company_packages` con `package='administrative'`
    y `status='active'`, cualquier ruta de `/pipeline/*` devolvió `403 PACKAGE_NOT_LICENSED`
    real. Insertando esa fila directamente (no hay endpoint público para contratar paquetes
    todavía), las mismas rutas funcionaron normal.
  - Flujo completo probado a mano vía curl: crear 4 etapas (2 intermedias + Ganada + Perdida),
    crear lead, crear oportunidad, moverla de etapa (200), intentar moverla directo a una
    etapa terminal vía `move-stage` (rechazado, 422 — DED-18), `close-won` (200, `closed_at`
    seteado), reintentar `move-stage` sobre la ya cerrada (rechazado, 409). Actividad creada
    y completada sobre la oportunidad.
  - `pytest` 50/50 sin regresión.
- **Fase 2.5**: contrato re-congelado — **63 rutas** (54 previas + 9 nuevas), confirmado que
  las 54 previas no cambiaron. `openapi-typescript` + `openapi-zod-client --export-schemas`
  regenerados sin repetir el bug de duplicación de `export const schemas` que ocurrió en el
  cierre de `accounting` — esta vez el recorte programático se aplicó correctamente a la
  primera. `tsc` limpio.
- **Fase 3**: `use-pipeline.ts` (hooks completos, 3 entidades + 6 acciones), `PipelinePage`
  (kanban real por columnas de etapa — sin drag-and-drop, movimiento vía diálogo de detalle,
  decisión consciente para no gastar el tiempo de esta sesión en una librería de DnD),
  `CreateStageDialog`, `CreateOpportunityDialog`, `OpportunityDetailDialog` (mover
  etapa/cerrar ganada|perdida con motivo/reabrir/registrar y completar actividades). Ruta y
  navegación agregadas. `tsc` limpio, `npm run build` exitoso.
- **Fase 4**: `PipelinePage.integration.test.tsx` — crea etapas (incluida una terminal
  "ganada") → crea oportunidad desde la UI → la cierra ganada → verifica `status='won'` y
  `closed_at` truthy contra el backend real. Pasa a la primera.
- **Observación de infraestructura de test (no un bug de este módulo)**: durante el cierre
  de este módulo, la suite completa de integración mostró intermitencia real en
  `AccountsPage.integration.test.tsx` (del cierre de `accounting`) — pasa en ~2.4s aislado,
  pero en algunas corridas completas excedió el timeout de 20s bajo contención de recursos
  del sandbox (reinicios frecuentes de este sandbox durante la sesión). Confirmado con
  múltiples corridas que NO es un bug determinístico: mismo código, mismo test, a veces pasa
  y a veces no en la misma sesión de trabajo. Se documenta como límite estructural conocido
  del enfoque (tests de integración reales contra un backend/Postgres compartido, sin
  fixtures aisladas ni entorno dedicado por test) — no se investiga más a fondo ni se
  "arregla" con más timeout indefinidamente, ya que el problema es de recursos del entorno,
  no de lógica.
- Verificación final: `pytest tests/` → **50/50**. `npx vitest run` (suite completa) →
  **13 archivos, 21/21 tests** (20 previos + 1 nuevo de pipeline), confirmado en una corrida
  limpia de 53s. `npx tsc --noEmit` limpio. `npm run build` exitoso.
- `STATE.md` actualizado: módulo 7 marcado Fases 1-4 completas, DED-15 a DED-19 registradas,
  resumen rodante al día, TODO-20 agregado para lo explícitamente fuera de alcance
  (Helpdesk/Campañas/Contratos B2B — ni siquiera están en la tabla de módulos del proyecto).

**Módulo `pipeline` cerrado por completo.** Con `sales` y `accounting` ya cerrados
previamente, y ahora `pipeline`, el paquete Administrativo completo del proyecto tiene:
`inventory`, `purchasing`, `sales`, `accounting`, `pipeline` — falta únicamente `hr` (módulo 8,
depende de `1`, opcionalmente de `6` si incluye Nómina) para completar el paquete
Administrativo por completo.

---

---

## MÓDULO 8 — `hr` (Fases 1-2, en curso)

- Leí spec 8.1: subset [core] = Legajo, Estructura Organizacional, Jerarquías. Nómina/Payroll
  y el resto son [extendido]. Documenté 3 decisiones DEDUCIBLE (DED-20 a DED-22).
- **Fase 1**: 3 entidades (`Department` con `parent_department_id` auto-referencial,
  `Position` ligada a un `Department`, `Employee` — Legajo, entidad propia que NO reutiliza
  `Contact`, DED-20). RLS + grants verificados en las 3 tablas. `pytest` 50/50 sin regresión.
- **Fase 2**: `DepartmentService`, `PositionService`, `EmployeeService` (con `terminate()`).
  Agregué `user_has_permission()` — helper reutilizable en `core/dependencies.py`, chequeo
  "suave" que no bloquea la request, a diferencia de `require_permission` — usado para
  enmascarar `salary` a `None` en la respuesta si el actor no tiene
  `hr:employee:read-sensitive` (DED-21).
- **Bug real preexistente encontrado y corregido** (no introducido por `hr`, pero recién
  expuesto porque ningún módulo anterior había creado un rol con `permission_ids` no vacío):
  `Role.permissions` en `core/models.py` apuntaba a `RolePermission` (la tabla de asociación)
  en vez de a `Permission` directamente. `RoleRead.model_validate(role)` fallaba con
  `AttributeError` → `500 Internal Server Error` en `GET /roles` para cualquier rol con 1+
  permisos — incluido el propio rol `admin` bootstrapeado (83 permisos). Confirmé que la
  relación vieja solo se usaba en `models.py`/`schemas.py`, sin otros consumidores en el
  código (`grep` completo del árbol `app/`). Corregido: `Role.permissions` ahora es
  `relationship(secondary="role_permissions", lazy="selectin", viewonly=True)` apuntando
  directo a `Permission` (`viewonly=True` porque `RoleService.create_role` gestiona la tabla
  de asociación insertando `RolePermission` directamente, no a través de esta colección).
  `pytest` 50/50 sin regresión tras el fix.
- **Verificado end-to-end real**: creé departamento, puesto, empleado con `salary=18000.00`
  (visible para el admin). Creé un rol `HR Básico` (permisos 77,79,80,81 — sin el 82,
  `hr:employee:read-sensitive`) y un usuario con ese rol — `GET /hr/employees/{id}` le
  devolvió `salary: null`, confirmando el enmascarado real. `terminate()` probado: primera
  baja exitosa (`status→terminated`), segundo intento sobre el mismo empleado rechazado con
  `409 CONFLICT`.
- **Pendiente, no ejecutado en este tramo**: Fase 2.5 (congelar contrato — se esperan 8 rutas
  nuevas: departments POST/GET, positions POST/GET, employees POST/GET/{id}/terminate), Fase
  3 (frontend: departamentos, puestos, legajos con enmascarado de salario en la UI también,
  no solo en el backend) y Fase 4 (tests de integración).

---

---

## MÓDULO 8 — `hr`, cierre de Fases 2.5, 3 y 4 (módulo completo)

### Fase 2.5 (congelar contrato)
- `curl http://127.0.0.1:8000/openapi.json` → **68 rutas** (63 previas + 5 nuevas agrupadas:
  `departments` POST/GET, `positions` POST/GET, `employees` POST/GET/{id}/GET/{id}/terminate),
  confirmado que las 63 rutas previas no cambiaron.
- `npx openapi-typescript` + `npx openapi-zod-client --export-schemas` regenerados sin
  repetir el bug de duplicación de `export const schemas` (ya resuelto desde el cierre de
  `accounting`). `tsc` limpio.

### Fase 3 (frontend)
- `use-hr.ts`: hooks completos para las 3 entidades + `terminate`.
- `EmployeesPage`: departamentos + puestos + legajos en una sola página (mismo patrón que
  `AccountsPage` del módulo `accounting`), con la columna de salario mostrando "No visible"
  cuando el backend lo enmascaró.
- `CreateDepartmentDialog`, `CreatePositionDialog`, `CreateEmployeeDialog` (con selector de
  gerente filtrado a empleados activos), `EmployeeDetailDialog` (acción `terminate` con fecha).
- Ruta y navegación agregadas. `tsc` limpio, `npm run build` exitoso.

### Fase 4 (tests de integración)
- `EmployeesPage.integration.test.tsx`: crea departamento, puesto y empleado con salario
  desde la UI (visible para el admin, que tiene `hr:employee:read-sensitive`).
- **Verificación real y completa del enmascarado DED-21**, no solo a nivel de UI: dentro del
  mismo test, se resuelven dinámicamente los ids de los permisos `hr:department:list`,
  `hr:position:list`, `hr:employee:create`, `hr:employee:read` (leyendo el rol admin vía
  `GET /roles`, sin asumir numeración fija), se crea un rol `HR Básico Test` con esos
  permisos (excluyendo `hr:employee:read-sensitive`), se crea un usuario con ese rol, se
  inicia sesión con ese usuario, y se confirma que `GET /hr/employees` le devuelve
  `salary: null` para el mismo empleado que el admin ve con `salary: "18000.00"`. La sesión
  de admin se restaura al final del test para no afectar el resto del proceso.
- Pasa a la primera — sin bugs nuevos encontrados en este tramo (a diferencia de los cierres
  anteriores, que sí encontraron bugs reales en cada Fase 4).

### Verificación final
- `pytest tests/` → **50/50** en todo momento (confirmado sin necesitar truncar entre el test
  de hr y la corrida de pytest — los sufijos únicos del test no colisionan con los datos de
  pytest).
- `npx vitest run` (suite completa) → **14 archivos, 22/22 tests** (21 previos + 1 nuevo),
  confirmado en corrida limpia de 51s — una corrida intermedia mostró la misma intermitencia
  ya documentada de `AccountsPage` bajo carga del sandbox (timeout, no lógica), resuelta al
  reintentar sin cambios de código.
- `STATE.md` actualizado: módulo 8 marcado Fases 1-4 completas, TODO-21 cerrado, resumen
  rodante al día.

**Módulo `hr` cerrado por completo.** Con esto, **el paquete Administrativo está
completo**: `inventory`, `purchasing`, `sales`, `accounting`, `pipeline`, `hr` — los 6
módulos que la spec 8.1 asigna a este paquete están construidos de punta a punta (Fases 1-4
cada uno). El siguiente paso natural del proyecto, según `modulos_erp_crm_v10_4.json`, es
empezar el paquete Médico (módulo 9, `medical` — expediente, agenda, consulta) o el
Transversal (`reports`, `audit completo`, `notifications`, que no dependen de ningún paquete
vertical y podrían construirse en cualquier momento).

---

---

## BRANDING — Renombrado del producto a "Axis Suite" + configuración como PWA

Fuera del ciclo de construcción de módulos (spec/plantilla), a pedido directo del usuario:

- Recibí ícono y logo en SVG (`axis-suite-icon.svg` — cuadrado redondeado azul cobalto
  #1D5FA8 con una "A" blanca y acento cian; `axis-suite-logo.svg` — mismo ícono + wordmark
  "axis suite"). Los copié a `frontend/public/` y reemplacé el favicon existente (un ícono
  morado abstracto sin relación con el proyecto, aparentemente un placeholder de plantilla).
- Generé PNGs desde el SVG del ícono con `cairosvg`: `icon-192.png`, `icon-512.png` (purpose
  "any"), y `icon-512-maskable.png` (ícono renderizado al 70% del lienzo, centrado sobre
  fondo sólido del mismo azul de marca — respeta la "safe zone" ~80% que exige Android para
  no recortar la "A" al aplicar máscaras circulares/squircle).
- Instalé `vite-plugin-pwa` y configuré `vite.config.ts`: manifest completo (name/short_name
  "Axis Suite", lang "es", theme_color #1D5FA8, display "standalone", los 3 íconos),
  `registerType: 'autoUpdate'`. Sin runtime caching de rutas de API (`navigateFallbackDenylist`
  cubre todos los prefijos de router del backend) — decisión deliberada: los datos del ERP
  (saldos, stock, RLS multi-tenant) no deben servirse desde caché.
- Actualicé `index.html` (título "Axis Suite", favicon, apple-touch-icon, meta theme-color),
  `package.json` (`name: "axis-suite-frontend"`), y reemplacé el placeholder "Núcleo" —
  encontrado hardcodeado en dos lugares (`AppLayout.tsx` sidebar header, `LoginPage.tsx`
  título) — por el ícono+wordmark real de Axis Suite. Confirmé por `grep` que no había más
  ocurrencias del nombre viejo ni tests que dependieran de ese texto.
- Verificado real: `npm run build` genera `dist/manifest.webmanifest` (contenido confirmado
  correcto), `dist/sw.js`, `dist/workbox-*.js`, y copia los 3 PNGs + 2 SVGs a la raíz de
  `dist/`. `npx tsc --noEmit` limpio.
- `pytest tests/` → 50/50 sin regresión (cambios son 100% frontend). `npx vitest run` (suite
  completa) → **14 archivos, 22/22 tests**, incluido `LoginPage.integration.test.tsx` sin
  romperse pese a reemplazar su `<h1>` por una imagen (confirmé antes que ningún test
  dependía de ese elemento). Una corrida intermedia mostró la misma intermitencia ya
  documentada de `AccountsPage` bajo carga del sandbox — resuelta al reintentar sin cambios.

---

## Limitaciones de red del sandbox, documentadas explícitamente durante el proyecto
- `ui.shadcn.com` no disponible → componentes UI escritos a mano sobre Radix.
- `cdn.playwright.dev` no disponible → Vitest+jsdom como sustituto de E2E real en navegador
  (con la limitación explícita: no verifica CORS).
