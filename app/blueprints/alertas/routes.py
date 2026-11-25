"""Endpoints de consulta, atención y reglas de alertas (M21)."""

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.schemas import (
    AlertaAccionSchema,
    AlertaFiltrosSchema,
    AlertaSchema,
    AlertasReglasActualizarSchema,
    ReglaSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import alertas_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.validacion import cuerpo

alertas_bp = Blueprint("alertas", __name__, url_prefix="/api/v1")


def _filtros():
    try:
        return AlertaFiltrosSchema().load(request.args)
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


def _rol():
    return usuario_actual().rol.codigo


@alertas_bp.get("/alertas")
@roles_requeridos("ADMIN", "OPERATIVO")
def listar_alertas():
    pagina, por_pagina = parametros_paginacion()
    resultado = alertas_service.listar(
        _filtros(), pagina, por_pagina, rol=_rol()
    )
    resultado["items"] = AlertaSchema(many=True).dump(resultado["items"])
    return jsonify(resultado)


@alertas_bp.get("/alertas/resueltas")
@roles_requeridos("ADMIN", "OPERATIVO")
def listar_resueltas():
    pagina, por_pagina = parametros_paginacion()
    resultado = alertas_service.listar(
        _filtros(), pagina, por_pagina, rol=_rol(), resueltas=True
    )
    resultado["items"] = AlertaSchema(many=True).dump(resultado["items"])
    return jsonify(resultado)


@alertas_bp.get("/alertas/reglas")
@roles_requeridos("ADMIN")
def listar_reglas():
    return jsonify(ReglaSchema(many=True).dump(alertas_service.listar_reglas()))


@alertas_bp.patch("/alertas/reglas")
@roles_requeridos("ADMIN")
def actualizar_reglas():
    datos = cuerpo(AlertasReglasActualizarSchema())
    cambios = {item["clave"]: item["valor"] for item in datos["reglas"]}
    if not cambios:
        raise ApiError("VALIDACION", "Se requiere al menos una regla", 400)
    resultado = alertas_service.actualizar_reglas(
        cambios, usuario_actual().id, request.remote_addr
    )
    return jsonify(ReglaSchema(many=True).dump(resultado))


@alertas_bp.post("/alertas/<int:alerta_id>/accion")
@roles_requeridos("ADMIN", "OPERATIVO")
def ejecutar_accion(alerta_id):
    datos = cuerpo(AlertaAccionSchema(), parcial=True)
    resultado = alertas_service.ejecutar_accion(
        alerta_id, datos, usuario_actual().id, request.remote_addr
    )
    resultado["alerta"] = AlertaSchema().dump(resultado["alerta"])
    return jsonify(resultado)
