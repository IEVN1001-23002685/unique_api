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


class Config:
    APP_ENV = os.getenv("APP_ENV", "development")
    DEBUG = _booleano("APP_DEBUG") if APP_ENV != "production" else False
    TESTING = False

    SECRET_KEY = os.getenv("SECRET_KEY", "change_me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change_me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=7)
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_COOKIE_SECURE = _booleano("JWT_COOKIE_SECURE", APP_ENV == "production")
    JWT_COOKIE_HTTPONLY = True
    JWT_COOKIE_SAMESITE = "Strict"
    JWT_COOKIE_CSRF_PROTECT = _booleano("JWT_COOKIE_CSRF_PROTECT", True)

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "")
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
