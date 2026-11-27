"""Configuración de la aplicación, cargada exclusivamente desde variables de entorno."""

import os
from datetime import timedelta


def _booleano(nombre: str, predeterminado: bool = False) -> bool:
    valor = os.getenv(nombre)
    if valor is None:
        return predeterminado
    return valor.strip().lower() in {"1", "true", "yes", "on"}


def _lista(nombre: str, predeterminado: str = "") -> list[str]:
    return [parte.strip() for parte in os.getenv(nombre, predeterminado).split(",") if parte.strip()]


def _secreto(nombre: str, produccion: bool) -> str:
    valor = os.getenv(nombre, "change_me").strip()
    if produccion and (not valor or valor == "change_me"):
        raise RuntimeError(f"{nombre} debe configurarse con un valor seguro en producción")
    return valor


def _same_site(secure: bool, csrf_protegido: bool) -> str:
    valor = os.getenv("JWT_COOKIE_SAMESITE", "Strict").strip()
    normalizado = {"strict": "Strict", "lax": "Lax", "none": "None"}.get(valor.lower())
    if normalizado is None:
        raise RuntimeError("JWT_COOKIE_SAMESITE debe ser Strict, Lax o None")
    if normalizado == "None" and (not secure or not csrf_protegido):
        raise RuntimeError(
            "JWT_COOKIE_SAMESITE=None requiere JWT_COOKIE_SECURE=true y "
            "JWT_COOKIE_CSRF_PROTECT=true"
        )
    return normalizado


def _database_uri() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("mysql://"):
        return "mysql+pymysql://" + url[len("mysql://") :]
    return url


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
if APP_ENV not in {"development", "testing", "production", "prod"}:
    raise RuntimeError("APP_ENV debe ser development, testing o production")

# Railway inyecta RAILWAY_ENVIRONMENT aunque APP_ENV quede sin definir: en ese caso
# la configuración debe fallar cerrado como en cualquier despliegue de producción.
ES_PRODUCCION = APP_ENV in {"production", "prod"} or bool(
    os.getenv("RAILWAY_ENVIRONMENT", "").strip()
)


class Config:
    APP_ENV = "production" if ES_PRODUCCION and APP_ENV == "prod" else APP_ENV
    DEBUG = _booleano("APP_DEBUG") if not ES_PRODUCCION else False
    TESTING = False

    SECRET_KEY = _secreto("SECRET_KEY", ES_PRODUCCION)
    JWT_SECRET_KEY = _secreto("JWT_SECRET_KEY", ES_PRODUCCION)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_COOKIE_SECURE = _booleano("JWT_COOKIE_SECURE", ES_PRODUCCION)
    JWT_COOKIE_HTTPONLY = True
    JWT_COOKIE_CSRF_PROTECT = _booleano("JWT_COOKIE_CSRF_PROTECT", True)
    JWT_COOKIE_SAMESITE = _same_site(JWT_COOKIE_SECURE, JWT_COOKIE_CSRF_PROTECT)
    JWT_REFRESH_COOKIE_NAME = os.getenv("JWT_REFRESH_COOKIE_NAME", "refresh_token").strip() or "refresh_token"
    JWT_REFRESH_CSRF_HEADER_NAME = (
        os.getenv("JWT_REFRESH_CSRF_HEADER_NAME", "X-CSRF-TOKEN").strip() or "X-CSRF-TOKEN"
    )

    SQLALCHEMY_DATABASE_URI = _database_uri()
    if ES_PRODUCCION and not SQLALCHEMY_DATABASE_URI:
        raise RuntimeError("DATABASE_URL debe configurarse en producción")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": 5,
        "max_overflow": 10,
    }

    CORS_ORIGINS = _lista("CORS_ORIGINS", "http://localhost:4200")
    if ES_PRODUCCION:
        if not CORS_ORIGINS or any(origen == "*" for origen in CORS_ORIGINS):
            raise RuntimeError("CORS_ORIGINS debe contener orígenes explícitos en producción")
        if any(not origen.startswith("https://") for origen in CORS_ORIGINS):
            raise RuntimeError("CORS_ORIGINS debe usar HTTPS en producción")
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "/var/lib/unique/uploads")
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
