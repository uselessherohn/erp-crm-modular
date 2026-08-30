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

## 1. Paquetes y módulos completados
- Núcleo: core (✓), contacts (✓)
- Administrativo: inventory (✓), purchasing (✓), sales (✓), accounting (✓), pipeline (✓), hr (✓)
- Médico: (—) todos
- Farmacéutico: (—) todos
- Web: (—) todos
- Transversal: reports (—), audit completo (—), notifications (—)

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

### Módulo 2 — contacts
- Entidad `Contact` (spec 2.3): flags `is_customer`/`is_vendor`/
  `is_patient`/`is_lead` no excluyentes. `ContactCreate` exige (DEDUCIBLE)
  al menos un flag activo — `model_validator`, invisible en el JSON
  Schema/OpenAPI, el Zod generado NO lo replica (limitación real de
  `model_validator`, no bug de codegen).
- Búsqueda: operador trigram `%` (usa `ix_contacts_name_trgm`, GIN +
  `pg_trgm`) — verificado tolerando typos y falta de tildes.

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

## 5. Resumen rodante (solo los últimos 3 módulos cerrados)
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
- TODO-02(infraestructura/despliegue): refresh token a cookie httpOnly +
  `Secure` + `SameSite=Strict`.
- TODO-03(cualquier módulo con `Idempotency-Key`): `idempotency_keys`
  existe, sin consumidor — el primer módulo financiero/dispensación debe
  implementar el flujo check-antes-de-escribir (spec 7), no ad-hoc.
  `accounting` (módulo 6, Fase 2) es ese primer módulo financiero — pendiente
  para POST /accounting/payments y POST /accounting/invoices.
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

## 7. Proyecto de migración (si aplica)
- Estado: sin proyecto de migración contratado.
