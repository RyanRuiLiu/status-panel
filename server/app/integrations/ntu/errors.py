"""NTU 对接层异常（每个类对应一种真实失败模式，调用方按需处置）"""


class NtuError(Exception):
    """NTU 对接层错误基类"""


class NtuAuthError(NtuError):
    """认证失败：凭据错误 / 登录未获得 CASTGC"""


class NtuCaptchaRequiredError(NtuAuthError):
    """学校要求滑块验证码，程序无法通过，需人工登录一次恢复会话"""


class NtuSessionExpiredError(NtuError):
    """业务会话过期信号（查询 302）——客户端内部自愈用，不应逃逸到调用方"""


class NtuSessionError(NtuError):
    """会话恢复失败：续期与完整登录均未奏效（等下个调度周期）"""


class NtuQueryError(NtuError):
    """查询业务失败（returncode=ERROR / HTTP 状态异常）"""


class NtuContractError(NtuError):
    """外部系统响应未通过契约校验（字段缺失 / 结构不符 / 非预期重定向）"""

    def __init__(self, message: str, checkpoint: str):
        super().__init__(message)
        self.checkpoint = checkpoint


class NtuCheckoutError(NtuError):
    """学校系统结账/维护期——调用方应静默跳过本轮，不算故障（不进重试族、不计入失败）"""


class NtuNetworkError(NtuError):
    """学校服务器网络层失败（连接失败/超时/重定向环等，httpx.HTTPError 全族翻译）"""
