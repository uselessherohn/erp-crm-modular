# Axis Suite — ERP/CRM Modular por Paquetes v10.4

Sistema ERP/CRM modular, comercializado bajo el nombre **Axis Suite**,
construido incrementalmente, módulo por módulo, con
verificación real en cada cierre (Postgres real, backend real corriendo,
sin mocks). Este README es un resumen legible para humanos; el detalle
técnico completo vive en `STATE.md` (estado actual, para retomar en una
sesión nueva) y `LOG_EJECUCION.md` (bitácora cronológica completa de todo
lo hecho, fase por fase).

## Estado actual del proyecto

**25 módulos completos de punta a punta** — el paquete Administrativo
está completo, Médico tiene sus 6 módulos construibles hoy completos
(incluido el 15, con su widget embebible verificado end-to-end contra
Postgres real), el paquete Web (website/ecommerce) está completo,
notifications, reports y audit completo (módulo 25) en Transversal, y
el paquete Farmacéutico está completo de punta a punta — sus 5 módulos
construibles hoy: dispensación (que además cubre, dentro del mismo
cierre, la parte core de sustancias controladas y el flujo de POS
farmacia — ver DED-49 en `STATE.md`), interacciones medicamentosas,
aseguradoras/copagos, reposición a droguerías y MTM/consulta
farmacéutica:

| # | Módulo | Paquete | Estado |
|---|--------|---------|--------|
| 1 | core (usuarios, permisos, empresa, auditoría) | Núcleo | ✓ Completo |
| 2 | contacts | Núcleo | ✓ Completo |
| 3 | inventory | Administrativo | ✓ Completo |
| 4 | purchasing | Administrativo | ✓ Completo |
| 5 | sales | Administrativo | ✓ Completo |
| 6 | accounting | Administrativo | ✓ Completo |
| 7 | pipeline (leads/oportunidades) | Administrativo | ✓ Completo |
| 8 | hr | Administrativo | ✓ Completo |
| 9 | medical (Expediente Clínico, Agenda, Consulta) | Médico | ✓ Completo |
| 10 | medical — recetas | Médico | ✓ Completo |
| 11 | medical — laboratorio | Médico | ✓ Completo |
| 12 | medical — teleconsulta | Médico | ✓ Completo |
| 13 | medical — facturación médica básica | Médico | ✓ Completo |
| 14 | medical — portal/mensajería paciente-médico | Médico | ✓ Completo |
| 15 | medical — reserva pública de citas (widget) | Médico | ✓ Completo — backend + widget embebible, verificado contra Postgres real |
| 16 | pharmacy — dispensación + verificación clínica (incluye sustancias controladas y POS farmacia) | Farmacéutico | ✓ Completo |
| 17 | pharmacy — interacciones medicamentosas (sustancias controladas ya cubierta en el módulo 16, DED-49) | Farmacéutico | ✓ Completo — verificado contra Postgres real |
| 18 | pharmacy — aseguradoras / copagos | Farmacéutico | ✓ Completo — verificado contra Postgres real |
| 20 | pharmacy — reposición a droguerías | Farmacéutico | ✓ Completo — verificado contra Postgres real |
| 21 | pharmacy — MTM / consulta farmacéutica | Farmacéutico | ✓ Completo — verificado contra Postgres real |
| 22 | website (CMS, formularios) | Web | ✓ Completo |
| 23 | ecommerce (carrito, checkout, pagos) | Web | ✓ Completo |
| 24 | reports | Transversal | ✓ Completo |
| 25 | audit completo (UI, retención configurable, reportería) | Transversal | ✓ Completo — verificado contra Postgres real |
| 26 | notifications | Transversal | ✓ Completo |

Farmacéutico ya no tiene ningún módulo `[extendido]` pendiente — los
últimos tres (Aseguradoras/Copagos, Reposición a Droguerías y MTM,
módulos 18/20/21) se cerraron y verificaron en esta sesión, sumados a
Interacciones (módulo 17) de la sesión anterior. De Transversal ya no
falta
nada construible hoy (audit completo, módulo 25, se cerró y verificó en
esta sesión — el audit mínimo ya vivía en el módulo 1).

