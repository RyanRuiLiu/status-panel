"""电量模块服务：查询侧状态聚合 + 用量统计 + 轮询编排 + 告警策略。"""

import itertools
import logging
import string
from datetime import UTC, date, datetime, time, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import NotifyCard, NotifyConfig, Settings
from app.electricity.repository import ElectricityRepository
from app.electricity.schemas import ElectricityStatus
from app.integrations.ntu.errors import (
    NtuAuthError,
    NtuCaptchaRequiredError,
    NtuCheckoutError,
    NtuContractError,
    NtuError,
)
from app.integrations.ntu.payment import BalanceClient
from app.integrations.ntu.schemas import RoomRef
from app.integrations.wecom import (
    CardAction,
    CardHorizontalItem,
    CardMainTitle,
    CardSource,
    TextNoticeCard,
    WeComBot,
)

logger = logging.getLogger(__name__)

# 学校所在地时区：中国全境 UTC+8、无夏令时（确定性事实）。自然日/自然月按此划分。
STATS_TZ = timezone(timedelta(hours=8))


def _local_date(dt: datetime) -> date:
    return dt.astimezone(STATS_TZ).date()


def _time_text(dt: datetime) -> str:
    return dt.astimezone(STATS_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _render(template: str, values: dict[str, object]) -> str:
    return string.Template(template).substitute(values)


def _build_card(
    cfg: NotifyCard,
    notify: NotifyConfig,
    now: datetime,
    values: dict[str, object],
) -> TextNoticeCard:
    fields = [
        CardHorizontalItem(keyname=key, value=_render(value, values))
        for key, value in cfg["fields"]
    ]
    fields.append(CardHorizontalItem(keyname="时间", value=_time_text(now)))
    desc = cfg.get("desc")
    return TextNoticeCard(
        main_title=CardMainTitle(
            title=_render(cfg["title"], values),
            desc=_render(desc, values) if desc is not None else None,
        ),
        source=CardSource(desc=notify["source_desc"], desc_color=cfg["severity"]),
        horizontal_content_list=fields,
        card_action=CardAction(type=1, url=notify["action_url"]),
    )


def compute_usage_stats(
    samples: list[tuple[datetime, float]], now: datetime
) -> dict[str, float | int | None]:
    """由采样序列计算用量指标（纯函数，now 注入便于测试）。

    - 用量 = 相邻采样余额下降量之和（充值跳升不计入）
    - 跨零点的下降量归属后一采样点的本地日期
    - 窗口指标：窗口内有采样 → 求和（可能为 0.0）；窗口内无采样 → None
    - estimated_days = 最新余额 ÷ 近7天日均（日均 = 近7天用量 ÷ min(7, 数据覆盖天数)），
      向下取整；无余额、近7天无用量或无采样 → None
    """
    drops: dict[date, float] = {}
    for (_, b0), (t1, b1) in itertools.pairwise(samples):
        drop = b0 - b1
        if drop > 0:
            drops[_local_date(t1)] = drops.get(_local_date(t1), 0.0) + drop

    today = _local_date(now)
    sample_days = {_local_date(t) for t, _ in samples}

    def day_sum(target: date) -> float | None:
        if target not in sample_days:
            return None
        return round(drops.get(target, 0.0), 2)

    def range_sum(days: int) -> float | None:
        window = {today - timedelta(days=i) for i in range(days)}
        if not (sample_days & window):
            return None
        return round(sum(v for d, v in drops.items() if d in window), 2)

    today_usage = day_sum(today)
    yesterday_usage = day_sum(today - timedelta(days=1))
    week_usage = range_sum(7)
    month_usage = range_sum(30)

    estimated_days: int | None = None
    if samples and week_usage is not None and week_usage > 0:
        first_day = min(sample_days)
        covered = min(7, (today - first_day).days + 1)
        daily = week_usage / covered
        estimated_days = int(samples[-1][1] / daily)

    return {
        "today_usage": today_usage,
        "yesterday_usage": yesterday_usage,
        "week_usage": week_usage,
        "month_usage": month_usage,
        "estimated_days": estimated_days,
    }


class ElectricityService:
    """查询侧服务（API 用）：单房间最新状态 + 用量统计。"""

    def __init__(self, repository: ElectricityRepository):
        self._repository = repository

    async def status(self) -> ElectricityStatus:
        """最新余额（未采样过时 balance 为 null）+ 用量指标。"""
        latest = await self._repository.latest_balance()
        now = datetime.now(UTC)
        month_start_local = _local_date(now) - timedelta(days=29)
        window_start = datetime.combine(month_start_local, time.min, tzinfo=STATS_TZ).astimezone(
            UTC
        )
        samples = await self._repository.samples_since(window_start)
        stats = compute_usage_stats(samples, now)
        return ElectricityStatus(
            balance=latest[0] if latest else None,
            sampled_at=latest[1] if latest else None,
            **stats,  # type: ignore[arg-type]  # 键与模型字段逐一对应，由 compute_usage_stats 契约测试保证
        )


class ElectricityPoller:
    """定时抓取编排：抓取配置房间 → 落库 → 按状态转换推送通知卡片。"""

    def __init__(
        self,
        client: BalanceClient,
        repository: ElectricityRepository,
        bot: WeComBot,
        settings: Settings,
    ):
        self._client = client
        self._repository = repository
        self._bot = bot
        self._settings = settings
        notify = settings.load_notify_cards()
        self._notify = notify
        self._cards = notify["cards"]
        self._stale_rounds = notify["stale_rounds"]
        self._outage_rounds = 0
        self._notified: set[str] = set()

    def register_jobs(self, scheduler: AsyncIOScheduler) -> None:
        """向调度器注册本模块的周期任务（lifespan 调用）。

        cron 对齐整点与半点（:00/:30），采样时间全部落在整分上。
        """
        scheduler.add_job(  # pyright: ignore[reportUnknownMemberType]  # apscheduler 3.x add_job 未标注类型
            self.poll_once,
            trigger="cron",
            minute="0,30",
            id="electricity:poll",
            replace_existing=True,
            misfire_grace_time=60,
            coalesce=True,
        )

    async def poll_once(self) -> None:
        ref = RoomRef(
            xiaoqu_id=self._settings.ntu_xiaoqu_id,
            loudong_id=self._settings.ntu_loudong_id,
            room_id=self._settings.ntu_room_id,
        )
        try:
            balance = await self._client.get_balance(ref)
        except NtuCheckoutError:
            logger.info("学校系统结账期，跳过本轮")
            return
        except NtuCaptchaRequiredError as e:
            await self._alert("captcha", str(e))
            return
        except NtuContractError as e:
            await self._alert("contract", f"{e} [{e.checkpoint}]")
            return
        except KeyError as e:
            await self._alert("contract", str(e))
            return
        except NtuAuthError as e:
            await self._alert("auth", str(e))
            return
        except NtuError as e:
            await self._silent_failure(e)
            return
        await self._repository.upsert_sample(balance)
        await self._on_success()

    async def _alert(self, kind: str, detail: str) -> None:
        self._outage_rounds += 1
        logger.warning("电量抓取告警 [%s]：%s", kind, detail)
        if kind in self._notified:
            return
        self._notified.add(kind)
        await self._send(kind, {})

    async def _silent_failure(self, error: NtuError) -> None:
        self._outage_rounds += 1
        logger.warning("电量抓取失败（连续 %d 轮）：%s", self._outage_rounds, error)
        if self._outage_rounds >= self._stale_rounds and "stale" not in self._notified:
            self._notified.add("stale")
            await self._send(
                "stale",
                {
                    "count": self._outage_rounds,
                    "last_success": await self._last_success_text(),
                },
            )

    async def _on_success(self) -> None:
        logger.info("电量采样写入成功")
        if not self._notified:
            self._outage_rounds = 0
            return
        self._outage_rounds = 0
        self._notified.clear()
        await self._send("recovered", {})

    async def _send(self, kind: str, values: dict[str, object]) -> None:
        if not self._bot.enabled:
            return
        card = _build_card(self._cards[kind], self._notify, datetime.now(UTC), values)
        await self._bot.send_text_notice_card(card)

    async def _last_success_text(self) -> str:
        latest = await self._repository.latest_balance()
        return _time_text(latest[1]) if latest else "无记录"
