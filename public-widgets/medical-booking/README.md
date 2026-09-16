# Widget de Reserva Pública de Citas (módulo 15)

Widget embebible, sin dependencias ni build step, que consume las 2
rutas públicas del módulo 15 (`medical` ↔ `website`, spec 8.2/8.4):

- `GET /public/medical/{company_id}/professionals/{professional_user_id}/busy-slots`
- `POST /public/medical/{company_id}/bookings`

No requiere JWT ni cuenta previa del paciente — crea el `Contact`
(`is_patient=true`) al reservar, igual que un formulario de captación
crea un lead (DED-46, mismo criterio de deduplicación por email).

## Por qué es un archivo aparte, no una página del panel

El panel administrativo (`frontend/`, React) es para el personal interno
de la clínica. Este widget es para pacientes anónimos, en el sitio
público de la clínica — que puede ser una `Page` de `website` (spec 8.4:
"el mismo motor de páginas/formularios aloja el widget") o un sitio
externo por completo, fuera de este proyecto. Por eso es JS plano: tiene
que poder pegarse en cualquier HTML, sin depender de que el sitio que lo
embebe use React, Vite, ni nada del stack de este panel.

## Uso

```html
<div data-axis-medical-booking
     data-api-base="https://api.tuclinica.hn"
     data-company-id="1"
     data-professional-id="7"></div>
<script src="https://tu-cdn-o-servidor/widget.js" defer></script>
```

Un `<div>` por profesional — el widget no tiene ni necesita un
directorio de profesionales (ver "Decisiones" más abajo). Si una página
necesita ofrecer varios profesionales, se embeben varias instancias del
widget, una por cada uno.

### Atributos `data-*`

| Atributo | Obligatorio | Default | Qué hace |
|---|---|---|---|
| `data-api-base` | Sí | — | URL base del backend (sin `/` final), ej. `https://api.tuclinica.hn` |
| `data-company-id` | Sí | — | `company_id` de la clínica |
| `data-professional-id` | Sí | — | `user_id` del profesional a mostrar |
| `data-slot-minutes` | No | `30` | Duración de cada cupo ofrecido |
| `data-start-hour` | No | `8` | Hora de inicio de la jornada (0–23, hora local del navegador) |
| `data-end-hour` | No | `18` | Hora de fin de la jornada |
| `data-days-ahead` | No | `14` | Cuántos días hacia adelante se muestran |
| `data-locale` | No | `es-HN` | Locale para formatear fechas/horas (`Intl.DateTimeFormat`) |

### Reinicialización en SPA

Si el `<div data-axis-medical-booking>` se inserta dinámicamente después
de que `widget.js` ya cargó (ej. una SPA del lado del cliente, o un modal
que se abre bajo demanda), llamar a `window.AxisMedicalBooking.init()`
para que lo detecte e inicialice.

## Decisiones de diseño (documentadas, no silenciosas — mismo criterio que el resto del proyecto)

- **Sin directorio público de profesionales** (TODO-46, `STATE.md`): el
  sitio que embebe el widget ya sabe qué `professional_user_id` mostrar
  — no se construyó un endpoint de "listar profesionales bookeables"
  porque no estaba en el alcance `[extendido]` original y no hay
  decisión tomada sobre si hace falta. Si llega a hacer falta, es un
  cambio aditivo (un tercer endpoint público de solo lectura), no
  rediseño de este widget.
- **El horario laboral (jornada, duración de cupo) vive en el widget, no
  en el backend.** La API pública solo expone ocupación real
  (`busy-slots`), nunca configuración interna de agenda — exponer
  "de 8 a 18, cupos de 30 min" en una ruta sin JWT sería filtrar
  configuración operativa de la clínica a cualquiera. Se resuelve acá
  con defaults razonables, configurables por quien embebe sin tocar este
  archivo.
- **Las fechas se calculan y muestran en la hora local del navegador de
  quien reserva**, no en la zona horaria de la compañía — la ruta
  pública no expone `Company.timezone`. Se envían al backend como ISO
  8601 con offset explícito (`Date.toISOString()`), así que el dato
  guardado es correcto sin importar en qué zona horaria esté el
  visitante ni el navegador de recepción que lo vea después en el panel.
- **Conflictos de horario (`409 CONFLICT`)**: el rango [carga de
  disponibilidad → confirmación] no está bloqueado — alguien más puede
  tomar el mismo cupo mientras el paciente llena el formulario. El
  widget lo maneja mostrando un mensaje claro y refrescando la
  disponibilidad real, en vez de dejar a la persona reintentando contra
  un horario que ya no existe. Verificado con una prueba real que
  reproduce la condición de carrera (ver nota de verificación en
  `STATE.md`).

## Verificación

Este widget se probó end-to-end contra el backend real (Postgres real,
sin mocks) con un arnés en `jsdom` + `fetch` nativo de Node, simulando
un navegador real: carga de disponibilidad, selección de día/horario,
llenado y envío del formulario, y dos casos límite reales (condición de
carrera al confirmar un cupo que alguien más tomó primero, y compañía
sin `medical`/`web` licenciado). El detalle completo está en
`LOG_EJECUCION.md`. No se dejó como prueba automatizada en el
repositorio (no hay un runner de tests de frontend fuera de `vitest`,
que corre dentro de `frontend/` con su propio `tsconfig`/`vite.config`,
y este widget vive deliberadamente fuera de ese árbol) — es un TODO
abierto, documentado en `STATE.md`, no una verificación que no se hizo.

## Servir este archivo

`widget.js` es un archivo estático — cualquier forma de servir un
archivo estático funciona (Nginx, un bucket S3/R2 público con CDN
delante, o el propio backend agregando una ruta de archivos estáticos).
Este cierre no incluye esa infraestructura de despliegue — es una
decisión operativa del entorno de cada cliente, no del código.
