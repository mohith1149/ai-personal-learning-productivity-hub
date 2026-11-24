"""Alembic environment — uses the app's settings and model metadata."""
from logging.config import fileConfig

from alembic import context

import app.models  # noqa: F401  (registers all tables)
from app.database import Base, engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        if sqlite:
            # SQLite batch mode rebuilds tables (CREATE new, copy, DROP old, RENAME). With foreign keys enforced, DROPping
            # a parent table CASCADE-DELETES its children, silently losing data. The pragma is a no-op inside a
            # transaction, so it is switched off here, before any migration work begins, and checked afterwards.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()  # end SQLAlchemy's autobegun transaction so Alembic owns (and commits) the next one
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        connection.commit()
        if sqlite:
            broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            if broken:
                raise RuntimeError(f"Migration left dangling foreign keys: {broken[:5]}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
