"""数据库基础设施：声明基类（含约束命名约定）、引擎与会话工厂。"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import MetaData, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import ConnectionPoolEntry

from app.config import Settings

# 约束命名约定（Alembic autogenerate 与 SQLite 约束操作的前提，SQLAlchemy 官方推荐配置）
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    """UTC 当前时间（存储统一 UTC，前端本地展示）。"""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """声明基类，各域模型模块继承。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_db_engine(settings: Settings) -> AsyncEngine:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(f"sqlite+aiosqlite:///{settings.db_path}")

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn: sqlite3.Connection, _record: ConnectionPoolEntry) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker[AsyncSession](engine, expire_on_commit=False)
