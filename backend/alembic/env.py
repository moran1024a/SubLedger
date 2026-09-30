from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import URL

from app.config import load_settings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    settings = load_settings()
    db = settings.database
    database_url = URL.create(
        "mysql+pymysql",
        username=db.username,
        password=db.password,
        host=db.host,
        port=db.port,
        database=db.database,
        query={"charset": db.charset},
    )
    context.configure(url=database_url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    settings = load_settings()
    db = settings.database
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = URL.create(
        "mysql+pymysql",
        username=db.username,
        password=db.password,
        host=db.host,
        port=db.port,
        database=db.database,
        query={"charset": db.charset},
    ).render_as_string(hide_password=False)
    connectable = engine_from_config(
        configuration,
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
