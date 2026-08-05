from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
#
# disable_existing_loggers=False matters here specifically: this env.py
# runs in-process (via app.db_migrate.run_migrations, called from
# app.main at startup), not just as a standalone `alembic` CLI invocation.
# fileConfig()'s default (True) disables every logger not explicitly
# listed in alembic.ini's [loggers] section -- which would silently kill
# the "cablelims" logger app/logging_config.py just finished configuring
# a few lines earlier in app.main, going unnoticed until someone needed
# the log file during an actual incident and found it empty.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Pulls in every ORM-mapped table so target_metadata below is complete --
# `import app.models.models` has the side effect of registering every
# mapped class onto app.db.Base.metadata, which is what autogenerate diffs
# against.
from app.db import Base, SQLALCHEMY_DATABASE_URL  # noqa: E402
import app.models.models  # noqa: E402,F401

target_metadata = Base.metadata

# The app's actual DB path (app/db.py's DATA_DIR, which respects the same
# packaged-install layout every other module relies on) always wins over
# whatever static alembic.ini has -- this is the same URL app.db.engine
# itself was built from, so `alembic upgrade head` run from a shell always
# targets the real database, not a stale hardcoded path.
config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # app.db_migrate.run_migrations() passes the actual Engine it was given
    # via config.attributes["connection"] (the standard Alembic
    # connection-sharing recipe) -- this is what lets it target a specific
    # database (a test's tmp_path SQLite file, not just the app's real one)
    # instead of always silently falling back to SQLALCHEMY_DATABASE_URL
    # above, which is a plain CLI invocation's only option (`alembic
    # upgrade head` from a shell has no engine to hand in).
    connectable = config.attributes.get("connection", None)
    owns_connectable = connectable is None
    if connectable is None:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        # render_as_batch=True: SQLite can't ALTER COLUMN, DROP COLUMN, or
        # add a constraint in place -- Alembic's batch mode works around
        # this by recreating the table (new table, copy rows, drop old,
        # rename) under the hood. Every future migration against this
        # SQLite-only app (see app/db.py's module docstring on the Postgres
        # question) needs this to do anything beyond ADD COLUMN.
        context.configure(
            connection=connection, target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    if owns_connectable:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
