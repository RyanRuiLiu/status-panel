"""共享测试替身。"""

from app.integrations.ntu.schemas import RoomRef


class FakeNtuClient:
    """BalanceClient 协议测试替身：按队列吐余额结果。"""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls: list[RoomRef] = []

    async def get_balance(self, room: RoomRef) -> float:
        self.calls.append(room)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
