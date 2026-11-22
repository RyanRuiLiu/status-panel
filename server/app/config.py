"""应用配置（pydantic-settings，全部来自环境变量 / .env）。

注意：真实密钥只放 .env（不入库），代码默认值一律为空。
"""

import json
from pathlib import Path
from typing import Literal, NotRequired, TypedDict, cast

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class NotifyCard(TypedDict):
    """通知卡片文案（title 必填；desc 可选，仅在标题未表达完整时补充）"""

    title: str
    desc: NotRequired[str]
    severity: Literal[0, 1, 2, 3]
    fields: list[list[str]]


class NotifyConfig(TypedDict):
    """通知配置：整卡点击地址、断流轮数阈值、五类卡片文案"""

    action_url: str
    source_desc: str
    stale_rounds: int
    cards: dict[str, NotifyCard]


class Settings(BaseSettings):
    cas_base_url: str = "https://authserver.ntu.edu.cn"
    pay_base_url: str = "https://pay.ntu.edu.cn"
    cas_username: str = ""
    cas_password: str = ""

    # 抓取房间（单房间，.env 配置）：无默认值，缺配置启动即失败——没有房间应用无意义
    ntu_xiaoqu_id: int
    ntu_loudong_id: int
    ntu_room_id: int

    # 浴室（ntu-shower 服务端）：地址与目标设备都属部署事实，.env 配置
    shower_base_url: str
    shower_device_id: str

    # 洗衣机域配置（JSON 文件，非密钥入库；改文件重启生效）
    laundry_config_path: str = "config/laundry.json"

    # 通知卡片文案（JSON 文件，改文件重启生效）
    notify_config_path: str = "config/notify.json"

    db_path: str = "data/status-panel.db"

    # 企业微信群机器人（空 = 禁用告警；填纯 key 或完整 webhook URL 均可）
    wecom_webhook_key: str = ""

    @field_validator("wecom_webhook_key", mode="before")
    @classmethod
    def _normalize_webhook_key(cls, v: object) -> object:
        """粘贴完整 webhook URL 时自动截取 key 参数（确定性归一，非推断）。"""
        if isinstance(v, str) and "key=" in v:
            return v.split("key=", 1)[1].strip()
        return v.strip() if isinstance(v, str) else v

    def load_laundry_machines(self) -> list[dict[str, str]]:
        """读取洗衣机域配置（文件按域留扩展位，machines 为其中一项）。"""
        data = json.loads(Path(self.laundry_config_path).read_text(encoding="utf-8"))
        return [
            {"goods_id": str(m["goods_id"]), "label": str(m["label"])} for m in data["machines"]
        ]

    def load_notify_cards(self) -> NotifyConfig:
        """读取通知卡片文案；键缺失在渲染时由 Template 显式炸出。"""
        data = json.loads(Path(self.notify_config_path).read_text(encoding="utf-8"))
        return cast("NotifyConfig", data)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
