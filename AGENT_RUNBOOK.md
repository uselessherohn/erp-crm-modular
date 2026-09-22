# AGENT_RUNBOOK.md — cómo correr la suite de calidad extendida sin supervisión

Este documento es para un agente LLM con acceso a red y a una terminal, sin
contexto previo del proyecto. Sigue los pasos en orden; cada uno dice qué
comando correr, qué esperar, y qué hacer si algo no sale así. Al final hay
una checklist para pegar en el reporte final.

No reemplaza `QUALITY_SUITE.md` (que documenta el QUÉ y el POR QUÉ de las
6 etapas originales) — este documento es el CÓMO operativo, extendido con
las 6 etapas nuevas: seguridad multi-tenant, concurrencia real, secretos,
rate-limiting, backup/restore, mutation testing, y E2E con navegador real.

## 0. Antes de empezar — qué necesitás

- Una terminal con `bash`, acceso de administrador (instalar paquetes del
  sistema), y **acceso saliente a internet** — específicamente necesitás
  llegar a: PyPI (`pypi.org`), npm (`registry.npmjs.org`), y, solo para la
  etapa de Playwright, `cdn.playwright.dev` / `playwright.azureedge.net`
  (descarga del binario de Chromium — bloqueado en algunos sandboxes; ver
  sección 7).
- ~15-20 minutos para el setup inicial, y entre 30 minutos y unas pocas
  horas para la corrida completa dependiendo de cuánto de `mutation`
  corras (es la única etapa cuyo tiempo escala con cuántos mutantes le
  pidas).

## 1. Levantar el entorno

```bash
# Postgres real — no hay mocks en ningún punto de esta suite
apt-get update && apt-get install -y postgresql postgresql-contrib
service postgresql start

# Roles y base — mismos nombres/valores que el resto del proyecto espera
su postgres -c "psql -c \"ALTER USER postgres PASSWORD 'postgres_dev_pw';\""
su postgres -c "psql -c \"CREATE DATABASE erp_crm_dev;\""
PGPASSWORD=postgres_dev_pw psql -h localhost -U postgres -d erp_crm_dev -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
PGPASSWORD=postgres_dev_pw psql -h localhost -U postgres -d erp_crm_dev -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
PGPASSWORD=postgres_dev_pw psql -h localhost -U postgres -d erp_crm_dev -c "
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'erp_app') THEN
      CREATE ROLE erp_app LOGIN PASSWORD 'erp_app_dev_pw' NOSUPERUSER NOBYPASSRLS;
    END IF;
  END
  \$\$;
"

# Backend
cd backend
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-qa.txt   # ruff, mypy, hypothesis, pip-audit, mutmut, etc.

cat > .env << 'EOF'
DATABASE_URL=postgresql+asyncpg://erp_app:erp_app_dev_pw@localhost:5432/erp_crm_dev
DATABASE_URL_AUTH_LOOKUP=postgresql+asyncpg://erp_auth_lookup:erp_auth_lookup_dev_pw@localhost:5432/erp_crm_dev
DATABASE_URL_ADMIN=postgresql+psycopg://postgres:postgres_dev_pw@localhost:5432/erp_crm_dev
JWT_SECRET_KEY=agent_run_secret_key_not_for_production
PGCRYPTO_KEY=agent_run_pgcrypto_key_not_for_production
INTERNAL_API_KEY=agent_run_internal_api_key_not_for_production
EOF

export $(cat .env | xargs)
alembic upgrade head   # crea erp_auth_lookup si no existe (ver primera migración) — confirmar "head" al final

# Frontend
cd ../frontend
npm install
```

**Punto de control**: `alembic current` debe imprimir una revisión con
`(head)`. Si falla acá, ningún paso siguiente va a funcionar — no sigas
sin resolver esto.

## 2. Las 6 etapas originales — no tocarlas primero

Antes de tocar nada nuevo, confirmá que lo que ya existía sigue funcionando:

```bash
cd backend
python ../scripts/qa_suite/run_quality_suite.py
```

Esto corre `baseline`, `sql-audit`, `frontend`, `http`, `property`,
`deps-audit` en orden (se detiene en la primera que falle). Si alguna de
estas 6 falla, es una regresión — no sigas con las etapas nuevas hasta
entender por qué (probablemente el entorno, no el código: revisar que
Postgres esté arriba, que `.env` tenga los valores de arriba).

## 3. Levantar un backend real — lo necesitan 4 de las 6 etapas nuevas

`concurrency`, `rate-limit-audit`, y el flujo Playwright necesitan un
`uvicorn` real corriendo, no en el mismo proceso que el test runner:

```bash
cd backend
. venv/bin/activate && export $(cat .env | xargs)
nohup uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/uvicorn.log 2>&1 &
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/docs   # debe imprimir 200
```

Si esto no imprime `200`, revisar `/tmp/uvicorn.log` antes de seguir —
todas las etapas de esta sección van a fallar de forma confusa si el
backend no está realmente arriba.

## 4. Las etapas nuevas que no necesitan nada especial

```bash
cd backend
python ../scripts/qa_suite/run_quality_suite.py --stage security
python ../scripts/qa_suite/run_quality_suite.py --stage secrets-audit
python ../scripts/qa_suite/run_quality_suite.py --stage backup-restore
```

- **`security`** (66 tests + 1 skip esperado): aislamiento multi-tenant.
  Cualquier fallo acá es severidad alta — un tenant pudo ver/tocar datos
  de otro. Investigar de inmediato, no seguir con el resto de la suite
  hasta cerrarlo.
- **`secrets-audit`**: si reporta hallazgos "reales" (no en la sección de
  posibles falsos positivos), tratarlo como incidente de seguridad — un
  secreto commiteado se asume comprometido, no alcanza con borrarlo
  (rotar la credencial; si está en el historial de git, también hace
  falta reescribir el historial).
