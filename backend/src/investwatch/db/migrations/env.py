"""Alembic environment: URL from settings, metadata from the ORM models."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from investwatch.config import get_settings
from investwatch.db.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL without a database connection."""
    context.configure(
        url=get_settings().sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured database."""
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = get_settings().sqlalchemy_url
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
