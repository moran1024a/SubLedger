from __future__ import annotations

import time
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


class Database:
    def __init__(self, settings: Settings):
        db = settings.database
        url = URL.create(
            drivername="mysql+pymysql",
            username=db.username,
            password=db.password,
            host=db.host,
            port=db.port,
            database=db.database,
            query={"charset": db.charset},
        )
        self.engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=db.pool_recycle,
            pool_timeout=db.pool_timeout,
            pool_size=db.pool_size,
            max_overflow=db.max_overflow,
            connect_args={"connect_timeout": db.connect_timeout},
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    def session(self) -> Session:
        return self.session_factory()

    def check_connection(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def wait_for_connection(self, attempts: int = 30, interval_seconds: int = 2) -> None:
        for attempt in range(attempts):
            if self.check_connection():
                return
            if attempt < attempts - 1:
                time.sleep(interval_seconds)
        raise RuntimeError(f"database is not reachable after {attempts} attempts")

    def run_migrations(self) -> None:
        from alembic import command
        from alembic.config import Config

        backend_dir = Path(__file__).resolve().parents[1]
        alembic_config = Config(str(backend_dir / "alembic.ini"))
        with self.engine.begin() as connection:
            alembic_config.attributes["connection"] = connection
            command.upgrade(alembic_config, "head")

    def dispose(self) -> None:
        self.engine.dispose()


def get_db_session(database: Database) -> Generator[Session, None, None]:
    session = database.session()
    try:
        yield session
    finally:
        session.close()
