"""共享测试夹具。"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.db import Base, create_db_engine, create_session_factory


def make_settings(**overrides: object) -> Settings:
    """测试配置：显式传全部必填项，不依赖 .env。"""
    values: dict[str, object] = {
        "ntu_xiaoqu_id": 2,
        "ntu_loudong_id": 3,
        "ntu_room_id": 1,
        "shower_base_url": "https://shower.test",
        "shower_device_id": "dev-1",
        "laundry_config_path": str(Path(__file__).parent / "fixtures" / "laundry.json"),
        "notify_config_path": str(Path(__file__).parent.parent / "config" / "notify.json"),
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
async def session_factory(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """临时 SQLite 库（按测试隔离，表结构直接建）。"""
    settings = make_settings(db_path=str(tmp_path / "test.db"))
    engine = create_db_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()
