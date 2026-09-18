# STATE.md — ERP/CRM v10.4 — Roberto (proyecto de referencia, sin cliente final asignado aún)

> **Nota de branding (fuera del ciclo de módulos)**: el producto se
> comercializa como **"Axis Suite"** — frontend renombrado (título,
> favicon, sidebar, login), configurado como PWA instalable
> (`vite-plugin-pwa`, ver `LOG_EJECUCION.md` sección "BRANDING"). No
> afecta contratos de API, modelos, ni la tabla de módulos — es
> puramente presentación del frontend.


## 0. HALLAZGO CRÍTICO retroactivo — leer antes de tocar cualquier servicio

**`app/database.py` tenía un bug real de aislamiento RLS bajo connection
pooling, con impacto en TODOS los módulos cerrados hasta `inventory`**
(corregido en el cierre de `purchasing`, módulo 4).

`AsyncSessionLocal` (basado en `async_sessionmaker(bind=engine)` desde la
Fase 1 de `core`) libera la conexión física al pool en cada `commit()`. La
siguiente query de la MISMA sesión lógica puede reengancharse a una
conexión física DISTINTA del pool, que nunca tuvo
`set_config('app.current_company_id', ..., false)` fijado. Cualquier
servicio con más de un `commit()` (la mayoría) podía perder su contexto
RLS a mitad de una operación.

Reproducido de forma determinística con los tests de `purchasing`:
`InsufficientPrivilegeError: new row violates row-level security policy
for table "warehouses"`. Es, con alta probabilidad, la explicación real de
los 500 intermitentes (`invalid input syntax for type bigint: ''`) vistos
antes en `inventory` que nunca se pudieron reproducir vía `curl` directo —
una sola request HTTP normalmente no agota tantas conexiones del pool
como para exponer la carrera, pero tests con múltiples conexiones
concurrentes sí.

**Fix**: `AsyncSessionLocal`/`AuthLookupSessionLocal` ahora ligan la
sesión a UNA conexión física (`engine.connect()` + `AsyncSession(bind=
connection)`) durante todo su ciclo de vida, sin importar cuántos commits
ocurran adentro. Mismo nombre, misma sintaxis de uso — cero cambios en
routers/servicios/tests existentes.

**Verificado**: 39/39 tests (`core`+`contacts`+`inventory`+`purchasing`)
siguen pasando tras el fix. No se re-ejecutaron los tests de frontend
(Vitest) tras este fix específico porque no tocan `app/database.py`
directamente — pendiente de una corrida de confirmación si se retoma
`inventory`/`contacts`/`core` frontend en el futuro (bajo riesgo, el fix
es transparente a nivel de API).

## 0.1 Fase 0 de la regresión QA externa (sep-2026) — 2 bugs reales de extensiones + 1 falso positivo de verify_state.py

Primera corrida de `alembic upgrade head` de este proyecto contra una
base Postgres **completamente limpia**, siguiendo `spec_regresion_qa_erp_crm_v1.md`
sección 1. El log original de Fase 0 (arriba, `LOG_EJECUCION.md`) registra
`CREATE EXTENSION pg_trgm; CREATE EXTENSION pgcrypto;` como "confirmadas
disponibles" en el servidor — pero esa confirmación nunca se tradujo en un
`CREATE EXTENSION` dentro de una migración real. Dos bugs reales, mismo
patrón:

1. **Migración `40b15e2afd9b` (contacts)**: `CREATE INDEX
   ix_contacts_name_trgm ... USING gin (name gin_trgm_ops)` sin que
   ninguna migración habilitara `pg_trgm` antes. Bloqueaba
   `alembic upgrade head` siempre, de punta a punta, en cualquier base
   limpia — nunca se había ejecutado así hasta esta sesión. Corregido en
   el commit `0da1637` (`CREATE EXTENSION IF NOT EXISTS pg_trgm` antes
   del índice, mismo patrón que `btree_gist` en `1669f8fbbc6b`).
2. **Migración `1669f8fbbc6b` (medical)**: `app/medical/services.py`
   cifra `clinical_record_entries.content` y los campos clínicos de
   `consultations` con `func.pgp_sym_encrypt`/`pgp_sym_decrypt`
   (pgcrypto, DED-24/DED-25), pero la extensión nunca se habilitaba en
   ninguna migración. No detectado antes porque ninguna sesión previa
   tuvo Postgres real para ejercitar un INSERT/UPDATE real sobre esas
   columnas. Corregido en el commit `a194f33`.

Con ambos fixes, `alembic upgrade head` corre limpio (29 migraciones,
head único `c4d8b3f61a97`), `scripts/validate_modules.py` confirma los
26 módulos sin ciclos/huérfanos, y el escaneo de RLS
(`information_schema.columns` × `pg_policies`) confirma **71/71 tablas**
con `company_id` en `ENABLE`+`FORCE ROW LEVEL SECURITY` + policy
`tenant_isolation`, sin excepciones.

3. **`scripts/verify_state.py` — tercer falso positivo de la misma
   clase que los 2 ya documentados** (ver `LOG_EJECUCION.md`):
   `check_no_legacy_boolean_field()` escaneaba `*.py` de todo el repo
   buscando el string literal `minimal_dependencies_only`, sin excluir
   su propio archivo — que necesariamente lo contiene, porque es el
   string que define la búsqueda. Reportaba `ERROR` en cada corrida
   aunque el código de la app estuviera limpio (confirmado: era el
   único hit). Corregido en el commit `95cef3c` excluyendo
   `Path(__file__)` del escaneo. Con el fix, `verify_state.py --db-url
   <real>` corre sin errores, incluyendo Nivel 1 (trigger
   `trg_audit_immutable`, índice único de `idempotency_keys`).

**`idempotency_keys` — TODO-03 (sección 6) confirmado cerrado**: tiene
consumidores reales en `app/accounting/routers.py` y
`app/ecommerce/routers.py` (facturas/pagos y el webhook de pago). No es
un hallazgo nuevo — solo la primera confirmación por lectura de código
de que el TODO ya estaba resuelto en la práctica.

## 0.2 2FA, recuperación de contraseña y activar/desactivar usuario — gap real cerrado (sep-2026)

Instrucción explícita del usuario tras el hallazgo de la sección 0.1:
aunque no bloqueaban el DoD original (spec 8.0 los marca **[core]**, no
[extendido], así que en rigor sí lo bloqueaban — la discrepancia es que
nunca se habían construido y esa omisión nunca quedó registrada como
decisión ni como TODO), se trataron como aspectos que requieren
corrección, no solo documentación.

**Confirmado contra `spec_erp_crm_v10_4.md` sección 8.0** (texto literal):
"Autenticación y Seguridad **[core]**: login, 2FA, recuperación de
contraseña, sesiones activas, JWT/OAuth2, política de contraseñas,
bloqueo por intentos." Al cierre original del módulo 1 se construyó
login/JWT/sesiones/bloqueo, pero 2FA y recuperación de contraseña no —
sin que STATE.md lo registrara como decisión DEDUCIBLE/AMBIGUO ni como
TODO diferido, simplemente no están. Activar/desactivar usuario no está
tan explícito en la spec, pero "Gestión de Usuarios [core]: perfiles,
**estados**..." lo implica, y no existía ningún endpoint para eso
(`UserRead.is_active` era de solo lectura, sin `UserUpdate`).

**Construido en la migración `6f6e78cc5e26`** (ver esa migración y
`app/core/services.py` para el detalle línea por línea):

- **2FA (TOTP)**: `TwoFactorService.setup/confirm/disable`, secreto
  generado con `pyotp`, cifrado en reposo con `pgcrypto`
  (`pgp_sym_encrypt`/`pgp_sym_decrypt`, mismo patrón exacto que `medical`
  — ver `app/medical/services.py`). `AuthService.login` exige
  `totp_code` cuando `user.totp_enabled=true`; sin código devuelve
  `422` con `details={"requires_2fa": true}` para que el cliente sepa
  pedirlo. `setup` no habilita 2FA hasta `confirm` (evita que un usuario
  quede bloqueado por un secreto que nunca confirmó poder leer).
  `disable` exige re-confirmar la contraseña.
- **Recuperación de contraseña**: `PasswordResetService.request_reset/
  confirm_reset`, mismo patrón cross-tenant que login/refresh (tabla
  `password_reset_tokens`, token de un solo uso hasheado con sha256,
  resuelto vía `erp_auth_lookup` sin conocer `company_id` de antemano).
  `request_reset` nunca revela si el email existe (mismo criterio que
  login). Confirmar el reset revoca todas las sesiones activas del
  usuario (igual que desactivar). El "envío" de email es un log local a
  `core` (no importa `app.notifications` — violaría el grafo de
  dependencias, `core` no depende de nada).
- **Activar/desactivar usuario**: `UserService.set_active`, `PATCH
  /users/{id}/status`, permiso nuevo `core:user:update_status`.
  Idempotente (desactivar dos veces no es error ni reescribe). Bloquea
  autodesactivación. Al desactivar, revoca de inmediato todas las
  sesiones activas (refresh tokens) del usuario — el access token JWT ya
  emitido sigue válido en tránsito, pero `get_current_user` re-chequea
  `is_active` en cada request, así que la ventana de exposición real es
  como máximo `jwt_access_token_expire_minutes`, nunca indefinida.

**Bug relacionado encontrado y corregido en el camino**: `AuthService.refresh`
no chequeaba `is_active` del usuario — un usuario desactivado con una
sesión todavía no revocada podía seguir renovando su access token para
siempre. Ahora chequea explícitamente (segunda capa de defensa, además de
la revocación de sesiones en `set_active`).

**Segundo bug relacionado, no introducido por este cierre pero encontrado
al probarlo**: no había ningún `logging.basicConfig()` en la app — el
logger raíz de Python queda en `WARNING` sin handlers por default, así
que cualquier `logger.info()` se descarta en silencio. Esto ya afectaba a
`notifications.LoggingEmailSender` (nunca detectado porque
`test_notifications_module.py` inyecta un `_FakeEmailSender` de test, no
ejercita el logger real) y hubiera afectado igual al nuevo log de
password-reset. Corregido en `app/main.py` con
`logging.basicConfig(level=logging.INFO)`.

Probado de tres formas: 16 tests nuevos en `test_core_module.py` (a nivel
de servicio), la suite completa (189/189, sin regresiones), y
manualmente end-to-end contra el servidor real con `curl` — los tres
flujos completos, incluyendo los caminos de error (token/código
incorrecto, reintento de token de un solo uso, autodesactivación
bloqueada, refresh revocado). Detalle completo de la sesión de `curl` en
LOG_EJECUCION.md.

## 1. Paquetes y módulos completados
- Núcleo: core (✓), contacts (✓)
- Administrativo: inventory (✓), purchasing (✓), sales (✓), accounting (✓), pipeline (✓), hr (✓)
- Médico: medical (✓ Completo — Fases 1-4 completas: backend, contrato, frontend, tests de integración reales), recetas (✓ Completo), laboratorio (✓ Completo), teleconsulta (✓ Completo), facturación médica básica (✓ Completo), portal/mensajería (✓ Completo), reserva pública de citas (✓ Completo — backend + widget embebible, verificado contra Postgres real, ver su sección)
- Farmacéutico: **completo de punta a punta** — dispensación + verificación clínica (✓ Completo — módulo 16), sustancias controladas (✓ Completo — módulo 16), interacciones medicamentosas (✓ Completo — módulo 17), reposición a droguerías (✓ Completo — módulo 20), aseguradoras/copagos (✓ Completo — módulo 18), POS farmacia (✓ Completo — módulo 16), MTM (✓ Completo — módulo 21) — 18/20/21 verificados contra Postgres real, sesión sep-2026
- Web: website (✓ Completo — verificado vía CI), ecommerce (✓ Completo — backend + configuración de panel interno verificados vía CI; storefront público es un frontend separado fuera de alcance de este panel)
- Transversal: reports (✓ Completo — verificado vía CI), audit completo (✓ Completo — módulo 25, verificado contra Postgres real, sesión sep-2026), notifications (✓ Completo — Fases 1-4 completas)

## 2. Contratos públicos vigentes (NO redefinir)

### Módulo 1 — core
- Entidad `User`: `email` **único globalmente** (no por compañía — AMB-01
  abajo). Campos: `full_name`, `locale`, `timezone`, `is_active`,
  `failed_login_attempts`, `locked_until`, `active_warehouse_id` (FK real
  a `warehouses.id`, `ON DELETE RESTRICT` — agregada en el cierre
  retroactivo de módulo 3/4), `created_by`/`updated_by`.
- `Role`/`Permission`/`RolePermission`/`UserRole`: RBAC granular, código
  `modulo:accion` (ej. `core:user:create`). `Role` por compañía;
  `Permission` catálogo global del sistema.
- `company_packages` (spec 2.4/13): `package` enum
  `administrative|medical|pharmacy|web`, `status`
  `active|suspended|deactivated`, `minimal_modules: list[str]|None`
  (JSONB). Dependencias reutilizables probadas (sin consumidor propio en
  `core` todavía): `get_active_packages`, `get_active_packages_cached`,
  `require_package`, `require_package_writable`.
- `audit` mínimo (spec 8.0): tabla + `AuditService.log_event(...)`.
  Trigger `trg_audit_immutable` (BEFORE UPDATE OR DELETE) — verificado con
  un UPDATE real rechazado, no solo con el DDL.
- `idempotency_keys` (spec 7): tabla + índice único `(company_id,
  idempotency_key, endpoint)` — **sin consumidor todavía** (TODO-03).
- `document_counters` (spec 5, numeración atómica) — agregado en el
  cierre de `purchasing`: `DocumentNumberingService.next_number(db, *,
  company_id, doc_type, prefix, year) -> str` (`"{prefix}-{year}-
  {num:06d}"`), patrón UPSERT-a-cero + `SELECT FOR UPDATE`, mismo criterio
  que `StockService._apply_delta`. Probado con 15 conexiones reales
  concurrentes — nunca duplica.
- RLS: `ENABLE`+`FORCE`+policy `tenant_isolation` en toda tabla con
  `company_id` de `core` — verificado con datos reales cruzando tenants.
- Rol `erp_auth_lookup` (BYPASSRLS, solo SELECT columnas explícitas) —
  exclusivo del lookup pre-auth de `/auth/{login,refresh}`.
- Excepciones (`app/shared/exceptions.py`): `DomainError` →
  `NotFoundError`(404)/`ValidationError`(422)/`ConflictError`(409)/
  `PermissionDeniedError`(403) → `PackageNotLicensedError`/
  `PackageSuspendedError`(403)/`IdempotencyConflictError`(409). Sobre
  uniforme `{"error": {"code","message","details"}}` — **para TODO error,
  incluyendo 422 de Pydantic y 404/405 nativos de Starlette** (handlers
  agregados en el cierre de `contacts`, ver DED-04 abajo).
- **2FA, recuperación de contraseña, activar/desactivar usuario — cerrados
  en la sesión de regresión QA externa (sep-2026, migración `6f6e78cc5e26`)**:
  ver sección 0.2 para el detalle completo de por qué faltaban y cómo se
  construyeron. Resumen: `TwoFactorService` (TOTP real vía `pyotp`, secreto
  cifrado con `pgcrypto`, mismo patrón que `medical`), `PasswordResetService`
  (token de un solo uso, mismo patrón cross-tenant que login/refresh),
  `UserService.set_active` (idempotente, revoca sesiones activas al
  desactivar, bloquea autodesactivación). `AuthService.refresh` corregido
  para chequear `is_active` (bug relacionado: antes un usuario desactivado
  podía seguir renovando su token indefinidamente). 16/16 tests nuevos en
  `test_core_module.py`, probado también end-to-end contra el servidor
  real (`curl`, ver LOG_EJECUCION.md).

### Módulo 2 — contacts
- Entidad `Contact` (spec 2.3): flags `is_customer`/`is_vendor`/
  `is_patient`/`is_lead` no excluyentes. `ContactCreate` exige (DEDUCIBLE)
  al menos un flag activo — `model_validator`, invisible en el JSON
  Schema/OpenAPI, el Zod generado NO lo replica (limitación real de
  `model_validator`, no bug de codegen).
- Búsqueda: operador trigram `%` (usa `ix_contacts_name_trgm`, GIN +
  `pg_trgm`) — verificado tolerando typos y falta de tildes.
- **3 hallazgos reales confirmados en la regresión QA externa (sep-2026)
  — cerrados en la migración `ea97b3b319d5`**:
  1. **`credit_limit` ahora tiene endpoint propio**: `PATCH
     /contacts/{id}/credit-limit`, permiso separado
     `contacts:contact:update_credit_limit` (campo financiero sensible,
     mismo criterio que separar `hr:employee:read-sensitive` del resto
     de lectura de empleado). `ContactService.update_credit_limit`.
  2. **`ContactService.list_contacts` ahora busca también por `email` y
     `tax_id`** (ILIKE — son identificadores exactos, no texto libre, no
     tiene sentido aplicarles trigram fuzzy como a `name`).
  3. **Email único por compañía** (DEDUCIBLE nuevo — a diferencia de
     `users.email`, que es único GLOBAL, AMB-01): índice único parcial
     `ux_contacts_company_email` `WHERE email IS NOT NULL` — dos
     contactos sin email no chocan entre sí. `ContactService.
     create_contact`/`update_contact` capturan el `IntegrityError` y lo
     traducen a `ConflictError` (409), no un 500 crudo.
  4 tests nuevos en `test_contacts_module.py` (10/10), probado también
  con sesiones separadas simulando el patrón real de requests HTTP
  independientes (ver LOG_EJECUCION.md — el primer intento de probarlo a
  mano con una sola sesión compartida expuso un footgun real de
  SQLAlchemy async: tras un `rollback()`, los objetos ya comprometidos de
  la MISMA sesión quedan expirados y tocarlos sin `await` explícito
  revienta con `MissingGreenlet` — no aplica a producción porque cada
  request tiene su propia sesión vía `Depends`, pero se documenta por si
  alguna vez se reutiliza una sesión entre pasos, como en un script o un
  worker).

### Módulo 3 — inventory (subset [core] de spec 8.1)
- Entidades: `Category`, `Warehouse`, `Product`, `Lot`, `StockMovement`
  (ledger append-only, sin trigger de BD — TODO-06), `StockLevel` (saldo
  materializado, DEDUCIBLE — spec dice "alta contención", no nombra la
  entidad; ahora con columna `version` para bloqueo optimista, spec 5).
- Concurrencia: `StockService._apply_delta` — UPSERT-a-cero + `SELECT FOR
  UPDATE`, serializa por fila `(product, warehouse, lot)`. Probado con 10
  conexiones reales concurrentes, stock nunca negativo.
- `StockService._record_movement_no_commit` vs `record_movement`: la
  primera NO commitea, para componer varios movimientos en UNA transacción
  más grande (usado por `purchasing.receive`) — el público sí commitea,
  para uso directo desde el router. Bug real corregido en el cierre de
  `purchasing`: `record_movement` original commiteaba internamente, lo que
  cortaba a la mitad cualquier composición.
- Transferencia = SIEMPRE dos `StockMovement` (`salida`+`entrada`) mismo
  `correlation_id`, atómicos.
- DEDUCIBLE: `ajuste` se interpreta siempre como baja. No confirmado por
  Roberto.
- **Regresión QA externa (sep-2026)**: matriz del catálogo (camino feliz
  por tipo/lote, límites, concurrencia con conexiones reales paralelas)
  ya cubierta por la suite existente (8/8 aislado, sin cambios). Único
  hueco real encontrado: **`product_type=servicio` nunca se ejercitaba
  en ningún test, y el código no lo distingue de
  `facturable`/`consumible` en absoluto** — un producto `servicio` hoy
  puede acumular/perder stock exactamente igual que cualquier otro tipo.
  La spec (8.1) lista los tres tipos pero no aclara si `servicio`
  debería bloquear `StockMovement` — no hay decisión que tomar sin
  confirmar con Roberto, así que se documenta el comportamiento REAL
  actual con un test (`test_servicio_product_type_has_no_special_stock_
  handling`) en vez de asumir una regla e implementarla. `reserved_
  quantity` (columna retroactiva) se revisa en el módulo 5 (`sales`),
  que es donde efectivamente se ejercita — ya tiene test dedicado en
  `test_sales_module.py`.
- [extendido] fuera de alcance: FEFO/FIFO/LIFO, alertas de caducidad,
  bloqueo/cuarentena de lote, costeo por lote, valoración, conversión de
  unidades, kits/BOM (TODO-07).

### Módulo 4 — purchasing (subset [core] de spec 8.1)
- Entidades: `PurchaseOrder` (header, `version` para bloqueo optimista de
  transiciones de estado), `PurchaseOrderLine`.
