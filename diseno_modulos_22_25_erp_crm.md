# Diseño propuesto — Módulos 22-25 (Web + Transversales pendientes)

> Complementa `spec_erp_crm_v10_4.md` y `STATE.md`. Sigue el mismo formato de
> contrato usado en los cierres de módulo anteriores (entidades, máquinas de
> estado, idempotencia, RLS, gating de paquetes, hooks cross-módulo) para que
> pueda incorporarse a `STATE.md` sin fricción cuando se construya cada uno.
> Todo lo marcado **DEDUCIBLE** o **AMBIGUO** sigue el mismo criterio del
> resto del proyecto: no confirmado por Roberto, decisión razonable tomada
> para poder avanzar, reversible si él dice lo contrario.

---

## 0. Nota de secuencia (bloqueante, ver auditoría)

`modulos_erp_crm_v10_4.json` declara `ecommerce` (23) con `depende_de: [22,
3, 5, 6]`. **Módulo 22 (`website`) no existe todavía en el repo** — ni
carpeta `app/website/`, ni mención en `STATE.md` §1 (Web: `(—) todos`). Este
documento diseña 22 en un nivel mínimo (solo lo que 23 necesita tocar) para
no bloquear el diseño de 23-25, pero **no reemplaza el diseño completo de
22** (CMS de páginas, formularios de captación como fuente de leads,
widget de reserva pública que desbloquea el módulo 15 de Médico). Recomendación:
construir 22 en su forma mínima *antes* de escribir código de 23, aunque el
diseño de ambos pueda revisarse en el mismo ciclo.

---

## 1. Módulo 22 — `website` (contexto mínimo para 23)

**Depende de**: Núcleo (1, 2) únicamente — spec 8.4, confirmado también en
`modulos_erp_crm_v10_4.json` (`depende_de: [1, 2]`, sin `inventory`).

Lo mínimo que 23 necesita que 22 ya exponga:
- Una entidad `Page` (o equivalente) que sirva de contenedor para las
  páginas de catálogo/producto del storefront — **DEDUCIBLE**: el catálogo
  de ecommerce (spec 8.4) vive en el dominio `ecommerce`, no en `website`;
  `website` solo necesita exponer el layout/CMS alrededor (header, footer,
  páginas institucionales). No hay dependencia dura de `Page` para que 23
  funcione — se puede construir 23 con rutas propias de catálogo sin tocar
  `website` en absoluto, y dejar la integración visual (banners promocionales
  del catálogo gestionados desde el CMS) como [extendido] posterior.
- `FormSubmission` → crea `Contact(is_lead=true)` directo sobre Núcleo
  (spec 8.4) — **sin relación con 23**, no es un prerequisito técnico real
  de ecommerce a pesar del orden en la tabla de módulos. La dependencia
  `depende_de: [22, ...]` de 23 en el JSON documenta más una **relación de
  paquete comercial** (ambos son "Web") que una dependencia de código dura.

**Conclusión de secuencia**: 23 puede diseñarse y construirse sin bloqueo
técnico real de 22, siempre que el gating de paquete (sección 2 abajo) no
dependa de que exista una fila `company_packages(package="web")` creada por
un flujo de 22 — se puede activar `web` directamente para pruebas de 23.
Documentar esto como excepción explícita a `modulos_erp_crm_v10_4.json` si
se confirma en la práctica, porque hoy el JSON (fuente única) dice lo
contrario.

---

## 2. Módulo 23 — `ecommerce`

> **Implementado** (backend + configuración de panel interno) en un cierre
> posterior a este documento — ver `STATE.md`, sección `ecommerce (módulo
> 23)`, para el contrato real, los hallazgos durante la implementación
> (algunos no anticipados acá, ej. la falta de un almacén "por defecto" —
> resuelto con `EcommerceSettings`) y qué quedó verificado vs no. Una
> desviación deliberada de este diseño: la sesión de carrito anónimo (2.4)
> se implementó como un token opaco devuelto en el body + header
> `X-Cart-Token`, no como cookie firmada — funcionalmente equivalente,
> más simple de implementar/probar sin navegador real. El resto de esta
> sección se deja tal cual se escribió originalmente, como referencia del
> razonamiento previo a construirlo.

**Depende de** (spec 8.4 + JSON): `website` (22, ver nota de secuencia
arriba), `inventory` (3), `sales` (5), `accounting` (6) — **los tres
siempre juntos**, nunca un subconjunto (spec 2.2).

### 2.1 Gating de paquete — punto AMBIGUO nuevo, a resolver aquí