**Nota de verificación**: 22/23/24 se escribieron en un entorno sin
Postgres/red/Node y se verificaron después vía CI (GitHub Actions,
Postgres y servidor reales) — ver la nota al inicio de la sección
`website` en `STATE.md` para el detalle completo, incluyendo un bug real
de permisos de secuencia de Postgres que ese CI encontró y corrigió. Los
módulos 15 y 25 se escribieron en las mismas condiciones (sin
Postgres/red) y **esta sesión de verificación externa (sep-2026) corrió
ambos por primera vez contra Postgres real**, en dos pasadas
consecutivas de la misma sesión:

- **Módulo 15**: backend (modelo, migración, servicios, 2 rutas
  públicas, 7 tests — no 9, corregido en `STATE.md`) pasa 7/7; la
  migración `a1c4f0e2b9d7` corre limpia. Esa misma corrida encontró y
  corrigió un bug real preexistente, no relacionado con el módulo 15: el
  fixture `store` de `test_ecommerce_module.py` nunca le daba stock
  físico al producto de prueba, por lo que
  `test_webhook_confirms_order_and_posts_invoice` fallaba con
  `ConflictError` al reservar stock. El frontend del widget
  (`public-widgets/medical-booking/`, fuera de `frontend/` a propósito —
  ver su README) se construyó en una sesión posterior y se verificó
  end-to-end contra Postgres real con un arnés en `jsdom` + `fetch`
  nativo (sin mocks): carga de disponibilidad, selección de
  día/horario, envío del formulario, y dos casos límite reales
  (condición de carrera al confirmar un cupo que alguien más tomó
  primero, y compañía sin `medical`/`web` licenciado). Con esto, el
  módulo 15 pasa a `✓ Completo`.
- **Módulo 25** (audit completo): backend (columna `audit.changes`,
  tabla `audit_retention_policies`, 3 rutas nuevas, 5 tests) pasa 5/5
  tras corregir **dos bugs reales**, ninguno relacionado con el 15:
  1. El helper `_log` de `test_audit_module.py` intentaba backdatear un
     evento de prueba con `UPDATE audit SET created_at = ...` para
     simular un evento "viejo" sin esperar días reales — pero el propio
     trigger de inmutabilidad que este módulo documenta (`trg_audit_immutable`,
     AMB-07) bloquea **cualquier** UPDATE/DELETE sobre `audit`, sin
     excepción. El test chocaba con su propia documentación. Corregido
     fijando `created_at` directo en el INSERT (el trigger no bloquea
     INSERT), sin pasar nunca por UPDATE.
  2. La migración `f3b6a1d9c204` nunca le otorgó a `erp_app` (el rol de
     runtime real de la API) permisos sobre la tabla nueva
     `audit_retention_policies` ni sobre su secuencia — el comentario
     original de la migración asumía, incorrectamente, que el `GRANT`
     sistémico ya cubría tablas futuras (`ALTER DEFAULT PRIVILEGES`
     nunca se configuró en este proyecto; cada tabla nueva necesita su
     propio `GRANT` explícito, mismo patrón que el bug de secuencias ya
     documentado en `1d9a25acd918`). `erp_app` fallaba con
     `InsufficientPrivilegeError: permission denied for table
     audit_retention_policies`. Corregido agregando el `GRANT` explícito
     a la migración.
- **Módulo 17** (pharmacy — interacciones medicamentosas; sustancias
  controladas ya cubierta en el módulo 16, DED-49): backend (2 tablas
  nuevas — `product_active_ingredients` multi-tenant con RLS,
  `drug_interaction_reference_entries` catálogo global sin RLS, seed
  fijo de 15 pares conocidos —, 3 rutas nuevas, 5 tests) pasa 5/5 desde
  el primer intento, sin bugs propios que corregir — a diferencia de los
  dos anteriores, su migración ya incluía los `GRANT` de tabla y
  secuencia correctos desde el principio.

Con los tres módulos verificados, `pytest tests/` queda en **158/158**
contra Postgres real (base recreada de cero), `alembic upgrade head`
corre limpio de punta a punta (28 migraciones), `contracts/openapi.json`
quedó recongelado contra el servidor real (142 rutas / 177 operaciones),
y `npx vitest run` (frontend, contra el backend y la base reales, sin
mocks) queda en **19/19 archivos, 29/29 tests**.

