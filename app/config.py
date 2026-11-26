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


def _secreto(nombre: str, app_env: str) -> str:
    valor = os.getenv(nombre, "change_me").strip()
    if app_env == "production" and (not valor or valor == "change_me"):
        raise RuntimeError(f"{nombre} debe configurarse con un valor seguro en producción")
    return valor


def _database_uri() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("mysql://"):
        return "mysql+pymysql://" + url[len("mysql://") :]
    return url


class Config:
    APP_ENV = os.getenv("APP_ENV", "development")
    DEBUG = _booleano("APP_DEBUG") if APP_ENV != "production" else False
    TESTING = False

    SECRET_KEY = _secreto("SECRET_KEY", APP_ENV)
    JWT_SECRET_KEY = _secreto("JWT_SECRET_KEY", APP_ENV)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_COOKIE_SECURE = _booleano("JWT_COOKIE_SECURE", APP_ENV == "production")
    JWT_COOKIE_HTTPONLY = True
    JWT_COOKIE_SAMESITE = "Strict"
    JWT_COOKIE_CSRF_PROTECT = _booleano("JWT_COOKIE_CSRF_PROTECT", False)

    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": 5,
        "max_overflow": 10,
    }

    CORS_ORIGINS = _lista("CORS_ORIGINS", "http://localhost:4200")
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "/var/lib/unique/uploads")
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