- Máquina de estados: `draft → confirmed → received → closed`, con
  `cancelled` alcanzable desde `draft`/`confirmed` (no desde `received`/
  `closed` — ya hay stock recibido, cancelar requeriría un flujo de
  devolución que no existe todavía). Todas las transiciones usan
  `SELECT ... FOR UPDATE` sobre la fila del PO.
- DEDUCIBLE: el número se genera al crear el `draft` (trazabilidad
  completa, incluso de drafts descartados) en vez de al confirmar
  (evitaría huecos en la secuencia). No confirmado por Roberto.
- DEDUCIBLE: `closed` es una acción administrativa manual sin lógica de
  negocio adicional todavía (no hay `accounting` con el que hacer match de
  factura) — cuando exista `accounting`, `closed` probablemente dispare
  más lógica (TODO-08).
- Recepción de mercancía = entrada REAL de stock vía
  `StockService._record_movement_no_commit` (no un efecto simbólico) —
  soporta recepción parcial (spec 8.1: "Control de Recepción Parcial
  [core]"), múltiples llamadas a `/receive` acumulan
  `quantity_received` por línea hasta completar.
- [extendido] fuera de alcance: Requisiciones internas, Gestión/
  Evaluación de Proveedores, RFQ, Contratos Marco/Blanket Orders.
- **Regresión QA externa (sep-2026)**: matriz del catálogo ya cubierta
  casi entera por la suite existente (10/10 aislado, sin bugs
  encontrados). Solo faltaban 2 tests explícitos para reglas que el
  código YA implementaba correctamente, sin cobertura: recibir mercancía
  de una PO en `draft` (nunca confirmada) → rechazado
  (`test_receive_on_draft_po_rejected`); cerrar una PO con saldo
  pendiente sin recibir → **confirmado que se bloquea, no existe cierre
  forzado** — `close()` exige `status=='received'` (recepción TOTAL, no
  solo `confirmed`), ni siquiera una recepción parcial alcanza
  (`test_close_with_pending_balance_rejected_no_forced_close`).
- Contrato Fase 2.5 re-congelado: `contracts/openapi.json` — 24 rutas, 33
  schemas. Frontend completo (Fase 3): listar/crear/confirmar/recibir
  (parcial, desde la UI)/cerrar/cancelar. Fase 4: flujo real de punta a
  punta probado (crear PO → confirmar → recibir 20 de 50 desde la UI →
  verificado el `stock_level` resultante directo contra el backend, no
  solo confiado en lo que muestra la pantalla).
- **Bug real de fricción de tipos, no de lógica**: `useFieldArray` de
  react-hook-form no resuelve el tipo cuando el array tiene campos
  `Decimal` (unión `number|string` generada desde Pydantic) anidados —
  "Type 'lines' does not satisfy the constraint 'never'", persistente con
  `z.input`, `z.infer` y genéricos explícitos. Resuelto manejando las
  líneas del formulario con `useState` simple en vez de RHF field array;
  la validación real sigue siendo 100% Zod al momento del submit, sin
  pérdida de garantías — el header (`vendor_id`/`warehouse_id`) sí sigue
  con RHF+zodResolver normal.
- **Bug real encontrado en el bootstrap/scripts**: `scripts/
  bootstrap_admin.py` fallaba con `NoReferencedTableError` al tocar
  `User` porque nunca importaba `app.inventory.models` — SQLAlchemy
  resuelve FKs declaradas como string de forma perezosa, y si el módulo
  que define la tabla destino nunca se importó en el proceso, la
  resolución revienta aunque el código no toque esa tabla directamente.
  Corregido creando `app/models_registry.py` (importa todos los módulos
  de modelos del proyecto) — cualquier script/entrypoint que no pase por
  `app.main` debe importarlo primero.

### Módulo 5 — sales (subset [core] de spec 8.1) — Fases 1-4 completas
- Entidades: `PriceList`+`PriceListItem` (precio por quiebre de volumen,
  `min_quantity` descendente), `Quote`+`QuoteLine`, `SalesOrder`+
  `SalesOrderLine`.
- **Reserva de stock real** (spec 8.1: "confirmados, asignación/reserva de
  stock") — `StockLevel.reserved_quantity` (hallazgo retroactivo a
  `inventory`, con `CHECK (reserved_quantity >= 0 AND reserved_quantity <=
  quantity)`). `StockService.reserve/release_reservation/ship` (nuevo):
  confirmar RESERVA (no descuenta físico), enviar SÍ descuenta físico y
  libera la reserva en la misma operación bloqueada. Probado con 10
  confirmaciones concurrentes reales — nunca sobrevende.
- Máquina de estados `SalesOrder`: draft→confirmed→en_preparacion→
  enviado→facturado, cancelado desde draft/confirmed/en_preparacion (no
  desde enviado — requeriría RMA, [extendido], no construido). Envío
  parcial soportado (mismo patrón que Recepción Parcial de purchasing).
- Máquina de estados `Quote`: draft→sent→accepted→converted (terminal) /
  expired / cancelled. `accept` valida `valid_until` contra la fecha real.
  `convert_to_order` crea la `SalesOrder` **en estado `draft`** (no
  auto-confirma) y actualiza la cotización en UNA transacción atómica
  (mismo patrón `_skip_commit` que `purchasing`) — confirmado leyendo
  `SalesOrderService.convert_to_order`, no asumido, al escribir el test de
  integración de Fase 4.
- DEDUCIBLE: solo se puede convertir una cotización `accepted` (no `sent`
  directo). No confirmado por Roberto.
- [extendido] fuera de alcance: Descuentos/Promociones, Comisiones de
  Vendedores, Devoluciones (RMA).
- **Regresión QA externa (sep-2026)**: hallazgo real — `README.md` lista
  el Motor de Contención Financiera como "verificado end-to-end", pero
  no existía NINGÚN test que lo reprodujera (ni acá, ni en `accounting`
  — sigue sin `test_accounting_module.py` dedicado, gap ya documentado).
  El código en sí ya estaba correcto (`SalesOrderService.confirm()` invoca
  `CreditControlService.assert_customer_not_blocked()` solo si
  `administrative` está activo). Se escribieron 2 tests nuevos que
  reproducen el flujo completo por primera vez: bloqueo por crédito
  excedido → sigue bloqueado si el límite sube pero no alcanza → se
  desbloquea de verdad al subir el límite lo suficiente (usando
  `ContactService.update_credit_limit`, el endpoint del módulo 2 de esta
  misma regresión); y el caso complementario, acoplamiento flojo
  confirmado: sin el paquete `administrative` activo, confirma sin
  evaluar contención financiera aunque el saldo esté groseramente
  excedido.
- **Fase 2.5 (contrato re-congelado: 38 rutas, 49 schemas) — completa.**
- **Fase 3 (frontend) — completa:** `PriceListsPage`+`CreatePriceListDialog`,
  `QuotesPage`+`CreateQuoteDialog`+`QuoteDetailDialog` (envío→conversión a
  orden), `SalesOrdersPage`+`CreateSalesOrderDialog`+`SalesOrderDetailDialog`
  (envío parcial línea por línea). `npx tsc --noEmit` limpio, `npm run
  build` exitoso.
- **Fase 4 (tests de integración frontend) — completa, cierre de TODO-12:**
  `PriceListsPage.integration.test.tsx` (crear lista con precio por
  quiebre de volumen), `QuotesPage.integration.test.tsx` (crear→enviar→
  aceptar→convertir a orden real, verificado contra backend), `SalesOrdersPage.
  integration.test.tsx` (crear→confirmar[reserva]→enviar completo[descuenta
  físico+libera reserva]→facturar, saldo de stock verificado contra
  Postgres en cada paso). 3 tests nuevos, todos reales contra backend en
  `127.0.0.1:8000` — sin mocks, mismo patrón que `purchasing`/`inventory`.
  Bugs de test (no de producción) encontrados y corregidos en el camino:
  colisión de `getByText` con el subtítulo de la página y con filas de
  otras cotizaciones/órdenes (resuelto acotando con `within(dialog)`/
  `within(table)`); timeout default de Vitest (5000ms) insuficiente para
  flujos de 3-4 transiciones de estado reales — subido a 15000ms, mismo
  criterio que `PurchaseOrdersPage.integration.test.tsx`.

### Módulo 6 — accounting (subset [core] de spec 8.1, motor de asientos
spec 7.1) — **Fases 1-4 completas**
- 11 entidades: `Account` (Plan de Cuentas mínimo, DED-09),
  `DocumentAccountMapping` (mapeo documento→cuentas, DED-10),
  `JournalEntry`+`JournalLine` (Motor de Asientos, append-only vía trigger
  `journal_prevent_update_delete` — mismo patrón que `trg_audit_immutable`
  del módulo 1, probado con UPDATE y DELETE reales bloqueados), `TaxRate`,
  `Invoice`+`InvoiceLine` (Facturación venta/proveedor, un solo modelo con
  `direction sale|purchase`, DED-11 sobre la cuenta `adjustment`),
  `CreditDebitNote`+`CreditDebitNoteLine`, `Payment`+`PaymentAllocation`
  (un pago puede aplicarse a 1+ facturas, parcial o total).
- Balance de asiento (`total_debit = total_credit`) forzado con CHECK a
  nivel de base, no solo en el servicio — defensa en profundidad, mismo
  criterio que `reserved_quantity<=quantity` en `inventory`.
- **Hallazgo retroactivo**: `credit_limit` (Numeric nullable) agregado a
  `Contact` para el Motor de Contención Financiera (DED-12) — mismo patrón
  que `reserved_quantity` agregado retroactivamente a `inventory` desde
  `sales`.
- RLS + `tenant_isolation` + grants aplicados a las 11 tablas, verificado
  con INSERT/DELETE reales bajo `SET app.current_company_id`.
- **`IdempotencyService`** (core, resuelve TODO-03): primer consumidor real
  del mecanismo de spec 7 — hash de payload determinístico, TTL por
  dominio (`idempotency_ttl_hours_accounting=72`), colisión con payload
  distinto → 409 `IDEMPOTENCY_KEY_CONFLICT`, solo persiste en 2xx/4xx
  definitivo. `IdempotencyService.run_command()` genérico, **cableado a
  los 9 endpoints financieros** de accounting (invoices/payments/
  credit-debit-notes: create/post/cancel). Verificado end-to-end: dos
  llamadas idénticas con la misma `Idempotency-Key` devuelven el mismo
  `id`/`version` (replay real sin reejecutar); clave repetida con payload
  distinto → 409; error de negocio (422) también se persiste y repite.
- `JournalService.post_entry()` genérico: resuelve cuentas vía
  `DocumentAccountMapping`, nunca hardcodea `account_id`; valida balance
  antes de persistir. Verificado con asiento real en Postgres: factura de
  1500+225 ISV → Dr CxC 1725 = Cr Ingresos 1500 + Cr ISV 225 (balanceado
  exacto, confirmado por consulta directa a `journal_lines`).
- Máquinas de estado con `SELECT...FOR UPDATE`: `Invoice`
  (draft→posted→partially_paid/paid, draft→cancelled — DEDUCIBLE: una
  factura `posted` NO se cancela directo, se revierte con nota),
  `CreditDebitNote` (draft→posted→terminal, draft→cancelled), `Payment`
  (draft→posted aplica allocations sobre facturas + genera asiento,
  draft→cancelled). `PaymentService.post()` bloquea facturas en orden
  ascendente de id para prevenir deadlock entre pagos concurrentes.
- **Hook cross-módulo real, verificado end-to-end**:
  `sales.SalesOrderService.confirm()` invoca
  `CreditControlService.assert_customer_not_blocked()` solo si el paquete
  `administrative` está activo. Probado real: con `credit_limit=500` y
  saldo 725, `sales/sales-orders/{id}/confirm` devolvió 409 con el motivo
  exacto, sin reservar stock; al subir el límite, la misma orden confirmó
  normal (200). Documentado en el docstring de `sales/services.py`.
- Fase 2.5: contrato re-congelado — **54 rutas** (38 previas + 16 nuevas),
  retrocompatibilidad confirmada. `openapi-typescript` + `openapi-zod-client
  --export-schemas` regenerados; bug real corregido: `--export-schemas` ya
  expone su propio `export const schemas = {...}` antes del array
  `endpoints` — el recorte correcto es cortar solo lo que sigue después
  (Zodios/makeApi), no reconstruir un export propio.
- Fase 3 (frontend): `use-accounting.ts`, `AccountsPage` (Plan de Cuentas +
  Tasas de Impuesto + Mapeo documento→cuentas), `InvoicesPage`,
  `PaymentsPage`, **`CreditDebitNotesPage`** (las 4 páginas completas, con
  sus diálogos de creación/detalle y acciones post/cancel). Rutas y
  navegación agregadas.
- **Fase 4 (tests de integración frontend) — completa**: 4 tests nuevos,
  todos reales contra backend en `127.0.0.1:8000` sin mocks —
  `AccountsPage` (cuenta+tasa+mapeo), `InvoicesPage` (crear→contabilizar,
  asiento verificado), `PaymentsPage` (crear→asignar→contabilizar, saldo
  de factura verificado), `CreditDebitNotesPage` (crear relacionada a
  factura→contabilizar).
  **3 bugs reales encontrados y corregidos gracias a estos tests:**
  1. Bug de backend: `CreditDebitNoteService.post()` construía
     `document_type` como `f"{note.direction}_{suffix}"` → generaba
     `"sale_credit_note"` (inválido, con 'e') en vez de
     `"sales_credit_note"` — corregido con mapeo explícito
     dirección→prefijo (asimetría real entre `sale`→`sales_` pero
     `purchase`→`purchase_`, igual que en `sales_invoice`/
     `purchase_invoice`).
  2. Condición de carrera real en Vitest: los archivos de test corren en
     paralelo por defecto; como todos golpean el mismo Postgres
     compartido, dos suites configurando el mismo
     `document_account_mapping` (clave única) se pisaban entre sí.
     Corregido con `fileParallelism: false` en `vitest.config.ts`,
     documentado con la razón exacta — afecta a toda la suite de
     integración, no solo a accounting.
  3. Condición de carrera de UI: el diálogo de creación podía no terminar
     de desmontarse antes de que el test consultara la tabla (la lista se
     refresca por invalidación de query un instante antes de que el
     diálogo se cierre). Corregido en `CreditDebitNotesPage`,
     `InvoicesPage`, `PaymentsPage`, y retroactivamente en
     `SalesOrdersPage` (test preexistente del módulo 5 con el mismo
     patrón, que resultó ser flaky bajo el nuevo `fileParallelism:false`).
- `pytest tests/` → **50/50** en todo momento de este cierre, sin
  regresión. `npx vitest run` → **20/20** (16 previos + 4 nuevos).
  `npx tsc --noEmit` limpio, `npm run build` exitoso.
- **Regresión QA externa (sep-2026) — hallazgo real sobre el propio
  catálogo de regresión**: `catalogo_casos_regresion_erp_crm_v1.md`
  afirma "Ya existe `tests/test_accounting_module.py` de una sesión
  anterior — correrlo primero". Confirmado por búsqueda exhaustiva en el
  repo real (clonado de GitHub): **ese archivo no existía en ningún
  lado.** El catálogo estaba desactualizado o incorrecto en este punto —
  no se le creyó a ciegas, se verificó primero. Escrito desde cero
  (`tests/test_accounting_module.py`, 14 casos): ciclo completo factura
  venta/compra con asiento balanceado, las 4 combinaciones nota×dirección
  (`document_type` correcto, primer test de BACKEND para el bug ya
  corregido que antes solo se verificaba vía frontend), pago con
  asignación actualiza `balance_due`/`status`, asiento desbalanceado
  rechazado, documento sin mapeo de cuenta rechazado sin dejar asiento
  parcial, pago que excede el saldo real chequeado en `post()` (no en
  `create()`) con dos pagos "válidos" por separado, factura `posted` no
  se cancela directo, Motor de Contención Financiera con las 2
  condiciones (vencida/excedida) probadas AISLADAS una de otra (no solo
  combinadas), RLS. **Todo pasó en el primer intento real — el motor de
  asientos ya estaba bien construido, el gap era pura falta de cobertura
  de test, no bugs.** 14/14, 212/212 en la suite completa.

### Módulo 7 — pipeline de leads/oportunidades sobre contacts (spec 2.3,
8.0) — **Fases 1-4 completas**
- **Caso especial**: toda la funcionalidad de este módulo está clasificada
  [extendido, requiere paquete Administrativo] en spec 8.0 — a diferencia
  de purchasing/sales/accounting que tenían un subset [core]. Se construyó
  igual porque `modulos_erp_crm_v10_4.json` lo incluye como módulo real
  con dependencias (`depende_de: [2, 6]`).
- 3 entidades: `Stage` (etapas configurables por compañía — spec sección
  11, cambio central de v9: ya no hay pipeline fijo — `is_won`/`is_lost`
  marcan etapas terminales, CHECK `NOT(is_won AND is_lost)` a nivel de
  fila), `Opportunity` (vinculada a `Contact` existente, sin duplicar el
  concepto de "Lead" — DED-15), `Activity` (con o sin oportunidad
  asociada, para nutrir leads antes de calificar).
- DED-16: "al menos una etapa `is_won` y una `is_lost`" es una regla de
  conjunto validada en el servicio (`_get_terminal_stage`), no un
  constraint de fila.
- DED-17: **Lead scoring [extendido] explícitamente NO construido** —
  `Opportunity` no tiene campo de score; spec no da fórmula/config.
- DED-18/AMBIGUO: movimiento libre entre etapas NO terminales (kanban
  real), pero alcanzar una etapa terminal es un comando explícito
  (`close-won`/`close-lost`), no un simple cambio de `stage_id` — y una
  oportunidad cerrada no se mueve sin `reopen` primero. Verificado real:
  mover directo a etapa terminal vía `move-stage` fue rechazado (422);
  `close-won` funcionó y quedó bloqueada para `move-stage` después (409).
- **DED-19 — hallazgo estructural del proyecto**: este es el **primer
  módulo donde `require_package` (scaffoldeado desde el módulo 1, nunca
  antes usado en un router real) se aplica de verdad**. Verificado
  end-to-end: sin `company_packages` con `administrative` activo,
  cualquier ruta de `/pipeline/*` devuelve 403 `PACKAGE_NOT_LICENSED`;
  activándolo, las mismas rutas funcionan normal. Reutiliza el código de
  error genérico existente en vez de inventar
  `UNSUPPORTED_WITHOUT_ADMIN_PACKAGE` como string nuevo.
- RLS + `tenant_isolation` + grants verificados en las 3 tablas nuevas.
- Fase 2.5: contrato re-congelado — **63 rutas** (54 previas + 9 nuevas),
  retrocompatibilidad confirmada.
- Fase 3 (frontend): `use-pipeline.ts`, `PipelinePage` (kanban por
  columnas de etapa, sin drag-and-drop — movimiento vía diálogo),
  `CreateStageDialog`, `CreateOpportunityDialog`, `OpportunityDetailDialog`
  (mover etapa/cerrar ganada|perdida/reabrir/actividades).
- Fase 4: `PipelinePage.integration.test.tsx` — crea etapas (incluida una
  terminal "ganada") → crea oportunidad → la cierra ganada → verificado
  contra el backend real.
- `pytest tests/` → 50/50 en todo momento. `npx vitest run` → **13
  archivos, 21/21 tests** (20 previos + 1 nuevo). `npx tsc --noEmit`
  limpio, `npm run build` exitoso.
- **Observación de infraestructura de test, no de este módulo
  específicamente**: la suite de integración completa mostró
  intermitencia real en `AccountsPage.integration.test.tsx` bajo carga
  del sandbox (pasa en ~2.4s aislado, pero puede exceder 20s en una
  corrida completa bajo contención de recursos) — confirmado que NO es un
  bug determinístico (mismo código, a veces pasa a veces no en la misma
  sesión). Documentado como límite estructural conocido del enfoque de
  integración real sin fixtures aisladas ni entorno dedicado por test.
- **Regresión QA externa (sep-2026)**: `tests/test_pipeline_module.py`
  no existía (mismo gap que `accounting`, sin discrepancia documentada
  esta vez — STATE.md ya decía "verificado end-to-end" refiriéndose a
  una verificación manual por `curl`, no a un test persistido). Escrito
  desde cero, 10 casos: etapa no puede ser ganada Y perdida a la vez,
  crear oportunidad sobre `Contact` existente + movimiento libre entre
  etapas no terminales (ida y vuelta), no se puede crear directo en
  etapa terminal, no se puede mover directo a etapa terminal (exige
  `close_won`/`close_lost`), cierre ganado/perdido solo por comando
  explícito, **mover una oportunidad ya cerrada (ganada Y perdida, los 2
  casos) → rechazado**, reabrir vuelve a `open` en la primera etapa no
  terminal y limpia `closed_at`/`lost_reason`, actividad de otra
  compañía nunca visible, RLS. **Los 10 casos pasaron en el primer
  intento real, sin bugs encontrados.** 10/10, 222/222 en la suite
  completa.

