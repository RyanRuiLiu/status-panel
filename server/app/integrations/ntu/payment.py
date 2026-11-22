"""MNetWorkUI 电费查询客户端。

核心纪律：最小化完整登录次数——学校后台会记录登录事件，
轻续期（零登录记录）优先，完整登录仅在 CASTGC 失效时发生并强制节流。
"""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from tenacity.wait import wait_base

from app.config import Settings

from . import cas
from .errors import (
    NtuAuthError,
    NtuCaptchaRequiredError,
    NtuCheckoutError,
    NtuContractError,
    NtuNetworkError,
    NtuQueryError,
    NtuSessionError,
    NtuSessionExpiredError,
)
from .schemas import RoomRef

# ---- 学校端点与常量----
CAS_LOGIN_PATH = "/authserver/login"
CAS_LOGOUT_PATH = "/authserver/logout"
CAS_NEED_CAPTCHA_PATH = "/authserver/checkNeedCaptcha.htl"
MNET_SERVICE_URL = (
    "http://pay.ntu.edu.cn/MNetWorkUI/signAuthentication?url=publicPayPro!openUserPayProList.do"
)
MNET_QUERY_PATH = "/MNetWorkUI/elecManage!querySydl10304.do"
FACTORY_CODE = "E017"  # 电费项目厂商码（项目页路径 elecdetails5118E017）
# 校区 id → sign 拼音；不在表内的 xiaoqu_id = 契约失败
CAMPUS_SIGNS = {1: "qidong", 2: "zhuxiaoqu", 4: "qixiu"}

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

_CASTGC_DOMAIN = "authserver.ntu.edu.cn"
_PAY_DOMAIN = "pay.ntu.edu.cn"

_DEFAULT_RETRY_WAIT = wait_exponential(multiplier=1, min=1, max=8)

# 可重试异常族：平台业务失败与网络层失败（幂等廉价的查询操作按主流做法统一有界重试）
_RETRYABLE = (NtuQueryError, NtuNetworkError)

_T = TypeVar("_T")

logger = logging.getLogger(__name__)


class BalanceClient(Protocol):
    """NTU 客户端抽象（轮询器依赖此协议，测试可用替身实现）。"""

    async def get_balance(self, room: RoomRef) -> float: ...


