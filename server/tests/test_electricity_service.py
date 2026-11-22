"""电量服务测试（最新状态 / 轮询编排 / 通知卡片状态转换）。"""

import re

import httpx

from app.electricity.repository import ElectricityRepository
from app.electricity.service import ElectricityPoller, ElectricityService
from app.integrations.ntu.errors import (
    NtuAuthError,
    NtuCaptchaRequiredError,
    NtuCheckoutError,
    NtuContractError,
    NtuQueryError,
)
from app.integrations.ntu.schemas import RoomRef
from app.integrations.wecom import WeComBot
from tests.conftest import make_settings
from tests.fakes import FakeNtuClient

TIME_PATTERN = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"


def repo(session_factory) -> ElectricityRepository:
    return ElectricityRepository(session_factory)


def capture_bot() -> tuple[WeComBot, list[dict]]:
    """发送捕获替身：记录 payload，不触网。"""
    sent: list[dict] = []
    bot = WeComBot(httpx.AsyncClient(), key="k")

    async def fake_send(card) -> None:
        sent.append(
            {"msgtype": "template_card", "template_card": card.model_dump(exclude_none=True)}
        )

    bot.send_text_notice_card = fake_send
    return bot, sent


def title(sent: list[dict], index: int = 0) -> str:
    return str(sent[index]["template_card"]["main_title"]["title"])


def fields(sent: list[dict], index: int = 0) -> list[dict]:
    return list(sent[index]["template_card"]["horizontal_content_list"])


def stale_rounds() -> int:
    return make_settings().load_notify_cards()["stale_rounds"]


def assert_time_last(sent: list[dict], index: int = 0) -> None:
    """时间置于字段行末位，标准格式精确到秒，不含汉字。"""
    rows = fields(sent, index)
    assert rows
    assert rows[-1]["keyname"] == "时间"
    assert re.match(TIME_PATTERN, rows[-1]["value"])


async def test_status_merges_latest(session_factory):
    r = repo(session_factory)
    await r.upsert_sample(98.0)
    status = await ElectricityService(r).status()
    assert status.balance == 98.0


async def test_status_empty_db_null(session_factory):
    status = await ElectricityService(repo(session_factory)).status()
    assert status.balance is None


async def test_poller_success_without_alert(session_factory):
    client = FakeNtuClient([98.0])
    bot, sent = capture_bot()
    poller = ElectricityPoller(client, repo(session_factory), bot, make_settings())

    await poller.poll_once()

    assert len(sent) == 0
    assert client.calls == [RoomRef(xiaoqu_id=2, loudong_id=3, room_id=1)]
    status = await ElectricityService(repo(session_factory)).status()
    assert status.balance == 98.0


async def test_poller_captcha_alert_deduped_then_recovered(session_factory):
    """需人工处置的事件触发即推，同类去重，恢复后推成功卡片。"""
    err = NtuCaptchaRequiredError("学校要求滑块验证码，需人工登录一次恢复会话")
    client = FakeNtuClient([err, err, 98.0])
    bot, sent = capture_bot()
    poller = ElectricityPoller(client, repo(session_factory), bot, make_settings())

    for _ in range(3):
        await poller.poll_once()

    assert len(sent) == 2
    assert title(sent, 0) == "滑块验证码需人工处理"
    assert title(sent, 1) == "电量数据恢复更新"
    assert "quote_area" not in sent[0]["template_card"]
    assert len(fields(sent, 0)) == 1
    assert_time_last(sent, 0)
    assert_time_last(sent, 1)


async def test_poller_auth_alert(session_factory):
    client = FakeNtuClient([NtuAuthError("您提供的用户名或者密码有误"), 98.0])
    bot, sent = capture_bot()
    poller = ElectricityPoller(client, repo(session_factory), bot, make_settings())

    await poller.poll_once()
    await poller.poll_once()

    assert title(sent, 0) == "登录凭据未通过验证"
    assert title(sent, 1) == "电量数据恢复更新"


