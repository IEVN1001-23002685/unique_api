"""Endpoints de solicitudes, inspección y resolución de devoluciones (M07)."""

import json

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.schemas import (
    DevolucionCrearSchema,
    DevolucionDictamenSchema,
    DevolucionFiltrosSchema,
    DevolucionRechazarSchema,
    DevolucionResolverSchema,
    DevolucionSchema,
)
from app.security import roles_requeridos, tiene_rol, usuario_actual
from app.services import devolucion_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.validacion import cuerpo

devoluciones_bp = Blueprint("devoluciones", __name__, url_prefix="/api/v1")


def _filtros():
    try:
        return DevolucionFiltrosSchema().load(request.args)
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


def _solicitud():
    if request.is_json:
        return cuerpo(DevolucionCrearSchema()), []
    crudo = request.form.get("datos")
    if not crudo:
        raise ApiError(
            "JSON_INVALIDO", "Se requiere el campo datos con la solicitud en JSON", 400
        )
    try:
        contenido = json.loads(crudo)
    except (TypeError, ValueError):
        raise ApiError("JSON_INVALIDO", "El campo datos no contiene JSON válido", 400)
    try:
        datos = DevolucionCrearSchema().load(contenido)
    except ValidationError as error:
        raise ApiError(
            "VALIDACION",
            "Datos inválidos",
            400,
            [
                {"campo": str(campo), "mensaje": str(mensaje)}
                for campo, mensaje in error.messages.items()
            ],
        )
    archivos = request.files.getlist("evidencias") or request.files.getlist("evidencia")
    return datos, [archivo for archivo in archivos if archivo and archivo.filename]


@devoluciones_bp.post("/devoluciones")
@roles_requeridos("CLIENTE")
def crear_devolucion():
    datos, archivos = _solicitud()
    resultado = devolucion_service.crear(
        datos, archivos, usuario_actual().id, request.remote_addr
    )
    return jsonify(DevolucionSchema().dump(resultado)), 201


@devoluciones_bp.get("/devoluciones")
@roles_requeridos("CLIENTE", "OPERATIVO")
def listar_devoluciones():
    filtros = _filtros()
    pagina, por_pagina = parametros_paginacion()
    es_cliente = tiene_rol("CLIENTE")
    resultado = devolucion_service.listar(
        filtros,
        usuario_id=usuario_actual().id if es_cliente else None,
        incluir_importes=not tiene_rol("OPERATIVO"),
        pagina=pagina,
        por_pagina=por_pagina,
    )
    resultado["items"] = DevolucionSchema(many=True).dump(resultado["items"])
    return jsonify(resultado)


@devoluciones_bp.patch("/devoluciones/<int:devolucion_id>/aprobar")
@roles_requeridos("ADMIN")
def aprobar_devolucion(devolucion_id):
    resultado = devolucion_service.aprobar(
        devolucion_id, usuario_actual().id, request.remote_addr
    )
    return jsonify(DevolucionSchema().dump(resultado))


@devoluciones_bp.patch("/devoluciones/<int:devolucion_id>/rechazar")
@roles_requeridos("ADMIN")
def rechazar_devolucion(devolucion_id):
    datos = cuerpo(DevolucionRechazarSchema())
    resultado = devolucion_service.rechazar(
        devolucion_id, datos, usuario_actual().id, request.remote_addr
    )
    return jsonify(DevolucionSchema().dump(resultado))


@devoluciones_bp.post("/devoluciones/<int:devolucion_id>/recibir")
@roles_requeridos("OPERATIVO")
def recibir_devolucion(devolucion_id):
    resultado = devolucion_service.recibir(
        devolucion_id, usuario_actual().id, request.remote_addr
    )
    return jsonify(DevolucionSchema().dump(resultado))


@devoluciones_bp.post("/devoluciones/<int:devolucion_id>/dictamen")
@roles_requeridos("OPERATIVO")
def dictaminar_devolucion(devolucion_id):
    datos = cuerpo(DevolucionDictamenSchema())
    resultado = devolucion_service.dictaminar(
        devolucion_id, datos, usuario_actual().id, request.remote_addr
    )
    return jsonify(DevolucionSchema().dump(resultado))


@devoluciones_bp.post("/devoluciones/<int:devolucion_id>/resolver")
@roles_requeridos("ADMIN")
def resolver_devolucion(devolucion_id):
    datos = cuerpo(DevolucionResolverSchema())
    resultado = devolucion_service.resolver(
        devolucion_id, datos, usuario_actual().id, request.remote_addr
    )
    return jsonify(DevolucionSchema().dump(resultado))