### Módulo 8 — hr (spec 8.1, subset [core]) — **Fases 1-4 completas**
- Alcance: Legajo, Estructura Organizacional, Jerarquías. [extendido]
  fuera de este cierre: Nómina/Payroll (agrega dependencia real de
  `accounting`, ya construido, sin bloqueo técnico, pero Payroll en sí
  mismo no se construye), Control de Asistencia y Horarios, Ausencias y
  Vacaciones, Evaluación de Desempeño, Reclutamiento.
- 3 entidades: `Department` (auto-referencial `parent_department_id`),
  `Position` (pertenece a un `Department`), `Employee` (Legajo).
- DED-20: `Employee` es entidad propia, NO reutiliza `Contact` — a
  diferencia de "Lead" (que sí reutiliza `Contact.is_lead`), un empleado
  no es un contacto de negocio. Vínculo opcional a `User` vía `user_id`
  nullable para el caso común del propio dueño/admin también siendo
  empleado.
- DED-21: datos sensibles — permiso separado `hr:employee:read-sensitive`
  (ve `salary`) vs `hr:employee:read` (ve el resto sin salario). Nuevo
  helper reutilizable `user_has_permission()` en `core/dependencies.py`
  (chequeo "suave", no bloquea la request — a diferencia de
  `require_permission`) usado en el router para enmascarar `salary` a
  `None` si falta el permiso sensible. **Verificado end-to-end real**:
  creé un rol `HR Básico` sin ese permiso y un usuario con ese rol —
  `GET /hr/employees/{id}` le devolvió `salary: null`, mientras el admin
  vio `18000.00` completo.
- DED-22: "Jerarquías" con dos relaciones self-referenciales
  independientes — `Department.parent_department_id` (organigrama) y
  `Employee.manager_employee_id` (línea de reporte) — no tienen que
  coincidir.
- `EmployeeService.terminate()` probado real: primera baja exitosa
  (`status→terminated`), segundo intento sobre el mismo empleado
  rechazado con 409 `CONFLICT`.
- **Bug real preexistente encontrado y corregido durante este cierre**
  (no introducido por `hr`, pero recién expuesto porque ningún módulo
  anterior había creado un rol con `permission_ids` no vacío hasta ahora):
  `Role.permissions` en `core/models.py` apuntaba a `RolePermission` (la
  tabla de asociación) en vez de a `Permission` directamente —
  `RoleRead.model_validate(role)` fallaba con `AttributeError` (500) en
  cualquier rol con 1+ permisos, incluido el propio rol `admin`
  bootstrapeado (83 permisos). Corregido: `Role.permissions` ahora es
  `relationship(secondary="role_permissions", viewonly=True)` apuntando
  directo a `Permission`. Verificado: `GET /roles` funciona con el rol
  admin de 83 permisos y con roles limitados; `pytest` 50/50 sin
  regresión tras el fix (confirmado que la relación vieja solo se usaba
  en `models.py`/`schemas.py`, sin otros consumidores).
- RLS + `tenant_isolation` + grants verificados en las 3 tablas nuevas.
  `pytest tests/` → 50/50 en todo momento de este cierre.
- Fase 2.5: contrato re-congelado — **68 rutas** (63 previas + 5 nuevas
  agrupadas: `departments`, `positions`, `employees` con su acción
  `terminate`), retrocompatibilidad confirmada.
- Fase 3 (frontend): `use-hr.ts`, `EmployeesPage` (departamentos + puestos
  + legajos en una sola página de configuración, mismo patrón que
  `AccountsPage`), `CreateDepartmentDialog`, `CreatePositionDialog`,
  `CreateEmployeeDialog`, `EmployeeDetailDialog` (con acción `terminate`
  y el salario mostrado como "No visible con tu permiso actual" cuando el
  backend lo enmascaró). `tsc` limpio, `npm run build` exitoso.
- Fase 4: `EmployeesPage.integration.test.tsx` — crea departamento, puesto
  y empleado con salario desde la UI (visible para admin) → **además
  verifica el enmascarado real de DED-21 de punta a punta**: crea un rol
  sin `hr:employee:read-sensitive` y un usuario con ese rol, ambos dentro
  del propio test (sin asumir ids de permisos fijos — los resuelve
  dinámicamente vía el rol admin), hace login con ese usuario y confirma
  que `GET /hr/employees` le devuelve `salary: null` para el mismo
  empleado que el admin ve completo. Pasa a la primera.
- `npx vitest run` (suite completa) → **14 archivos, 22/22 tests** (21
  previos + 1 nuevo), confirmado en corrida limpia de 51s (una corrida
  intermedia mostró la misma intermitencia ya documentada de
  `AccountsPage` bajo carga del sandbox — no una regresión).
- **Regresión QA externa (sep-2026)**: `tests/test_hr_module.py` escrito
  desde cero (el catálogo ya documentaba correctamente este hueco, sin
  sorpresas). 7 casos, incluidos los 2 que el catálogo marcaba como "sin
  respuesta confirmada":
  1. **Jerarquía circular**: no hay una validación explícita que la
     rechace — es **estructuralmente imposible**, porque
     `EmployeeService` no tiene NINGÚN endpoint de actualización
     (`create`/`get`/`list`/`terminate` únicamente) y `manager_employee_id`
     solo puede apuntar a un empleado que ya existía antes. El resultado
     observable coincide con lo que pedía el catálogo (nunca hay un
     ciclo persistido), pero el mecanismo real es distinto de una regla
     de validación — es la ausencia total de un camino para actualizar
     el legajo después de crearlo.
  2. **Desactivar un jefe con subordinados**: confirmado que NO bloquea
     y NO reasigna — deja al subordinado con `manager_employee_id`
     apuntando a un empleado `terminated`, huérfano real, sin ninguna
     limpieza automática.
  3. `hr:employee:read-sensitive` (DED-21): confirmado con la función
     real del router (`user_has_permission`, no una reimplementación) —
     sin el permiso, `salary` viaja como `None` server-side (el campo
     existe en el JSON, pero enmascarado, nunca omitido ad-hoc ni
     filtrable client-side); con el permiso, viaja completo.
  **Gap de producto observado, no arreglado sin confirmar alcance**: no
  existe ningún endpoint para actualizar un `Employee` después de
  creado — ni reasignar `manager_employee_id`, ni cambiar `position_id`/
  `department`/`salary`. El legajo es efectivamente de solo
  alta+baja. Si esto es intencional para este cierre o un gap a cerrar
  como los de `core`/`contacts`, es una decisión de producto pendiente
  de confirmar, no algo que se decidió unilateralmente acá. 7/7, 229/229
  en la suite completa.
- **Instrucción explícita del usuario: cerrar el gap de arriba como
  corrección**, mismo criterio que `core`/`contacts`. `EmployeeService.
  update()` nuevo (`PATCH /hr/employees/{id}`) — reasigna
  `manager_employee_id`/`position_id`/`salary`/campos básicos. Con esto,
  la jerarquía circular deja de ser estructuralmente imposible (ya no es
  solo create+existencia previa) — así que ACÁ es donde corresponde la
  validación real que antes no hacía falta: recorrido hacia arriba por
  la cadena de managers del candidato, rechaza si vuelve a llegar al
  propio empleado (probado con ciclos de 2 y de 3 eslabones, y
  confirmado que extender una cadena válida sin ciclo sigue funcionando).
  Autoasignación como propio gerente rechazada explícita. No se puede
  editar un empleado ya `terminated`. `salary` gatea aparte
  (`hr:employee:update-sensitive`, permiso nuevo, mismo criterio que
  `contacts:contact:update_credit_limit` — chequeo a nivel router, no de
  servicio, mismo patrón que el enmascarado de lectura DED-21). 6 tests
  nuevos (13/13 en el archivo), 235/235 en la suite completa.

### `medical` (módulo 9 — Expediente Clínico, Agenda Médica, Consulta) — ✓ COMPLETO
- Paquete requerido: `medical` (`require_package("medical")` en todas las
  rutas, spec 2.4). Depende solo de `core`+`contacts` (spec 8.2) — sin
  dependencia de `Administrativo`.
- Paciente = `Contact.is_patient=true` — sin entidad `Patient` propia.
- **Rutas nuevas: 12** (80 rutas totales del sistema, 68 previas + 11 de
  Fase 2 + 1 agregada en Fase 3 — `GET /medical/appointments/{id}/
  consultation`, hueco real de Fase 2 expuesto por el frontend: no había
  forma de recuperar la consulta de una cita ya completada sin conocer su
  id de antemano):
  `POST/GET /medical/records`, `GET /medical/records/{id}`,
  `GET /medical/patients/{patient_contact_id}/records`,
  `POST/GET /medical/appointments`, `GET /medical/appointments/{id}`,
  `POST /medical/appointments/{id}/confirm`,
  `POST /medical/appointments/{id}/reschedule`,
  `POST /medical/appointments/{id}/cancel`,
  `GET /medical/appointments/{id}/consultation`,
  `POST /medical/consultations`, `GET /medical/consultations/{id}`,
  `POST /medical/consultations/{id}/correct`.
- Cifrado en reposo (pgcrypto, spec 8.2 [core]): `pgp_sym_encrypt`/
  `pgp_sym_decrypt` vía `sqlalchemy.func`, clave = `settings.pgcrypto_key`
  (variable de entorno, DED-24-KEY — ver AMB-KEY más abajo). Cifrados:
  `ClinicalRecordEntry.content`, `Consultation.diagnosis_text`,
  `Consultation.physical_exam`, `Consultation.treatment_plan`. En claro:
  `Consultation.diagnosis_cie10` (código estandarizado), `Appointment.
  reason`/`cancellation_reason` (no es diagnóstico ni nota clínica).
  **Verificado en Fase 4**: la columna cruda en Postgres nunca contiene el
  texto plano (test explícito por cada entidad cifrada).
- Versionado "nunca se sobrescribe" (spec 8.2): `previous_entry_id`
  (`ClinicalRecordEntry`), `previous_consultation_id`/`superseded_by_id`
  (`Consultation`). Sin endpoints UPDATE/DELETE. El invariante "una sola
  consulta vigente por cita" se garantiza con `SELECT ... FOR UPDATE`
  (bloqueo de fila real), no con constraint — ver hallazgo de Fase 4 en
  DED-25 (sección 4) y en la migración `1669f8fbbc6b`.
- Bloqueo de horario real: `EXCLUDE USING gist` (`btree_gist`) sobre
  `(professional_user_id, tstzrange(scheduled_start, scheduled_end, '[)'))`
  para citas `scheduled`/`confirmed`. **Verificado con test de
  concurrencia real** (8 inserts simultáneos para el mismo profesional/
  horario traslapado → exactamente 1 gana).
- RBAC clínico "own patients" vs "read-all": `medical:record:read-all` /
  `medical:consultation:read-all` pasa siempre; sin ese permiso, se exige
  `...:read-own-patients` Y que el actor tenga al menos una `Appointment`
  con ese paciente (`professional_has_treated`, sin tabla de asignación
  paciente↔profesional separada).
- Auditoría: TODO acceso de lectura (`GET` de entrada de expediente, lista
  por paciente, consulta) pasa por `AuditService.log_event` con
  `correlation_id`, sin excepción (spec 8.2). Verificado en Fase 4.
- "Profesional" = `User` directamente (DED-23) — sin entidad
  `Practitioner` separada. TODO si se necesita agendar personal sin
  cuenta de login.
- **Fase 4 backend**: `tests/test_medical_module.py` — 15 tests nuevos
  (65/65 total, sin regresión) contra Postgres real desde una base
  recreada de cero (`DROP DATABASE`→`CREATE DATABASE`→`alembic upgrade
  head`, mismo patrón de verificación limpia que `pipeline`). Cubre:
  cifrado a nivel de fila cruda (2 tests), versionado sin sobrescritura
  (Expediente y Consulta), bloqueo de horario con concurrencia real,
  confirmar/reprogramar/cancelar cita, "una consulta por cita" +
  corrección, consulta requiere cita activa, RBAC "own patients"
  (`professional_has_treated`), y aislamiento RLS cross-tenant.
- **Fase 3 (frontend) — completa.** `use-medical.ts` (hooks de React
  Query), `CreateAppointmentDialog.tsx`, `AppointmentDetailDialog.tsx`
  (confirmar/reprogramar/cancelar + registrar/ver/corregir consulta
  inline), `MedicalPage.tsx` (Agenda + Expediente Clínico por paciente
  con corrección de entradas). Ruta `/medical` y nav "Médico" registrados.
  `MedicalPage.integration.test.tsx`: flujo completo real (agendar →
  confirmar → registrar consulta con diagnóstico) + **verificación RBAC
  real contra la API** (un usuario con `medical:consultation:read-own-
  patients` sin `-all`, que nunca atendió al paciente, recibe 403 real al
  pedir la consulta directamente — no solo "no se muestra en la UI",
  mismo patrón que el test de enmascarado de `salary` en `hr`).
- **AMB-KEY** (pgcrypto, spec 1.1 — 5 campos obligatorios, DEDUCIBLE por
  defecto ante ausencia de gestor de secretos declarado):
  `key_location=variable de entorno (settings.pgcrypto_key, .env local)`,
  `rotation_period_days=sin rotación definida`, `owner=Roberto`,
  `rekey_plan=no definido — TODO si se confirma requisito regulatorio`,
  `backup_policy=hereda backup de la base completa, sin backup separado
  de la clave`. **Sigue AMBIGUO en un punto no resuelto por el default**:
  período de retención regulatoria del log de auditoría clínico (AMB-02,
  sección 4) — Roberto no lo ha confirmado todavía.

### `notifications` (módulo 26 — Transversal) — ✓ COMPLETO
- **Sin `require_package`** — disponible para cualquier compañía sin
  importar el paquete contratado (spec 2.2: los paquetes verticales
  *usan* `notifications`, no la *habilitan*).
- **Rutas nuevas: 6** (86 rutas totales del sistema, 80 previas + 6):
  `POST/GET /notifications/templates`, `PATCH /notifications/templates/
  {code}`, `POST /notifications/send`, `GET /notifications`,
  `POST /notifications/{id}/read`, `POST /notifications/read-all`.
- Motor de Correos (DED-27): interfaz real (`EmailSender`) con
  implementación de desarrollo (`LoggingEmailSender`) que registra el
  envío (`email_status='logged_only'`) en vez de entregarlo — el sandbox
  de este proyecto no tiene salida de red hacia ningún proveedor SMTP/API
  (misma limitación que `ui.shadcn.com`/`cdn.playwright.dev`). Producción
  reemplaza la clase inyectada, el resto del módulo no cambia.
- Plantillas Dinámicas (DED-29): reemplazo de `{variable}` con
  `str.Formatter.vformat` + diccionario que no lanza `KeyError` en
  variables faltantes — sin Jinja2 (evita SSTI en contenido que puede
  incluir texto de usuario en `context`).
- Notificación siempre dirigida a un `User` interno (DED-28) — mensajería
  a `Contact` (confirmación de pedido, recordatorio de cita) es
  responsabilidad de cada módulo consumidor (`sales`, `medical`), no de
  este motor genérico.
- Sin RBAC de lectura granular — `GET /notifications` siempre filtra por
  `recipient_user_id = actor.id`; "leer notificaciones de otro usuario"
  no existe como concepto.
- **Hallazgo real de regeneración de contrato**: `openapi-zod-client`
  emite `z.record(valueSchema)` (firma Zod v3, un solo argumento) para
  `dict[str, str]` — Zod v4 (instalado en este proyecto) exige
  `z.record(keySchema, valueSchema)`, 2 argumentos. Parche puntual
  documentado in situ en `schemas.ts` (`NotificationSend.context`) —
  mismo tipo de ajuste que ya existía para el cliente Zodios descartado,
  ahora también necesario dentro de los schemas que sí se conservan.
- 11 tests backend nuevos (76/76 total). Frontend: `NotificationBell.tsx`
  (campana global en `AppLayout`, contador de no leídas, poll cada 30s —
  sin WebSocket/SSE, TODO si se necesita push real-time) +
  `NotificationsPage.tsx` (gestión de plantillas + envío manual).
  `NotificationsPage.integration.test.tsx`: crea y edita una plantilla,
  envía por plantilla con contexto real, y verifica que la campana
  refleja el no leído y que marcarla como leída persiste contra el
  backend — no solo un cambio visual.
- Bootstrap del entorno de test (`bootstrap_admin.py`) corregido en este
  cierre: ya no asume `company_id=1` — busca "El Roble" por nombre (el id
  real depende de cuántas filas consumió la secuencia antes del
  bootstrap, ej. tests de pytest corridos previamente).

### `medical` — recetas (módulo 10) — ✓ COMPLETO
- Vive en el mismo paquete Python `app/medical/` que el módulo 9 (mismo
  dominio "Médico", mismo router con prefijo `/medical` — no cada módulo
  de la tabla es una carpeta/router nueva, ver spec sección 10).
- **Rutas nuevas: 4** (90 rutas totales, 86 previas + 4):
  `POST /medical/prescriptions`, `GET /medical/prescriptions/{id}`,
  `GET /medical/patients/{patient_contact_id}/prescriptions`,
  `POST /medical/prescriptions/{id}/void`.
- Cabecera (`Prescription`) + líneas (`PrescriptionLine`, DED-31) — una
  receta casi siempre lleva más de un medicamento.
- `dispensing_status` (`not_applicable | pending | dispensed`) calculado
  al emitir según si el paquete `pharmacy` está activo para la compañía
  (`pending` si sí, `not_applicable` si no) — Farmacéutico aún no se
  construyó en este proyecto; cuando se construya, ese módulo es quien
  transiciona `pending -> dispensed`, no `medical`.
- **Sin cifrado pgcrypto** en `PrescriptionLine` (DED-32) — spec 8.2
  limita el cifrado explícitamente a diagnóstico/notas de Consulta, no a
  Recetas; se siguió la spec al pie de la letra en vez de extender el
  alcance por iniciativa propia.
- Inmutable con anulación (`void` + motivo obligatorio), no edición —
  mismo patrón que documentos `confirmed`/`cancelled` del resto del ERP
  (DED-33) — a diferencia de Expediente Clínico/Consulta, la spec no
  exige "nunca se sobrescribe" para Recetas.
- RBAC clínico idéntico a `records`/`consultations`:
  `medical:prescription:read-all` vs `...:read-own-patients` +
  `professional_has_treated`.
- 5 tests backend nuevos (81/81 total): múltiples líneas por receta,
  `dispensing_status` según paquete `pharmacy`, anulación con guardia de
  doble-anulación, listado por paciente cruzando 2 consultas distintas,
  receta sobre consulta inexistente. **Todos al primer intento** — sin
  hallazgos reales de lógica en Fase 4 esta vez.
- Frontend: sección "Recetas" integrada dentro de
  `AppointmentDetailDialog.tsx` (aparece una vez hay consulta
  registrada) — emitir con líneas dinámicas (agregar/quitar
  medicamento), anular con motivo. `MedicalPage.integration.test.tsx`
  extendido con el flujo completo (emitir → verificar
  `dispensing_status` real contra el backend → anular → verificar que
  persiste).

### `medical` — laboratorio (módulo 11) — ✓ COMPLETO
- **Rutas nuevas: 6** (96 rutas totales, 90 previas + 6):
  `POST/GET /medical/lab-orders`, `GET /medical/lab-orders/{id}`,
  `GET /medical/patients/{patient_contact_id}/lab-orders`,
  `POST /medical/lab-order-tests/{id}/result`,
  `POST/GET /medical/lab-order-tests/{id}/attachments`,
  `GET /medical/attachments/{attachment_id}/download`.
- Cabecera (`LabOrder`) + líneas (`LabOrderTest`, DED-34) — mismo
  criterio que Recetas. Orden y resultado viven en la misma fila
  (transición `pending -> resulted`, DED-35) — sin tabla `LabResult`
  separada. La orden pasa a `completed` automáticamente cuando todas sus
  pruebas tienen resultado (transición derivada, no pedida por el actor).
- Marcado de valor crítico (`is_critical`) **explícito** (checkbox al
  cargar el resultado), no inferido automáticamente comparando contra el
  rango de referencia (DED-36) — los rangos llegan en formatos
  heterogéneos ("70-100 mg/dL", "<5 UI/L", "Negativo") sin una unidad
  normalizada por prueba que permita un parseo confiable sin un catálogo
  de pruebas — fuera de alcance de este cierre.
