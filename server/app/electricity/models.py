"""电量模块模型（electricity_samples 余额原始数据；抓取房间在应用配置中）。"""

from datetime import datetime

from sqlalchemy import DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, utcnow


class ElectricitySample(Base):
    """余额原始数据。upsert 去重：同分钟只留一条。"""

    __tablename__ = "electricity_samples"
    __table_args__ = (UniqueConstraint("sampled_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    balance: Mapped[float]
    sampled_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
