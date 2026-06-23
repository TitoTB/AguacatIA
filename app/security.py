import base64
import hashlib
import hmac
import os
import time


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"pbkdf2_sha256${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = encoded.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return hmac.compare_digest(actual, expected)


def new_secret() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def sign_session(secret: str, username: str = "admin") -> str:
    issued_at = str(int(time.time()))
    nonce = new_secret()
    payload = f"{username}:{issued_at}:{nonce}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def verify_session(secret: str, token: str, max_age_seconds: int = 60 * 60 * 24 * 14) -> bool:
    parts = token.split(":")
    if len(parts) != 4:
        return False
    username, issued_at, nonce, signature = parts
    payload = f"{username}:{issued_at}:{nonce}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        return int(time.time()) - int(issued_at) <= max_age_seconds
    except ValueError:
        return False