- **Primer uso real de la tabla `core.Attachment`** (existía desde el
  módulo 1, nunca antes conectada a nada). Se construyó
  `AttachmentService` (`app/core/services.py`) — genérico por
  `entity_type`/`entity_id`, pero **sin** un endpoint `POST /attachments`
  universal: cada módulo consumidor expone su propio endpoint anidado
  (`POST /medical/lab-order-tests/{id}/attachments`) que llama al
  servicio con un `entity_type` fijo después de verificar su propio RBAC
  — evita la superficie de un endpoint que deja adjuntar archivos a un
  `entity_id` de un módulo ajeno sin pasar por su control de acceso.
  Almacenamiento en disco local (`attachment_storage_root`, config) —
  DEDUCIBLE por ausencia de proveedor de object storage real en el
  sandbox, mismo criterio que `EmailSender` en `notifications`.
- **Hallazgo real de Fase 4**: la orden no transicionaba a `completed`
  tras resultar la última prueba pendiente — la causa fue que este
  proyecto usa `AsyncSession(autoflush=False)` (decisión de Fase 1 de
  `core`) y el chequeo "¿todas las pruebas están resulted?" hacía un
  `SELECT` nuevo que no veía el cambio recién hecho en memoria sobre la
  prueba actual. Corregido con un `await db.flush()` explícito antes del
  chequeo — no es la primera vez que este patrón (`autoflush=False`)
  exige un flush explícito en el proyecto, pero sí la primera vez que un
  test lo atrapó en vivo.
- 5 tests backend nuevos (86/86 total): múltiples pruebas por orden,
  orden completa automáticamente cuando se resultan todas, resultado no
  se puede cargar dos veces, ida y vuelta real de un adjunto (escribir a
  disco + leer de vuelta, con `monkeypatch` sobre `attachment_storage_
  root` para no ensuciar el filesystem real en tests), orden sobre
  consulta inexistente.
- Frontend: sección "Laboratorio" integrada en `AppointmentDetailDialog`
  (misma ubicación que "Recetas") — ordenar múltiples pruebas, cargar
  resultado con checkbox de crítico, adjuntar/descargar archivo. Se
  agregaron dos helpers nuevos a `api-client.ts` que no existían:
  `apiUploadFile` (multipart — `apiRequest` solo serializa JSON) y
  `apiDownloadFile` (blob autenticado — un `<a href>` normal no manda el
  header `Authorization`). `MedicalPage.integration.test.tsx` extendido
  con el flujo completo (ordenar → cargar resultado crítico → verificar
  contra el backend).

### `medical` — teleconsulta (módulo 12) — ✓ COMPLETO
- **Rutas nuevas: 5** (101 rutas totales, 96 previas + 5):
  `POST /medical/teleconsultations`, `GET /medical/teleconsultations/{id}`,
  `GET /medical/appointments/{appointment_id}/teleconsultation`,
  `POST /medical/teleconsultations/{id}/start`,
  `POST /medical/teleconsultations/{id}/end`.
- `TeleconsultationSession` vinculada directamente a una `Appointment`
  (no a una `Consultation`, a diferencia de Recetas/Laboratorio) — la
  spec dice explícitamente "vinculada a una cita de Agenda". La sección
  del frontend aparece independiente de si ya existe una consulta.
- **La spec exige integración con proveedor externo real (Twilio/Daily)
  y prohíbe explícitamente implementar WebRTC propio** salvo pedido
  explícito (DED-37) — el sandbox no tiene salida de red hacia ningún
  proveedor de videollamada. Interfaz real `TeleconsultationProvider`
  (`create_room`/`end_room`) con implementación de desarrollo
  (`DevStubTeleconsultationProvider`) que genera una URL de sala local
  determinística sin llamar a ningún proveedor — producción inyecta un
  cliente real detrás de la misma interfaz, el resto del módulo no
  cambia. Mismo patrón que `EmailSender` (notifications) y
  `AttachmentService` (medical — laboratorio).
- Una sola sesión activa (`scheduled`/`active`) por cita a la vez — sin
  índice único parcial (mismo motivo ya documentado en DED-25: no es
  diferible en Postgres), garantizado con el chequeo dentro de la misma
  transacción de creación.
- Sin grabación/almacenamiento de video (DED-39) — la spec pide "sala de
  videollamada", no grabación, y grabar consultas médicas tiene
  implicaciones regulatorias de consentimiento sin resolver en ningún
  AMB de este proyecto. Solo se guarda metadata de la sesión.
- 6 tests backend nuevos (92/92 total): generación de URL de sala, uso de
  un proveedor inyectado (doble de prueba, no el real), una sola sesión
  activa por cita, no se puede crear sobre una cita cancelada, ciclo de
  vida completo iniciar/finalizar con verificación de que el proveedor
  inyectado recibe la llamada de cierre, "última sesión por cita" cuando
  hay más de una a lo largo del tiempo. **Todos al primer intento.**
- Frontend: sección "Teleconsulta" en `AppointmentDetailDialog` (crear
  sala, abrir enlace, iniciar, finalizar) — visible ya con la cita sola,
  sin esperar a que exista una consulta. `MedicalPage.integration.test.tsx`
  extendido con el flujo completo (crear → iniciar → finalizar,
  verificado contra el backend en cada transición).

### `medical` — facturación médica básica (módulo 13) — ✓ COMPLETO
- **Rutas nuevas: 3** (104 rutas totales, 101 previas + 3):
  `POST /medical/billing`, `GET /medical/consultations/{id}/billing`,
  `POST /medical/billing/{id}/cancel`.
- "Si `accounting` está activo" (spec) se interpreta como "el paquete
  `administrative` está activo para la compañía" (DED-40) — no existe
  activación granular por sub-módulo dentro de un paquete (spec 2.4).
- Un solo `amount` por consulta, sin líneas de conceptos (DED-41) — la
  spec dice "recibo/factura por consulta", no un desglose facturable.
- Cuando `administrative` está activo, se reutiliza el motor de asientos
  real de `accounting` (`InvoiceService.create_draft`+`.post()`, sección
  7.1) con `source_document_type='medical_consultation'` — **sin
  duplicar lógica de facturación dentro de `medical`** (DED-42). Esto
  implica que el `Contact` del paciente debe tener `is_customer=true`
  para poder facturarlo — regla general del ERP que `medical` no
  desactiva ni asume en silencio; se propaga el mismo error que
  cualquier otro intento de facturar a un contacto sin ese flag.
- Cuando `administrative` NO está activo, genera un `MedicalBillingRecord`
  en modo `simple_receipt` — numeración atómica real
  (`DocumentNumberingService`, doc_type='medical_receipt') pero sin
  asiento contable, declarado como TODO explícito (spec) si el cliente
  activa Administrativo más tarde.
- 5 tests backend nuevos (97/97 total) — **primer test del proyecto que
  cruza `medical` con el motor de asientos real de `accounting`**:
  comprobante simple cuando `administrative` inactivo, factura real
  contabilizada cuando está activo (con Plan de Cuentas + mapeo mínimo
  construidos en el propio test, ya que no hay ningún seed automático),
  rechazo de un segundo comprobante activo para la misma consulta,
  anular y volver a facturar permitido, consulta inexistente. **Todos
  al primer intento.**
- **Hallazgo real de Fase 3 (frontend)**: el primer intento del test de
  integración asumía el camino `simple_receipt`, pero la compañía de
  prueba compartida ya tiene `administrative` activo desde el bootstrap
  — el camino real es `accounting_invoice`, que además exige
  `is_customer=true` en el contacto (mismo comportamiento que cualquier
  otra factura, no un bug). El test se ajustó para reflejar el
  comportamiento real: crea Plan de Cuentas + mapeo mínimo y activa
  `is_customer` en el paciente antes de facturar.
- Frontend: sección "Facturación" en `AppointmentDetailDialog` — emitir
  comprobante, anular con motivo. `MedicalPage.integration.test.tsx`
  extendido con el flujo completo, verificando contra el backend que la
  factura quedó realmente contabilizada (`invoice_id` presente, no solo
  un estado visual).

### `medical` — portal / mensajería paciente-médico (módulo 14) — ✓ COMPLETO
- **Rutas nuevas: 3** (107 rutas totales, 104 previas + 3):
  `POST /medical/messages`, `GET /medical/patients/{patient_contact_id}/messages`,
  `POST /medical/messages/{id}/read`.
- `notifications` (módulo 26) es Transversal en este proyecto — sin
  `require_package`, siempre disponible sin importar el paquete
  contratado (DED-43). La rama de la spec "si `notifications` no está
  activo, hilo mínimo sin avisos" nunca se ejecuta en este sistema tal
  como está construido: cada mensaje `sender_role='patient'` dispara
  siempre una notificación in-app real al profesional tratante.
- **Sin autenticación de pacientes** (DED-44) — este proyecto nunca
  construyó login para `Contact`. Los mensajes con `sender_role='patient'`
  se registran por personal clínico en nombre del paciente (transcripción
  de llamada/correo) — `author_user_id` (siempre un `User` real,
  autenticado) es distinto de `sender_role` (de parte de quién habla el
  mensaje). TODO explícito: portal con autenticación propia del paciente,
  fuera de alcance de este cierre.
- Aviso automático de "resultados de laboratorio disponibles" (mencionado
  como caso de uso en la spec) **NO** se integró con el cierre de una
  `LabOrder` del módulo 11 en este cierre, para no reabrir/modificar
  código ya cerrado y probado — declarado como TODO explícito.
- 4 tests backend nuevos (101/101 total): mensaje de profesional a
  paciente NO genera notificación (evita ruido — el profesional que
  escribe no necesita que se le notifique a sí mismo), mensaje de
  paciente SÍ genera notificación real (verificado contra la tabla
  `notifications`, no solo que el servicio no lanzó error), orden
  cronológico + marcar leído, mensaje sobre contacto sin `is_patient`
  rechazado. Todos al primer intento.
- Frontend: sección "Mensajes" en `MedicalPage.tsx` (bajo el selector de
  paciente compartido con Expediente Clínico, no dentro de una cita
  específica — la mensajería es a nivel paciente, no a nivel consulta),
  con poll cada 30s (mismo criterio que `NotificationBell`).
  `MedicalPage.integration.test.tsx` con un test nuevo: envía un mensaje
  de parte del paciente, verifica contra el backend que la notificación
  real se generó para el profesional correcto, y marca el mensaje como
  leído verificando que persiste.

### `medical` — reserva pública de citas (módulo 15) — ✓ COMPLETO, backend + widget verificados contra Postgres real

> **Nota de verificación externa (sep-2026, sesión posterior a la
> escritura del módulo — Postgres real, base recreada de cero, no
> simulado)**: los 4 puntos del checklist original ya se corrieron y
> están en verde. `alembic upgrade head` corre limpio con `a1c4f0e2b9d7`
> sobre las 25 migraciones previas; `pytest tests/test_medical_module.py`
> pasa completo, **7 tests reales de este módulo, no 9** (el número
> original era incorrecto — corregido acá y en el punto 5 de esta
> sección); `contracts/openapi.json` quedó recongelado contra el
> servidor real (136 rutas / 170 operaciones en esa pasada, luego 139/174
> tras el módulo 25). Esa misma corrida encontró y corrigió, de paso, un
> bug real preexistente en `test_ecommerce_module.py` sin relación con
> este módulo — ver la sección `website`/`ecommerce`/`reports` más abajo
> y el README.
>
> **Punto 4 (frontend), cerrado en una sesión posterior**: se construyó
> `public-widgets/medical-booking/widget.js` — vanilla JS sin
> dependencias, deliberadamente fuera de `frontend/` (ver su propio
> `README.md` para el razonamiento completo: es para el sitio público,
> no el panel administrativo, mismo argumento que ya usó `ecommerce` para
> no construir su storefront). Verificado end-to-end contra Postgres real
> con un arnés en `jsdom` + `fetch` nativo de Node (sin mocks, simulando
> un navegador real): carga de disponibilidad, selección de día/horario,
> envío del formulario y confirmación exitosa; más dos casos límite
> reales — (a) condición de carrera genuina (se intercepta la petición
> del widget justo antes de que salga, se reserva el mismo horario por
> otra vía, y se confirma que el widget muestra un mensaje claro de
> conflicto y queda en un estado usable, no colgado), y (b) compañía sin
> `medical`/`web` licenciado (mensaje amigable, no un error técnico). Con
> esto el módulo pasa a `✓ COMPLETO`.
>
> Checklist original de cierre real (histórico, dejado para contexto):
> 1. ~~Migrar (`a1c4f0e2b9d7`, agrega `appointments.booked_via_public_widget`).~~
> 2. ~~Correr `pytest tests/test_medical_module.py` (sección módulo 15).~~
> 3. ~~Congelar `contracts/openapi.json` (2 rutas nuevas).~~
> 4. ~~Decidir y construir la superficie de frontend real (a diferencia de
>    `medical` 9-14, este módulo no tiene página interna propia).~~

- **Última pieza de la tabla de módulos de Médico** — `depende_de: [9,
  22]` (Agenda Médica + `website`). Ya no estaba bloqueado desde que se
  cerró `website` (módulo 22); se construye en esta sesión.
- **Sin tablas nuevas**: reutiliza `Appointment` (módulo 9) por completo.
  Única adición al esquema: `booked_via_public_widget: bool` (DEDUCIBLE,
  no pedido explícitamente por la spec) — distingue una cita creada por
  el widget de una creada por personal de recepción, mismo criterio
  retroactivo que `reserved_quantity`/`credit_limit` en cierres
  anteriores. Puramente informativo, no cambia ninguna máquina de
  estados ni ninguna regla de negocio existente.
