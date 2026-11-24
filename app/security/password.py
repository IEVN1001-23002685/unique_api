"""Hashing y verificación de contraseñas con Argon2."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def generar_hash(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(hash_almacenado: str, password: str) -> bool:
    try:
        return _hasher.verify(hash_almacenado, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def necesita_rehash(hash_almacenado: str) -> bool:
    return _hasher.check_needs_rehash(hash_almacenado)