`company_packages.package` es un enum de 4 valores (`administrative`,
`medical`, `pharmacy`, `web`) — no distingue "solo website" de
"website + ecommerce" dentro del mismo valor `web` (spec 2.2/2.4). Ningún
módulo anterior tuvo este problema porque Farmacéutico/Médico no tienen un
submódulo opcional *dentro* del mismo paquete con dependencias técnicas tan
distintas entre sí.

**DEDUCIBLE (no confirmado por Roberto)** — propuesta, reutilizando el campo
`minimal_modules` ya existente en vez de agregar un campo nuevo:
- Fila `company_packages(package="web")`: `website` se considera activo por
  el solo hecho de que la fila exista (igual que hoy). `minimal_modules`
  en **esta misma fila** pasa a listar `["ecommerce"]` cuando el cliente
  también contrató ecommerce — antes este campo solo se usaba para
  "arrastre técnico hacia `administrative`"; aquí se generaliza a
  "submódulos activos de este paquete", uso compatible con el tipo
  `list[str] | None` ya declarado.
- Cuando `"ecommerce" in minimal_modules` de la fila `web`, el sistema debe
  **además** garantizar una fila `company_packages(package="administrative",
  minimal_modules=["inventory","sales","accounting"])` — mismo patrón exacto
  que usa Farmacéutico hoy (`minimal_modules=["inventory","accounting"]`
  sobre la fila `administrative`). Si el cliente ya tiene Administrativo
  completo, esa fila existe con `minimal_modules=None` y no hace falta
  tocarla — `get_active_packages` ya resuelve ese caso (spec 2.4).
- `require_package("web")` sigue bloqueando cualquier ruta de `website`
  (páginas/formularios) con `PACKAGE_NOT_LICENSED` si no hay fila `web`.
  Las rutas `[core]` de `ecommerce` (catálogo/carrito/checkout/pagos)
  necesitan una verificación **adicional**: `require_package("web",
  submodule="ecommerce")` — nueva variante de la dependency existente que
  además valida `"ecommerce" in minimal_modules`, mismo criterio que ya
  aplica `get_active_packages` para distinguir submódulos mínimos de
  `administrative`. Sin esto, un cliente que compró Web solo para
  `website` vería 403 en rutas de catálogo, pero hoy la dependency no
  tiene forma de diferenciarlo — **hay que extender
  `get_active_packages`/`require_package`, no solo consumirlos tal cual
  existen**.

Este es el hallazgo de diseño más importante de este documento: **sin este
cambio en `core.packages`, 23 no se puede gatear correctamente** con el
mecanismo actual. Recomiendo confirmarlo con Roberto antes de escribir
código — es exactamente el tipo de ambigüedad que en v10.3 causó el bug real
de acceso indebido a rutas `[core]` de `sales` (spec 2.4), y aquí el riesgo
es simétrico: un cliente de solo `website` con acceso a catálogo/checkout
que nunca contrató.

### 2.2 Entidades propuestas

- `Cart` — `id`, `company_id`, `contact_id: nullable` (carrito anónimo vs
  registrado, spec 8.4 "sesiones anónimas y registradas"), `session_token`
  (firmado, para el caso anónimo — ver 2.4), `status`
  (`open|checked_out|abandoned`), `currency_code`, `created_at`,
  `expires_at` (limpieza de carritos anónimos abandonados — TODO batch job,
  no bloqueante para el MVP).
- `CartItem` — `cart_id`, `product_id` (FK a `inventory.Product`),
  `quantity`, `unit_price_snapshot` (precio congelado al agregar, spec
  "Listas de Precios" de `sales` ya resuelve el cálculo — este campo es
  cache de UI/checkout, no fuente de verdad de precio final).
- `Order` — **DEDUCIBLE: no es una entidad nueva**. Reutiliza
  `sales.SalesOrder` igual que "recetas" (módulo 10) reutiliza `Contact` en
  vez de duplicar — mismo criterio DED-15 (pipeline) aplicado aquí. El
  checkout de ecommerce **crea directamente** un `SalesOrder` en `draft`
  (mismo patrón que `Quote.convert_to_order`, módulo 5) en vez de inventar
  un modelo `EcommerceOrder` paralelo.
- `PaymentGatewayEvent` — `id`, `company_id`, `gateway` (`stripe|paypal|
  mercadopago`), `event_id` (clave de deduplicación real, **no** el header
  `Idempotency-Key` de spec 7 — es un mecanismo separado, spec 8.4 lo aclara
  explícitamente), `payload_raw` (JSONB, para auditoría/replay manual),
  `processed_at`, `sales_order_id: nullable`. Índice único
  `(company_id, gateway, event_id)`.

### 2.3 Flujo de checkout → automatización de orden [core]

