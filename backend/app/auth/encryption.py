"""Fernet encryption for API keys — keys never stored in plaintext."""

from cryptography.fernet import Fernet

from app.config import settings


def _get_fernet() -> Fernet:
    key = settings.FERNET_KEY
    if not key:
        raise RuntimeError("FERNET_KEY not configured")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_key(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()
