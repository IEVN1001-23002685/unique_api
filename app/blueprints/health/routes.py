"""Endpoints de liveness y readiness del servicio."""

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from app.extensions import db
from app.utils.errores import ApiError

health_bp = Blueprint("health", __name__, url_prefix="/api/v1/health")


@health_bp.get("")
def liveness():
    return jsonify({"estado": "ok", "servicio": "api"})


@health_bp.get("/db")
def readiness():
    try:
        db.session.execute(text("SELECT 1")).scalar()
    except Exception:
        current_app.logger.exception("MySQL no disponible durante health/db")
        raise ApiError("BASE_DATOS_NO_DISPONIBLE", "La base de datos no está disponible", 503)
    return jsonify({"estado": "ok", "base_datos": "disponible"})
