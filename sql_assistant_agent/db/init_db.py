from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from sql_assistant_agent.config.config import (
    APP_DB_HOST,
    APP_DB_NAME,
    APP_DB_PASSWORD,
    APP_DB_PORT,
    APP_DB_USER,
)
from sql_assistant_agent.db.models import Base


def _build_mysql_url() -> str:
    return (
        f"mysql+pymysql://{APP_DB_USER}:{APP_DB_PASSWORD}"
        f"@{APP_DB_HOST}:{APP_DB_PORT}/{APP_DB_NAME}?charset=utf8mb4"
    )


def _ensure_database_exists() -> None:
    url_no_db = (
        f"mysql+pymysql://{APP_DB_USER}:{APP_DB_PASSWORD}"
        f"@{APP_DB_HOST}:{APP_DB_PORT}/?charset=utf8mb4"
    )
    engine = create_engine(url_no_db)
    with engine.connect() as conn:
        conn.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{APP_DB_NAME}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
    engine.dispose()


_ensure_database_exists()

_engine = create_engine(_build_mysql_url(), pool_pre_ping=True, pool_recycle=3600)
_SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def create_tables() -> None:
    Base.metadata.create_all(_engine)


def get_db() -> Iterator[Session]:
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Iterator[Session]:
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


create_tables()
