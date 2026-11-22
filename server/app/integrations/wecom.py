"""企业微信群机器人薄封装。

template_card/text_notice 全字段封装；发送层统一校验 errcode 契约，
限频（20 条/分钟）由告警策略层保证。字段长度"建议"值不做强校验（服务端为准）。
"""

from typing import Any, Literal

import httpx
from pydantic import BaseModel

SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"


class WeComError(Exception):
    """webhook 发送失败（errcode != 0）"""


class CardSource(BaseModel):
    """卡片来源角标（desc 建议 ≤13 字；desc_color：0 灰 / 1 黑 / 2 红 / 3 绿）"""

    desc: str | None = None
    desc_color: Literal[0, 1, 2, 3] | None = None
    icon_url: str | None = None


class CardMainTitle(BaseModel):
    """一级标题（title 建议 ≤26 字；与卡片 sub_title_text 至少一项填写）+ 辅助信息（≤30 字）"""

    title: str | None = None
    desc: str | None = None


class CardEmphasisContent(BaseModel):
    """关键数据大字样式（title 建议 ≤10 字，desc 建议 ≤15 字）"""

    title: str | None = None
    desc: str | None = None


class CardQuoteArea(BaseModel):
    """引用区（type：0/不填无点击，1 跳 url，2 跳小程序）"""

    type: Literal[0, 1, 2] | None = None
    url: str | None = None
    appid: str | None = None
    pagepath: str | None = None
    title: str | None = None
    quote_text: str | None = None


class CardHorizontalItem(BaseModel):
    """字段行（keyname 建议 ≤5 字；value 在 type=2 时为文件名，建议 ≤26 字）"""

    keyname: str
    value: str | None = None
    type: Literal[1, 2, 3] | None = None  # 1 跳 url / 2 文件附件 / 3 成员详情
    url: str | None = None
    media_id: str | None = None
    userid: str | None = None


class CardJumpItem(BaseModel):
    """跳转指引（title 建议 ≤13 字；type：0/不填无点击，1 跳 url，2 跳小程序）"""

    type: Literal[1, 2] | None = None
    title: str
    url: str | None = None
    appid: str | None = None
    pagepath: str | None = None


class CardAction(BaseModel):
    """整卡点击动作（type：1 跳 url，2 打开小程序）"""

    type: Literal[1, 2]
    url: str | None = None
    appid: str | None = None
    pagepath: str | None = None


class TextNoticeCard(BaseModel):
    """文本通知模板卡片（官方 template_card/text_notice 全字段）"""

    card_type: Literal["text_notice"] = "text_notice"
    source: CardSource | None = None
    main_title: CardMainTitle | None = None
    emphasis_content: CardEmphasisContent | None = None
    quote_area: CardQuoteArea | None = None
    sub_title_text: str | None = None
    horizontal_content_list: list[CardHorizontalItem] = []
    jump_list: list[CardJumpItem] = []
    card_action: CardAction


class WeComBot:
    """群机器人客户端。key 为空 = 告警禁用（调用方通过 enabled 判断跳过）。"""

    def __init__(self, http: httpx.AsyncClient, key: str):
        self._http = http
        self._key = key

    @property
    def enabled(self) -> bool:
        return bool(self._key)

    async def send_text_notice_card(self, card: TextNoticeCard) -> None:
        """文本通知模板卡片。"""
        await self._send(
            {"msgtype": "template_card", "template_card": card.model_dump(exclude_none=True)}
        )

    async def _send(self, payload: dict[str, Any]) -> None:
        resp = await self._http.post(SEND_URL, params={"key": self._key}, json=payload)
        result = resp.json()
        if result["errcode"] != 0:
            raise WeComError(
                f"webhook 发送失败: errcode={result['errcode']} errmsg={result['errmsg']}"
            )
