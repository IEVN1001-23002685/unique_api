"""Endpoints de órdenes de producción, materiales, calidad y plan sugerido (M16)."""

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.schemas import (
    CancelarOrdenSchema,
    DictamenSchema,
    OrdenCrearSchema,
    OrdenFiltrosSchema,
    RevisionSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import produccion_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.validacion import cuerpo

produccion_bp = Blueprint("produccion", __name__, url_prefix="/api/v1")


def _filtros(schema):
    pagina, por_pagina = parametros_paginacion()
    try:
        datos = schema.load(request.args)
    except ValidationError as error:
        raise ApiError(
            "VALIDACION",
            "Parámetros inválidos",
            400,
            [
                {"campo": campo, "mensaje": str(mensaje)}
                for campo, mensaje in error.messages.items()
            ],
        )
    datos["pagina"] = pagina
    datos["por_pagina"] = por_pagina
    return datos


@produccion_bp.get("/produccion/ordenes")
@roles_requeridos("OPERATIVO")
def listar_ordenes():
    filtros = _filtros(OrdenFiltrosSchema())
    return jsonify(
        produccion_service.listar(
            filtros, filtros["pagina"], filtros["por_pagina"]
        )
    )


@produccion_bp.post("/produccion/ordenes")
@roles_requeridos("OPERATIVO")
def crear_orden():
    datos = cuerpo(OrdenCrearSchema())
    return jsonify(
        produccion_service.crear(datos, usuario_actual().id, request.remote_addr)
    ), 201


@produccion_bp.get("/produccion/plan-sugerido")
@roles_requeridos("OPERATIVO")
def plan_sugerido():
    filtros = _filtros(OrdenFiltrosSchema())
    datos = {"sku": filtros.get("q"), "incluir_ceros": False}
    return jsonify(
        produccion_service.plan_sugerido(
            datos, filtros["pagina"], filtros["por_pagina"]
        )
    )


@produccion_bp.get("/produccion/pendientes-produccion")
@roles_requeridos("OPERATIVO")
def pendientes_produccion():
    filtros = _filtros(OrdenFiltrosSchema())
    return jsonify(
        produccion_service.pendientes_produccion(
            filtros, filtros["pagina"], filtros["por_pagina"]
        )
    )


@produccion_bp.get("/produccion/ordenes/<int:orden_id>")
@roles_requeridos("OPERATIVO")
def detalle_orden(orden_id):
    return jsonify(produccion_service.detalle(orden_id))


@produccion_bp.post("/produccion/ordenes/<int:orden_id>/reservar")
@roles_requeridos("OPERATIVO")
def reservar_materiales(orden_id):
    return jsonify(
        produccion_service.reservar_materiales(
            orden_id, usuario_actual().id, request.remote_addr
        )
    )


@produccion_bp.post("/produccion/ordenes/<int:orden_id>/solicitar-compra")
@roles_requeridos("OPERATIVO")
def solicitar_compra(orden_id):
    return jsonify(
        produccion_service.solicitar_compra(
            orden_id, usuario_actual().id, request.remote_addr
        )
    )


@produccion_bp.post("/produccion/ordenes/<int:orden_id>/iniciar")
@roles_requeridos("OPERATIVO")
def iniciar_produccion(orden_id):
    datos = cuerpo(RevisionSchema(), parcial=True)
    return jsonify(
        produccion_service.iniciar_produccion(
            orden_id,
            datos,
            usuario_actual().id,
            request.headers.get("Idempotency-Key"),
            request.remote_addr,
        )
    )


@produccion_bp.post("/produccion/ordenes/<int:orden_id>/revision")
@roles_requeridos("OPERATIVO")
def enviar_revision(orden_id):
    datos = cuerpo(RevisionSchema(), parcial=True)
    return jsonify(
        produccion_service.enviar_revision(
            orden_id, datos, usuario_actual().id, request.remote_addr
        )
    )


@produccion_bp.post("/produccion/ordenes/<int:orden_id>/dictamen")
@roles_requeridos("OPERATIVO")
def registrar_dictamen(orden_id):
    datos = cuerpo(DictamenSchema())
    return jsonify(
        produccion_service.registrar_dictamen(
            orden_id, datos, usuario_actual().id, request.remote_addr
        )
    )


@produccion_bp.post("/produccion/ordenes/<int:orden_id>/cancelar")
@roles_requeridos("OPERATIVO")
def cancelar_orden(orden_id):
    datos = cuerpo(CancelarOrdenSchema())
    return jsonify(
        produccion_service.cancelar(
            orden_id, datos, usuario_actual().id, request.remote_addr
        )
    )
