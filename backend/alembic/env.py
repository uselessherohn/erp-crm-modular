import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
from app.core import models  # noqa: E402  (registra los modelos en Base.metadata)
from app.contacts import models as contacts_models  # noqa: E402,F401
from app.inventory import models as inventory_models  # noqa: E402,F401
from app.purchasing import models as purchasing_models  # noqa: E402,F401
from app.sales import models as sales_models  # noqa: E402,F401
from app.accounting import models as accounting_models  # noqa: E402,F401
from app.pipeline import models as pipeline_models  # noqa: E402,F401
from app.hr import models as hr_models  # noqa: E402,F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Migraciones (DDL) corren con el rol dueño de las tablas (postgres), no con
# el rol de runtime de la API (erp_app, sin BYPASSRLS) — spec seccion 5.
config.set_main_option("sqlalchemy.url", settings.database_url_admin)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
