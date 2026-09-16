/*!
 * Axis Suite — Widget de Reserva Pública de Citas (módulo 15)
 *
 * Vanilla JS sin dependencias, pensado para vivir fuera del panel
 * administrativo (React) — se embebe en CUALQUIER sitio público, típico
 * caso de uso: pegado en el `content` (HTML crudo) de una Page de
 * `website` (spec 8.4, "Widget de Reserva Pública de Citas") o en un
 * sitio externo por completo. Por eso no usa build step, JSX ni
 * dependencias de npm — un solo <script> y listo.
 *
 * Consume únicamente las 2 rutas públicas sin JWT del módulo 15:
 *   GET  /public/medical/{company_id}/professionals/{professional_user_id}/busy-slots
 *   POST /public/medical/{company_id}/bookings
 *
 * Uso (ver README.md de esta carpeta para el detalle completo):
 *
 *   <div data-axis-medical-booking
 *        data-api-base="https://api.tuclinica.hn"
 *        data-company-id="1"
 *        data-professional-id="7"></div>
 *   <script src=".../widget.js" defer></script>
 *
 * Diseño deliberado (AMB, documentado igual que el resto del proyecto):
 * - No hay directorio público de profesionales (TODO-46, STATE.md) — el
 *   sitio que embebe el widget ya sabe qué `professional_user_id`
 *   mostrar (un profesional por instancia del widget).
 * - El horario laboral (hora de inicio/fin, duración de cupo) no vive en
 *   el backend — la API pública solo expone ocupación, nunca
 *   configuración interna. Se resuelve acá, vía atributos `data-*` con
 *   defaults razonables (8:00–18:00, cupos de 30 min), configurables por
 *   quien embebe el widget sin tocar este archivo.
 * - Las fechas se generan y muestran en la hora LOCAL del navegador de
 *   quien reserva, no en la zona horaria de la compañía (la ruta pública
 *   no expone `Company.timezone`). Se envían al backend como ISO 8601
 *   con offset explícito (`Date.toISOString()`), así que la corrección
 *   del dato no depende de en qué zona horaria esté el visitante.
 */
