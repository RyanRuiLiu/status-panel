"""电量仓储契约测试（upsert 去重 / 最新余额）。"""

from datetime import UTC, datetime, timedelta

from app.electricity.models import ElectricitySample
from app.electricity.repository import ElectricityRepository


def repo(session_factory) -> ElectricityRepository:
    return ElectricityRepository(session_factory)


async def add_sample(session_factory, balance: float, minutes_ago: int) -> None:
    async with session_factory() as session:
        session.add(
            ElectricitySample(
                balance=balance,
                sampled_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
            )
        )
        await session.commit()


async def test_upsert_same_minute_dedup(session_factory):
    r = repo(session_factory)
    anchor = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)  # 固定锚点，避免跨分钟边界的时序偶发

    await r.upsert_sample(100.0, sampled_at=anchor)
    await r.upsert_sample(98.5, sampled_at=anchor)  # 同分钟写入 → 更新而非新增

    async with session_factory() as session:
        rows = (await session.execute(ElectricitySample.__table__.select())).fetchall()
    assert len(rows) == 1
    assert rows[0].balance == 98.5


async def test_upsert_different_minute_keeps_both(session_factory):
    r = repo(session_factory)
    now = datetime.now(UTC)
    await r.upsert_sample(100.0, sampled_at=now.replace(second=0, microsecond=0))
    await r.upsert_sample(
        98.0, sampled_at=(now - timedelta(minutes=1)).replace(second=0, microsecond=0)
    )

    async with session_factory() as session:
        rows = (await session.execute(ElectricitySample.__table__.select())).fetchall()
    assert len(rows) == 2


async def test_latest_balance(session_factory):
    await add_sample(session_factory, 100.0, minutes_ago=30)
    await add_sample(session_factory, 98.0, minutes_ago=5)
    latest = await repo(session_factory).latest_balance()
    assert latest is not None
    assert latest[0] == 98.0


async def test_latest_balance_empty_db_none(session_factory):
    assert await repo(session_factory).latest_balance() is None


async def test_reads_return_utc_aware(session_factory):
    """SQLite 读回 naive datetime，仓储层必须显式挂 UTC（时区运算的前提）。"""
    await repo(session_factory).upsert_sample(
        98.0, sampled_at=datetime(2026, 11, 9, 16, 0, tzinfo=UTC)
    )

    latest = await repo(session_factory).latest_balance()
    assert latest is not None
    assert latest[1].tzinfo is UTC

    rows = await repo(session_factory).samples_since(datetime(2026, 11, 1, tzinfo=UTC))
    assert rows[0][0].tzinfo is UTC
    assert rows[0][0].utcoffset() == timedelta(0)