async def test_poller_contract_alert_matches_event(session_factory):
    """响应异常事件的标题贴合事件本身，技术细节不进入卡片。"""
    err = NtuContractError("登录页未找到 pwdEncryptSalt 所在表单", "登录页参数解析")
    client = FakeNtuClient([err, 98.0])
    bot, sent = capture_bot()
    poller = ElectricityPoller(client, repo(session_factory), bot, make_settings())

    await poller.poll_once()
    await poller.poll_once()

    assert title(sent, 0) == "学校系统返回内容异常"
    assert len(fields(sent, 0)) == 1
    assert_time_last(sent, 0)


async def test_poller_keyerror_is_contract_alert(session_factory):
    client = FakeNtuClient([KeyError("balance"), 98.0])
    bot, sent = capture_bot()
    poller = ElectricityPoller(client, repo(session_factory), bot, make_settings())

    await poller.poll_once()
    await poller.poll_once()

    assert title(sent, 0) == "学校系统返回内容异常"


async def test_poller_checkout_period_is_silent(session_factory):
    """结账期静默跳过，连续多轮也不告警。"""
    client = FakeNtuClient([NtuCheckoutError("学校系统结账期")] * stale_rounds())
    bot, sent = capture_bot()
    poller = ElectricityPoller(client, repo(session_factory), bot, make_settings())

    for _ in range(stale_rounds()):
        await poller.poll_once()

    assert len(sent) == 0


async def test_poller_stale_alert_after_threshold(session_factory):
    """常态业务错误累计到阈值才推断流卡片，恢复后推成功卡片。"""
    rounds = stale_rounds()
    client = FakeNtuClient([NtuQueryError("查询失败: 连接超时")] * rounds + [98.0])
    bot, sent = capture_bot()
    poller = ElectricityPoller(client, repo(session_factory), bot, make_settings())

    for _ in range(rounds + 1):
        await poller.poll_once()

    assert len(sent) == 2
    assert title(sent, 0) == "电量数据持续未更新"
    assert title(sent, 1) == "电量数据恢复更新"
    assert "emphasis_content" not in sent[0]["template_card"]
    assert "quote_area" not in sent[0]["template_card"]
    assert fields(sent, 0)[0] == {"keyname": "未更新次数", "value": f"{rounds} 次"}
    assert fields(sent, 0)[1]["keyname"] == "上次更新"
    assert_time_last(sent, 0)
    assert_time_last(sent, 1)


async def test_poller_silent_failure_below_threshold(session_factory):
    rounds = stale_rounds()
    client = FakeNtuClient([NtuQueryError("x")] * (rounds - 1))
    bot, sent = capture_bot()
    poller = ElectricityPoller(client, repo(session_factory), bot, make_settings())

    for _ in range(rounds - 1):
        await poller.poll_once()

    assert len(sent) == 0


async def test_poller_counter_resets_on_success(session_factory):
    rounds = stale_rounds()
    outcomes = [NtuQueryError("x")] * (rounds - 1) + [98.0] + [NtuQueryError("y")] * (rounds - 1)
    client = FakeNtuClient(outcomes)
    bot, sent = capture_bot()
    poller = ElectricityPoller(client, repo(session_factory), bot, make_settings())

    for _ in range(len(outcomes)):
        await poller.poll_once()

    assert len(sent) == 0


async def test_poller_disabled_bot_skips_send(session_factory):
    """bot 未配置 key = 通知禁用：告警也不触网，状态仍完成转换。"""
    err = NtuCaptchaRequiredError("学校要求滑块验证码，需人工登录一次恢复会话")
    client = FakeNtuClient([err, 98.0])
    bot, sent = capture_bot()
    disabled = WeComBot(httpx.AsyncClient(), key="")
    disabled.send_text_notice_card = bot.send_text_notice_card
    poller = ElectricityPoller(client, repo(session_factory), disabled, make_settings())

    await poller.poll_once()
    await poller.poll_once()

    assert disabled.enabled is False
    assert len(sent) == 0