1. `POST /ecommerce/checkout` valida carrito, dirección, método de pago →
   crea `SalesOrder(status=draft)` + `SalesOrderLine` por cada `CartItem`,
   usando `sales.SalesOrderService` existente sin duplicar lógica de
   reserva de stock (`StockService.reserve`, ya construido en módulo 5).
2. Redirección/checkout hospedado externo (Stripe/PayPal/MercadoPago) — el
   backend nunca toca datos de tarjeta (spec 8.4, fuera de alcance PCI-DSS).
3. `POST /ecommerce/webhooks/{gateway}`:
   - Verifica firma criptográfica del payload contra el secreto configurado
     (`Stripe-Signature` o equivalente) **antes** de leer el body como
     confiable — spec 8.4, control de seguridad explícito nuevo en v10.3.
   - Busca `(company_id, gateway, event_id)` en `PaymentGatewayEvent`; si ya
     existe, responde `200` sin reprocesar (idempotencia por `event_id`,
     **no** por header — distinto del mecanismo de `idempotency_keys`
     genérico de spec 7, aunque con el mismo principio de una sola vez).
   - Si es nuevo: confirma el `SalesOrder` (dispara reserva→confirmación,
     mismo camino que un `SalesOrder` confirmado manualmente), genera la
     `Invoice` vía `accounting.JournalService`/`DocumentAccountMapping` ya
     existentes (sin inventar un mapeo de cuentas nuevo — reutiliza el motor
     de asientos genérico del módulo 6), y dispara notificación de
     confirmación de pedido vía `notifications` (mismo patrón de
     integración real que `medical` → `notifications` en el módulo 14,
     TODO-38).
4. TTL de idempotencia para el endpoint de checkout (header
   `Idempotency-Key`, mecanismo genérico de spec 7): **24 horas**, ya
   declarado explícitamente en spec 7 bajo `sales`/`ecommerce` — sin
   ambigüedad aquí, solo aplicarlo.

### 2.4 Carritos anónimos — sesión sin JWT de usuario

**AMBIGUO, no confirmado por Roberto**: el resto del sistema autentica con
JWT de `User` (módulo 1). Un carrito anónimo no tiene usuario. Propuesta
DEDUCIBLE: cookie firmada de sesión de storefront (`HttpOnly`, `Secure`,
`SameSite=Lax` — no `Strict`, porque el checkout puede volver desde un
dominio externo de pasarela de pago) con un `session_token` opaco que
identifica el `Cart`, sin relación con RBAC/`Role`/`Permission` del panel
interno — es un mecanismo de autenticación distinto y deliberadamente más
simple, exclusivo del `storefront/` (ver estructura de carpetas, spec
sección 10). RLS de `company_id` sigue aplicando (el storefront sirve un
solo `company_id` por dominio/subdominio — **DEDUCIBLE**, no confirmado qué
mecanismo resuelve el `company_id` del storefront: ¿subdominio, dominio
custom, header? — dejar como TODO explícito, no bloquea el resto del diseño).

### 2.5 Fuera de alcance [extendido] — igual que la spec, sin construir aquí

Gestión de Envíos, Cupones y Descuentos, Reseñas y Calificaciones,
Devoluciones de Ecommerce, Venta OTC en línea integrada con Farmacéutico
(spec 8.4) — este último bloqueado además porque Farmacéutico (16-21) no
existe todavía en el repo.

---

## 3. Módulo 24 — `reports`

**Depende de**: "los módulos ya construidos que quiera cruzar, no de una
lista fija" (JSON, nota explícita) — a diferencia de todo lo demás, no tiene
un grafo de dependencia obligatoria fijo.

### 3.1 Gating de paquete

