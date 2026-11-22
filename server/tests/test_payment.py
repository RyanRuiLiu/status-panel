# pyright: reportPrivateUsage=false
"""电费客户端契约测试（respx 全链路 mock）"""

from pathlib import Path

import httpx
import pytest
import respx
from httpx import Response
from tenacity import wait_none

from app.config import Settings
from app.integrations.ntu.errors import (
    NtuCaptchaRequiredError,
    NtuCheckoutError,
    NtuContractError,
    NtuNetworkError,
    NtuQueryError,
    NtuSessionError,
)
from app.integrations.ntu.payment import (
    CAS_LOGIN_PATH,
    CAS_LOGOUT_PATH,
    CAS_NEED_CAPTCHA_PATH,
    MNET_QUERY_PATH,
    MOBILE_UA,
    NtuPaymentClient,
)
from app.integrations.ntu.schemas import RoomRef

CAS = "https://authserver.ntu.edu.cn"
PAY = "https://pay.ntu.edu.cn"
QUERY_URL = PAY + MNET_QUERY_PATH
ROOM = RoomRef(xiaoqu_id=2, loudong_id=28, room_id=28075)
SUCCESS_BODY = '{"balance": 45.2, "returncode": "SUCCESS", "returnmsg": "ok"}'
LOGIN_PAGE = (Path(__file__).parent / "fixtures" / "cas_login.html").read_text(encoding="utf-8")


def make_client(min_login_interval: float = 0.0) -> NtuPaymentClient:
    http = httpx.AsyncClient(headers={"User-Agent": MOBILE_UA})
    settings = Settings(
        cas_username="tester",
        cas_password="secret",
        ntu_xiaoqu_id=2,
        ntu_loudong_id=28,
        ntu_room_id=28075,
        shower_base_url="https://shower.test",
        shower_device_id="dev-1",
    )
    return NtuPaymentClient(
        http, settings, min_login_interval=min_login_interval, retry_wait=wait_none()
    )


def expired() -> Response:
    return Response(302, headers={"Location": PAY + "/MNetWorkUI/slogin.html"})


def mock_ticket_chain(castgc: str | None):
    """ticket 校验链：signAuthentication 签发 JSESSIONID → 落地 showPublic。"""
    headers = {
        "Set-Cookie": f"JSESSIONID=js-{castgc or 'x'}; Path=/MNetWorkUI",
        "Location": PAY + "/MNetWorkUI/showPublic",
    }
    respx.get(PAY + "/MNetWorkUI/signAuthentication").mock(
        return_value=Response(302, headers=headers)
    )
    respx.get(PAY + "/MNetWorkUI/showPublic").mock(return_value=Response(200, text="ok"))


def mock_full_login(castgc: str) -> respx.Route:
    """完整登录链：logout → 验证码预检 → 登录页 → 表单提交（签发 CASTGC）→ ticket 链。"""
    respx.get(CAS + CAS_LOGOUT_PATH).mock(return_value=Response(200, text="注销成功"))
    respx.get(CAS + CAS_NEED_CAPTCHA_PATH).mock(
        return_value=Response(200, text='{"isNeed": false}')
    )
    respx.get(CAS + CAS_LOGIN_PATH).mock(return_value=Response(200, text=LOGIN_PAGE))
    mock_ticket_chain(castgc)
    return respx.post(CAS + CAS_LOGIN_PATH).mock(
        return_value=Response(
            302,
            headers={
                "Set-Cookie": f"CASTGC={castgc}; Path=/authserver; Domain=authserver.ntu.edu.cn",
                "Location": PAY + "/MNetWorkUI/signAuthentication?ticket=ST-1",
            },
        )
    )


@respx.mock
async def test_get_balance_success():
    c = make_client()
    query = respx.post(QUERY_URL).mock(return_value=Response(200, text=SUCCESS_BODY))
    assert await c.get_balance(ROOM) == 45.2
    # 契约：查询体（sign 由校区 id 映射）
    body = query.calls.last.request.content.decode()
    assert "sign=zhuxiaoqu" in body  # xiaoqu_id=2 → zhuxiaoqu
    assert "factorycode=E017" in body
    assert "room_id=28075" in body


@respx.mock
async def test_campus_sign_mapping():
    """sign 随校区 id 映射（qidong/zhuxiaoqu/qixiu，学校页面源码）。"""
    c = make_client()
    query = respx.post(QUERY_URL).mock(return_value=Response(200, text=SUCCESS_BODY))
    await c.get_balance(RoomRef(xiaoqu_id=1, loudong_id=1, room_id=1))
    assert "sign=qidong" in query.calls.last.request.content.decode()


@respx.mock
async def test_expired_then_light_renew():
    """有 CASTGC：会话过期 → 轻续期（CAS 直接签 ST，零登录记录）→ 重试成功。"""
    c = make_client()
    c._http.cookies.set("CASTGC", "TGT-live", domain="authserver.ntu.edu.cn")
    respx.post(QUERY_URL).mock(side_effect=[expired(), Response(200, text=SUCCESS_BODY)])
    respx.get(CAS + CAS_LOGIN_PATH).mock(
        return_value=Response(
            302, headers={"Location": PAY + "/MNetWorkUI/signAuthentication?ticket=ST-1"}
        )
    )
    mock_ticket_chain("TGT-live")
    assert await c.get_balance(ROOM) == 45.2


