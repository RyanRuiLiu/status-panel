"""展示配置端点契约测试（config 端点与洗衣机域配置加载）。"""

from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import app as main_app
from tests.conftest import make_settings


@pytest.fixture
async def api() -> AsyncIterator[httpx.AsyncClient]:
    """main 应用的 ASGI 客户端：不触发 lifespan，手动注入 Settings（config 端点只读它）。"""
    main_app.state.settings = make_settings()
    transport = httpx.ASGITransport(app=main_app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    yield client
    await client.aclose()


def test_load_laundry_machines_maps_fields():
    settings = make_settings()
    machines = settings.load_laundry_machines()
    assert machines == [
        {"goods_id": "test-1", "label": "1号机"},
        {"goods_id": "test-2", "label": "2号机"},
    ]


def test_load_laundry_machines_missing_file_raises(tmp_path):
    settings = make_settings(laundry_config_path=str(tmp_path / "absent.json"))
    with pytest.raises(FileNotFoundError):
        settings.load_laundry_machines()


def test_settings_requires_shower_fields():
    """浴室地址与设备是必填部署事实，缺失即启动失败。"""
    with pytest.raises(ValidationError):
        Settings(  # 故意缺 shower 必填项，验证启动即失败
            # _env_file 是 pydantic-settings 运行时参数（签名走 **values 未标注），隔离 .env 用
            _env_file=None,  # pyright: ignore[reportCallIssue]
            ntu_xiaoqu_id=2,
            ntu_loudong_id=3,
            ntu_room_id=1,
        )


async def test_config_endpoint_returns_domain_grouped_payload(api):
    """config 端点按域分组透传配置值；端点自身不加工。"""
    r = await api.get("/api/v1/config")
    assert r.status_code == 200
    body = r.json()
    assert body["laundry"]["machines"] == [
        {"goods_id": "test-1", "label": "1号机"},
        {"goods_id": "test-2", "label": "2号机"},
    ]
    assert body["shower"] == {"base_url": "https://shower.test", "device_id": "dev-1"}