Spec 8.1 lista `reports` dentro de "Incluye" de Administrativo, junto con
`audit` y `notifications`. `notifications` está **explícitamente eximido**
de `require_package` (STATE.md, módulo 26: "spec 2.2: los paquetes
verticales *usan* `notifications`, no la *habilitan*"). **DEDUCIBLE, no
confirmado**: `reports` no tiene ese mismo carácter de infraestructura
transversal usada por todos los paquetes — es una capa que consulta datos
de negocio (inventario, ventas, contabilidad, y potencialmente médico/
farmacéutico si el cliente los tiene activos). Propuesta: `reports` sí
requiere `require_package("administrative")` para existir como paquete, y
**cada widget/reporte individual** que cruce datos de un paquete vertical
(ej. un dashboard que mezcle `sales` + `medical`) valida además el paquete
de origen de cada dominio que toca — nunca expone datos de un paquete no
contratado solo porque `reports` esté activo. Esto es consistente con el
principio de spec 2.4 ("el estado del paquete es una invariante de dominio,
no una protección exclusiva de la capa HTTP") aplicado a nivel de fuente de
datos, no solo de ruta.

### 3.2 Entidades propuestas (mínimas — el dato real vive en cada módulo)

- `Dashboard` — `id`, `company_id`, `name`, `owner_user_id`,
  `layout: JSONB` (posiciones de widgets).
- `DashboardWidget` — `dashboard_id`, `widget_type` (`metric|chart|table`),
  `query_definition: JSONB` (referencia a una consulta **predefinida y
  whitelisted** por módulo fuente — nunca SQL arbitrario desde el cliente,
  para no reabrir superficie de ataque de inyección ni saltarse RLS).
- **[core] Reportes Cruzados / Exportación**: no requieren tabla propia —
  son endpoints de agregación de solo lectura sobre los modelos existentes
  (`StockLevel`, `Invoice`, `SalesOrder`, etc.), con exportación a
  PDF/XLSX/CSV como formato de respuesta, no como entidad persistida.

### 3.3 Fuera de alcance [extendido]

Report Builder (consultas ad-hoc configurables por el usuario), Programación
de Reportes (envío periódico automático — dependería de `notifications` +
un scheduler, ninguno de los dos con ese consumidor todavía).

---

## 4. Módulo 25 — `audit` completo

**Depende de**: Núcleo (1) únicamente — opera sobre la tabla `audit` ya
creada y protegida por `trg_audit_immutable` desde el módulo 1 (spec 8.0).
**No crea tabla nueva, no la duplica** — la spec lo aclara dos veces (8.0 y
8.1), y `STATE.md` ya reserva esta responsabilidad exclusivamente para el
módulo 25.

### 4.1 Alcance real de este cierre

- **Registro de Actividad [core]**: endpoints de consulta/filtro
  (`entity_type`, `entity_id`, `user_id`, rango de fechas, `correlation_id`)
  sobre la tabla `audit` existente. Solo lectura — el mínimo del módulo 1 ya
  escribe.
- **Control de Cambios (Diff) [core]**: **AMBIGUO, no confirmado** —
  `AuditService.log_event()` (módulo 1) no está documentado en `STATE.md`
  con un campo explícito de `before`/`after`. Si el mínimo actual solo
  guarda el evento sin snapshot de valores, calcular un diff real requiere
  o (a) agregar columnas `before_state`/`after_state: JSONB` al evento en
  el momento de escribirlo (retroactivo, como pasó con `reserved_quantity`
  en `inventory` o `credit_limit` en `contacts`), o (b) que este módulo
  reconstruya el diff comparando eventos consecutivos del mismo
  `entity_id` — más frágil, depende de que cada escritura relevante ya
  llame a `log_audit_event`. Recomiendo (a): confirmarlo revisando primero
  la firma real de `AuditService.log_event()` en el código (no asumida
  aquí) antes de diseñar el diff a ciegas.
- **Retención y Depuración [core]**: job de purga configurable (default 90
  días, spec 8.1) sobre eventos operativos generales — **excluye
  explícitamente** los registros de acceso al expediente clínico (spec 8.2,
  AMB-02 en `STATE.md`, todavía sin confirmar el período regulatorio con
  Roberto). El job de purga de este módulo debe filtrar por `entity_type`
  para no tocar esos registros mientras AMB-02 siga abierto — un purgado
  genérico sin ese filtro sería un incumplimiento regulatorio real, no solo
  un bug.

### 4.2 Dependencia cruzada con AMB-02 (Médico)

Este módulo **no resuelve** AMB-02 — solo debe respetarlo. Si se construye
25 antes de que Roberto confirme el período de retención clínica, la
política de purga de este módulo debe excluir esos eventos por completo
(no aplicar ningún TTL) en vez de asumir un default, mismo criterio
conservador que el proyecto ya usó con `AMB-KEY` en `medical`.

---

## 5. Resumen de decisiones abiertas para Roberto

1. ¿`minimal_modules` en la fila `web` de `company_packages` es el
   mecanismo correcto para distinguir `website` solo vs `website+ecommerce`,
   o prefiere separar el enum en dos valores de paquete? (sección 2.1)
2. ¿Cómo resuelve el storefront público el `company_id` de cada request
   (subdominio, dominio custom, header)? (sección 2.4)
3. ¿`reports`/`audit` completo deben quedar detrás de
   `require_package("administrative")`, o se eximen del gating igual que
   `notifications`? (secciones 3.1 y 4)
4. Confirmar si `AuditService.log_event()` ya guarda `before`/`after` antes
   de diseñar el Control de Cambios (Diff) del módulo 25. (sección 4.1)