**Cierre de Farmacéutico completo** (sesión posterior, tres módulos
recibidos como dos ZIPs separados — módulo 18 ramificado justo después
del 17, y módulos 20/21 juntos, ramificados directo del estado ya
verificado de los módulos 15/25, sin conocer todavía el 17/18): se
aplicó el mismo merge quirúrgico que en cierres anteriores, aislando
cada diff contra su base real y reencadenando las 3 migraciones nuevas
en una sola cadena lineal (17→18→21→20). El merge automático de
parches dejó dos artefactos reales que hubo que corregir a mano: una
función truncada en `pharmacy/services.py` (contenido cortado por el
parche difuso) y un bloque de permisos duplicado en
`bootstrap_admin.py` — ninguno de los dos es un bug del código
original, ambos son ruido propio de la herramienta de parcheo, y se
verificaron ambos arreglos contra Postgres real antes de seguir.
Además se encontraron **dos bugs reales genuinos**, ninguno relacionado
con el contenido de los tres módulos en sí: (1) las migraciones de MTM y
Reposición a Droguerías no le otorgaban permisos a `erp_app` sobre sus
tablas nuevas — tercera vez que aparece este mismo bug sistémico (ver
`1d9a25acd918` y la nota del módulo 25 más arriba) —, corregido antes de
correr contra Postgres real por primera vez; y (2) el test de cierre de
sesión de MTM con facturación real no configuraba el mapeo contable
necesario (mismo patrón ya visto en `test_ecommerce_module.py`/
`test_reports_module.py`), corregido agregando el mismo helper ya
existente. Por último, `PharmacyPage.integration.test.tsx` (el test
original de dispensación, del módulo 16) dejó de pasar porque el módulo
20 agrega un segundo selector "Sucursal" en la misma pantalla — corregido
acotando la búsqueda a la sección de dispensación específicamente.
Con todo corregido: `pytest tests/` queda en **185/185**, 31 migraciones
limpias de punta a punta, `contracts/openapi.json` recongelado (162
rutas / 200 operaciones), y `npx vitest run` en **19/19 archivos, 30/30
tests**.

**Cierre de pendientes de verificación (sesión posterior)**: se
resolvieron los tres cabos sueltos que quedaban documentados —
cobertura de frontend faltante en `audit`/`18`/`20`/`21`, y
`scripts/purge_audit.py` nunca ejecutado de punta a punta.

- **`AuditPage.integration.test.tsx` (nuevo)**: cubre un evento real
  (crear un contacto) apareciendo filtrado por tipo de entidad en el
  registro, y la edición de la política de retención. Al escribirlo se
  encontró un **bug real en la propia app**: el campo "Días de
  retención" mostraba el valor ya guardado como *fallback de
  renderizado* mientras estaba vacío — al borrarlo para escribir un
  número nuevo, el campo "revivía" el valor anterior de inmediato, y
  escribir después lo concatenaba (ej. 90 guardado + escribir "51" →
  quedaba "9051", no "51"). Corregido en `AuditPage.tsx`: el campo se
  inicializa una sola vez con contenido editable real, no con un
  fallback que reaparece.
- **`PharmacyPage.insurance-mtm-reorder.integration.test.tsx` (nuevo)**:
  cubre el ciclo completo de MTM (crear sesión → cerrar y facturar), de
  Aseguradoras (aseguradora → póliza → reclamo → enviar → aprobar →
  pagar, contra una dispensación real) y de Reposición (configurar un
  punto de pedido). Sin bugs de la app — dos ajustes reales al propio
  test (el paciente de MTM necesita `is_customer=true` para poder
  facturarle, no solo `is_patient`; y hay que configurar los mapeos
  contables antes de correr el archivo en aislamiento, mismo patrón que
  otros tests del proyecto).