- **Gating combinado, no cubierto por ningún patrón previo**: la spec
  describe la misma integración desde dos lados (8.2 "requiere Web
  activo"; 8.4 "requiere Médico activo") — el gating real exige AMBOS.
  Ni `require_package` (JWT) ni `website.ensure_web_package_active`
  (un solo paquete) servían tal cual; se creó
  `medical.dependencies.ensure_public_booking_active`, que además
  bloquea `suspended` en cualquiera de los dos paquetes (spec 13 —
  crear una cita es una escritura, no solo lectura, a diferencia de
  `ensure_web_package_active` que solo bloquea `deactivated`).
- **Reutiliza el bloqueo de horario real de `AppointmentService`**
  (`EXCLUDE USING gist`, DED-26) en vez de duplicar la lógica de
  concurrencia — `PublicBookingService.create` construye el
  `Appointment` directamente pero captura el mismo `IntegrityError` de
  `excl_appointments_professional_overlap` con un mensaje orientado al
  público (\"otra persona lo reservó primero\"), no al mensaje interno.
- **DED-58 (nueva)**: `Contact` del paciente resuelto/creado por email
  con el mismo criterio de deduplicación que
  `website.FormSubmissionService._find_or_create_lead_contact` (DED-46)
  — si ya existe un `Contact` con ese email en la compañía, se reutiliza
  y se le agrega `is_patient=true` sin pisar sus otros flags (`is_lead`/
  `is_customer` si ya los tenía); sin email, siempre se crea uno nuevo
  (`PublicBookingCreate` exige email O teléfono, no ambos).
- **DED-59 (nueva)**: el endpoint de disponibilidad
  (`GET .../busy-slots`) devuelve solo `scheduled_start`/`scheduled_end`
  de citas `scheduled`/`confirmed` — nunca `patient_contact_id`, motivo,
  ni ningún otro campo de `Appointment`. Es una ruta anónima (sin JWT);
  exponer PHI ahí sería una fuga real, no un simple descuido de forma.
  Citas `cancelled`/`no_show`/`completed` no bloquean el horario.
- **DEDUCIBLE, no confirmado por Roberto**: no se validó que
  `professional_user_id` corresponda a un `User` real "agendable"
  (ej. con algún rol clínico) antes de aceptar la reserva — mismo
  criterio que el `AppointmentService.create` interno (módulo 9), que
  tampoco lo valida más allá de la FK. La spec no describe un catálogo
  de "profesionales publicables"; se asume que la página que embebe el
  widget ya sabe qué `professional_user_id` mostrar (ej. inyectado por
  `website.Page.content`, sin construir un directorio público de
  personal — decisión deliberada por privacidad, no solo por alcance).
- **AMB-06, nueva, no confirmado por Roberto**: si el widget necesita
  poder listar profesionales bookeables por sí mismo (en vez de que la
  página que lo embebe ya conozca el id), haría falta un endpoint
  público adicional y probablemente un flag "visible públicamente" en
  algún lado — no construido en este cierre, fuera del alcance mínimo
  de la spec (que solo pide "lee disponibilidad... y crea la cita").
- **7 tests backend** (`tests/test_medical_module.py`, sección módulo
  15) — **verificados en verde contra Postgres real** (ver nota al
  inicio de esta sección; el número original documentado era 9, no 7 —
  corregido acá):
  crea contacto nuevo por email, reutiliza contacto existente sin pisar
  flags, rechaza traslape de horario (mismo `ConflictError` que el
  interno), exige email o teléfono, filtra disponibilidad por
  traslape y excluye citas canceladas, gating requiere ambos paquetes
  (2 tests: bloquea sin ambos activos, bloquea `suspended`).
- **Frontend: construido en `public-widgets/medical-booking/`**
  (`widget.js` + `demo.html` + `README.md`), fuera de `frontend/` a
  propósito. A diferencia de los módulos 9-14 (que viven dentro de
  `MedicalPage`/`AppointmentDetailDialog` del panel interno), este es un
  widget para el **sitio público**, no para el panel administrativo —
  mismo argumento que ya usó `ecommerce` (módulo 23) para no construir
  el storefront ("carrito y checkout... son, por diseño, un frontend
  separado, no parte de este panel administrativo"). Vanilla JS sin
  dependencias ni build step (tiene que poder pegarse en cualquier HTML,
  incluido el `content` de una `Page` de `website` — spec 8.4: "el mismo
  motor de páginas/formularios aloja el widget"). Decisiones de diseño
  documentadas en su propio `README.md`: sin directorio público de
  profesionales (TODO-46, sigue abierto — un `<div>` por profesional),
  horario laboral resuelto en el widget vía `data-*` (la API pública
  nunca expone configuración de agenda, solo ocupación real), fechas en
  hora local del navegador con ISO 8601 + offset al backend (la ruta
  pública no expone `Company.timezone`). Servir el archivo estático
  (Nginx/CDN/bucket público) queda fuera de este cierre — es una
  decisión operativa de cada entorno de cliente, no del código.
- Bootstrap: sin cambios — El Roble ya tenía `web` y `medical` activos
  desde los cierres de esos módulos, y las rutas públicas no llevan
  RBAC (anónimas por diseño).

### `website` (módulo 22) — ✓ COMPLETO (verificado vía CI: pytest + e2e, ver nota abajo)

> **Nota de verificación externa (posterior a la escritura de website,
> ecommerce y reports — GitHub Actions, jobs `pytest` + `e2e`, Postgres y
> servidor reales, no simulados)**: los tres módulos de este paquete
> (22/23/24) pasaron completos — 137/137 tests backend, `alembic upgrade
> head` limpio, `npm run build` + `npx vitest run` completo (16 archivos
> de integración del frontend) contra el servidor vivo, y
> `contracts/openapi.json` re-congelado a 134 rutas / 168 operaciones
> reales. En el camino se encontró y corrigió un **BUG REAL sistémico**
> (permisos de secuencia de Postgres faltantes desde el módulo `hr`, ver
> migración `1d9a25acd918` y el resumen rodante más abajo) — no era
> específico de ningún módulo de este paquete, pero solo se manifestó al
> insertar en una tabla de `ecommerce` como `erp_app` real. El resto de
> las decisiones DEDUCIBLE/AMBIGUO documentadas en cada sección de abajo
> (DED-45..51, AMB-03..05) siguen abiertas — la verificación externa
> confirma que el código corre correctamente, no resuelve las preguntas
> pendientes para Roberto.

> A diferencia de todo lo demás en este documento, este cierre **no pasó
> por el DoD real** (spec 11): se escribió backend + frontend completos
> siguiendo al pie los contratos y patrones ya establecidos, pero el
> entorno donde se hizo no tenía Postgres, acceso a red (ni `pip install`
> ni `npm install` funcionaron — confirmado, no asumido), ni
> `node_modules` instalado. **No confundir `△` con `✓`** — no se corrió
> `pytest`, no se corrió `npm run build`/`vitest`, y el contrato
> (`contracts/openapi.json`) NO se re-congeló porque eso requiere un
> servidor real corriendo. Antes de marcar este módulo `(✓)` en la
> sección 1, alguien con un entorno real tiene que:
> 1. Levantar Postgres + correr las migraciones (incluye `be79a5e3b927`).
> 2. Correr `pytest tests/test_website_module.py tests/test_core_module.py`
>    (el segundo por el fix de `require_package`, ver hallazgo abajo).
> 3. Levantar el servidor, congelar `contracts/openapi.json`
>    (`curl http://127.0.0.1:8000/openapi.json`), correr
>    `npx openapi-typescript` + `npx openapi-zod-client --export-schemas`,
>    y **borrar `frontend/src/lib/website-temp-contract.ts`**,
>    reemplazando sus usos en `use-website.ts`/`WebsitePage.tsx` por los
>    tipos/schemas generados reales.
> 4. Correr `npm run build` (chequeo de tipos) y
>    `npx vitest run src/pages/WebsitePage.integration.test.tsx`.

- **Rutas nuevas: 10** (117 rutas totales, 107 previas + 10): panel interno
  (`POST/GET /website/pages`, `GET/PATCH /website/pages/{id}`,
  `POST /website/pages/{id}/publish`, `POST /website/pages/{id}/unpublish`,
  `GET /website/form-submissions`, `GET /website/form-submissions/{id}`) +
  storefront público sin JWT (`GET /public/website/{company_id}/pages/{slug}`,
  `POST /public/website/{company_id}/forms`).
- Depende solo de Núcleo (spec 8.4) — sin tocar `inventory` ni ningún
  paquete vertical. La dependencia `depende_de: [22, 3, 5, 6]` que el JSON
  declara para `ecommerce` (23) es una relación de paquete comercial, no
  una dependencia de código real de `website` — ver
  `diseno_modulos_22_25_erp_crm.md` sección 1.
- **DEDUCIBLE**: `Page` con dos estados (`draft`/`published`), sin flujo
  de aprobación editorial — no confirmado por Roberto, extensión aditiva
  si hace falta un tercer estado más adelante.
- **DEDUCIBLE**: `FormSubmission` busca un `Contact` existente por email
  dentro de la compañía antes de crear uno nuevo (evita duplicar leads);
  si ya existe y no era `is_lead`, se marca `is_lead=true` sin pisar otros
  flags (`is_customer`, etc.) — mismo criterio de "no duplicar el
  concepto" que DED-15 (`pipeline` reutiliza `Contact`, no un modelo
  `Lead` aparte).
- **AMBIGUO, no confirmado por Roberto**: cómo resuelve el storefront
  público el `company_id` de cada request en producción (subdominio,
  dominio propio, header). Implementado con `company_id` explícito en la
  URL (`/public/website/{company_id}/...`) — funcionalmente correcto y
  suficiente para levantar el módulo, pero casi seguro no es el mecanismo
  final. Cambiarlo el día que se confirme solo debería tocar
  `website/dependencies.py`/`routers.py` (rutas públicas), no
  `services.py` ni los modelos.
- **Gating de paquete**: `require_package("web")` a nivel de router para
  el panel interno (JWT); las rutas públicas usan
  `ensure_web_package_active()` (mismo criterio de error
  `PACKAGE_NOT_LICENSED`, sin duplicar la lógica de dominio de
  `get_active_packages`) porque `require_package` depende de JWT, que una
  request anónima del storefront no tiene.
- **BUG REAL encontrado y corregido en `core/dependencies.py`** (afecta a
  todo el proyecto, no solo a `website`): la condición de `minimal_module`
  en `require_package()` tenía código muerto (`row.package != package`
  siempre era `False`, porque `row` sale de `packages.get(package)`) — el
  chequeo nunca bloqueaba nada, para ningún llamador, desde que se
  escribió. No se había detectado porque ningún router real usaba
  `minimal_module=` todavía (`pipeline` y `medical` lo usan sin ese
  parámetro). Corregido con la semántica correcta (lista vacía/`None` =
  compra completa, pasa cualquier submódulo; lista no vacía = solo pasa si
  el submódulo está en la lista). Test de regresión agregado en
  `tests/test_core_module.py`. Directamente relevante para el gating de
  `ecommerce` (módulo 23, ver `diseno_modulos_22_25_erp_crm.md` sección
  2.1) — sin este fix, ese diseño no se podía implementar de forma segura.
- Bootstrap: paquete `web` activado para la compañía de prueba (El Roble)
  y 8 permisos nuevos (`website:page:*`, `website:form_submission:*`)
  agregados a `scripts/bootstrap_admin.py`.
- 7 tests backend escritos (`test_website_module.py`, sin contar) + 1 test
  de regresión en `test_core_module.py` — **NO ejecutados** (ver nota al
  inicio de esta sección).
- Frontend: `WebsitePage.tsx` (dos secciones: Páginas y Formularios
  recibidos), `hooks/use-website.ts`, ruta `/website` + ítem de nav
  "Sitio Web" en `AppLayout.tsx`. Usa
  `frontend/src/lib/website-temp-contract.ts` — **shim temporal hecho a
  mano**, NO viene de codegen (ver nota al inicio de esta sección para el
  motivo y el TODO de reemplazo). `WebsitePage.integration.test.tsx`
  escrito, **NO ejecutado**.

### `ecommerce` (módulo 23) — ✓ COMPLETO (verificado vía CI: pytest + e2e, ver nota abajo)

> Misma advertencia que `website` arriba — backend completo + página de
> configuración en el panel interno, pero **no ejecutado** contra Postgres
> ni frontend real (sin acceso a red/DB/Node en el entorno de escritura).
> No confundir `△` con `✓`. Checklist de cierre real: migrar
> (`355c2d2ae36f`), correr `pytest tests/test_ecommerce_module.py`, congelar
> contrato + codegen real (y borrar
> `frontend/src/lib/ecommerce-temp-contract.ts`), `npm run build` +
> `vitest run src/pages/EcommercePage.integration.test.tsx`.

- **Rutas nuevas: 9** (126 rutas totales, 117 previas + 9): panel interno
  (`POST/GET/PATCH /ecommerce/settings`) + storefront público sin JWT
  (`GET /public/ecommerce/{company_id}/catalog`,
  `POST /public/ecommerce/{company_id}/carts`,
  `GET /public/ecommerce/{company_id}/carts/{cart_id}`,
  `POST /public/ecommerce/{company_id}/carts/{cart_id}/items`,
  `POST /public/ecommerce/{company_id}/carts/{cart_id}/checkout`,
  `POST /public/ecommerce/{company_id}/webhooks/{gateway}`).
- **No se inventó un modelo `Order` paralelo**: el checkout crea
  directamente una `sales.SalesOrder` real vía
  `SalesOrderService.create_draft(..., _skip_commit=True)` — misma
  transacción que actualizar el `Cart` (mismo patrón que
  `QuoteService.convert_to_order`, módulo 5).
- **Gating de paquete resuelto** (cierra el AMBIGUO de
  `diseno_modulos_22_25_erp_crm.md` sección 2.1, con una solución más
  simple de lo que ese documento anticipaba): `require_package("web",
  minimal_module="ecommerce")` + `require_package("administrative",
  minimal_module="sales")` — reutiliza el campo `minimal_modules` ya
  existente sin necesidad de una variante nueva de `require_package` (el
  fix del bug de módulo 22 ya le dio la semántica correcta: lista vacía/
  `None` = compra completa = pasa cualquier submódulo). El bootstrap de El
  Roble no necesitó tocarse — ya tenía `web` y `administrative` con
  `minimal_modules=None` (compra completa), que bajo la semántica
  corregida ya cubre `ecommerce` y `sales` sin arrastre explícito.
- **HALLAZGO REAL no anticipado en el diseño**: `sales.SalesOrder`
  requiere `warehouse_id` obligatorio, y `inventory.Warehouse` no tiene
  ningún campo "por defecto" — sin configurar cuál almacén despacha los
  pedidos online, el checkout no tiene forma de armar la orden. Se agregó
  `EcommerceSettings` (una fila por compañía: `default_warehouse_id`,
  `default_price_list_id`, `webhook_secret`) — el checkout falla con
  `ValidationError` explícito si no está configurada, en vez de adivinar
  un almacén.
- **DEDUCIBLE**: catálogo público = productos activos que tengan precio
  en la lista de precios resuelta (`EcommerceSettings.default_price_list_id`
  o, si no está seteada, la `PriceList` con `is_default=true`) — un
  producto sin esa entrada simplemente no aparece, no es un error.
- **DEDUCIBLE**: el precio de cada línea se re-verifica en el checkout
  contra `PriceListService.get_price` (reutilizado de `sales`, sin
  reimplementar la resolución por quiebre de cantidad) en vez de copiar
  `CartItem.unit_price_snapshot` — un carrito puede quedar abierto un
  buen rato antes de pagarse.
- **DEDUCIBLE, simplificación explícita**: verificación de firma de
  webhook con HMAC-SHA256 y un secreto por compañía
  (`EcommerceSettings.webhook_secret`), no el esquema propio de cada
  pasarela real — no se integró ningún SDK de Stripe/PayPal/MercadoPago
  en este cierre (spec 8.4 no especifica cuál usar). El payload esperado
  del webhook es un contrato propio simplificado
  (`{event_id, sales_order_id, status}`); un adaptador real traduciría el
  webhook nativo de cada pasarela a esta forma — TODO explícito.
- **LIMITACIÓN CONOCIDA, documentada en el propio código**
  (`WebhookService.handle_payment_event`): confirmar la orden, facturar y
  contabilizar, y registrar el `PaymentGatewayEvent` de deduplicación NO
  son atómicos entre sí — `SalesOrderService.confirm` e
  `InvoiceService.create_draft`/`.post` hacen su propio commit interno y
  no exponen `_skip_commit`. Si el proceso se cae entre confirmar la
  orden y registrar el evento, un reintento legítimo de la pasarela
  chocaría con `ConflictError`. TODO explícito: agregar `_skip_commit` a
  esos servicios para poder envolver todo en una sola transacción, igual
  que se hizo en `CheckoutService.checkout()`.
- **No se integró notificación al cliente** en la confirmación de pago —
  `notifications` (módulo 26) solo notifica `User` internos, no `Contact`
  externos; no existe canal de email transaccional al cliente en este
  proyecto. TODO explícito, no una omisión silenciosa (el diseño original
  en `diseno_modulos_22_25_erp_crm.md` asumía —incorrectamente— que se
  podía reusar el mismo patrón que `medical` → `notifications`, módulo
  14; ese patrón notifica personal interno, no aplica acá).
- Bootstrap: `EcommerceSettings` creada para El Roble (sin
  `default_warehouse_id`/`default_price_list_id` — un admin real los
  configura después) y 2 permisos nuevos (`ecommerce:settings:read`,
  `ecommerce:settings:update`).
- 7 tests backend (`test_ecommerce_module.py`) — **verificados en verde
  contra Postgres real** (sesión de verificación externa sep-2026; ver
  nota al inicio de esta sección). Dos gaps reales encontrados y
  corregidos en el camino, ninguno un problema del entorno:
  1. El fixture `store` no configuraba `DocumentAccountMapping` para
     `sales_invoice` antes de que el webhook contabilizara la factura.
     Corregido agregando `_setup_sales_invoice_account_mappings` al
     fixture (mismo patrón que `test_medical_module.py`).
  2. Con ese fix ya aplicado, `test_webhook_confirms_order_and_posts_invoice`
     seguía fallando — esta vez por `ConflictError: Stock disponible
     insuficiente` al confirmar la orden vía webhook
     (`SalesOrderService.confirm` → `StockService.reserve`), porque el
     fixture `store` nunca le daba stock físico al producto de prueba
     (`quantity=0` desde su creación). Corregido agregando una entrada de
     stock real (`StockService.record_movement`, `movement_type=entrada`,
     cantidad 50) al fixture. Este segundo bug no tenía relación con la
     contabilización y no estaba documentado antes de esta sesión.
- Frontend: solo `EcommercePage.tsx` (configuración de almacén/lista de
  precios por defecto) + `hooks/use-ecommerce.ts` — el catálogo, carrito
  y checkout del storefront público son, por diseño, un frontend
  *separado* (spec 10), no parte de este panel administrativo. Usa
  `frontend/src/lib/ecommerce-temp-contract.ts` (shim temporal, mismo
  motivo que `website-temp-contract.ts`). `EcommercePage.integration.test.tsx`
  escrito, **NO ejecutado**.

### `reports` (módulo 24) — ✓ COMPLETO (verificado vía CI: pytest + e2e, ver nota abajo)

> Misma advertencia que `website`/`ecommerce` arriba. Checklist de cierre
> real: `pip install openpyxl reportlab` (dependencias nuevas, ver
> `requirements.txt` — **tampoco instaladas/verificadas** en este
> entorno), migrar (`57990ab9bc72`), correr
> `pytest tests/test_reports_module.py`, congelar contrato + codegen real
> (borrar `frontend/src/lib/reports-temp-contract.ts`), `npm run build`.
> Sin test de integración de frontend para esta página (a diferencia de
> `website`/`ecommerce`) — recorte explícito de alcance de este cierre por
> tiempo, no un olvido.

- **Rutas nuevas: 8** (134 rutas totales, 126 previas + 8):
  `GET /reports/metrics`, `GET /reports/metrics/{key}/data`,
  `GET /reports/metrics/{key}/export`,
  `POST/GET /reports/dashboards`, `GET/PATCH/DELETE /reports/dashboards/{id}`.
- **DEDUCIBLE**: "Dashboards Interactivos" se modeló con los widgets
  embebidos en una columna JSONB de `Dashboard` (`widgets: list[dict]`),
  no como una tabla `DashboardWidget` separada — spec no especifica la
  granularidad; alcanza para dashboards con varios widgets sin el costo
  de un CRUD anidado completo.
- **"Reportes Cruzados" implementado como whitelist de 4 métricas
  predefinidas** (`app/reports/metrics.py`), nunca SQL arbitrario desde
  el cliente (spec 5): `sales_by_customer`, `top_products_by_revenue`,
  `accounts_receivable_open`, `stock_by_warehouse`. Cada consulta filtra
  `company_id` explícito en el SQL, no solo confía en RLS (un `GROUP BY`
  con un JOIN mal filtrado sería un fallo silencioso de aislamiento entre
  compañías mucho más difícil de notar que en una consulta de un solo
  registro — segunda capa de defensa, no la única).
- **Gating de paquete**: `require_package("administrative")` completo,
  sin `minimal_module` — decisión tomada (no solo propuesta) porque
  `reports` es una capa de negocio sobre datos del Administrativo, a
  diferencia de `notifications` (infraestructura transversal, exenta de
  gating). **AMBIGUO, no confirmado por Roberto** — ver AMB-05 abajo.
- **TODO explícito, fuera de alcance de este cierre**: ninguna métrica
  cruza `medical`/`pharmacy` — cruzar esos paquetes exigiría validar el
  paquete de origen de cada dominio tocado antes de exponer el resultado
  (`diseno_modulos_22_25_erp_crm.md` sección 3.1), no solo el paquete
  `administrative` que gatea el router en general.
- **Exportación**: CSV con stdlib (`csv`, sin dependencia nueva); XLSX vía
  `openpyxl`; PDF vía `reportlab` con una tabla simple (`Table`/
  `SimpleDocTemplate`) — ambos agregados a `requirements.txt`, sin
  instalar/verificar en este entorno. Los tres formatos generan el
  archivo completo en memoria antes de responder (sin streaming) —
  aceptable con el `LIMIT 50` de la métrica más grande; si una métrica
  futura puede devolver miles de filas, esto necesita revisarse.
- No se agregaron permisos nuevos al bootstrap más allá de los propios
  del módulo (`reports:metric:read`, `reports:export:run`,
  `reports:dashboard:*`) — El Roble ya tenía `administrative` con compra
  completa, así que no hizo falta tocar `company_packages`.
- 12 tests backend escritos (`test_reports_module.py`, incluye los 3 de
  exportación que dependen de `openpyxl`/`reportlab` sin instalar) —
  **NO ejecutados**. **Corrección posterior (sesión de verificación)**:
  los 4 tests que usan el fixture `sales_fixture` (`test_sales_by_customer_metric`,
  `test_top_products_by_revenue_metric`, `test_accounts_receivable_open_metric`,
  `test_stock_by_warehouse_metric`) tenían el mismo gap real que
  `ecommerce` arriba — `InvoiceService.post` sin `DocumentAccountMapping`
  configurado. Corregido con el mismo helper. Sigue pendiente correr
  `pytest` real para confirmarlo.
- Frontend: `ReportsPage.tsx` (explorador de métricas con rango de
  fechas + exportación, y sección de dashboards) + `hooks/use-reports.ts`.
  Reutiliza `apiDownloadFile` ya existente en `lib/api-client.ts` (mismo
  mecanismo que la descarga de adjuntos de `medical`) para las
  descargas — no se inventó un mecanismo nuevo. Usa
  `frontend/src/lib/reports-temp-contract.ts` (shim temporal, mismo
  motivo que los anteriores). **Sin test de integración escrito** para
  esta página — recorte de alcance explícito por tiempo.
### `pharmacy` — dispensación + verificación clínica (módulo 16) — ✓ COMPLETO
- **Primer módulo del paquete Farmacéutico** — `depende_de: [1, 2, 3, 6]`
  (Núcleo, contacts, inventory, accounting mínimos), NO depende de
  `medical` aunque se integra con él si está activo.
- **Rutas nuevas: 7** (114 rutas totales, 107 previas + 7):
  `POST/GET /pharmacy/dispensations`, `GET /pharmacy/dispensations/{id}`,
  `GET /pharmacy/patients/{patient_contact_id}/dispensations`,
  `POST /pharmacy/dispensations/{id}/void`,
  `POST/GET/DELETE /pharmacy/controlled-substances`,
  `GET /pharmacy/controlled-substances/log`.
- **FEFO real (DED-45)**: `inventory` (módulo 3) dejó FEFO/FIFO/LIFO
  explícitamente fuera de su propio cierre — su docstring lo declara TODO
  explícito. `pharmacy` es el primer módulo que lo necesita de verdad, y
  lo implementa consumiendo las primitivas ya reales de `inventory`
  (`Lot.expiry_date`, `StockLevel`, `StockService.ship`) sin tocar el
  módulo 3 ya cerrado/probado. Una cantidad que excede un solo lote
  genera automáticamente varias `DispensationLine` (una por lote).
- Sustancias Controladas (DED-46): tabla propia de `pharmacy`
  (`ControlledSubstanceProduct`, FK a `inventory.Product`) en vez de
  agregar una columna a un módulo ajeno. Libro de registro append-only
  (`ControlledSubstanceLogEntry`) generado automáticamente.
- Verificación Clínica (DED-47, revisado en Fase 3 — ver hallazgo abajo):
  se consulta el expediente médico real solo si `medical` está activo
  **y** el contacto tiene `is_patient=true`; en cualquier otro caso se
  exige el formulario mínimo de alergias (`allergy_check_notes`).
- Paciente/cliente de farmacia = cualquier `Contact`, sin exigir
  `is_patient=true` (DED-48) — un cliente de mostrador no es
  necesariamente un paciente de `medical`.
- POS Farmacia (DED-49): reutiliza la misma `DispensationOrder` (una
  venta de mostrador es una dispensación con `prescription_id=NULL`),
  no una entidad separada — evita duplicar FEFO/verificación/controladas.
- Anular NO revierte el descuento de inventario (DED-50) — la spec no
  describe un flujo de devolución. TODO explícito.
- 11 tests backend nuevos (112/112 total): FEFO consume el lote que
  vence antes, división automática entre lotes cuando uno no alcanza,
  stock insuficiente → 409, formulario de alergias obligatorio sin
  `medical`, receta requiere `medical` activo, venta de mostrador con
  cobro, sustancia controlada genera entrada en el libro (y una NO
  controlada no genera nada), anular no restituye stock + doble-anulación
  bloqueada, orden inexistente → 404, aislamiento RLS cross-tenant.
  **Todos al primer intento.**
- **Hallazgo real de Fase 3 (frontend)**: el primer intento del test de
  integración fallaba en silencio (sin excepción visible) — al reproducir
  la petición directo con `curl` contra el backend real (en vez de seguir
  ajustando el test a ciegas) apareció el error real: `medical` estaba
  activo para la compañía de prueba compartida, así que `pharmacy`
  intentaba consultar el expediente médico del cliente — pero ese cliente
  de farmacia no tenía `is_patient=true` (correcto, según DED-48), y
  `ClinicalRecordService` exige ese flag. Corregido: el chequeo contra el
  expediente médico ahora requiere `medical` activo **y**
  `patient.is_patient=true`; en cualquier otro caso cae al formulario
  mínimo, sin importar si `medical` está activo o no.
- **Efecto colateral real de activar `pharmacy` en el fixture
  compartido**: el test de `medical` (`MedicalPage.integration.test.tsx`)
  verificaba `dispensing_status == 'not_applicable'` para una receta
  recién emitida — con `pharmacy` ahora activo en la compañía de prueba,
  el valor correcto pasó a ser `'pending'` (DED-30, medical — recetas).
  No era una regresión: el test viejo verificaba el estado correcto para
  el fixture de ESE momento; se actualizó para reflejar el fixture actual.
- Frontend: `PharmacyPage.tsx` — dispensación/POS con líneas dinámicas de
  medicamento, gestión de sustancias controladas (marcar/desmarcar +
  libro de registro visible). `PharmacyPage.integration.test.tsx`: FEFO
  real verificado end-to-end (dos lotes con vencimiento distinto, se
  confirma cuál se consumió), marcar sustancia controlada, y verificar
  que la segunda dispensación sí generó una entrada real en el libro.

### `pharmacy` — interacciones medicamentosas (módulo 17) — ✓ COMPLETO, VERIFICADO contra Postgres real

> Cubre la parte "Interacciones [extendido]" del módulo 17 — la parte
> "Sustancias Controladas [core]" ya había quedado cubierta dentro del
> cierre del módulo 16 (DED-49). Recibido como ZIP separado, ramificado
> de un estado del repo previo a los módulos 15 y 25 — mismo patrón de
> merge que el módulo 25 (ver su nota de merge más abajo): se copiaron
> sin conflicto los archivos exclusivos de este módulo, se aplicó a mano
> el único cambio real sobre un archivo ya tocado (`bootstrap_admin.py`,
> 2 permisos nuevos), y se reencadenó la migración nueva (`67040fb9b867`)
> de `down_revision=1d9a25acd918` a `f3b6a1d9c204` (el head real en
> `main` a esa altura) — documentado en la propia migración.
>
> **A diferencia de los módulos 15 y 25, esta migración no tuvo que
> corregirse**: ya incluía `GRANT SELECT, INSERT, UPDATE, DELETE ON
> product_active_ingredients TO erp_app` y `GRANT USAGE, SELECT ON
> SEQUENCE product_active_ingredients_id_seq TO erp_app` desde el primer
> intento, con un comentario propio citando explícitamente el bug
> sistémico de `1d9a25acd918` como el motivo. Verificado contra Postgres
> real (sesión de verificación externa, sep-2026): `alembic upgrade
> head` corre limpio con `67040fb9b867` sobre las 27 migraciones
> previas; `pytest tests/test_pharmacy_module.py` pasa completo, **158/158
> tests en total** desde el primer intento, sin ningún bug propio de este
> módulo que corregir; `contracts/openapi.json` recongelado contra el
> servidor real (142 rutas / 177 operaciones); `npx vitest run` en verde
> (19/19 archivos, 29/29 tests — ver el diagnóstico real, no relacionado
> con este módulo, de una flakiness histórica de `AccountsPage`/
> `StockPage` en `LOG_EJECUCION.md`, sección de esta misma sesión).

- **2 tablas nuevas**:
  - `product_active_ingredients` — multi-tenant, RLS estándar
    (`tenant_isolation`, `company_id`), único `(company_id, product_id)`
    — qué principio activo tiene cada producto DE ESTA compañía.
  - `drug_interaction_reference_entries` — catálogo GLOBAL, sin RLS,
    sin `company_id` (DED-53, mismo criterio que `permissions`: un
    catálogo de referencia clínica no varía por compañía). Sin endpoint
    de escritura pública — se administra por seed/migración, no por API
    (mismo criterio que `permissions`). Seed fijo de 15 pares conocidos
    y reales (DED-51, pedido explícito de Roberto — no una API externa),
    con severidad `moderate`/`major`, siempre en orden alfabético
    (`ingredient_a < ingredient_b`, check constraint) para que el lookup
    de un par sea determinista sin importar en qué orden se pasen los
    dos principios activos.
- **3 rutas nuevas**: `POST/GET /pharmacy/products/active-ingredients`
  (mapear/listar principio activo por producto),
  `POST /pharmacy/interactions/check` (chequear interacciones entre un
  conjunto de productos, resolviendo sus principios activos primero).
  2 permisos nuevos (`pharmacy:interaction:manage`,
  `pharmacy:interaction:check`) agregados a `scripts/bootstrap_admin.py`.
- **Frontend**: `PharmacyPage.tsx` extendido (sección de interacciones),
  `use-pharmacy.ts` extendido. A diferencia de `website`/`ecommerce`/
  `reports`/`audit` (que usan un `*-temp-contract.ts` hecho a mano en vez
  de tocar el cliente tipado "real"), este módulo sí actualizó
  `frontend/src/lib/generated/{api-types,schemas}.ts` directamente —
  ambos enfoques conviven en el proyecto; no hay codegen automático real
  todavía (ver nota en la sección `website` sobre ese TODO).

### `pharmacy` — aseguradoras / copagos (módulo 18) — ✓ COMPLETO, VERIFICADO contra Postgres real

> Recibido junto con el módulo 17 en el mismo ZIP (`erp-crm-modular-main.zip`,
> sin sufijo de número — ramificado justo después de `67040fb9b867`).
> Mismo patrón de merge que los anteriores: archivos exclusivos copiados
> sin conflicto, migración `a3f8c1d9e0b2` ya encadenada correctamente
> tras el módulo 17 sin necesidad de reencadenar. Ya traía los `GRANT`
> de tabla y secuencia correctos desde el principio, con comentario
> propio citando `1d9a25acd918` — igual que el módulo 17, este autor ya
> conocía el bug sistémico. Verificado junto con los módulos 20/21 en la
> misma corrida (ver su nota de cierre conjunto más abajo, en
> `LOG_EJECUCION.md`, y el resumen en el README).

- **3 tablas nuevas**: `insurance_providers` (aseguradoras con las que
  trabaja la farmacia), `patient_insurance_policies` (póliza de un
  paciente con una aseguradora, número de póliza, % de copago),
  `insurance_claims` (ciclo de vida completo: `submitted` → `approved`/
  `rejected` → `paid`, con su propia factura y pago reales vía
  `InvoiceService`/`PaymentService` al aprobarse — no un monto simulado).
- **Endpoints**: administración de aseguradoras y pólizas, más el ciclo
  de vida del reclamo (`submit`/`approve`/`reject`/`pay`). 2 permisos
  nuevos (`pharmacy:insurance:manage`, `pharmacy:insurance:claim`).

### `pharmacy` — MTM / consulta farmacéutica (módulo 21) — ✓ COMPLETO, VERIFICADO contra Postgres real

> Recibido junto con el módulo 20 en el mismo ZIP
> (`erp-crm-modular-main-modulo20.zip`), ramificado directo del estado
> ya verificado de los módulos 15/25 (`f3b6a1d9c204`), sin conocer
> todavía los módulos 17/18 (que para entonces ya estaban en `main`).
> Reencadenado de `down_revision=f3b6a1d9c204` a `down_revision=a3f8c1d9e0b2`
> (tip real de la cadena de farmacia a esa altura: 17→18) para mantener
> una sola cadena lineal — documentado en la propia migración
> (`b7e2f5a13c68`).
>
> **A diferencia de los módulos 17 y 18, esta migración SÍ tuvo el bug
> sistémico de `1d9a25acd918`** (sin `GRANT` sobre `pharmacy_mtm_sessions`/
> `pharmacy_mtm_billing_records` ni sus secuencias) — corregido antes de
> correr contra Postgres real por primera vez, así que nunca llegó a
> fallar en un pytest real. También se encontró un bug real en el propio
> test de cierre (`test_mtm_session_close_with_administrative_posts_real_invoice`):
> no configuraba `DocumentAccountMapping` antes de que `close()` (con
> `administrative` activo) contabilizara una factura real — mismo patrón
> ya visto en `test_ecommerce_module.py`/`test_reports_module.py`,
> corregido con el mismo helper ya existente en este archivo.

- **2 tablas nuevas**: `pharmacy_mtm_sessions` (sesión de consulta
  farmacéutica: revisión de medicación, adherencia, efectos adversos,
  recomendaciones, tarifa), `pharmacy_mtm_billing_records` (facturación
  de la sesión — `accounting_invoice` si `administrative` está activo,
  `simple_receipt` si no, mismo desacople clínico/financiero que
  `consultations`/`medical_billing_records` de `medical`, DED-62).
- **Endpoints**: crear/cerrar/cancelar sesión, ver facturación, cancelar
  registro de facturación. 2 permisos nuevos
  (`pharmacy:mtm_session:create`, `pharmacy:mtm_session:read`).

### `pharmacy` — reposición a droguerías (módulo 20) — ✓ COMPLETO, VERIFICADO contra Postgres real

> Mismo ZIP y mismo reencadene que el módulo 21 (de hecho
> `c4d8b3f61a97` ya venía correctamente encadenado tras `b7e2f5a13c68`
> en el ZIP original — solo hizo falta reencadenar el punto de partida
> de todo el par, no cada uno por separado). **Mismo bug sistémico de
> `GRANT` faltante que el módulo 21**, sobre `pharmacy_reorder_points` —
> corregido igual, antes de la primera corrida real.
>
> **Bug real de merge, no del módulo**: al fusionar el parche de este
> módulo contra el árbol que ya tenía los módulos 17/18/25 mezclados, el
> merge automático (`patch --fuzz=5`) produjo dos artefactos que hubo
> que corregir a mano — una función de `pharmacy/services.py`
> (`ControlledSubstanceLogService.list`, del módulo 16 original) quedó
> con su `return` cortado a mitad, generando un `SyntaxError` real al
> compilar, y un bloque de 3 permisos de `audit` quedó duplicado en
> `bootstrap_admin.py`, causando `UniqueViolationError` real al correr
> `bootstrap_admin.py` contra Postgres. Ambos son ruido de la
> herramienta de parcheo, no error de ningún autor de módulo — se
> detectaron porque `pytest`/`bootstrap_admin.py` fallaron de verdad
> contra Postgres real, no por inspección visual del diff.
>
> También apareció un bug real, genuino, en
> `PharmacyPage.integration.test.tsx` (el test original de dispensación,
> del módulo 16): dejó de pasar porque este módulo agrega un segundo
> selector con `aria-label="Sucursal"` en la misma pantalla (para el
> formulario de puntos de pedido), y el test buscaba por esa etiqueta
> sin acotar la búsqueda a su propia sección. Corregido con `within()`,
> scopeado a la sección "Dispensación / Venta de mostrador" por su
> encabezado.
>
> Con los tres módulos (18/20/21) y sus fixes: `pytest tests/` en
> **185/185**, 31 migraciones limpias de punta a punta,
> `contracts/openapi.json` recongelado (162 rutas / 200 operaciones),
> `npx vitest run` en **19/19 archivos, 30/30 tests**. Detalle completo
> de la corrida en `LOG_EJECUCION.md`.

- **1 tabla nueva**: `pharmacy_reorder_points` (punto de pedido y
  cantidad de reposición por `(company_id, product_id, warehouse_id)`).
- **Endpoints**: CRUD de puntos de pedido, listar sugerencias de
  reposición (calculadas: stock disponible bajo el punto configurado),
  y generar una orden de compra real en `purchasing` desde una
  sugerencia — **requiere el paquete Administrativo completo** (spec
  8.3: sin él, "la sugerencia queda como lista exportable sin flujo de
  aprobación", DED-66). 2 permisos nuevos
  (`pharmacy:reorder_point:manage`, `pharmacy:reorder_point:read`).
- **TODO cerrado (sesión posterior, sep-2026)**: se escribió
  `PharmacyPage.insurance-mtm-reorder.integration.test.tsx`, cubriendo
  el ciclo completo de MTM (crear → cerrar y facturar), Aseguradoras
  (aseguradora → póliza → reclamo → enviar → aprobar → pagar, contra
  una dispensación real) y Reposición (configurar punto de pedido). Sin
  bugs de la app — dos ajustes al propio test (el paciente de MTM
  necesita `is_customer=true`, y hay que configurar los mapeos
  contables antes de correr el archivo en aislamiento).

### `audit` — paquete completo (módulo 25) — ✓ COMPLETO, VERIFICADO contra Postgres real

> **Nota de verificación externa (sep-2026, sesión posterior a la
> escritura del módulo)**: se instaló Postgres real ad-hoc y se corrió
> el módulo por primera vez. `alembic upgrade head` corre limpio con
> `f3b6a1d9c204` sobre las 26 migraciones previas (incluida `a1c4f0e2b9d7`,
> módulo 15); `pytest tests/test_audit_module.py` pasa 5/5;
> `contracts/openapi.json` quedó recongelado contra el servidor real
> (139 rutas / 174 operaciones, incluidas las 3 de este módulo);
> `npx vitest run` completo (19/19 archivos, 28/28 tests, aunque este
> módulo no tiene su propio archivo de test de integración de frontend
> — ver TODO nuevo más abajo). Se encontraron y corrigieron **dos bugs
> reales**, ninguno relacionado con el módulo 15:
>
> 1. **Test chocaba con el propio trigger de inmutabilidad que este
>    módulo documenta.** El helper `_log` de `test_audit_module.py`
>    insertaba un evento de auditoría y LUEGO intentaba
>    `UPDATE audit SET created_at = ...` para simular un evento "viejo"
>    sin esperar días reales (necesario para probar la ventana de
>    retención). Pero `trg_audit_immutable` (módulo 1, spec 8.0) bloquea
>    **cualquier** UPDATE/DELETE sobre `audit` incondicionalmente — el
>    mismo comportamiento que `app/audit/models.py` describe
>    explícitamente en su docstring (AMB-07) como la razón por la que la
>    "Depuración" real necesita `scripts/purge_audit.py` fuera de la
>    capa de aplicación. El test nunca podía pasar tal como estaba
>    escrito, contra Postgres real, con el rol de runtime real (`erp_app`,
>    sin bypass de RLS ni de trigger). Corregido: cuando se necesita
>    backdatear, se construye el `AuditLog` con `created_at` ya fijado
>    ANTES del único INSERT (el trigger no bloquea INSERT, solo
>    UPDATE/DELETE) — se deja de pasar por `AuditService.log_event` (que
>    a propósito no expone ese parámetro; la app real nunca backdatea un
>    evento) solo para ese caso.
> 2. **GRANT de tabla faltante, real, sistémico.** La migración
>    `f3b6a1d9c204` nunca otorgó a `erp_app` permisos sobre la tabla
>    nueva `audit_retention_policies` ni sobre su secuencia. El
>    comentario original de la migración asumía —incorrectamente— que el
>    `GRANT` sistémico de `1d9a25acd918` (que solo cubre secuencias
>    existentes al momento en que corre) más el `GRANT ... ON ALL TABLES`
>    de la migración inicial (que tampoco cubre tablas futuras: este
>    proyecto NUNCA configuró `ALTER DEFAULT PRIVILEGES`) ya dejaban
>    cubierta cualquier tabla nueva. Es el mismo patrón de bug que
>    `1d9a25acd918` ya documentó para secuencias, aquí aplicado a una
>    tabla — y, a diferencia de aquella vez, nadie lo había ejercitado
>    todavía contra Postgres real como `erp_app` (ni pytest ni ningún
>    cierre previo insertaban en esta tabla). `erp_app` fallaba con
>    `InsufficientPrivilegeError: permission denied for table
>    audit_retention_policies` en el primer SELECT/INSERT real. Corregido
>    agregando `GRANT SELECT, INSERT, UPDATE, DELETE ON
>    audit_retention_policies TO erp_app` y `GRANT USAGE, SELECT ON
>    audit_retention_policies_id_seq TO erp_app` a la propia migración
>    `f3b6a1d9c204`, en vez de una migración de reparación aparte (a
>    diferencia de `1d9a25acd918`, que sí necesitó ser una migración
>    nueva porque el bug de secuencias ya estaba desplegado en cierres
>    previos — este se corrigió en la misma migración porque el módulo
>    25 nunca había llegado a `main` todavía).
>
> **Diseño real, documentado sin resolver en silencio (AMB-07)**: la
> "Depuración" (borrado físico de filas vencidas de `audit`) no puede
> ejecutarse desde la capa HTTP de la API — el trigger de inmutabilidad
> bloquea el DELETE incluso para `erp_app`, que no es dueño de la tabla
> y no puede desactivar el trigger. `scripts/purge_audit.py` existe para
> esto: corre fuera de la API, con credenciales elevadas (el rol
> `postgres`/admin dueño de la tabla), y usa la misma lógica de
> `AuditRetentionService` para calcular qué filas son candidatas antes
> de un DELETE directo.
>
> **Corrido de punta a punta contra Postgres real (sesión posterior,
> sep-2026)**: se sembraron eventos de auditoría vencidos reales
> (incluido uno `medical.*`, para confirmar la exclusión), se fijó una
> política de retención agresiva vía la API, y se confirmó que
> `--dry-run` reporta el mismo conteo que
> `GET /audit/retention-policy/purge-eligible`. El borrado real (con
> confirmación interactiva `BORRAR`) eliminó exactamente las filas
> vencidas no-clínicas, dejó intacto el evento `medical.*` y cualquier
> fila dentro de la ventana de retención, y reactivó el trigger de
> inmutabilidad al terminar (confirmado con un `DELETE` manual posterior
> contra esa misma fila, que volvió a fallar con el mismo error que
> antes de correr el script). **Bug real encontrado y corregido**: con
> `--company-id`, fallaba con `psycopg.errors.AmbiguousColumn` — el
> filtro SQL interpolado (`company_filter`) usaba `company_id` sin
> calificar en una consulta que hace JOIN entre `audit` y
> `audit_retention_policies` (ambas tienen esa columna). Corregido
> calificando como `a.company_id` en las 3 consultas donde se interpola.
>
> Eventos `medical.*` quedan protegidos de la política de retención
> configurable sin importar cuántos días se configuren — ver
> `AuditQueryService.MEDICAL_EVENT_PREFIX` en `app/audit/services.py` y
> la nota en `AuditRetentionPolicy.retention_days` (spec 8.1, explícito:
> la retención regulatoria clínica nunca depende de esta configuración).
>
> **TODO cerrado (sesión posterior, sep-2026)**: se escribió
> `AuditPage.integration.test.tsx` — cubre un evento real (crear un
> contacto) apareciendo filtrado por tipo de entidad en el registro, y
> la edición de la política de retención. Al escribirlo se encontró un
> **bug real en la propia app**: el campo "Días de retención" mostraba
> el valor ya guardado como *fallback de renderizado* mientras el
> usuario lo tenía vacío — al borrarlo para escribir un número nuevo, el
> campo "revivía" el valor anterior de inmediato, y escribir después lo
> concatenaba (ej. 90 guardado + escribir "51" → quedaba "9051", no
> "51"). Corregido en `AuditPage.tsx`: `days` ahora se inicializa una
> sola vez (vía `useEffect`) con contenido editable real, no con un
> valor de respaldo que se recalcula en cada render.
>
> Columna `changes` (JSONB, nullable) en `audit`: agregada
> retroactivamente. Los ~20 call-sites de `AuditService.log_event` que
> ya existían antes de este módulo (uno por módulo cerrado) NO se
> retrofittearon para poblarla — tocaría cada módulo ya cerrado, fuera
> de alcance de este cierre. Queda disponible desde ahora en adelante;
> `null` en filas antiguas significa "sin diff capturado", no un error.

## 3. Paquetes activos por cliente (company_packages)
- (sin cliente final asignado — ciclo de referencia/plantilla del
  producto. Datos de prueba truncados al cerrar cada fase.)





## 4. Decisiones DEDUCIBLE/AMBIGUO acumuladas

| ID | Módulo | Tipo | Decisión | Estado |
|---|---|---|---|---|
| AMB-01 | #1 core | AMBIGUO | Spec no especifica cómo el cliente identifica su `company_id` antes de autenticarse. Adoptado: `email` único globalmente + rol `erp_auth_lookup` (BYPASSRLS, solo lectura) exclusivo del lookup pre-auth. | Abierto — pendiente confirmación de Roberto |
| DED-01 | #1 core | DEDUCIBLE | Onboarding de compañías protegido con `X-Internal-Api-Key` estático, no RBAC. | Abierto — reemplazar por panel superadmin real |
| DED-02 | #1 core | DEDUCIBLE | `active_warehouse_id` sin FK real al cierre de core. | **Resuelto** en módulo 3/4 |
| DED-03 | #1 core | DEDUCIBLE | JWT solo en memoria del frontend, se pierde al refrescar. | Abierto — TODO-02 |
| DED-04 | #2 contacts | DEDUCIBLE | Sobre de error uniforme extendido a 422 Pydantic y 404/405 Starlette (antes solo cubría `DomainError`). | Resuelto, ver `tests/test_error_envelope.py` |
| DED-05 | #3 inventory | DEDUCIBLE | `ajuste` de stock siempre interpretado como baja. | Abierto — pendiente confirmación de Roberto |
| DED-06 | #4 purchasing | DEDUCIBLE | Numeración de PO al crear el draft, no al confirmar. | Abierto — pendiente confirmación de Roberto |
| DED-07 | #4 purchasing | DEDUCIBLE | `closed` sin lógica de negocio adicional (no hay `accounting` con qué hacer match). | Abierto — revisar cuando exista `accounting` |
| DED-08 | #5 sales | DEDUCIBLE | Solo se puede convertir a orden una cotización en estado `accepted`, no `sent` directo. | Abierto — pendiente confirmación de Roberto |
| DED-09 | #6 accounting | DEDUCIBLE | Plan de Cuentas mínimo modelado como catálogo plano de "roles" fijos (`receivable/payable/income/tax/cash_bank/adjustment`), no jerárquico — plan completo es [extendido]. | Documentado, no requiere confirmación (spec 8.1 lista los roles explícitamente) |
| DED-10 | #6 accounting | DEDUCIBLE | Mapeo documento→cuentas (spec 7.1) modelado como tabla explícita `document_account_mappings(company_id, document_type, role, account_id)` — un documento puede necesitar más de un rol en la misma transacción. | Documentado, no requiere confirmación |
| DED-11 | #6 accounting | DEDUCIBLE | Factura de proveedor usa la cuenta `adjustment` como contrapartida de `payable` en el plan mínimo, porque el plan mínimo no incluye cuentas de gastos/inventario (spec 8.1 no las lista). | Abierto — reconfigurar sin tocar el motor cuando el cliente compre Plan de Cuentas completo |
| DED-12 | #6 accounting | AMBIGUO | Motor de Contención Financiera: "deuda vencida" = factura de venta con `due_date` pasado y `balance_due>0`; "crédito excedido" = suma de `balance_due` de facturas `posted`/`partially_paid` > `contacts.credit_limit`. NO incluye órdenes de venta confirmadas aún no facturadas en el cálculo. | Abierto — pendiente confirmación de Roberto |
| DED-15 | #7 pipeline | DEDUCIBLE | "Lead" reutiliza `Contact.is_lead` existente — no se crea una tabla `Lead` separada. | Documentado, no requiere confirmación (spec 2.3 ya define el flag) |
| DED-16 | #7 pipeline | DEDUCIBLE | "Al menos una etapa `is_won` y una `is_lost`" es una regla de conjunto validada en el servicio al cerrar, no un constraint de fila. | Documentado, no requiere confirmación |
| DED-17 | #7 pipeline | DEDUCIBLE | Lead scoring [extendido] explícitamente NO construido — sin fórmula/config especificada en la spec. | Abierto — TODO si el cliente lo requiere |
| DED-18 | #7 pipeline | AMBIGUO | Movimiento libre entre etapas no terminales (kanban); alcanzar etapa terminal es comando explícito (`close-won`/`close-lost`), no un cambio directo de `stage_id`. | Abierto — pendiente confirmación de Roberto |
| DED-19 | #7 pipeline | DEDUCIBLE | Bloqueo por paquete no licenciado reutiliza `PACKAGE_NOT_LICENSED` (403) existente en vez de `UNSUPPORTED_WITHOUT_ADMIN_PACKAGE` como código nuevo. | Documentado, no requiere confirmación |
| DED-20 | #8 hr | DEDUCIBLE | `Employee` es entidad propia, no reutiliza `Contact` — sin flag `is_employee` en `Contact`. Vínculo opcional a `User` vía `user_id`. | Documentado, no requiere confirmación |
| DED-21 | #8 hr | DEDUCIBLE | Permiso separado `hr:employee:read-sensitive` para ver `salary`; enmascarado a `None` en el router si falta, vía nuevo helper `user_has_permission()`. | Documentado, no requiere confirmación |
| DED-22 | #8 hr | DEDUCIBLE | "Jerarquías" con dos relaciones independientes: `Department.parent_department_id` (organigrama) y `Employee.manager_employee_id` (línea de reporte), sin obligar a que coincidan. | Documentado, no requiere confirmación |
| DED-23 | #9 medical | DEDUCIBLE | "Profesional" se modela como `User` directamente, sin entidad `Practitioner` separada. | Documentado, no requiere confirmación — TODO si se necesita agendar personal sin cuenta de login |
| DED-24 | #9 medical | DEDUCIBLE | Cifrado pgcrypto limitado a `diagnosis_text`/`physical_exam`/`treatment_plan` (Consulta) y `content` (Expediente); `diagnosis_cie10` y `Appointment.reason`/`cancellation_reason` en claro (código estandarizado / no es diagnóstico ni nota clínica). | Documentado, no requiere confirmación (spec 8.2 limita el cifrado explícitamente) |
| DED-25 | #9 medical | DEDUCIBLE | Corrección de Consulta/Expediente = fila nueva enlazada, nunca UPDATE. "Una consulta vigente por cita" garantizado con `SELECT ... FOR UPDATE`, no con constraint (índice único parcial probado y revertido en Fase 4 — no es diferible en Postgres). | Documentado, no requiere confirmación — ver migración `1669f8fbbc6b` |
| DED-26 | #9 medical | DEDUCIBLE | Bloqueo de horario real con `EXCLUDE USING gist` (`btree_gist`) en vez de validación de aplicación. | Documentado, no requiere confirmación |
| AMB-02 | #9 medical | AMBIGUO | Período de retención regulatoria del log de auditoría clínico (spec 8.2) — sin dato de la normativa hondureña aplicable ni de cuánto tiempo quiere Roberto conservarlo. | Abierto — pendiente confirmación de Roberto |
| DED-27 | #26 notifications | DEDUCIBLE | Motor de Correos = interfaz real (`EmailSender`) + implementación de desarrollo que registra en vez de entregar — sin proveedor SMTP/API configurado (sin salida de red en el sandbox). | Documentado, no requiere confirmación — TODO de despliegue: credenciales del proveedor real |
| DED-28 | #26 notifications | DEDUCIBLE | Notificación siempre dirigida a `User` interno, nunca a `Contact` — mensajería a terceros es responsabilidad de cada módulo consumidor. | Documentado, no requiere confirmación |
| DED-29 | #26 notifications | DEDUCIBLE | Plantillas dinámicas con reemplazo `{variable}` simple (sin Jinja2, evita SSTI), placeholder faltante → cadena vacía en vez de error. | Documentado, no requiere confirmación |
| DED-30 | #10 medical (recetas) | DEDUCIBLE | Una `Prescription` siempre se emite dentro de una `Consultation` — no existe receta "suelta". | Documentado, no requiere confirmación |
| DED-31 | #10 medical (recetas) | DEDUCIBLE | Cabecera + líneas (`PrescriptionLine`) en vez de una fila por medicamento — una receta real casi siempre lleva más de uno. | Documentado, no requiere confirmación |
| DED-32 | #10 medical (recetas) | DEDUCIBLE | Sin cifrado pgcrypto en datos de receta — spec 8.2 limita el cifrado explícitamente a diagnóstico/notas de Consulta. | Documentado, no requiere confirmación — corrección de spec si Roberto decide lo contrario |
| DED-33 | #10 medical (recetas) | DEDUCIBLE | Receta inmutable con anulación (`void`+motivo), no con patrón de corrección encadenada — spec no exige "nunca se sobrescribe" para Recetas explícitamente. | Documentado, no requiere confirmación |
| DED-34 | #11 medical (laboratorio) | DEDUCIBLE | Cabecera + líneas (`LabOrderTest`) — mismo criterio que Recetas (DED-31), una orden casi siempre pide más de una prueba. | Documentado, no requiere confirmación |
| DED-35 | #11 medical (laboratorio) | DEDUCIBLE | Orden y resultado en la misma fila (`LabOrderTest`), sin tabla `LabResult` separada — el resultado completa campos que ya existen en la línea de la orden. | Documentado, no requiere confirmación |
| DED-36 | #11 medical (laboratorio) | DEDUCIBLE | Marcado de valor crítico explícito (checkbox), no inferido comparando contra el rango de referencia — formatos heterogéneos sin unidad normalizada, sin catálogo de pruebas. | Documentado, no requiere confirmación — TODO si se necesita cálculo automático con un catálogo de pruebas |
| DED-37 | #12 medical (teleconsulta) | DEDUCIBLE | Interfaz real `TeleconsultationProvider` con implementación de desarrollo (URL de sala local) — spec exige proveedor externo real (Twilio/Daily) y prohíbe WebRTC propio; sin salida de red en el sandbox hacia esos proveedores. | Documentado, no requiere confirmación — TODO de despliegue: credenciales de un proveedor real |
| DED-38 | #12 medical (teleconsulta) | DEDUCIBLE | Una sola sesión activa por cita, garantizada por chequeo transaccional (no índice único parcial, mismo motivo que DED-25). | Documentado, no requiere confirmación |
| DED-39 | #12 medical (teleconsulta) | DEDUCIBLE | Sin grabación/almacenamiento de video — la spec pide sala de videollamada, no grabación; implicaciones regulatorias de consentimiento sin resolver. | Documentado, no requiere confirmación |
| DED-40 | #13 medical (facturación) | DEDUCIBLE | "accounting activo" = paquete `administrative` activo — no existe activación granular por sub-módulo dentro de un paquete. | Documentado, no requiere confirmación |
| DED-41 | #13 medical (facturación) | DEDUCIBLE | Un solo `amount` por consulta, sin líneas de conceptos — la spec dice "recibo/factura por consulta", no un desglose facturable. | Documentado, no requiere confirmación — TODO si se necesita facturar conceptos por separado |
| DED-42 | #13 medical (facturación) | DEDUCIBLE | Cuando `administrative` activo, se reutiliza el motor de asientos real de `accounting` (sin duplicar lógica) — el paciente debe tener `is_customer=true`, misma regla que cualquier factura. | Documentado, no requiere confirmación |
| DED-43 | #14 medical (portal/mensajería) | DEDUCIBLE | `notifications` es Transversal (sin `require_package`) en este proyecto — siempre disponible; no aplica la rama condicional de la spec ("si no está activo, hilo mínimo sin avisos"). | Documentado, no requiere confirmación |
| DED-44 | #14 medical (portal/mensajería) | DEDUCIBLE | Sin autenticación de pacientes — mensajes `sender_role='patient'` los registra personal clínico en nombre del paciente, `author_user_id` siempre es un `User` real. | Documentado, no requiere confirmación — TODO si se construye portal con login propio del paciente |
| DED-45 | #22 website | DEDUCIBLE | `Page` con dos estados (`draft`/`published`), sin flujo de aprobación editorial. | Abierto — pendiente confirmación de Roberto |
| DED-46 | #22 website | DEDUCIBLE | `FormSubmission` reutiliza un `Contact` existente por email (marcándolo `is_lead=true` si no lo era) en vez de crear un duplicado; sin email, siempre crea uno nuevo. | Abierto — pendiente confirmación de Roberto |
| AMB-03 | #22 website | AMBIGUO | Cómo resuelve el storefront público el `company_id` de cada request en producción (subdominio, dominio propio, header) — implementado con `company_id` explícito en la URL como variante funcional mínima. | Abierto — pendiente confirmación de Roberto |
| DED-47 | #23 ecommerce | DEDUCIBLE | Sesión de carrito anónimo como token opaco (body + header `X-Cart-Token`), no cookie firmada — desviación deliberada del diseño original en `diseno_modulos_22_25_erp_crm.md` 2.4. | Documentado, no requiere confirmación — cambiar a cookie no toca `services.py` |
| DED-48 | #23 ecommerce | DEDUCIBLE | `EcommerceSettings` (nueva, no anticipada en el diseño) resuelve la falta de un almacén "por defecto" en `inventory.Warehouse` — checkout falla explícito si no está configurada. | Abierto — pendiente confirmación de Roberto sobre si el almacén debería poder variar por región/método de envío en vez de ser uno solo por compañía |
| DED-49 | #23 ecommerce | DEDUCIBLE | Verificación de webhook con HMAC-SHA256 + secreto propio por compañía, contrato de payload simplificado — no se integró ningún SDK de pasarela real. | Abierto — bloqueante real antes de producción, depende de qué pasarela(s) elija Roberto |
| AMB-04 | #23 ecommerce | AMBIGUO | Confirmar/facturar/registrar evento de pago no son atómicos entre sí (`SalesOrderService.confirm`/`InvoiceService.*` no exponen `_skip_commit`) — riesgo de `ConflictError` en un reintento de webhook tras una caída a medio proceso. | Abierto — requiere extender esos servicios, fuera del alcance de este cierre |
| DED-50 | #24 reports | DEDUCIBLE | "Dashboards Interactivos" con widgets embebidos en JSONB (`Dashboard.widgets`), no una tabla `DashboardWidget` separada. | Documentado, no requiere confirmación — extensión aditiva si hace falta más estructura |
| DED-51 | #24 reports | DEDUCIBLE | "Reportes Cruzados" implementado como whitelist fija de 4 métricas predefinidas (`app/reports/metrics.py`), nunca SQL arbitrario desde el cliente. | Abierto — Roberto podría querer métricas adicionales o un Report Builder real ([extendido], no construido) |
| AMB-05 | #24 reports | AMBIGUO | Gating de `reports` con `require_package("administrative")` completo (no exento como `notifications`) — decisión tomada, no solo propuesta, pero no confirmada por Roberto. | Abierto — pendiente confirmación de Roberto |
| DED-52 | #16 pharmacy | DEDUCIBLE | FEFO implementado en `pharmacy` (no en `inventory`, que lo dejó explícitamente fuera de su cierre) — consume primero el lote que vence antes, divide entre lotes si uno no alcanza. | Documentado, no requiere confirmación |
| DED-53 | #16 pharmacy | DEDUCIBLE | Sustancias Controladas marcadas con tabla propia de `pharmacy` (FK a `inventory.Product`), sin modificar el esquema de `inventory`. | Documentado, no requiere confirmación |
| DED-54 | #16 pharmacy | DEDUCIBLE (revisado en Fase 3) | Verificación clínica contra expediente real solo si `medical` activo **y** `is_patient=true`; si no, formulario mínimo de alergias obligatorio. | Documentado, no requiere confirmación |
| DED-55 | #16 pharmacy | DEDUCIBLE | Cliente de farmacia = cualquier `Contact`, sin exigir `is_patient=true` — no es necesariamente un paciente de `medical`. | Documentado, no requiere confirmación |
| DED-56 | #16 pharmacy | DEDUCIBLE | POS Farmacia reutiliza `DispensationOrder` (venta sin receta = `prescription_id=NULL`), sin entidad separada. | Documentado, no requiere confirmación |
| DED-57 | #16 pharmacy | DEDUCIBLE | Anular una dispensación NO revierte el descuento de inventario — spec no describe flujo de devolución. | Documentado, no requiere confirmación — TODO si se necesita devolución real |
| DED-58 | #15 medical (reserva pública) | DEDUCIBLE | `Contact` del paciente resuelto/creado por email, mismo criterio que DED-46 (`website` FormSubmission) — reutiliza y agrega `is_patient=true` sin pisar otros flags; sin email, no aplica (email o teléfono es obligatorio). | Documentado, no requiere confirmación |
| DED-59 | #15 medical (reserva pública) | DEDUCIBLE | Endpoint de disponibilidad devuelve solo el rango horario ocupado (`scheduled`/`confirmed`), nunca PHI — ruta anónima sin JWT. | Documentado, no requiere confirmación |
| AMB-06 | #15 medical (reserva pública) | AMBIGUO | El widget no puede listar profesionales bookeables por sí mismo — asume que la página que lo embebe ya conoce el `professional_user_id`. Si se necesita un directorio público de personal, requiere endpoint y modelado nuevos. | Abierto — pendiente confirmación de Roberto |

## 5. Resumen rodante (últimos módulos cerrados — 22/23/24 y 16 se trabajaron
en paralelo desde la misma base, portal/mensajería módulo 14; ver más abajo
para módulos anteriores)
- Módulo 15 (medical — reserva pública de citas) — **✓ COMPLETO,
  backend + widget VERIFICADOS contra Postgres real** (sesión de
  verificación externa sep-2026, en dos partes: backend primero,
  widget en una sesión posterior; originalmente escrito sin
  Postgres/red, mismo motivo que 22/23/24 en su momento). Última pieza
  de la tabla de Médico, ya no bloqueada desde el cierre de `website`.
  Sin tablas nuevas — reutiliza `Appointment`, con un flag retroactivo
  (`booked_via_public_widget`). Gating combinado nuevo
  (`ensure_public_booking_active`, exige `web` Y `medical` activos y no
  suspendidos — ninguna dependencia FastAPI existente cubría dos paquetes a
  la vez). Reutiliza el bloqueo de horario real de `AppointmentService`
  (`EXCLUDE USING gist`) sin duplicar la lógica de concurrencia. Contacto de
  paciente deduplicado por email con el mismo criterio que `website`
  (DED-46 → DED-58). Endpoint de disponibilidad deliberadamente minimalista
  (solo rango horario, nunca PHI — DED-59). 7 tests backend (no 9 —
  número corregido tras contarlos contra el archivo real), todos en
  verde. **Frontend construido y verificado** en
  `public-widgets/medical-booking/` (TODO-45 cerrado) — widget
  embebible vanilla JS, deliberadamente fuera de `frontend/`, mismo
  argumento que ya usó `ecommerce` para no construir su storefront
  dentro del panel.
- **BUG REAL sistémico, encontrado y corregido en migración `1d9a25acd918`**:
  `bootstrap_admin.py` fallaba en CI con `permission denied for sequence
  ecommerce_settings_id_seq` al insertar como `erp_app` real (no
  superusuario) — reproducido en local para diagnosticarlo (blob storage
  de logs de Actions no accesible desde el entorno de chat). Causa: el
  `GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO erp_app` de
  la migración inicial (`1483b27d4cff`, módulo core) solo cubre las
  secuencias que existían en ese momento — Postgres no lo aplica
  retroactivamente a secuencias creadas por migraciones posteriores, y
  ninguna migración desde `hr` (módulo 8) en adelante volvió a otorgar el
  `USAGE` sobre sus propias secuencias nuevas (solo repetían el `GRANT`
  de privilegios de tabla). Nunca se había detectado porque ningún test
  de `pytest` ni cierre previo había insertado una fila como `erp_app`
  real en una tabla creada después de `hr` — afecta potencialmente a
  hr, medical (+ recetas/laboratorio/teleconsulta/facturación/portal),
  notifications, website, ecommerce, reports y pharmacy. Fix: re-emitir
  el `GRANT` contra todas las secuencias existentes hoy. Verificado en
  local (reset de BD limpio + migrar + bootstrap completo → `bootstrap
  ok`) antes de subir.
- Módulo 24 (reports, Transversal) — **✓ COMPLETO — verificado vía CI** (sin
  Postgres/red/Node en el entorno de escritura). Exportación de Datos
  [core] a XLSX/PDF (`openpyxl`/`reportlab`, dependencias nuevas
  tampoco instaladas). Dashboards con widgets embebidos en JSONB
  (DED-50, sin tabla `DashboardWidget` separada). Reportes Cruzados =
  whitelist fija de 4 métricas predefinidas, nunca SQL arbitrario
  (DED-51). Gating con `require_package("administrative")` completo, no
  exento como `notifications` (AMB-05, no confirmado por Roberto). 10
  tests backend escritos, sin correr. Checklist de cierre real
  pendiente: instalar dependencias, migrar (`57990ab9bc72`), pytest,
  congelar contrato, build+vitest.
- Módulo 23 (ecommerce, paquete Web) — **✓ COMPLETO — verificado vía CI**
  (misma advertencia). Checkout crea un `sales.SalesOrder` real
  (`SalesOrderService.create_draft`), no un modelo `Order` paralelo.
  Gating resuelto reutilizando `minimal_modules` tal cual, gracias al
  fix del bug de `require_package` del cierre de website (AMB-04
  aparte: confirmar/facturar/registrar-evento no son atómicos entre sí).
  Hallazgo real no anticipado en el diseño: `sales.SalesOrder` exige
  `warehouse_id` sin default — se agregó `EcommerceSettings`
  (`default_warehouse_id`/`default_price_list_id`/`webhook_secret` por
  compañía). Webhook con HMAC-SHA256 + contrato propio simplificado, sin
  SDK de pasarela real (DED-49). Carrito anónimo con token opaco
  (`X-Cart-Token`), no cookie firmada — desviación deliberada de
  `diseno_modulos_22_25_erp_crm.md` 2.4 (DED-47). 8 tests backend + 1
  test de integración frontend escritos, sin correr.
- Módulo 22 (website, primer módulo del paquete Web) — **✓ COMPLETO —
  verificado vía CI** (este cierre es el que originó la advertencia △
  — ningún cierre anterior a este había quedado sin pasar
  por el DoD real). **BUG REAL encontrado y corregido**: `minimal_module`
  en `require_package` nunca se evaluaba (`row.package != package`
  siempre falso) — dead code desde que existe la función; sin
  consumidor real todavía, así que no afectó producción, pero el fix
  era condición previa para el gating de `ecommerce` (módulo 23). Test
  de regresión agregado en `test_core_module.py`. `Page` con
  `draft`/`published`, sin flujo editorial (DED-45). `FormSubmission`
  reutiliza `Contact` existente por email (DED-46). Resolución de
  `company_id` del storefront público con `company_id` explícito en la
  URL, no subdominio/dominio propio (AMB-03, no confirmado). 7 tests
  backend + 1 de regresión, sin correr en el entorno de escritura.
  **Verificado externamente después, vía CI** (GitHub Actions, jobs
  `pytest` + `e2e` con Postgres/servidor reales): 109/109 tests, build +
  `vitest run` completo de los 16 archivos de integración del frontend,
  contrato congelado a 117 rutas reales.
- Módulo 16 (pharmacy — dispensación + verificación clínica) — **Fases
  1-4 completas.** Primer módulo del paquete Farmacéutico. FEFO real
  implementado acá (DED-45, `inventory` lo dejó fuera de su cierre) —
  consume el lote que vence antes, divide entre lotes si uno no alcanza.
  Sustancias Controladas con tabla propia (DED-46, sin tocar
  `inventory.Product`) + libro de registro automático. POS Farmacia
  reutiliza `DispensationOrder` (DED-49, sin entidad separada). Anular
  no revierte stock (DED-50). Contrato re-congelado: 114 rutas (107+7).
  11 tests backend nuevos (112/112 total) — todos al primer intento.
  **Hallazgo real de Fase 3**: `pharmacy` intentaba consultar el
  expediente médico de cualquier cliente cuando `medical` estaba activo,
  sin chequear que el cliente realmente tuviera `is_patient=true` — un
  cliente de mostrador no tiene por qué tenerlo (DED-48). Se encontró
  reproduciendo la petición con `curl` contra el backend real en vez de
  seguir ajustando el test a ciegas. Efecto colateral real, no una
  regresión: activar `pharmacy` en el fixture compartido cambió
  `dispensing_status` de una receta de `not_applicable` a `pending`
  (DED-30) — el test de `medical` se actualizó para reflejar el estado
  correcto del fixture actual. Frontend: `PharmacyPage.tsx` (dispensación
  + gestión de sustancias controladas), con FEFO verificado end-to-end
  contra dos lotes reales de vencimiento distinto.
- Módulo 14 (medical — portal/mensajería paciente-médico) — **Fases 1-4
  completas.** `notifications` es Transversal en este proyecto (sin
  `require_package`, DED-43) — siempre disponible, así que cada mensaje
  `sender_role='patient'` dispara una notificación in-app real al
  profesional, sin rama condicional. Sin autenticación de pacientes
  (DED-44) — mensajes de paciente los registra personal clínico en su
  nombre, `author_user_id` siempre un `User` real. Contrato
  re-congelado: 107 rutas (104+3). 4 tests backend nuevos (101/101
  total) — todos al primer intento, incluida la verificación real de
  que la notificación se generó (no solo que el servicio no lanzó
  error). Frontend: sección "Mensajes" en `MedicalPage` a nivel
  paciente (no dentro de una cita), con poll cada 30s.
- Módulo 13 (medical — facturación médica básica) — **Fases 1-4
  completas.** "accounting activo" = paquete `administrative` activo
  (DED-40, sin activación granular por sub-módulo). Un solo `amount` por
  consulta (DED-41). Cuando `administrative` está activo, reutiliza el
  motor de asientos real de `accounting` sin duplicar lógica (DED-42) —
  **primer test del proyecto que cruza `medical` con el motor de
  asientos real**, construyendo su propio Plan de Cuentas + mapeo mínimo
  (sin seed automático en el proyecto). Cuando no está activo, emite un
  comprobante simple con numeración atómica, sin asiento. Contrato
  re-congelado: 104 rutas (101+3). 5 tests backend nuevos (97/97 total)
  — todos al primer intento. **Hallazgo real de Fase 3**: el primer
  intento del test de frontend asumía el camino `simple_receipt`, pero
  la compañía de prueba compartida ya tenía `administrative` activo —
  ajustado para reflejar el camino real (`accounting_invoice`, que exige
  `is_customer=true` en el paciente, igual que cualquier factura).
- Módulo 10 (medical — recetas) — **Fases 1-4 completas.** Cabecera
  (`Prescription`) + líneas (`PrescriptionLine`, DED-31), `dispensing_
  status` calculado según paquete `pharmacy` activo (DED-30), sin
  cifrado pgcrypto (DED-32, spec limita el cifrado a Consulta), inmutable
  con anulación en vez de edición (DED-33). Contrato re-congelado: 90
  rutas (86+4). 5 tests backend nuevos (81/81 total) — **todos al primer
  intento, sin hallazgos reales de Fase 4** (a diferencia de casi todos
  los módulos anteriores). Frontend: sección "Recetas" integrada en
  `AppointmentDetailDialog`, flujo completo verificado en
  `MedicalPage.integration.test.tsx` (emitir → `dispensing_status` real
  → anular → persiste).
- Módulo 26 (notifications) — **Fases 1-4 completas.** Transversal — sin
  `require_package`. Motor de Correos como interfaz real con
  implementación de desarrollo (sin proveedor SMTP configurado en el
  sandbox), Plantillas Dinámicas con reemplazo `{variable}` seguro (sin
  Jinja2). **Hallazgo real**: `openapi-zod-client` emite la firma Zod v3
  de `z.record()` para `dict[str,str]`, incompatible con Zod v4 —
  parcheado puntualmente en `schemas.ts`, documentado in situ. Contrato
  re-congelado: 86 rutas (80+6). 11 tests backend nuevos (76/76 total).
  Frontend: campana global (`NotificationBell`, contador de no leídas,
  poll 30s) + página de gestión de plantillas y envío manual, con test
  de integración que verifica lectura real (no solo UI). Se corrigió
  también `bootstrap_admin.py` para no asumir `company_id=1`.
- Módulo 9 (medical) — **Fases 1-4 completas.** Expediente Clínico +
  Agenda Médica + Consulta. Primer uso real de `pgcrypto` en el proyecto
  y primer `EXCLUDE USING gist` (bloqueo de horario, verificado con
  concurrencia real: 8 inserts simultáneos → gana 1). **Dos hallazgos
  reales**: (1) Fase 4 backend — un índice único parcial para "una
  consulta vigente por cita" no es diferible en Postgres, revertido a
  favor de `SELECT ... FOR UPDATE`; (2) Fase 3 frontend — faltaba
  `GET /medical/appointments/{id}/consultation` (Fase 2 nunca contempló
  recuperar la consulta de una cita ya completada sin conocer su id).
  Contrato re-congelado: 80 rutas (68+12). 65/65 tests backend (15
  nuevos). Frontend completo (`MedicalPage` + 2 diálogos), con
  verificación RBAC "own patients" real contra la API (403 genuino, no
  solo ocultamiento en la UI). AMB-02 (retención de auditoría clínica)
  sigue abierta.
- Módulo 8 (hr): **Fases 1-4 completas.** Legajo, Estructura
  Organizacional, Jerarquías. Enmascarado de `salary` por permiso
  separado verificado end-to-end real, incluido en el test de
  integración de Fase 4 (crea rol+usuario limitado dentro del propio
  test, sin asumir ids fijos). **Encontró y corrigió un bug real
  preexistente**: `Role.permissions` apuntaba a la tabla de asociación en
  vez de a `Permission`, rompiendo `GET /roles` con 500 en cualquier rol
  con permisos — nunca antes expuesto porque ningún módulo previo había
  creado un rol con `permission_ids`. Contrato re-congelado: 68 rutas
  (63+5). Frontend completo (`EmployeesPage` + 4 diálogos). 50/50 tests
  backend + 22/22 tests frontend. TODO-21 cerrado.
- Módulo 7 (pipeline): Fases 1-4 completas. Caso especial: toda su
  funcionalidad es [extendido] en spec 8.0, construido igual por estar en
  la tabla de módulos. Primer módulo con `require_package` aplicado de
  verdad (scaffoldeado desde el módulo 1, nunca antes usado) — verificado
  end-to-end: 403 sin paquete activo, funciona normal con paquete activo.
  Kanban con movimiento libre entre etapas no terminales, cierre
  ganada/perdida como comando explícito. Contrato re-congelado: 63 rutas
  (54+9). Frontend completo (`PipelinePage` + 3 diálogos). 50/50 tests
  backend + 21/21 tests frontend.
- Módulo 6 (accounting): Fases 1-4 completas. Motor de asientos genérico
  verificado con asiento real balanceado en Postgres. Hook cross-módulo
  real en `sales.confirm()` (Motor de Contención Financiera) probado
  end-to-end: bloquea con 409 y desbloquea al corregir el límite de
  crédito. `IdempotencyService` nuevo en `core` (TODO-03), cableado a los
  9 endpoints financieros y verificado con replay real. Contrato
  re-congelado: 54 rutas (38+16). Frontend completo: `AccountsPage`,
  `InvoicesPage`, `PaymentsPage`, `CreditDebitNotesPage`. Fase 4 encontró
  y corrigió 3 bugs reales (uno de backend, dos de infraestructura de
  test). TODO-14 cerrado.
- Módulo 5 (sales): Fases 1-4 completas. Dos máquinas de estado (`Quote`,
  `SalesOrder`) + reserva real de stock (nuevo concepto:
  `reserved_quantity` en `StockLevel`, retroactivo a `inventory`),
  probada con 10 confirmaciones concurrentes reales. Listas de precios
  con quiebre de volumen. Contrato re-congelado (38 rutas, 49 schemas),
  frontend completo (`PriceListsPage`, `QuotesPage`, `SalesOrdersPage`).
  11 tests backend + 3 tests frontend, todos reales. TODO-12 cerrado.

## 6. TODOs diferidos con contrato mínimo
- TODO-44(medical — reserva pública de citas, módulo 15): ~~checklist de
  verificación real pendiente (migrar, pytest, congelar contrato)~~ —
  **cerrado**, ver nota de verificación al inicio de su sección.
- TODO-45(medical — reserva pública de citas, módulo 15): ~~decidir y
  construir el frontend público real (widget embebible)~~ — **cerrado**,
  `public-widgets/medical-booking/`, ver nota de verificación en su
  sección.
- TODO-46([extendido] medical — reserva pública de citas, futuro):
  directorio público de profesionales bookeables (AMB-06) — si el
  widget necesita listarlos en vez de recibir el id ya resuelto. Sigue
  abierto — no se construyó, un `<div>` del widget = un profesional.
- TODO-02(infraestructura/despliegue): refresh token a cookie httpOnly +
  `Secure` + `SameSite=Strict`.
- TODO-03(cualquier módulo con `Idempotency-Key`): ~~`idempotency_keys`
  existe, sin consumidor~~ — **cerrado**, confirmado en la Fase 0 de la
  regresión QA externa (sep-2026, ver sección 0.1): consumidores reales
  en `app/accounting/routers.py` y `app/ecommerce/routers.py`.
- TODO-04(cualquier módulo no-Núcleo): `require_package`/
  `require_package_writable` construidos y probados, sin endpoint real
  que los use todavía.
- TODO-05(inventory): completar `get_current_warehouse_id` con
  `db.get(Warehouse, ...)` + validar `company_id` — la FK ya existe,
  falta la validación en el dependency.
- TODO-06(inventory): `StockMovement` sin trigger de inmutabilidad de BD
  (a diferencia de `audit`) — hoy solo disciplina de código.
- TODO-07([extendido] inventory): FEFO/FIFO/LIFO, alertas de caducidad,
  bloqueo/cuarentena de lote, costeo por lote, valoración, conversión de
  unidades, kits/BOM.
- TODO-08(purchasing, ahora que existe `accounting` Fase 1): revisar en
  Fase 2 de `accounting` si `closed` de `PurchaseOrder` debe disparar
  lógica de match de factura (DED-07 vinculado).
- TODO-09(purchasing): **Resuelto en este cierre** — contrato
  re-congelado, frontend completo, flujo E2E probado.
- TODO-10([extendido] purchasing): Requisiciones internas, Gestión/
  Evaluación de Proveedores, RFQ, Contratos Marco/Blanket Orders.
- TODO-11([extendido] sales): campañas con vigencia temporal en
  `PriceList` (hoy no tiene fecha de inicio/fin propia).
- TODO-12(sales): **Resuelto en este cierre** — contrato re-congelado (38
  rutas, 49 schemas), frontend completo (listas de precios, cotizaciones
  con conversión a orden, órdenes de venta con reserva/envío/facturación),
  Fase 4 (3 tests de integración frontend reales, sin mocks) y
  `verify_state.py` re-ejecutado.
- TODO-13([extendido] sales): Descuentos/Promociones, Comisiones de
  Vendedores, Devoluciones (RMA).
- TODO-14(accounting): **Resuelto en este cierre.** Fases 1-4 completas:
  backend, contrato, frontend de cuentas/facturas/notas/pagos, tests de
  integración (4 nuevos, 3 bugs reales encontrados y corregidos), e
  `IdempotencyService` cableado a los 9 endpoints financieros.
- TODO-15([extendido] accounting): Plan de Cuentas completo (jerárquico,
  cuentas analíticas, centros de costo), Libro Diario y Mayor (UI de
  consulta), Conciliación Bancaria, Activos Fijos, Presupuestos, Tipos de
  Cambio y Revaluación Multi-moneda.
- TODO-20([extendido] pipeline): Lead scoring (DED-17, sin fórmula
  especificada). Fuera de la tabla de módulos por completo (no son
  módulo 7, son features que dependen de pipeline pero nunca se listaron
  en `modulos_erp_crm_v10_4.json`): Casos de Soporte/Helpdesk, Campañas de
  Marketing, Contratos con Cliente (B2B) — los tres [extendido, requiere
  Administrativo] según spec 8.0.
- TODO-21(hr): **Resuelto en este cierre.** Fases 1-4 completas: backend,
  contrato (68 rutas), frontend (`EmployeesPage` + 4 diálogos), Fase 4
  (test de integración que incluye la verificación real del enmascarado
  de `salary` con un rol/usuario limitado creados dentro del propio
  test).
- TODO-22([extendido] hr): Nómina/Payroll (agrega dependencia real de
  `accounting`, sin bloqueo técnico ya que está construido), Control de
  Asistencia y Horarios, Ausencias y Vacaciones, Evaluación de Desempeño,
  Reclutamiento.
- TODO-23(medical): **Resuelto en este cierre.** Fases 1-4 completas:
  backend (modelos, `pgcrypto`, `EXCLUDE USING gist`, servicios, routers,
  80 rutas, 15 tests backend) + frontend (`MedicalPage` + 2 diálogos,
  test de integración con verificación RBAC real).
- TODO-24([extendido], módulo 15 medical): reserva pública de citas —
  único módulo de la tabla de Médico que falta; sigue bloqueado porque
  depende de `website` (módulo 22, paquete Web, tampoco construido).
  Módulo 14 (portal/mensajería) se resolvió en este cierre — ver
  TODO-38. Con esto, Médico tiene sus 5 módulos construibles completos.
- TODO-25(notifications): **Resuelto en este cierre.** Fases 1-4
  completas: backend (86 rutas, 11 tests) + frontend (campana global +
  página de plantillas/envío).
- TODO-26([extendido] notifications): Canales Adicionales (SMS, push),
  Preferencias por Usuario (silenciar tipos de notificación, elegir
  canal por defecto).
- TODO-27(notifications, despliegue): reemplazar `LoggingEmailSender` por
  una implementación real (SES/SendGrid/etc.) cuando haya credenciales de
  un proveedor SMTP/API configurables — sin bloqueo técnico, la interfaz
  ya está lista (DED-27).
- TODO-28(medical — recetas, módulo 10): **Resuelto en este cierre.**
  Fases 1-4 completas: backend (90 rutas, 5 tests) + frontend (sección
  "Recetas" en `AppointmentDetailDialog`).
- TODO-29(medical — recetas, integración futura): cuando se construya
  Farmacéutico (módulo 16+), ese módulo es quien transiciona
  `dispensing_status` de `pending` a `dispensed` — `medical` no tiene
  ningún endpoint que lo haga, por diseño (ver DED-30 en STATE.md
  sección "recetas").
- TODO-30(medical — laboratorio, módulo 11): **Resuelto en este cierre.**
  Fases 1-4 completas: backend (96 rutas, 5 tests, primer uso real de
  `core.Attachment`) + frontend (sección "Laboratorio" en
  `AppointmentDetailDialog`).
- TODO-31(medical — laboratorio, extensión futura): catálogo de pruebas
  (`test_catalog`) con rangos de referencia estructurados por prueba y
  unidad normalizada, para poder calcular `is_critical` automáticamente
  en vez de depender del checkbox manual (DED-36).
- TODO-32(core — attachments, extensión futura): `AttachmentService`
  usa disco local (`attachment_storage_root`) — reemplazar por un backend
  de object storage real (S3/GCS/etc.) cuando haya credenciales de un
  proveedor configurables, mismo criterio que TODO-27 (notifications).
- TODO-33(medical — teleconsulta, módulo 12): **Resuelto en este
  cierre.** Fases 1-4 completas: backend (101 rutas, 6 tests, interfaz
  real de proveedor con stub de desarrollo) + frontend (sección
  "Teleconsulta" en `AppointmentDetailDialog`).
- TODO-34(medical — teleconsulta, despliegue): reemplazar
  `DevStubTeleconsultationProvider` por un cliente real (Twilio/Daily)
  cuando haya credenciales configurables — sin bloqueo técnico, la
  interfaz ya está lista (DED-37), mismo criterio que TODO-27
  (notifications) y TODO-32 (attachments).
- TODO-35(medical — facturación médica básica, módulo 13): **Resuelto en
  este cierre.** Fases 1-4 completas: backend (104 rutas, 5 tests,
  primer cruce real con el motor de asientos de `accounting`) + frontend
  (sección "Facturación" en `AppointmentDetailDialog`).
- TODO-36(medical — facturación, extensión futura): líneas de conceptos
  facturables por consulta (procedimientos, insumos) en vez de un solo
  `amount` (DED-41) — si se necesita desglosar la factura.
- TODO-37(medical — facturación, integración futura): cuando el cliente
  activa `administrative` después de haber emitido comprobantes
  `simple_receipt`, esos comprobantes NO se migran retroactivamente a
  asientos contables (DED-40) — declarado explícito por la spec, sin
  resolver en este cierre.
- TODO-38(medical — portal/mensajería, módulo 14): **Resuelto en este
  cierre.** Fases 1-4 completas: backend (107 rutas, 4 tests, primera
  integración real con `notifications` desde otro módulo) + frontend
  (sección "Mensajes" en `MedicalPage`, a nivel paciente).
- TODO-39(medical — portal/mensajería, extensión futura): portal de
  paciente con autenticación propia (DED-44) — cuando exista, el
  paciente podría escribir mensajes directamente sin pasar por personal
  clínico transcribiendo.
- TODO-40(medical — portal/mensajería, integración futura): aviso
  automático de "resultados de laboratorio disponibles" (mencionado en
  la spec) integrado con el cierre de una `LabOrder` (módulo 11) — no se
  conectó en este cierre para no reabrir código ya probado.
- TODO-41(pharmacy, módulo 16): **Resuelto en este cierre.** Fases 1-4
  completas: backend (114 rutas, 11 tests, FEFO real implementado por
  primera vez en el proyecto) + frontend (`PharmacyPage` — dispensación/
  POS + sustancias controladas).
- TODO-42(pharmacy, extensión futura): flujo de devolución de un
  producto dispensado (DED-50) — anular hoy no revierte el descuento de
  inventario; si se necesita, define sus propias reglas (¿se puede
  devolver un controlado? ¿el lote original sigue vigente?).
- TODO-43(pharmacy, módulos futuros 17-21): Interacciones [extendido],
  Aseguradoras/Copagos [extendido], POS farmacia como módulo separado
  (ya cubierto por DED-49 dentro del 16), Reposición a Droguerías
  [extendido], MTM [extendido] — módulos separados en la tabla, no
  construidos todavía.

## 7. Proyecto de migración (si aplica)
- Estado: sin proyecto de migración contratado.