(function () {
  "use strict";

  var STYLE_ID = "axb-styles";
  var DEFAULTS = {
    apiBase: "",
    slotMinutes: 30,
    startHour: 8,
    endHour: 18,
    daysAhead: 14,
    locale: "es-HN",
  };

  var MONTH_DAY_FMT_CACHE = {};
  var TIME_FMT_CACHE = {};

  function injectStylesOnce() {
    if (document.getElementById(STYLE_ID)) return;
    var style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = [
      ".axb-root{--axb-bg:#fbfaf7;--axb-surface:#ffffff;--axb-ink:#1f2d29;",
      "--axb-ink-soft:#5b6b65;--axb-accent:#2f6f62;--axb-accent-ink:#ffffff;",
      "--axb-border:#dde3e0;--axb-slot-bg:#f1f5f3;--axb-slot-hover:#e3ece8;",
      "--axb-error:#9a3b34;--axb-error-bg:#fbeeec;--axb-radius:10px;",
      "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,",
      "'Helvetica Neue',Arial,sans-serif;color:var(--axb-ink);",
      "background:var(--axb-surface);border:1px solid var(--axb-border);",
      "border-radius:calc(var(--axb-radius) + 4px);padding:24px;",
      "max-width:480px;box-sizing:border-box;line-height:1.45}",
      ".axb-root *,.axb-root *::before,.axb-root *::after{box-sizing:border-box}",
      ".axb-steps{display:flex;gap:8px;margin-bottom:20px;font-size:12.5px;",
      "color:var(--axb-ink-soft)}",
      ".axb-step{display:flex;align-items:center;gap:6px}",
      ".axb-step-dot{width:18px;height:18px;border-radius:50%;",
      "border:1.5px solid var(--axb-border);display:flex;align-items:center;",
      "justify-content:center;font-size:11px;flex:none}",
      ".axb-step.is-active .axb-step-dot{border-color:var(--axb-accent);",
      "color:var(--axb-accent);font-weight:600}",
      ".axb-step.is-done .axb-step-dot{background:var(--axb-accent);",
      "border-color:var(--axb-accent);color:var(--axb-accent-ink)}",
      ".axb-title{font-size:17px;font-weight:600;margin:0 0 4px}",
      ".axb-subtitle{font-size:13.5px;color:var(--axb-ink-soft);margin:0 0 18px}",
      ".axb-daystrip{display:flex;gap:8px;overflow-x:auto;padding-bottom:4px;",
      "margin-bottom:16px;-webkit-overflow-scrolling:touch}",
      ".axb-day{flex:none;border:1px solid var(--axb-border);",
      "background:var(--axb-surface);border-radius:var(--axb-radius);",
      "padding:8px 12px;text-align:center;cursor:pointer;font-size:13px;",
      "color:var(--axb-ink)}",
      ".axb-day:hover{background:var(--axb-slot-hover)}",
      ".axb-day.is-selected{border-color:var(--axb-accent);",
      "background:var(--axb-accent);color:var(--axb-accent-ink)}",
      ".axb-day-dow{display:block;font-size:11px;",
      "text-transform:capitalize;opacity:.8}",
      ".axb-day-num{display:block;font-size:15px;font-weight:600}",
      ".axb-slots{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;",
      "margin-bottom:8px}",
      ".axb-slot{border:1px solid var(--axb-border);background:var(--axb-slot-bg);",
      "border-radius:var(--axb-radius);padding:9px 6px;cursor:pointer;",
      "font-size:13px;color:var(--axb-ink);text-align:center}",
      ".axb-slot:hover{background:var(--axb-slot-hover)}",
      ".axb-slot:focus-visible,.axb-day:focus-visible,",
      ".axb-btn:focus-visible,.axb-input:focus-visible{",
      "outline:2px solid var(--axb-accent);outline-offset:2px}",
      ".axb-empty{font-size:13.5px;color:var(--axb-ink-soft);",
      "padding:18px 4px;text-align:center}",
      ".axb-field{margin-bottom:12px}",
      ".axb-label{display:block;font-size:12.5px;color:var(--axb-ink-soft);",
      "margin-bottom:5px}",
      ".axb-input{width:100%;border:1px solid var(--axb-border);",
      "border-radius:var(--axb-radius);padding:9px 11px;font-size:14px;",
      "color:var(--axb-ink);background:var(--axb-surface);font-family:inherit}",
      ".axb-hint{font-size:12px;color:var(--axb-ink-soft);margin-top:10px}",
      ".axb-summary{background:var(--axb-slot-bg);border-radius:var(--axb-radius);",
      "padding:12px 14px;font-size:13.5px;margin-bottom:16px}",
      ".axb-summary strong{display:block;font-size:15px;margin-bottom:2px}",
      ".axb-actions{display:flex;gap:10px;margin-top:18px}",
      ".axb-btn{border:none;border-radius:var(--axb-radius);padding:11px 16px;",
      "font-size:14px;font-weight:600;cursor:pointer;font-family:inherit}",
      ".axb-btn-primary{background:var(--axb-accent);color:var(--axb-accent-ink);",
      "flex:1}",
      ".axb-btn-primary:disabled{opacity:.55;cursor:default}",
      ".axb-btn-ghost{background:transparent;color:var(--axb-ink-soft);",
      "border:1px solid var(--axb-border)}",
      ".axb-error{background:var(--axb-error-bg);color:var(--axb-error);",
      "border-radius:var(--axb-radius);padding:10px 12px;font-size:13px;",
      "margin-bottom:14px}",
      ".axb-success{text-align:center;padding:12px 4px}",
      ".axb-success-icon{width:44px;height:44px;border-radius:50%;",
      "background:var(--axb-accent);color:var(--axb-accent-ink);",
      "display:flex;align-items:center;justify-content:center;margin:0 auto 14px;",
      "font-size:22px}",
      "@media (prefers-reduced-motion:no-preference){.axb-panel{",
      "animation:axb-fade .15s ease-out}}",
      "@keyframes axb-fade{from{opacity:0;transform:translateY(2px)}",
      "to{opacity:1;transform:translateY(0)}}",
      "@media (max-width:360px){.axb-slots{grid-template-columns:repeat(2,1fr)}}",
    ].join("");
    document.head.appendChild(style);
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    attrs = attrs || {};
    for (var key in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, key)) continue;
      if (key === "class") node.className = attrs[key];
      else if (key === "text") node.textContent = attrs[key];
      else if (key.indexOf("on") === 0 && typeof attrs[key] === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), attrs[key]);
      } else {
        node.setAttribute(key, attrs[key]);
      }
    }
    (children || []).forEach(function (child) {
      if (child) node.appendChild(child);
    });
    return node;
  }

  function dowFormatter(locale) {
    if (!MONTH_DAY_FMT_CACHE[locale]) {
      MONTH_DAY_FMT_CACHE[locale] = new Intl.DateTimeFormat(locale, { weekday: "short" });
    }
    return MONTH_DAY_FMT_CACHE[locale];
  }

  function timeFormatter(locale) {
    if (!TIME_FMT_CACHE[locale]) {
      TIME_FMT_CACHE[locale] = new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" });
    }
    return TIME_FMT_CACHE[locale];
  }

  function sameDay(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  function addMinutes(date, minutes) {
    return new Date(date.getTime() + minutes * 60000);
  }

  function overlaps(startA, endA, startB, endB) {
    return startA < endB && endA > startB;
  }

  /** Errores de red o de validación local, distintos de un error de la API. */
  function LocalError(message) {
    this.message = message;
  }

  async function apiRequest(config, path, options) {
    options = options || {};
    var res;
    try {
      res = await fetch(config.apiBase + path, {
        method: options.method || "GET",
        headers: options.body ? { "Content-Type": "application/json" } : undefined,
        body: options.body ? JSON.stringify(options.body) : undefined,
      });
    } catch (networkErr) {
      throw new LocalError("No se pudo conectar con el servidor. Verificá tu conexión e intentá de nuevo.");
    }

    var payload = null;
    try {
      payload = await res.json();
    } catch (parseErr) {
      /* Respuesta vacía o no-JSON — se maneja según status abajo. */
    }

    if (!res.ok) {
      var code = payload && payload.error && payload.error.code;
      var message = (payload && payload.error && payload.error.message) || null;
      var err = new LocalError(friendlyErrorMessage(code, message));
      err.code = code;
      err.status = res.status;
      throw err;
    }

    return payload;
  }

  function friendlyErrorMessage(code, backendMessage) {
    if (code === "PACKAGE_NOT_LICENSED" || code === "PACKAGE_SUSPENDED") {
      return "La reserva en línea no está disponible en este momento. Por favor comunicate directamente con nosotros.";
    }
    if (code === "CONFLICT") {
      return "Ese horario ya no está disponible — alguien más lo tomó. Elegí otro, por favor.";
    }
    if (code === "VALIDATION_ERROR" && backendMessage) {
      return backendMessage;
    }
    return backendMessage || "Ocurrió un error inesperado. Por favor intentá de nuevo en unos minutos.";
  }

  function buildCandidateSlots(config, busySlots, now) {
    var days = [];
    for (var d = 0; d < config.daysAhead; d++) {
      var dayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate() + d, 0, 0, 0, 0);
      var slots = [];
      var cursor = new Date(dayStart.getFullYear(), dayStart.getMonth(), dayStart.getDate(), config.startHour, 0, 0, 0);
      var dayEnd = new Date(dayStart.getFullYear(), dayStart.getMonth(), dayStart.getDate(), config.endHour, 0, 0, 0);

      while (addMinutes(cursor, config.slotMinutes) <= dayEnd) {
        var slotEnd = addMinutes(cursor, config.slotMinutes);
        var isPast = cursor < now;
        var isBusy = busySlots.some(function (busy) {
          return overlaps(cursor, slotEnd, busy.start, busy.end);
        });
        if (!isPast && !isBusy) {
          slots.push({ start: new Date(cursor), end: new Date(slotEnd) });
        }
        cursor = slotEnd;
      }

      days.push({ date: dayStart, slots: slots });
    }
    return days;
  }

  function AxisMedicalBookingWidget(container) {
    var config = {
      apiBase: (container.getAttribute("data-api-base") || DEFAULTS.apiBase).replace(/\/+$/, ""),
      companyId: container.getAttribute("data-company-id"),
      professionalId: container.getAttribute("data-professional-id"),
      slotMinutes: parseInt(container.getAttribute("data-slot-minutes"), 10) || DEFAULTS.slotMinutes,
      startHour: parseInt(container.getAttribute("data-start-hour"), 10) || DEFAULTS.startHour,
      endHour: parseInt(container.getAttribute("data-end-hour"), 10) || DEFAULTS.endHour,
      daysAhead: parseInt(container.getAttribute("data-days-ahead"), 10) || DEFAULTS.daysAhead,
      locale: container.getAttribute("data-locale") || DEFAULTS.locale,
    };

    if (!config.apiBase || !config.companyId || !config.professionalId) {
      container.textContent =
        "Widget de reserva mal configurado: faltan data-api-base, data-company-id o data-professional-id.";
      return;
    }

    var state = {
      step: "loading", // loading | unavailable | pick-day | pick-time | form | submitting | success | fatal
      days: [],
      selectedDayIndex: 0,
      selectedSlot: null,
      formError: null,
    };

    container.classList.add("axb-root");

    function render() {
      container.innerHTML = "";
      var panel = el("div", { class: "axb-panel" });

      if (state.step === "loading") {
        panel.appendChild(el("p", { class: "axb-empty", text: "Cargando disponibilidad…" }));
      } else if (state.step === "unavailable" || state.step === "fatal") {
        panel.appendChild(el("div", { class: "axb-error", text: state.formError || "No disponible." }));
      } else if (state.step === "pick-day" || state.step === "pick-time") {
        renderSteps(panel, 1);
        panel.appendChild(el("h3", { class: "axb-title", text: "Elegí fecha y hora" }));
        panel.appendChild(el("p", { class: "axb-subtitle", text: "Seleccioná un horario disponible para tu cita." }));
        renderDayStrip(panel);
        renderTimeGrid(panel);
      } else if (state.step === "form") {
        renderSteps(panel, 2);
        panel.appendChild(el("h3", { class: "axb-title", text: "Tus datos" }));
        renderSummary(panel);
        renderForm(panel);
      } else if (state.step === "submitting") {
        renderSteps(panel, 2);
        panel.appendChild(el("p", { class: "axb-empty", text: "Confirmando tu cita…" }));
      } else if (state.step === "success") {
        renderSteps(panel, 3);
        renderSuccess(panel);
      }

      container.appendChild(panel);
    }

    function renderSteps(panel, activeIndex) {
      var labels = ["Fecha", "Datos", "Confirmación"];
      var steps = el("div", { class: "axb-steps" });
      labels.forEach(function (label, i) {
        var cls = "axb-step" + (i === activeIndex ? " is-active" : i < activeIndex ? " is-done" : "");
        steps.appendChild(
          el("span", { class: cls }, [
            el("span", { class: "axb-step-dot", text: i < activeIndex ? "✓" : String(i + 1) }),
            el("span", { text: label }),
          ])
        );
      });
      panel.appendChild(steps);
    }

    function renderDayStrip(panel) {
      var strip = el("div", { class: "axb-daystrip" });
      state.days.forEach(function (day, index) {
        if (day.slots.length === 0) return;
        var isSelected = index === state.selectedDayIndex;
        strip.appendChild(
          el(
            "button",
            {
              type: "button",
              class: "axb-day" + (isSelected ? " is-selected" : ""),
              "aria-pressed": isSelected ? "true" : "false",
              onClick: function () {
                state.selectedDayIndex = index;
                render();
              },
            },
            [
              el("span", { class: "axb-day-dow", text: dowFormatter(config.locale).format(day.date) }),
              el("span", { class: "axb-day-num", text: String(day.date.getDate()) }),
            ]
          )
        );
      });
      if (!strip.childNodes.length) {
        panel.appendChild(el("p", { class: "axb-empty", text: "No hay cupos disponibles en los próximos días. Por favor comunicate directamente con nosotros." }));
        return;
      }
      panel.appendChild(strip);
    }

    function renderTimeGrid(panel) {
      var day = state.days[state.selectedDayIndex];
      if (!day || day.slots.length === 0) return;
      var grid = el("div", { class: "axb-slots" });
      day.slots.forEach(function (slot) {
        grid.appendChild(
          el("button", {
            type: "button",
            class: "axb-slot",
            text: timeFormatter(config.locale).format(slot.start),
            onClick: function () {
              state.selectedSlot = slot;
              state.step = "form";
              state.formError = null;
              render();
            },
          })
        );
      });
      panel.appendChild(grid);
    }

    function renderSummary(panel) {
      var slot = state.selectedSlot;
      var dateLabel = new Intl.DateTimeFormat(config.locale, { weekday: "long", day: "numeric", month: "long" }).format(slot.start);
      var timeLabel = timeFormatter(config.locale).format(slot.start) + " – " + timeFormatter(config.locale).format(slot.end);
      panel.appendChild(
        el("div", { class: "axb-summary" }, [
          el("strong", { text: capitalize(dateLabel) }),
          el("span", { text: timeLabel }),
        ])
      );
    }

    function capitalize(text) {
      return text.charAt(0).toUpperCase() + text.slice(1);
    }

    function renderForm(panel) {
      if (state.formError) {
        panel.appendChild(el("div", { class: "axb-error", text: state.formError }));
      }

      var nameInput = el("input", { class: "axb-input", type: "text", id: "axb-name", required: "required" });
      var emailInput = el("input", { class: "axb-input", type: "email", id: "axb-email" });
      var phoneInput = el("input", { class: "axb-input", type: "tel", id: "axb-phone" });
      var reasonInput = el("input", { class: "axb-input", type: "text", id: "axb-reason" });

      panel.appendChild(
        el("div", { class: "axb-field" }, [el("label", { class: "axb-label", for: "axb-name", text: "Nombre completo" }), nameInput])
      );
      panel.appendChild(
        el("div", { class: "axb-field" }, [el("label", { class: "axb-label", for: "axb-email", text: "Email" }), emailInput])
      );
      panel.appendChild(
        el("div", { class: "axb-field" }, [el("label", { class: "axb-label", for: "axb-phone", text: "Teléfono" }), phoneInput])
      );
      panel.appendChild(el("p", { class: "axb-hint", text: "Dejanos al menos un email o un teléfono de contacto." }));
      panel.appendChild(
        el("div", { class: "axb-field" }, [el("label", { class: "axb-label", for: "axb-reason", text: "Motivo de la consulta (opcional)" }), reasonInput])
      );

      var actions = el("div", { class: "axb-actions" }, [
        el("button", {
          type: "button",
          class: "axb-btn axb-btn-ghost",
          text: "Volver",
          onClick: function () {
            state.step = "pick-time";
            state.formError = null;
            render();
          },
        }),
        el("button", {
          type: "button",
          class: "axb-btn axb-btn-primary",
          text: "Confirmar cita",
          onClick: function () {
            submitBooking({
              name: nameInput.value.trim(),
              email: emailInput.value.trim(),
              phone: phoneInput.value.trim(),
              reason: reasonInput.value.trim(),
            });
          },
        }),
      ]);
      panel.appendChild(actions);
    }

    function renderSuccess(panel) {
      var slot = state.selectedSlot;
      var dateLabel = new Intl.DateTimeFormat(config.locale, { weekday: "long", day: "numeric", month: "long" }).format(slot.start);
      var timeLabel = timeFormatter(config.locale).format(slot.start);
      panel.appendChild(
        el("div", { class: "axb-success" }, [
          el("div", { class: "axb-success-icon", text: "✓" }),
          el("p", { class: "axb-title", text: "¡Cita confirmada!" }),
          el("p", { class: "axb-subtitle", text: capitalize(dateLabel) + " a las " + timeLabel }),
        ])
      );
    }

    async function submitBooking(fields) {
      if (!fields.name) {
        state.formError = "El nombre es obligatorio.";
        render();
        return;
      }
      if (!fields.email && !fields.phone) {
        state.formError = "Se requiere al menos un email o teléfono de contacto.";
        render();
        return;
      }

      state.step = "submitting";
      state.formError = null;
      render();

      try {
        await apiRequest(config, "/public/medical/" + config.companyId + "/bookings", {
          method: "POST",
          body: {
            professional_user_id: parseInt(config.professionalId, 10),
            scheduled_start: state.selectedSlot.start.toISOString(),
            scheduled_end: state.selectedSlot.end.toISOString(),
            reason: fields.reason || null,
            patient_name: fields.name,
            patient_email: fields.email || null,
            patient_phone: fields.phone || null,
          },
        });
        state.step = "success";
        render();
      } catch (err) {
        if (err.code === "CONFLICT") {
          // El cupo se ocupó entre que se cargó la disponibilidad y que se
          // confirmó — se refresca la disponibilidad real en vez de dejar
          // a la persona reintentando contra un horario que ya no existe.
          state.formError = err.message;
          state.step = "form";
          render();
          await loadAvailability();
          return;
        }
        state.formError = err.message;
        state.step = "form";
        render();
      }
    }

    async function loadAvailability() {
      var now = new Date();
      var rangeFrom = now;
      var rangeTo = addMinutes(now, config.daysAhead * 24 * 60);

      try {
        var busyRaw = await apiRequest(
          config,
          "/public/medical/" +
            config.companyId +
            "/professionals/" +
            config.professionalId +
            "/busy-slots?date_from=" +
            encodeURIComponent(rangeFrom.toISOString()) +
            "&date_to=" +
            encodeURIComponent(rangeTo.toISOString())
        );
        var busySlots = busyRaw.map(function (s) {
          return { start: new Date(s.scheduled_start), end: new Date(s.scheduled_end) };
        });
        state.days = buildCandidateSlots(config, busySlots, now);
        state.selectedDayIndex = state.days.findIndex(function (d) {
          return d.slots.length > 0;
        });
        if (state.selectedDayIndex < 0) state.selectedDayIndex = 0;
        state.step = "pick-day";
      } catch (err) {
        state.step = "unavailable";
        state.formError = err.message;
      }
      render();
    }

    render();
    loadAvailability();
  }

  function init() {
    injectStylesOnce();
    var containers = document.querySelectorAll("[data-axis-medical-booking]");
    containers.forEach(function (container) {
      if (container.getAttribute("data-axb-initialized") === "true") return;
      container.setAttribute("data-axb-initialized", "true");
      AxisMedicalBookingWidget(container);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Expuesto por si el sitio que embebe necesita reinicializar el widget
  // tras insertar el contenedor dinámicamente (ej. SPA del lado del
  // cliente, o un modal que se abre bajo demanda).
  window.AxisMedicalBooking = { init: init };
})();
