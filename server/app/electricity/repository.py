"""电量数据仓储（DB 访问层，全部走 async session）。"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.electricity.models import ElectricitySample


def _as_utc(t: datetime) -> datetime:
    """SQLite 返回 naive datetime（存储值为 UTC 但不带时区标记），显式挂 UTC 供时区运算。"""
    return t.replace(tzinfo=UTC)


class ElectricityRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def upsert_sample(self, balance: float, sampled_at: datetime | None = None) -> None:
        """写入采样（UTC 分钟为采样时间窗，同窗去重；显式时间戳供迁移导入用）。"""
        if sampled_at is None:
            sampled_at = datetime.now(UTC).replace(second=0, microsecond=0)
        async with self._session_factory() as session:
            stmt = (
                sqlite_insert(ElectricitySample)
                .values(balance=balance, sampled_at=sampled_at)
                .on_conflict_do_update(index_elements=["sampled_at"], set_={"balance": balance})
            )
            await session.execute(stmt)
            await session.commit()

    async def latest_balance(self) -> tuple[float, datetime] | None:
        """最新余额；从未采样过返回 None。"""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ElectricitySample.balance, ElectricitySample.sampled_at)
                .order_by(ElectricitySample.sampled_at.desc())
                .limit(1)
            )
            row = result.first()
            return (row[0], _as_utc(row[1])) if row else None

    async def samples_since(self, start: datetime) -> list[tuple[datetime, float]]:
        """窗口内原始采样（按时间升序），供用量统计。"""
        async with self._session_factory() as session:
            result = await session.execute(
                select(ElectricitySample.sampled_at, ElectricitySample.balance)
                .where(ElectricitySample.sampled_at >= start)
                .order_by(ElectricitySample.sampled_at)
            )
            return [(_as_utc(t), b) for t, b in result.all()]
