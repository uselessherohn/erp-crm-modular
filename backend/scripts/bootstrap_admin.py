import asyncio
from app import models_registry  # noqa: F401  (registra todos los modelos — ver ese módulo)
from app.database import AsyncSessionLocal
from app.core import models, security
from sqlalchemy import select, text


async def bootstrap():
    async with AsyncSessionLocal() as db:
        # Se busca "El Roble" por nombre en vez de asumir company_id=1 —
        # el id real depende de cuántas filas haya consumido la secuencia
        # antes de este bootstrap (ej. tests de pytest corridos antes).
        company_id = (
            await db.execute(select(models.Company.id).where(models.Company.name == "El Roble"))
        ).scalar_one()
        await db.execute(text("SELECT set_config('app.current_company_id', :cid, false)"), {"cid": str(company_id)})
        perms = [
            models.Permission(code="core:user:create", description="Crear usuarios"),
            models.Permission(code="core:user:list", description="Listar usuarios"),
            models.Permission(code="core:user:read", description="Ver un usuario"),
            models.Permission(code="core:role:create", description="Crear roles"),
            models.Permission(code="core:role:list", description="Listar roles"),
            models.Permission(code="contacts:contact:create", description="Crear contactos"),
            models.Permission(code="contacts:contact:list", description="Listar contactos"),
            models.Permission(code="contacts:contact:read", description="Ver un contacto"),
            models.Permission(code="contacts:contact:update", description="Editar contactos"),
            models.Permission(code="inventory:category:create", description="Crear categorías"),
            models.Permission(code="inventory:category:list", description="Listar categorías"),
            models.Permission(code="inventory:warehouse:create", description="Crear almacenes"),
            models.Permission(code="inventory:warehouse:list", description="Listar almacenes"),
            models.Permission(code="inventory:product:create", description="Crear productos"),
            models.Permission(code="inventory:product:list", description="Listar productos"),
            models.Permission(code="inventory:product:read", description="Ver un producto"),
            models.Permission(code="inventory:stock:write", description="Registrar movimientos de stock"),
            models.Permission(code="inventory:stock:read", description="Ver saldos de stock"),
            models.Permission(code="purchasing:po:create", description="Crear órdenes de compra"),
            models.Permission(code="purchasing:po:list", description="Listar órdenes de compra"),
            models.Permission(code="purchasing:po:read", description="Ver una orden de compra"),
            models.Permission(code="purchasing:po:confirm", description="Confirmar orden de compra"),
            models.Permission(code="purchasing:po:cancel", description="Cancelar orden de compra"),
            models.Permission(code="purchasing:po:receive", description="Registrar recepción de mercancía"),
            models.Permission(code="purchasing:po:close", description="Cerrar orden de compra"),
            models.Permission(code="sales:price_list:create", description="Crear listas de precios"),
            models.Permission(code="sales:price_list:list", description="Listar listas de precios"),
            models.Permission(code="sales:quote:create", description="Crear cotizaciones"),
            models.Permission(code="sales:quote:list", description="Listar cotizaciones"),
            models.Permission(code="sales:quote:read", description="Ver una cotización"),
            models.Permission(code="sales:quote:send", description="Enviar cotización"),
            models.Permission(code="sales:quote:accept", description="Aceptar cotización"),
            models.Permission(code="sales:quote:cancel", description="Cancelar cotización"),
            models.Permission(code="sales:quote:convert", description="Convertir cotización a orden"),
            models.Permission(code="sales:order:create", description="Crear órdenes de venta"),
            models.Permission(code="sales:order:list", description="Listar órdenes de venta"),
            models.Permission(code="sales:order:read", description="Ver una orden de venta"),
            models.Permission(code="sales:order:confirm", description="Confirmar orden de venta"),
            models.Permission(code="sales:order:prepare", description="Pasar orden a preparación"),
            models.Permission(code="sales:order:ship", description="Registrar envío"),
            models.Permission(code="sales:order:invoice", description="Facturar orden de venta"),
            models.Permission(code="sales:order:cancel", description="Cancelar orden de venta"),
            models.Permission(code="accounting:account:create", description="Crear cuenta contable"),
            models.Permission(code="accounting:account:list", description="Listar cuentas contables"),
            models.Permission(
                code="accounting:document_account_mapping:upsert", description="Configurar mapeo documento→cuentas"
            ),
            models.Permission(
                code="accounting:document_account_mapping:list", description="Listar mapeo documento→cuentas"
            ),
            models.Permission(code="accounting:tax_rate:create", description="Crear tasa de impuesto"),
            models.Permission(code="accounting:tax_rate:list", description="Listar tasas de impuesto"),
            models.Permission(code="accounting:invoice:create", description="Crear factura"),
            models.Permission(code="accounting:invoice:list", description="Listar facturas"),
            models.Permission(code="accounting:invoice:read", description="Ver una factura"),
            models.Permission(code="accounting:invoice:post", description="Contabilizar factura"),
            models.Permission(code="accounting:invoice:cancel", description="Cancelar factura en borrador"),
            models.Permission(code="accounting:credit_debit_note:create", description="Crear nota de crédito/débito"),
            models.Permission(code="accounting:credit_debit_note:list", description="Listar notas de crédito/débito"),
            models.Permission(code="accounting:credit_debit_note:read", description="Ver una nota de crédito/débito"),
            models.Permission(code="accounting:credit_debit_note:post", description="Contabilizar nota de crédito/débito"),
            models.Permission(code="accounting:credit_debit_note:cancel", description="Cancelar nota en borrador"),
            models.Permission(code="accounting:payment:create", description="Crear pago/cobro"),
            models.Permission(code="accounting:payment:list", description="Listar pagos/cobros"),
            models.Permission(code="accounting:payment:read", description="Ver un pago/cobro"),
            models.Permission(code="accounting:payment:post", description="Contabilizar pago/cobro"),
            models.Permission(code="accounting:payment:cancel", description="Cancelar pago en borrador"),
            models.Permission(code="accounting:credit_status:read", description="Consultar Motor de Contención Financiera"),
            models.Permission(code="pipeline:stage:create", description="Crear etapa de pipeline"),
            models.Permission(code="pipeline:stage:list", description="Listar etapas de pipeline"),
            models.Permission(code="pipeline:opportunity:create", description="Crear oportunidad"),
            models.Permission(code="pipeline:opportunity:list", description="Listar oportunidades"),
            models.Permission(code="pipeline:opportunity:read", description="Ver una oportunidad"),
            models.Permission(code="pipeline:opportunity:move_stage", description="Mover oportunidad de etapa"),
            models.Permission(code="pipeline:opportunity:close", description="Cerrar oportunidad ganada/perdida"),
            models.Permission(code="pipeline:opportunity:reopen", description="Reabrir oportunidad cerrada"),
            models.Permission(code="pipeline:activity:create", description="Registrar actividad"),
            models.Permission(code="pipeline:activity:list", description="Listar actividades"),
            models.Permission(code="pipeline:activity:complete", description="Completar actividad"),
            models.Permission(code="hr:department:create", description="Crear departamento"),
            models.Permission(code="hr:department:list", description="Listar departamentos"),
            models.Permission(code="hr:position:create", description="Crear puesto"),
            models.Permission(code="hr:position:list", description="Listar puestos"),
            models.Permission(code="hr:employee:create", description="Crear legajo de empleado"),
            models.Permission(code="hr:employee:read", description="Ver legajo (sin salario)"),
            models.Permission(code="hr:employee:read-sensitive", description="Ver salario del legajo"),
            models.Permission(code="hr:employee:terminate", description="Dar de baja a un empleado"),
            models.Permission(code="medical:record:create", description="Crear entrada de expediente clínico"),
            models.Permission(code="medical:record:read-own-patients", description="Ver expediente de pacientes propios"),
            models.Permission(code="medical:record:read-all", description="Ver expediente de cualquier paciente"),
            models.Permission(code="medical:appointment:create", description="Agendar cita"),
            models.Permission(code="medical:appointment:list", description="Listar citas"),
            models.Permission(code="medical:appointment:read", description="Ver una cita"),
            models.Permission(code="medical:appointment:confirm", description="Confirmar cita"),
            models.Permission(code="medical:appointment:reschedule", description="Reprogramar cita"),
            models.Permission(code="medical:appointment:cancel", description="Cancelar cita"),
            models.Permission(code="medical:consultation:create", description="Registrar/corregir consulta"),
            models.Permission(code="medical:consultation:read-own-patients", description="Ver consulta de pacientes propios"),
            models.Permission(code="medical:consultation:read-all", description="Ver consulta de cualquier paciente"),
            models.Permission(code="notifications:template:create", description="Crear/editar plantillas de notificación"),
            models.Permission(code="notifications:template:list", description="Listar plantillas de notificación"),
            models.Permission(code="notifications:notification:send", description="Enviar una notificación"),
            models.Permission(code="medical:prescription:create", description="Emitir/anular receta"),
            models.Permission(code="medical:prescription:read-own-patients", description="Ver recetas de pacientes propios"),
            models.Permission(code="medical:prescription:read-all", description="Ver recetas de cualquier paciente"),
            models.Permission(code="medical:lab_order:create", description="Ordenar laboratorio / cargar resultado"),
            models.Permission(code="medical:lab_order:read-own-patients", description="Ver laboratorio de pacientes propios"),
            models.Permission(code="medical:lab_order:read-all", description="Ver laboratorio de cualquier paciente"),
            models.Permission(code="medical:teleconsultation:create", description="Abrir/iniciar/finalizar sesión de teleconsulta"),
            models.Permission(code="medical:teleconsultation:read-own-patients", description="Ver teleconsulta de pacientes propios"),
            models.Permission(code="medical:teleconsultation:read-all", description="Ver teleconsulta de cualquier paciente"),
            models.Permission(code="medical:billing:create", description="Emitir/anular facturación médica"),
            models.Permission(code="medical:billing:read-own-patients", description="Ver facturación de pacientes propios"),
            models.Permission(code="medical:billing:read-all", description="Ver facturación de cualquier paciente"),
        ]
        db.add_all(perms)
        await db.flush()

        role = models.Role(company_id=company_id, name="admin", description="Bootstrap admin")
        db.add(role)
        await db.flush()
        for p in perms:
            db.add(models.RolePermission(role_id=role.id, permission_id=p.id))

        user = models.User(
            company_id=company_id,
            email="admin@elroble.hn",
            full_name="Admin Bootstrap",
            hashed_password=security.hash_password("SuperSegura123"),
        )
        db.add(user)
        await db.flush()
        db.add(models.UserRole(user_id=user.id, role_id=role.id))

        # Paquetes activos — condición de arranque para `require_package`
        # (spec 2.4), sin la cual TODAS las rutas gateadas devuelven 403 sin
        # importar el RBAC. Sin endpoint público para contratar paquetes
        # todavía (TODO conocido) — se activa directo contra la base, igual
        # que se documentó en el cierre de `pipeline`.
        db.add(models.CompanyPackage(company_id=company_id, package="administrative", status="active"))
        db.add(models.CompanyPackage(company_id=company_id, package="medical", status="active"))

        await db.commit()
        print("bootstrap ok — user_id:", user.id, "role_id:", role.id)


asyncio.run(bootstrap())
