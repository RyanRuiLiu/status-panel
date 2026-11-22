"""电量模块 Pydantic 模型（服务层类型化边界，路由复用为响应模型）。"""

from datetime import datetime

from pydantic import BaseModel


class ElectricityStatus(BaseModel):
    """当前电量状态；无法计算的指标一律 None（前端显示 —）。

    - balance/sampled_at：最新采样（全历史范围）
    - today/yesterday/week/month_usage：对应自然日窗口内的用量累计（度）
    - estimated_days：余额 ÷ 近7天日均，向下取整
    """

    balance: float | None
    sampled_at: datetime | None
    today_usage: float | None
    yesterday_usage: float | None
    week_usage: float | None
    month_usage: float | None
    estimated_days: int | None
