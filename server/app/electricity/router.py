"""电量模块路由（公开只读端点）。"""

from fastapi import APIRouter, Request

from app.electricity.repository import ElectricityRepository
from app.electricity.schemas import ElectricityStatus
from app.electricity.service import ElectricityService

router = APIRouter(prefix="/api/v1/electricity", tags=["electricity"])


def _service(request: Request) -> ElectricityService:
    return ElectricityService(ElectricityRepository(request.app.state.session_factory))


@router.get("", response_model=ElectricityStatus)
async def electricity_status(request: Request) -> ElectricityStatus:
    """当前电量余额与用量统计（整点/半点 cron 抓取的最新采样）。"""
    return await _service(request).status()
