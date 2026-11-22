"""CAS 统一身份认证协议"""

import base64
import secrets
from dataclasses import dataclass

from bs4 import BeautifulSoup
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from .errors import NtuContractError

# 学校 encrypt.js 的随机字符集（原文照抄：去除易混淆字符的 49 字符表）
_AES_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"


def _random_string(length: int) -> str:
    return "".join(secrets.choice(_AES_CHARS) for _ in range(length))


def encrypt_password(password: str, salt: str) -> str:
    """按学校 encrypt.js 逻辑加密密码。

    明文 = 64 位随机前缀 + 密码；key = salt（UTF-8）；IV = 16 位随机串；
    AES-128-CBC + PKCS7，输出 base64 密文。

    随机前缀恰好占满 4 个密文块，使 IV 只影响第 1 块随机数据——服务端用
    任意 IV 解密后从第 65 字节起即可读到密码，因此 IV 无需告知服务端。
    """
    key = salt.strip().encode()
    iv = _random_string(16).encode()
    plaintext = (_random_string(64) + password).encode()

    padder = PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()


@dataclass(frozen=True)
class LoginPage:
    """登录页动态参数（每次加载都变化，必须现场解析）"""

    salt: str
    execution: str
    lt: str


def parse_login_page(html: str) -> LoginPage:
    """从登录页 HTML 提取账号密码表单（userNameLogin）的动态参数。

    任一字段缺失 = 学校页面结构改版，契约失败，显式抛错。
    """
    soup = BeautifulSoup(html, "html.parser")
    salt_input = soup.find("input", id="pwdEncryptSalt")
    form = salt_input.find_parent("form") if salt_input else None
    if form is None or salt_input is None:
        raise NtuContractError("登录页未找到 pwdEncryptSalt 所在表单", "登录页参数解析")
    execution_input = form.find("input", attrs={"name": "execution"})
    if execution_input is None:
        raise NtuContractError("登录页未找到 execution 参数", "登录页参数解析")
    lt_input = form.find("input", attrs={"name": "lt"})
    return LoginPage(
        salt=str(salt_input["value"]),
        execution=str(execution_input["value"]),
        lt=str(lt_input["value"]) if lt_input else "",
    )


def extract_error_message(html: str) -> str:
    """提取登录失败消息。

    学校登录页存在两个消息通道：`#showErrorTip` 为 CAS 标准错误位，
    `#formErrorTip2` 为主题错误通道。
    """
    soup = BeautifulSoup(html, "html.parser")
    for el_id in ("showErrorTip", "formErrorTip2"):
        el = soup.find(id=el_id)
        if el is not None and el.get_text(strip=True):
            return el.get_text(strip=True)
    return ""
