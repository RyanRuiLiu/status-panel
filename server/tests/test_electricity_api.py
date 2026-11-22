"""电量 API 端到端测试（公开只读）。"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI

from app.db import Base, create_db_engine, create_session_factory
from app.electricity.repository import ElectricityRepository
from app.electricity.router import router as electricity_router
from tests.conftest import make_settings


@pytest.fixture
async def api(tmp_path) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    settings = make_settings(db_path=str(tmp_path / "api.db"))
    engine = create_db_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(electricity_router)
    app.state.session_factory = create_session_factory(engine)
    app.state.settings = settings

    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    yield client, app
    await client.aclose()
    await engine.dispose()


async def test_status_returns_latest_sample(api):
    client, app = api
    await ElectricityRepository(app.state.session_factory).upsert_sample(98.0)

    r = await client.get("/api/v1/electricity")
    assert r.status_code == 200
    body = r.json()
    assert body["balance"] == 98.0
    assert body["sampled_at"] is not None


async def test_status_empty_db_nulls(api):
    client, _ = api
    r = await client.get("/api/v1/electricity")
    assert r.status_code == 200
    body = r.json()
    assert body["balance"] is None
    assert body["sampled_at"] is None


async def test_status_stale_sample_outside_window(api):
    """仅有的采样在 30 天窗口外：余额与更新时间如实显示旧值，窗口指标全 null。"""
    client, app = api
    old = datetime.now(UTC) - timedelta(days=40)
    await ElectricityRepository(app.state.session_factory).upsert_sample(98.0, sampled_at=old)

    r = await client.get("/api/v1/electricity")
    assert r.status_code == 200
    body = r.json()
    assert body["balance"] == 98.0
    assert body["sampled_at"] is not None
    assert body["today_usage"] is None
    assert body["yesterday_usage"] is None
    assert body["week_usage"] is None
    assert body["month_usage"] is None
    assert body["estimated_days"] is None