class NtuPaymentClient:
    """登录态生命周期 + 电费查询。单实例贯穿应用生命周期（cookie jar 常驻内存）。"""

    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        min_login_interval: float = 600.0,
        retry_attempts: int = 3,
        retry_wait: wait_base = _DEFAULT_RETRY_WAIT,
    ):
        self._http = http
        self._settings = settings
        self._min_login_interval = min_login_interval
        self._retry_attempts = retry_attempts
        self._retry_wait = retry_wait
        self._last_full_login = float("-inf")

    # ---- 对外入口（统一会话自愈 + 网络层异常翻译）----

    async def get_balance(self, room: RoomRef) -> float:
        """查询房间余额（度）。会话过期时自愈一次（轻续期→完整登录）后重试一次。"""

        async def op() -> float:
            result = await self._post_json(
                MNET_QUERY_PATH,
                {
                    "room_id": room.room_id,
                    "loudong_id": room.loudong_id,
                    "xiaoqu_id": room.xiaoqu_id,
                    "factorycode": FACTORY_CODE,
                    "sign": CAMPUS_SIGNS[room.xiaoqu_id],
                },
            )
            return float(result["balance"])

        return await self._with_session(lambda: self._with_retry(op))

    # ---- 平台 API 统一契约----

    async def _post_json(self, path: str, data: dict[str, object]) -> dict[str, Any]:
        """POST 平台接口并执行统一响应契约。"""
        resp = await self._http.post(self._pay_url(path), data=data)
        if resp.is_redirect:  # 302 的 Location 是状态分类点
            location = resp.headers.get("location", "")
            if "slogin.html" in location:
                raise NtuSessionExpiredError("请求被重定向到登录页")
            if "/pages/error/accounting.jsp" in location:
                raise NtuCheckoutError("学校系统结账期")
            raise NtuContractError(f"异常重定向: {location}", "重定向去向")
        if resp.status_code != 200:
            raise NtuQueryError(f"HTTP {resp.status_code}")

        try:
            result = resp.json()
        except ValueError:
            raise NtuContractError("响应非 JSON", "查询响应字段") from None

        if result["returncode"] != "SUCCESS":
            raise NtuQueryError(f"查询失败: {result['returnmsg']}")
        return result

    async def _with_session(self, op: Callable[[], Awaitable[_T]]) -> _T:
        """会话过期自愈一次后重试一次；网络层失败统一翻译为 NtuNetworkError。"""
        try:
            try:
                return await op()
            except NtuSessionExpiredError:
                await self._restore_session()
                try:
                    return await op()
                except NtuSessionExpiredError as e:
                    raise NtuSessionError("续期后查询仍被拒，等下个调度周期") from e
        except httpx.HTTPError as e:
            raise NtuNetworkError("学校服务器网络异常") from e

    async def _with_retry(self, op: Callable[[], Awaitable[_T]]) -> _T:
        """tenacity 有界重试：指数退避（业界标准重试库，可重试族 = 业务失败 + 网络失败）。"""
        return await AsyncRetrying(
            retry=retry_if_exception_type(_RETRYABLE),
            stop=stop_after_attempt(self._retry_attempts),
            wait=self._retry_wait,
            reraise=True,
        )(op)

    # ---- 会话恢复----

    async def _restore_session(self) -> None:
        logger.info("业务会话过期，触发自愈")
        if self._has_castgc() and await self._light_renew():
            return
        await self._full_login()

    async def _light_renew(self) -> bool:
        """CASTGC 有效时重走 SSO 跳转链换新 JSESSIONID——无凭据提交，零登录记录。"""
        await self._http.get(
            self._cas_url(CAS_LOGIN_PATH),
            params={"service": MNET_SERVICE_URL},
            follow_redirects=True,
        )
        renewed = self._has_pay_session()
        logger.info("轻续期%s", "成功" if renewed else "未取得业务会话")
        return renewed

    async def _full_login(self) -> None:
        since = time.monotonic() - self._last_full_login
        if since < self._min_login_interval:
            logger.warning("完整登录节流中（距上次登录 %d 秒）", int(since))
            raise NtuSessionError(f"完整登录节流中（距上次登录 {int(since)} 秒）")
        self._last_full_login = time.monotonic()

        if self._has_castgc():
            await self._http.get(self._cas_url(CAS_LOGOUT_PATH))  # 销毁旧 TGT，避免死会话堆积

        captcha = await self._http.get(
            self._cas_url(CAS_NEED_CAPTCHA_PATH), params={"username": self._settings.cas_username}
        )
        try:
            need = captcha.json()["isNeed"]
        except ValueError as e:
            raise NtuContractError("验证码预检响应非 JSON", "验证码预检响应") from e
        if need:
            logger.warning("学校要求验证码，需人工登录恢复会话")
            raise NtuCaptchaRequiredError("学校要求滑块验证码，需人工登录一次恢复会话")

        page = await self._http.get(
            self._cas_url(CAS_LOGIN_PATH), params={"service": MNET_SERVICE_URL}
        )
        lp = cas.parse_login_page(page.text)

        logger.info("完整登录：提交凭据")
        form = {
            "username": self._settings.cas_username,
            "password": cas.encrypt_password(self._settings.cas_password, lp.salt),
            "lt": lp.lt,
            "execution": lp.execution,
            "_eventId": "submit",
            "cllt": "userNameLogin",
            "dllt": "",  # 手机主题页面运行时将 dllt 置空
        }
        resp = await self._http.post(
            self._cas_url(CAS_LOGIN_PATH),
            params={"service": MNET_SERVICE_URL},
            data=form,
            follow_redirects=True,  # 走完 CAS → ticket 校验 → JSESSIONID 全链
        )
        if not self._has_castgc():
            raise NtuAuthError(cas.extract_error_message(resp.text) or "登录未获得 CASTGC")
        if not self._has_pay_session():
            logger.warning("完整登录已获 CASTGC，但未取得 JSESSIONID")
        logger.info("完整登录成功")

    # ---- 会话状态 ----

    def _has_castgc(self) -> bool:
        return any(
            c.name == "CASTGC" and _CASTGC_DOMAIN in (c.domain or "")
            for c in self._http.cookies.jar
        )

    def _has_pay_session(self) -> bool:
        return any(
            c.name == "JSESSIONID" and _PAY_DOMAIN in (c.domain or "")
            for c in self._http.cookies.jar
        )

    # ---- URL ----

    def _cas_url(self, path: str) -> str:
        return self._settings.cas_base_url + path

    def _pay_url(self, path: str) -> str:
        return self._settings.pay_base_url + path
