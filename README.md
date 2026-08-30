# ERP/CRM Modular por Paquetes — v10.4

Sistema ERP/CRM modular construido incrementalmente, módulo por módulo, con
verificación real en cada cierre (Postgres real, backend real corriendo,
sin mocks). Este README es un resumen legible para humanos; el detalle
técnico completo vive en `STATE.md` (estado actual, para retomar en una
sesión nueva) y `LOG_EJECUCION.md` (bitácora cronológica completa de todo
lo hecho, fase por fase).

## Estado actual del proyecto

**8 módulos completos de punta a punta** (Fases 1-4: modelos, servicios,
contrato congelado, frontend, tests de integración reales) — **el
paquete Administrativo está completo**:

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

Los paquetes Médico, Farmacéutico y Web, y los módulos transversales
(reports, audit completo, notifications), todavía no se empezaron —
son el siguiente paso natural del proyecto.

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
pytest tests/ -q   # 50/50 esperados

# Frontend
cd frontend
npm install
npx tsc --noEmit    # limpio
npm run build       # exitoso
npx vitest run       # suite de integración real contra el backend de arriba
```

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
  (63+ rutas al momento de este corte).
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
