"""用量统计契约测试（compute_usage_stats 纯函数：充值/跨零点/窗口/覆盖天数/零值）。"""

from datetime import UTC, datetime, timedelta

from app.electricity.service import STATS_TZ, compute_usage_stats

# 固定"现在"：本地（UTC+8）2026-11-10 23:00 = UTC 15:00，避免跨日边界偶发
NOW = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)


def sample(local_ymd: str, hm: str, balance: float) -> tuple[datetime, float]:
    """按本地时间构造采样点（转 UTC 存储）。"""
    t = datetime.fromisoformat(f"{local_ymd}T{hm}:00+08:00")
    return t.astimezone(UTC), balance


def stats(samples: list[tuple[datetime, float]]) -> dict[str, float | int | None]:
    return compute_usage_stats(samples, NOW)


def test_today_usage_sums_drops():
    samples = [
        sample("2026-11-10", "08:00", 100.0),
        sample("2026-11-10", "12:00", 98.0),
        sample("2026-11-10", "20:00", 96.5),
    ]
    assert stats(samples)["today_usage"] == 3.5


def test_recharge_jump_not_counted():
    # 100 → 98（用 2）→ 充值到 200 → 195（用 5）：今日 = 7，跳升不计
    samples = [
        sample("2026-11-10", "08:00", 100.0),
        sample("2026-11-10", "10:00", 98.0),
        sample("2026-11-10", "12:00", 200.0),
        sample("2026-11-10", "20:00", 195.0),
    ]
    assert stats(samples)["today_usage"] == 7.0


def test_midnight_drop_attributed_to_later_day():
    # 23:50 → 次日 00:10 的下降归属次日（后一采样点的本地日期）；
    # 昨日有采样但无归属下降 → 0.0（有采样即求和口径）
    samples = [
        sample("2026-11-09", "23:50", 100.0),
        sample("2026-11-10", "00:10", 95.0),
    ]
    s = stats(samples)
    assert s["today_usage"] == 5.0
    assert s["yesterday_usage"] == 0.0


def test_day_with_samples_but_no_drop_is_zero():
    # 当天有采样但余额未变（或纯充值）→ 0.0 度，而非 None
    samples = [
        sample("2026-11-10", "08:00", 100.0),
        sample("2026-11-10", "12:00", 100.0),
    ]
    assert stats(samples)["today_usage"] == 0.0


def test_no_sample_today_null():
    samples = [
        sample("2026-11-08", "10:00", 100.0),
        sample("2026-11-08", "22:00", 95.0),
    ]
    s = stats(samples)
    assert s["today_usage"] is None
    assert s["yesterday_usage"] is None


def test_week_and_month_windows_include_today():
    samples = [
        sample("2026-11-03", "10:00", 200.0),  # 8 天前 → 不在 7 天窗口
        sample("2026-11-03", "22:00", 190.0),
        sample("2026-11-04", "10:00", 180.0),  # 7 天窗口首日（today-6）
        sample("2026-11-04", "22:00", 170.0),
        sample("2026-11-09", "10:00", 160.0),
        sample("2026-11-09", "22:00", 150.0),
        sample("2026-11-10", "12:00", 145.0),
    ]
    s = stats(samples)
    # 近7天 = 11-04..11-10：11-04 两段共 20 + 11-09 两段共 20 + 11-10 的 5
    assert s["week_usage"] == 45.0
    # 近30天含 11-03 的 10：45 + 10 = 55
    assert s["month_usage"] == 55.0


def test_window_without_samples_null():
    samples = [sample("2026-10-01", "10:00", 100.0), sample("2026-10-01", "22:00", 90.0)]
    s = stats(samples)
    assert s["week_usage"] is None
    assert s["month_usage"] is None
    assert s["today_usage"] is None


def test_estimated_days_floor_and_covered_cap():
    # 首个采样在昨天（覆盖 2 天），近7天用量 6.0 → 日均 3.0 → 余额 100 → 33 天
    samples = [
        sample("2026-11-09", "10:00", 106.0),
        sample("2026-11-09", "22:00", 103.0),
        sample("2026-11-10", "12:00", 100.0),
    ]
    assert stats(samples)["estimated_days"] == 33


def test_estimated_days_uses_seven_when_covered():
    # 覆盖 10 天 → min(7,10)=7 → 日均 = 近7天用量 ÷ 7
    samples = [
        sample("2026-11-01", "10:00", 170.0),
        sample("2026-11-01", "22:00", 160.0),
        sample("2026-11-08", "22:00", 110.0),
        sample("2026-11-10", "12:00", 96.5),
    ]
    # 近7天窗口 = 11-04..11-10：50（11-08）+ 13.5（11-10）；11-01 的 10 度在窗口外
    s = stats(samples)
    assert s["week_usage"] == 63.5
    # 96.5 ÷ (63.5/7) = 10.63… → 向下取整 10
    assert s["estimated_days"] == 10


def test_estimated_days_zero_usage_none():
    samples = [
        sample("2026-11-09", "10:00", 100.0),
        sample("2026-11-10", "12:00", 100.0),
    ]
    assert stats(samples)["estimated_days"] is None


def test_empty_samples_all_none():
    s = stats([])
    assert s == {
        "today_usage": None,
        "yesterday_usage": None,
        "week_usage": None,
        "month_usage": None,
        "estimated_days": None,
    }


def test_stats_timezone_is_utc8():
    assert STATS_TZ.utcoffset(NOW) == timedelta(hours=8)
