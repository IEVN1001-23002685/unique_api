"""Endpoints de indicadores y exportación del dashboard (M20)."""

from flask import Blueprint, Response, jsonify, request
from marshmallow import ValidationError

from app.schemas import DashboardFiltrosSchema
from app.security import roles_requeridos
from app.services import dashboard_service
from app.utils.errores import ApiError

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/v1")


def _filtros():
    try:
        return DashboardFiltrosSchema().load(request.args)
    except ValidationError as error:
        raise ApiError(
            "VALIDACION",
            "Parámetros inválidos",
            400,
            [
                {"campo": str(campo), "mensaje": str(mensaje)}
                for campo, mensaje in error.messages.items()
            ],
        )


@dashboard_bp.get("/dashboard/resumen")
@roles_requeridos("ADMIN")
def resumen():
    return jsonify(dashboard_service.resumen(_filtros()))


@dashboard_bp.get("/dashboard/ventas")
@roles_requeridos("ADMIN")
def ventas():
    return jsonify(dashboard_service.ventas(_filtros()))


@dashboard_bp.get("/dashboard/produccion")
@roles_requeridos("ADMIN", "OPERATIVO")
def produccion():
    return jsonify(dashboard_service.produccion(_filtros()))


@dashboard_bp.get("/dashboard/abastecimiento")
@roles_requeridos("ADMIN", "OPERATIVO")
def abastecimiento():
    return jsonify(dashboard_service.abastecimiento(_filtros()))


@dashboard_bp.get("/dashboard/logistica")
@roles_requeridos("ADMIN", "OPERATIVO")
def logistica():
    return jsonify(dashboard_service.logistica(_filtros()))


@dashboard_bp.get("/dashboard/exportar")
@roles_requeridos("ADMIN")
def exportar():
    contenido = dashboard_service.exportar(_filtros())
    return Response(
        contenido,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="dashboard-unique.csv"'},
    )
