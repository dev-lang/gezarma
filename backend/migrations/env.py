"""Entorno de Alembic: usa los modelos de la app y la DATABASE_URL de config."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app import models  # noqa: F401  (registra todas las tablas en Base.metadata)
from backend.app.config import DATABASE_URL
from backend.app.database import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    # Permite que la app (o los tests) pasen una URL/conexión propia
    return config.attributes.get("url") or DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(
        url=_url(), target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"}, render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    connectable = engine_from_config(
        {"sqlalchemy.url": _url()}, prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as conn:
        _run(conn)


def _run(connection) -> None:
    # render_as_batch: SQLite no soporta la mayoría de los ALTER TABLE;
    # el modo batch de Alembic recrea la tabla cuando hace falta.
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