- **`scripts/purge_audit.py` corrido de punta a punta contra Postgres
  real por primera vez**: se sembraron eventos de auditoría vencidos
  reales, se confirmó que `--dry-run` reporta el mismo conteo que
  `GET /audit/retention-policy/purge-eligible`, y que el borrado real
  excluye correctamente eventos `medical.*` y reactiva el trigger de
  inmutabilidad al final (confirmado con un `DELETE` manual posterior,
  que vuelve a fallar como debe). **Bug real encontrado**: pasar
  `--company-id` fallaba con `AmbiguousColumn` — el filtro SQL
  interpolado no calificaba `company_id` con el alias de tabla,
  ambiguo en un JOIN con `audit_retention_policies` (que también tiene
  esa columna). Corregido calificando como `a.company_id`.

Con todo esto: `pytest tests/` sigue en **185/185** (sin módulos
nuevos, solo tests agregados), y `npx vitest run` sube a **21/21
archivos, 35/35 tests**.

**Corrección (sesión posterior, cierre del widget del módulo 15 y del
módulo de Interacciones — ver más abajo)**: en esta misma sesión se
había reportado que `AccountsPage.integration.test.tsx` fallaba por
"ambigüedad de texto acumulada" al correr la suite varias veces sin
recrear la base, y que se resolvía solo al correr una vez limpia sin
cambio de código. **Eso resultó ser una lectura incompleta.** En una
corrida posterior, limpia, de un solo intento, el mismo test volvió a
fallar — la causa real es que el orden real en que Vitest ejecuta los
archivos no es necesariamente el alfabético, así que cualquier otro
archivo que cree un mapeo `document_type=sales_invoice` (con otro rol)
antes de que corra `AccountsPage`, en la misma corrida, ya vuelve
ambiguo su `getByText("Factura de venta")` — no hacía falta repetir la
suite completa. Corregido esperando por el código de cuenta (único por
corrida) en vez de por la etiqueta genérica del documento. De paso
apareció un segundo bug real, en `StockPage.integration.test.tsx`: dos
de las tres aserciones del test corrían de forma síncrona justo después
de la primera (que sí esperaba de forma async), sin esperar a que
terminara de pintar el resto de la fila — una carrera real contra el
propio render, no contra el backend. Corregido envolviendo las tres en
el mismo `waitFor`. Con ambos fixes, `npx vitest run` vuelve a quedar en
verde de forma estable (confirmado con más de una corrida limpia
consecutiva).

## Marca e instalación como PWA

El frontend usa la marca **Axis Suite** (ícono y logo en
`frontend/public/axis-suite-icon.svg` y `axis-suite-logo.svg`) y está
configurado como Progressive Web App vía `vite-plugin-pwa`
(`frontend/vite.config.ts`): manifest con íconos 192/512 y una variante
maskable, `theme_color` #1D5FA8, `display: standalone`. Al visitar el
sitio compilado (`npm run build && npm run preview`, o el deploy real)
desde Chrome/Edge/Android, el navegador ofrece "Instalar app"
automáticamente. El service worker (`workbox`) precachea el shell
estático de la SPA pero **no** cachea rutas de API — los datos siempre
se piden frescos al backend (necesario dado el aislamiento multi-tenant
por RLS y los saldos de stock/facturas que cambian constantemente).

## Cómo verificar que todo funciona

El proyecto se verifica en **Nivel 1**: Postgres real, backend FastAPI
real corriendo, frontend React real, sin mocks en ningún punto.

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# configurar .env con las cadenas de conexión (ver LOG_EJECUCION.md, Módulo 1)
alembic upgrade head
uvicorn app.main:app --reload

# en otra terminal
pytest tests/ -q   # 185 tests; ver nota abajo sobre el estado real de la corrida

