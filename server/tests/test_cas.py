"""CAS 协议契约测试（fixture = 合成登录页：结构与真实页一致，盐值与域名已合成）"""

import base64
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from app.integrations.ntu.cas import encrypt_password, extract_error_message, parse_login_page

FIXTURES = Path(__file__).parent / "fixtures"
SALT = "SynteticSalt0001"  # 合成 fixture 中的盐（与真实盐等长，AES-128 语义一致）


def _decrypt_as_server(ciphertext_b64: str, salt: str) -> str:
    """按服务端消费方式解密（IV 置零）——随机前缀吸收 IV 影响，密码从第 65 字节起。"""
    raw = base64.b64decode(ciphertext_b64)
    decryptor = Cipher(algorithms.AES(salt.strip().encode()), modes.CBC(b"\x00" * 16)).decryptor()
    unpadder = PKCS7(128).unpadder()
    plain = unpadder.update(decryptor.update(raw) + decryptor.finalize()) + unpadder.finalize()
    return plain[64:].decode()


def test_encrypt_password_server_semantics():
    """服务端消费语义：IV 未知（置零解密）也能从第 65 字节读到密码——随机前缀吸收 IV 影响。"""
    cipher = encrypt_password("secret123", SALT)
    assert _decrypt_as_server(cipher, SALT) == "secret123"


def test_encrypt_password_ciphertext_structure():
    raw = base64.b64decode(encrypt_password("x", SALT))
    assert len(raw) % 16 == 0  # AES 分块
    assert len(raw) >= 80  # 64 随机前缀 + 至少 1 字节密码 + PKCS7 padding


def test_parse_login_page_fixture():
    html = (FIXTURES / "cas_login.html").read_text(encoding="utf-8")
    lp = parse_login_page(html)
    assert lp.salt == SALT
    assert lp.execution == "e1s1"
    assert lp.lt == ""


def test_extract_error_message():
    html = '<span id="showErrorTip"><span>您提供的用户名或者密码有误</span></span>'
    assert extract_error_message(html) == "您提供的用户名或者密码有误"