- **`backup-restore`**: necesita `pg_dump`/`psql`/`createdb`/`dropdb` en
  el PATH (vienen con la instalación de Postgres del paso 1) y permiso
  para crear/dropear bases — usa el mismo rol admin que Alembic.

## 5. Las etapas que necesitan el backend del paso 3

```bash
cd backend
python ../scripts/qa_suite/run_quality_suite.py --stage concurrency
python ../scripts/qa_suite/run_quality_suite.py --stage rate-limit-audit
```

- **`concurrency`**: dos escenarios (oversell de stock, idempotencia bajo
  carrera real). Un mensaje de "✗ FALLO CRÍTICO" en oversell o duplicado
  de orden es un bug real de concurrencia — el tipo de cosa que solo se
  ve bajo carga real, no en tests secuenciales. Un "⚠ HALLAZGO (no
  bloqueante)" es una señal a investigar pero no bloquea el resto.
- **`rate-limit-audit`**: casi seguro va a reportar el hallazgo ya
  conocido (sin rate-limiting por IP en `/auth/login`) salvo que alguien
  ya lo haya corregido — no es una regresión de esta corrida, es un
  hallazgo preexistente documentado en `STATE.md`.

**Si algo en esta sección se cuelga o tira errores raros de conexión**:
lo más probable es que Postgres o uvicorn se hayan caído entre pasos
(pasa en sandboxes con timeouts de inactividad). Revisar con
`service postgresql status` y `curl http://127.0.0.1:8000/docs`, y
relanzar lo que haga falta del paso 1/3 antes de reintentar — no es
necesariamente un bug real.

## 6. Mutation testing — la única etapa que hay que correr manualmente aparte

`mutation` NO está en la corrida por defecto (`OPTIONAL_STAGES`) porque
tarda minutos incluso acotada, y no es un gate pasa/no-pasa sino una
herramienta exploratoria:

```bash
cd backend
python ../scripts/qa_suite/run_quality_suite.py --stage mutation
```

Al final va a imprimir un resumen tipo `54/70 killed, 16 survived`. Un
mutante sobreviviente no es un fallo — es una señal de que esa línea, pese
a tener cobertura, no tiene un test que realmente la ponga a prueba. Para
ver el código exacto de un mutante sobreviviente:

```bash
python -m mutmut show <id>
```

Está acotada a `app/core/security.py` — ver el comentario en
`backend/pyproject.toml` bajo `[tool.mutmut]` para extenderla a otro
módulo (necesita un archivo de tests rápido y aislado para ese módulo, no
la suite completa — si no existe uno, escribirlo primero vale más que
dejar que mutmut corra ~350s por mutante).

## 7. Playwright — la única etapa con un requisito de red distinto

Esta es la etapa que más probablemente NO haya podido correr quien armó
esta suite (verificado con un intento real de instalación que falló por
red bloqueada). Confirmar el acceso ANTES de gastar tiempo en el resto de
los pasos:

```bash
cd frontend
npx playwright install chromium
```

- **Si esto funciona** (descarga el binario sin error), seguir con los
  pasos de abajo.
- **Si falla con algo como `Host not in allowlist: cdn.playwright.dev`**:
  el entorno donde corre el agente bloquea ese host — no hay forma de
  correr esta etapa ahí. Reportarlo como limitación del entorno, no como
  fallo de la suite, y seguir con el resto (las otras 11 etapas no
  dependen de esto).

Con el navegador instalado:

```bash
# El backend del paso 3 tiene que seguir corriendo — Playwright pega
# contra él (vía el build del frontend, que a su vez pega contra
# http://127.0.0.1:8000).
cd frontend
npx playwright test --config=tests/e2e/playwright.config.ts
```

`global-setup.ts` siembra "El Roble" + el admin de bootstrap
(`admin@elroble.hn` / `SuperSegura123`) la primera vez — necesita
`INTERNAL_API_KEY` en el entorno (el mismo valor de `backend/.env`):

```bash
export INTERNAL_API_KEY=agent_run_internal_api_key_not_for_production
```

**Sobre `critical-flow.spec.ts` específicamente**: sus selectores se
confirmaron leyendo el componente real (`CreatePaymentDialog.tsx`), pero
nunca se corrieron contra un navegador real antes de esta corrida (mismo
motivo de red). Si falla, antes de asumir un bug de la app: mirar el
video/trace que Playwright genera en `frontend/test-results/` (configurado
con `trace: "retain-on-failure"`) — es muy probable que sea un selector
que necesita un ajuste menor (ej. el texto exacto de una opción de un
`Select` de Radix), no un problema real de la aplicación. Si después de
mirar el trace sigue sin quedar claro, es una señal genuinamente nueva —
tratarla como tal.

## 8. Checklist para el reporte final

Copiar y completar:

```
[ ] Etapas 1-6 (originales): ______ (todas en verde / detalle de lo que falló)
[ ] security: ______ / 66 tests, ______ skip
[ ] concurrency: oversell ______, idempotencia ______
[ ] secrets-audit: ______ hallazgos reales, ______ posibles falsos positivos
[ ] rate-limit-audit: throttling ______, timing side-channel ______
[ ] backup-restore: ______
[ ] mutation: ______ / ______ killed (si se corrió)
[ ] playwright: ______ (corrió / bloqueado por red — especificar cuál)
```

Cualquier casilla que no diga "en verde"/"sin hallazgos" necesita una
línea de detalle: qué falló, el comando exacto para reproducirlo, y si ya
había un hallazgo documentado para eso en `STATE.md` o si es nuevo.
