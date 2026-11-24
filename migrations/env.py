import logging
from logging.config import fileConfig

from alembic import context
from flask import current_app

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.runtime.migration")


def include_object(objeto, nombre, tipo, reflejado, comparado):
    if tipo == "table" and objeto.info.get("excluir_de_migraciones", False):
        return False
    return True


def run_migrations_offline():
    context.configure(
        url=current_app.config["SQLALCHEMY_DATABASE_URI"],
        target_metadata=current_app.extensions["migrate"].db.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = current_app.extensions["migrate"].db.engine
    with connectable.connect() as conexion:
        context.configure(
            connection=conexion,
            target_metadata=current_app.extensions["migrate"].db.metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
