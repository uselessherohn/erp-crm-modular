# Axis Suite — ERP/CRM Modular por Paquetes v10.4

Sistema ERP/CRM modular, comercializado bajo el nombre **Axis Suite**,
construido incrementalmente, módulo por módulo, con
verificación real en cada cierre (Postgres real, backend real corriendo,
sin mocks). Este README es un resumen legible para humanos; el detalle
técnico completo vive en `STATE.md` (estado actual, para retomar en una
sesión nueva) y `LOG_EJECUCION.md` (bitácora cronológica completa de todo
lo hecho, fase por fase).

## Estado actual del proyecto

**19 módulos completos de punta a punta** más **1 módulo con backend
completo pendiente de verificación real** (módulo 15, ver nota △ abajo)
— el paquete Administrativo está completo, Médico tiene sus 6 módulos
construibles hoy completos, el paquete Web (website/ecommerce) está
completo, el primer módulo Transversal (notifications) más reports
también, y el paquete Farmacéutico tiene su primer módulo (que además
cubre, dentro del mismo cierre, la parte core de sustancias controladas
y el flujo de POS farmacia — ver DED-49 en `STATE.md`):

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
| 15 | medical — reserva pública de citas (widget) | Médico | △ Backend verificado (Postgres real), falta frontend del widget |
| 16 | pharmacy — dispensación + verificación clínica (incluye sustancias controladas y POS farmacia) | Farmacéutico | ✓ Completo |
| 22 | website (CMS, formularios) | Web | ✓ Completo |
| 23 | ecommerce (carrito, checkout, pagos) | Web | ✓ Completo |
| 24 | reports | Transversal | ✓ Completo |
| 26 | notifications | Transversal | ✓ Completo |

De Farmacéutico faltan Interacciones, Aseguradoras/Copagos, Reposición a
Droguerías y MTM (módulos 17-21, todos `[extendido]`). De Transversal
falta audit completo (módulo 25; el audit mínimo ya vive en el módulo 1).

**Nota de verificación**: 22/23/24 se escribieron en un entorno sin
Postgres/red/Node y se verificaron después vía CI (GitHub Actions,
Postgres y servidor reales) — ver la nota al inicio de la sección
`website` en `STATE.md` para el detalle completo, incluyendo un bug real
de permisos de secuencia de Postgres que ese CI encontró y corrigió. El
módulo 15 se escribió en las mismas condiciones (sin Postgres/red) y
**esta sesión de verificación externa (sep-2026) lo corrió por primera
vez contra Postgres real**: su backend (modelo, migración, servicios, 2
rutas públicas, 7 tests — no 9, corregido en `STATE.md`) pasa 7/7, la
migración `a1c4f0e2b9d7` corre limpia sobre las 25 anteriores, y
`contracts/openapi.json` quedó recongelado contra el servidor real (136
rutas / 170 operaciones). Esa misma corrida también encontró y corrigió
un bug real preexistente, no relacionado con el módulo 15: el fixture
`store` de `test_ecommerce_module.py` nunca le daba stock físico al
producto de prueba, por lo que `test_webhook_confirms_order_and_posts_invoice`
fallaba con `ConflictError` al reservar stock — la suite completa queda
en 144/144 tras el fix. Lo que **sigue sin construir** del módulo 15 es
el frontend del widget (es para el sitio público, no una pantalla del
panel — ver TODO-45 en `STATE.md`); por eso sigue marcado `△` y no `✓`.

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
pytest tests/ -q   # 144 tests; ver nota abajo sobre el estado real de la corrida

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

Todos estos hallazgos, con el detalle completo de cómo se reprodujeron y
corrigieron, están documentados en `LOG_EJECUCION.md`.