# Frontend
cd frontend
npm install
npx tsc --noEmit    # limpio
npm run build       # exitoso
npx vitest run       # suite de integración real contra el backend de arriba
```

**Nota sobre la última corrida real de `pytest tests/`** (actualizada,
sesión de verificación externa sep-2026 — Postgres real, base recreada de
cero): `test_ecommerce_module.py::test_webhook_confirms_order_and_posts_invoice`
y 4 tests de `test_reports_module.py` fallaban porque sus fixtures
disparaban la contabilización automática de una factura (`InvoiceService.post`)
sin configurar antes un `DocumentAccountMapping` para `sales_invoice` —
el mismo paso que sí hace `test_medical_module.py`. Corregido replicando
ese mismo patrón (`_setup_sales_invoice_account_mappings`) en ambos
archivos de test — confirmado en verde. Esa misma corrida real destapó un
**segundo bug, independiente del anterior y hasta ahora no documentado**:
con el mapping ya corregido, `test_webhook_confirms_order_and_posts_invoice`
seguía fallando, pero por `ConflictError: Stock disponible insuficiente`
— el fixture `store` nunca le daba stock físico al producto de prueba
antes de confirmar la orden vía webhook (`StockService.reserve` rechaza
reservar sobre `quantity=0`). Corregido agregando una entrada de stock
real (`StockService.record_movement`) al fixture. **Confirmado: 144/144
tests en verde** contra Postgres real, base recreada de cero
(`DROP DATABASE`→`CREATE DATABASE`→`alembic upgrade head`), incluyendo
las 25 migraciones previas más `a1c4f0e2b9d7` (módulo 15).

## Qué leer según lo que necesites

- **¿Quieres saber qué falta y por qué se tomó cada decisión de diseño?**
  → `STATE.md`. Tiene la tabla de módulos completados, los contratos
  públicos vigentes, las decisiones DEDUCIBLE/AMBIGUO acumuladas (22 hasta
  ahora, cada una con su justificación), y los TODOs diferidos.
- **¿Quieres el historial completo de cómo se construyó cada módulo, con
  los bugs reales que se encontraron y cómo se corrigieron?** →
  `LOG_EJECUCION.md`. Es la bitácora cronológica completa, módulo por
  módulo, fase por fase.
- **¿Quieres el contrato de API vigente?** → `contracts/openapi.json`
  (134 rutas / 168 operaciones al momento de este corte, congelado
  automáticamente por el job `e2e` del CI contra el servidor real).
- **¿Quieres la tabla de módulos y dependencias del sistema completo?** →
  `modulos_erp_crm_v10_4.json` (26 módulos totales planeados).

## Hallazgos destacados de este proyecto

Algunos bugs reales — no cosméticos — que se encontraron y corrigieron
durante la construcción, gracias al criterio de verificar todo contra un
entorno real en cada cierre en vez de confiar en la revisión de código:

- **Reserva de stock con concurrencia real**: `reserved_quantity` en
  `inventory`, probado con 10 confirmaciones de órdenes simultáneas —
  nunca sobrevende.
- **Motor de asientos contables balanceado**: verificado con un asiento
  real en Postgres (factura con impuesto, balance exacto Debe=Haber).
- **Motor de Contención Financiera**: bloqueo real de una orden de venta
  por crédito excedido, verificado end-to-end incluyendo el desbloqueo al
  corregir el límite.
- **Mecanismo de idempotencia** (spec sección 7): replay real verificado
  con la misma `Idempotency-Key` — la segunda llamada no reejecuta nada.
- **Bug de construcción de `document_type`** en notas de crédito/débito
  (`sale_credit_note` inválido vs `sales_credit_note` correcto),
  encontrado por un test de integración real, no por revisión de código.
- **Bug de `Role.permissions`**: un `AttributeError` real que rompía
  `GET /roles` con cualquier rol que tuviera permisos asignados —
  presente desde el primer módulo, nunca antes expuesto porque ningún
  test había ejercitado ese camino hasta el módulo `hr`.
- **`require_package` aplicado por primera vez de verdad** en `pipeline`
  (módulo 7) — verificado con 403 real sin el paquete activo.
- **Enmascarado de datos sensibles verificado end-to-end**: en `hr`, un
  test de integración crea un rol y un usuario limitados dentro del
  propio test (sin asumir ids de permisos fijos) para confirmar que el
  salario de un empleado viaja como `null` para quien no tiene el
  permiso `hr:employee:read-sensitive`, mientras el admin lo ve completo.

- **Dos extensiones de Postgres nunca habilitadas en ninguna migración**
  (`pg_trgm` en `contacts`, `pgcrypto` en `medical`) — encontradas en la
  Fase 0 de la regresión QA externa (sep-2026), la primera vez que
  `alembic upgrade head` corrió contra una base completamente limpia; la
  primera bloqueaba la migración siempre, la segunda habría roto el
  cifrado clínico en el primer uso real.

Todos estos hallazgos, con el detalle completo de cómo se reprodujeron y
corrigieron, están documentados en `LOG_EJECUCION.md`.
