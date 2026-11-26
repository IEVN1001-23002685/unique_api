"""Endpoints de liveness y readiness del servicio."""

import json
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify
from sqlalchemy import text

from app.extensions import db
from app.utils.errores import ApiError

health_bp = Blueprint("health", __name__, url_prefix="/api/v1")


@health_bp.get("/health")
def liveness():
    return jsonify({"estado": "ok", "servicio": "api"})


@health_bp.get("/openapi.json")
def openapi_json():
    ruta = Path(current_app.root_path).parent / "docs" / "openapi.json"
    if not ruta.exists():
        raise ApiError("OPENAPI_NO_ENCONTRADA", "La especificación OpenAPI no está disponible", 503)
    return Response(ruta.read_text(encoding="utf-8"), mimetype="application/json")


@health_bp.get("/docs")
def swagger_ui():
    html = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UNIQUE API Docs</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
<style>body{margin:0;background:#fafafa}</style></head>
<body><div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>window.ui=SwaggerUIBundle({url:'/api/v1/openapi.json',dom_id:'#swagger-ui',presets:[SwaggerUIBundle.presets.apis],layout:'BaseLayout'});</script>
</body></html>"""
    return Response(html, mimetype="text/html; charset=utf-8")


@health_bp.get("/health/db")
def readiness():
    try:
        db.session.execute(text("SELECT 1")).scalar()
    except Exception:
        current_app.logger.exception("MySQL no disponible durante health/db")
        raise ApiError("BASE_DATOS_NO_DISPONIBLE", "La base de datos no está disponible", 503)
    return jsonify({"estado": "ok", "base_datos": "disponible"})
