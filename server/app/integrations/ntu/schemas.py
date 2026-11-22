"""NTU 对接层出入参模型"""

from pydantic import BaseModel


class RoomRef(BaseModel):
    """电费查询房间标识（学校缴费系统 querySydl 接口参数）"""

    xiaoqu_id: int
    loudong_id: int
    room_id: int
