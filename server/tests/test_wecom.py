"""企业微信封装契约测试"""

import httpx
import pytest
import respx
from httpx import Response

from app.integrations.wecom import (
    CardAction,
    CardMainTitle,
    CardSource,
    TextNoticeCard,
    WeComBot,
    WeComError,
)

SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"


def make_bot(key: str = "test-key") -> WeComBot:
    return WeComBot(httpx.AsyncClient(), key)


def card() -> TextNoticeCard:
    return TextNoticeCard(
        main_title=CardMainTitle(title="电量抓取失败"),
        source=CardSource(desc="status-panel", desc_color=2),
        sub_title_text="28211",
        horizontal_content_list=[],
        jump_list=[],
        card_action=CardAction(type=1, url="https://pay.ntu.edu.cn/MNetWorkUI/showPublic"),
    )


@respx.mock
async def test_send_card_payload_contract():
    bot = make_bot()
    route = respx.post(SEND_URL).mock(
        return_value=Response(200, json={"errcode": 0, "errmsg": "ok"})
    )

    await bot.send_text_notice_card(card())

    payload = route.calls.last.request.read().decode()
    assert '"msgtype":"template_card"' in payload
    assert '"card_type":"text_notice"' in payload  # 必填子类型标识
    assert '"main_title":{"title":"电量抓取失败"}' in payload  # main_title 是对象


@respx.mock
async def test_send_card_errcode_nonzero_raises():
    bot = make_bot()
    respx.post(SEND_URL).mock(
        return_value=Response(200, json={"errcode": 42045, "errmsg": "wrong json format"})
    )
    with pytest.raises(WeComError):
        await bot.send_text_notice_card(card())


def test_disabled_bot_has_no_key():
    assert make_bot(key="").enabled is False
    assert make_bot(key="k").enabled is True