@respx.mock
async def test_expired_then_full_login():
    """无 CASTGC：会话过期 → 完整登录（logout → 验证码预检 → 表单提交）→ 重试成功。"""
    c = make_client()
    respx.post(QUERY_URL).mock(side_effect=[expired(), Response(200, text=SUCCESS_BODY)])
    login_post = mock_full_login("TGT-new")

    assert await c.get_balance(ROOM) == 45.2

    # 契约：表单字段
    body = login_post.calls.last.request.content.decode()
    assert "username=tester" in body
    assert "password=" in body  # 密文字段
    assert "cllt=userNameLogin" in body
    assert "dllt=" in body  # 手机主题：dllt 为空
    assert "rmShown" not in body  # PC 主题字段，手机版不存在
    assert "userPassword" not in body  # 原文密码字段被禁用，不提交


@respx.mock
async def test_light_renew_fail_falls_to_full_login():
    """CASTGC 已死：轻续期落回登录页（拿不到 JSESSIONID）→ 完整登录。"""
    c = make_client()
    c._http.cookies.set("CASTGC", "TGT-dead", domain="authserver.ntu.edu.cn")
    respx.post(QUERY_URL).mock(side_effect=[expired(), Response(200, text=SUCCESS_BODY)])
    respx.get(CAS + CAS_LOGIN_PATH).mock(
        return_value=Response(200, text=LOGIN_PAGE)
    )  # 轻续期落回登录页
    mock_full_login("TGT-fresh")
    assert await c.get_balance(ROOM) == 45.2


@respx.mock
async def test_captcha_required():
    """checkNeedCaptcha 返回 isNeed=true → 软失败（滑块无法程序化通过）。"""
    c = make_client()
    respx.post(QUERY_URL).mock(return_value=expired())
    respx.get(CAS + CAS_NEED_CAPTCHA_PATH).mock(return_value=Response(200, text='{"isNeed": true}'))
    with pytest.raises(NtuCaptchaRequiredError):
        await c.get_balance(ROOM)


@respx.mock
async def test_checkout_period():
    """结账期：302 → pages/error/accounting.jsp（生产日志实证，2026-11-01/02 共 12 例）。"""
    c = make_client()
    respx.post(QUERY_URL).mock(
        return_value=Response(
            302,
            headers={"Location": PAY + "/MNetWorkUI/school/ntdx/pages/error/accounting.jsp"},
        )
    )
    with pytest.raises(NtuCheckoutError):
        await c.get_balance(ROOM)


@respx.mock
async def test_unknown_redirect_is_contract_breach():
    """302 去向既非 slogin 也非结账页 = 未观测状态 → NtuContractError 显式炸出。"""
    c = make_client()
    respx.post(QUERY_URL).mock(
        return_value=Response(302, headers={"Location": PAY + "/MNetWorkUI/somewhere_new.html"})
    )
    with pytest.raises(NtuContractError):
        await c.get_balance(ROOM)


@respx.mock
async def test_business_error():
    c = make_client()
    respx.post(QUERY_URL).mock(
        return_value=Response(
            200, text='{"balance": null, "returncode": "ERROR", "returnmsg": "连接超时"}'
        )
    )
    with pytest.raises(NtuQueryError):
        await c.get_balance(ROOM)


@respx.mock
async def test_transient_error_retried():
    """通用有界重试：前两次业务失败、第三次成功 → 整体成功（3 次调用）。"""
    c = make_client()
    route = respx.post(QUERY_URL).mock(
        side_effect=[
            Response(200, text='{"balance": null, "returncode": "ERROR", "returnmsg": "连接超时"}'),
            Response(200, text='{"balance": null, "returncode": "ERROR", "returnmsg": "连接超时"}'),
            Response(200, text=SUCCESS_BODY),
        ]
    )
    assert await c.get_balance(ROOM) == 45.2
    assert route.calls.call_count == 3


@respx.mock
async def test_retry_exhausted():
    """重试耗尽后抛出最后一次的错误（3 次尝试）。"""
    c = make_client()
    route = respx.post(QUERY_URL).mock(
        return_value=Response(
            200, text='{"balance": null, "returncode": "ERROR", "returnmsg": "连接超时"}'
        )
    )
    with pytest.raises(NtuQueryError):
        await c.get_balance(ROOM)
    assert route.calls.call_count == 3


@respx.mock
async def test_full_login_throttled():
    """登录次数纪律：节流窗口内拒绝第二次完整登录。"""
    c = make_client(min_login_interval=600)
    mock_full_login("TGT-1")

    await c._full_login()  # 第一次：成功
    with pytest.raises(NtuSessionError):
        await c._full_login()  # 节流窗口内：拒绝


@respx.mock
async def test_transport_error_translated():
    """网络层失败（连接拒绝/超时等 httpx.HTTPError 全族）统一翻译为 NtuNetworkError。"""
    c = make_client()
    respx.post(QUERY_URL).mock(side_effect=httpx.ConnectError("connection refused"))
    with pytest.raises(NtuNetworkError):
        await c.get_balance(ROOM)


@respx.mock
async def test_needcaptcha_contract_breach():
    """验证码预检响应非 JSON = 响应不符合契约 → NtuContractError（不裸抛 ValueError）。"""
    c = make_client()
    respx.post(QUERY_URL).mock(return_value=expired())
    respx.get(CAS + CAS_NEED_CAPTCHA_PATH).mock(
        return_value=Response(200, text="<html>维护中</html>")
    )
    with pytest.raises(NtuContractError):
        await c.get_balance(ROOM)
