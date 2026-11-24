"""Hash de tokens de refresco y recuperación."""

import hashlib
import secrets


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generar_token_opaco() -> str:
    return secrets.token_urlsafe(48)
