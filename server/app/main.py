"""status-panel 服务端入口：组装全局设施与各域模块。"""

import logging
from contextlib import asynccontextmanager
from importlib.metadata import version

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request

from app.config import Settings
from app.db import create_db_engine, create_session_factory
from app.electricity.repository import ElectricityRepository
from app.electricity.router import router as electricity_router
from app.electricity.service import ElectricityPoller
from app.integrations.ntu.payment import MOBILE_UA, NtuPaymentClient
from app.integrations.wecom import WeComBot


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 标准库 logging 直出容器 stdout；uvicorn 已配置 root 时 basicConfig 自动空操作
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = Settings()  # pyright: ignore[reportCallIssue]  # 必填项由 .env 提供，静态检查不可见
    if not settings.cas_username or not settings.cas_password:
        raise RuntimeError(
            "CAS_USERNAME / CAS_PASSWORD 必填（缺凭据会反复提交空密码，账号可能被锁）"
        )
    http = httpx.AsyncClient(timeout=15, headers={"User-Agent": MOBILE_UA})
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    client = NtuPaymentClient(http, settings)
    bot = WeComBot(http, settings.wecom_webhook_key)
    poller = ElectricityPoller(client, ElectricityRepository(session_factory), bot, settings)

    scheduler = AsyncIOScheduler()
    poller.register_jobs(scheduler)
    scheduler.start()

    app.state.settings = settings
    app.state.http = http
    app.state.ntu = client
    app.state.session_factory = session_factory

    yield

    scheduler.shutdown(wait=False)  # APScheduler 3.x 的 shutdown 为同步方法
    await http.aclose()
    await engine.dispose()


app = FastAPI(title="status-panel", version=version("status-panel"), lifespan=lifespan)
app.include_router(electricity_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/config")
async def display_config(request: Request) -> dict[str, object]:
    """展示配置：小程序启动时拉取，值的变化不依赖发版。

    按域分组，新增域即新增键：
    - laundry.machines：洗衣机展示清单（config/laundry.json，改文件重启生效）
    - shower.base_url / shower.device_id：ntu-shower 服务端地址与目标设备（.env，部署事实）
    """
    settings: Settings = request.app.state.settings
    return {
        "laundry": {"machines": settings.load_laundry_machines()},
        "shower": {
            "base_url": settings.shower_base_url,
            "device_id": settings.shower_device_id,
        },
    }
