"""
Importa TODOS los módulos de modelos del proyecto, sin excepción.

Motivo (bug real encontrado en scripts/bootstrap_admin.py): SQLAlchemy
resuelve las FK declaradas como string (ej. ForeignKey("warehouses.id"))
de forma perezosa, cuando se configuran los mappers — si el módulo que
define esa tabla nunca se importó en el proceso, la resolución falla con
NoReferencedTableError, aunque el código que falla ni siquiera toque esa
tabla directamente (le pasa a cualquier operación sobre `User`, que tiene
una FK a `warehouses`, en un proceso que solo importó `app.core.models`).

Cualquier script o entrypoint que no pase por `app.main` (que sí importa
todo vía los routers) debe importar este módulo primero, no los módulos
de modelos sueltos.
"""
from app.core import models as core_models  # noqa: F401
from app.contacts import models as contacts_models  # noqa: F401
from app.inventory import models as inventory_models  # noqa: F401
from app.purchasing import models as purchasing_models  # noqa: F401
from app.sales import models as sales_models  # noqa: F401
from app.accounting import models as accounting_models  # noqa: F401
from app.pipeline import models as pipeline_models  # noqa: F401
from app.hr import models as hr_models  # noqa: F401
