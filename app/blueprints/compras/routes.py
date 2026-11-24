"""Endpoints de requisiciones, cotizaciones, órdenes y recepciones (M14)."""

from flask import Blueprint, Response, jsonify, request
from marshmallow import ValidationError

from app.schemas import (
    CotizacionCrearSchema,
    FiltrosOrdenSchema,
    FiltrosRequisicionSchema,
    OrdenCompraActualizarSchema,
    OrdenCompraCrearSchema,
    RecepcionCrearSchema,
    RequisicionActualizarSchema,
    RequisicionCrearSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import compras_service
from app.utils.errores import ApiError
from app.utils.paginacion import paginar_lista, parametros_paginacion
from app.utils.validacion import cuerpo

compras_bp = Blueprint("compras", __name__, url_prefix="/api/v1")


def _filtros(schema):
    try:
        return schema.load(request.args)
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


def _ip():
    return request.remote_addr


@compras_bp.get("/requisiciones")
@roles_requeridos("OPERATIVO")
def listar_requisiciones():
    pagina, por_pagina = parametros_paginacion()
    return jsonify(
        compras_service.listar_requisiciones(
            _filtros(FiltrosRequisicionSchema()), pagina, por_pagina
        )
    )


@compras_bp.post("/requisiciones")
@roles_requeridos("OPERATIVO")
def crear_requisicion():
    datos = cuerpo(RequisicionCrearSchema())
    return jsonify(compras_service.crear_requisicion(datos, usuario_actual().id, _ip())), 201


@compras_bp.patch("/requisiciones/<int:requisicion_id>")
@roles_requeridos("OPERATIVO")
def actualizar_requisicion(requisicion_id):
    datos = cuerpo(RequisicionActualizarSchema())
    return jsonify(
        compras_service.actualizar_requisicion(
            requisicion_id, datos, usuario_actual().id, _ip()
        )
    )


@compras_bp.delete("/requisiciones/<int:requisicion_id>")
@roles_requeridos("OPERATIVO")
def cancelar_requisicion(requisicion_id):
    compras_service.cancelar_requisicion(requisicion_id, usuario_actual().id, _ip())
    return "", 204


@compras_bp.post("/requisiciones/<int:requisicion_id>/cotizaciones")
@roles_requeridos("ADMIN")
def crear_cotizacion(requisicion_id):
    datos = cuerpo(CotizacionCrearSchema())
    return jsonify(
        compras_service.crear_cotizacion(requisicion_id, datos, usuario_actual().id)
    ), 201


@compras_bp.get("/cotizaciones")
@roles_requeridos("ADMIN")
def listar_cotizaciones():
    requisicion_id = request.args.get("requisicion_id", type=int)
    pagina, por_pagina = parametros_paginacion()
    items = compras_service.listar_cotizaciones(requisicion_id)
    return jsonify(paginar_lista(items, pagina, por_pagina))


@compras_bp.post("/cotizaciones/<int:cotizacion_id>/elegir")
@roles_requeridos("ADMIN")
def elegir_cotizacion(cotizacion_id):
    return jsonify(compras_service.elegir_cotizacion(cotizacion_id, usuario_actual().id, _ip()))


@compras_bp.get("/ordenes-compra")
@roles_requeridos("ADMIN")
def listar_ordenes():
    pagina, por_pagina = parametros_paginacion()
    return jsonify(
        compras_service.listar_ordenes(_filtros(FiltrosOrdenSchema()), pagina, por_pagina)
    )


@compras_bp.post("/ordenes-compra")
@roles_requeridos("ADMIN")
def crear_orden():
    datos = cuerpo(OrdenCompraCrearSchema())
    return jsonify(compras_service.crear_orden(datos, usuario_actual().id, _ip())), 201


@compras_bp.get("/ordenes-compra/<int:orden_id>")
@roles_requeridos("ADMIN")
def obtener_orden(orden_id):
    return jsonify(compras_service.obtener_orden(orden_id))


@compras_bp.patch("/ordenes-compra/<int:orden_id>")
@roles_requeridos("ADMIN")
def actualizar_orden(orden_id):
    datos = cuerpo(OrdenCompraActualizarSchema())
    return jsonify(
        compras_service.actualizar_orden(orden_id, datos, usuario_actual().id, _ip())
    )


@compras_bp.delete("/ordenes-compra/<int:orden_id>")
@roles_requeridos("ADMIN")
def cancelar_orden(orden_id):
    compras_service.cancelar_orden(orden_id, usuario_actual().id, _ip())
    return "", 204


@compras_bp.post("/ordenes-compra/<int:orden_id>/emitir")
@roles_requeridos("ADMIN")
def emitir_orden(orden_id):
    return jsonify(compras_service.emitir_orden(orden_id, usuario_actual().id, _ip()))


@compras_bp.post("/ordenes-compra/<int:orden_id>/cancelar")
@roles_requeridos("ADMIN")
def cancelar_orden_accion(orden_id):
    return jsonify(compras_service.cancelar_orden(orden_id, usuario_actual().id, _ip()))


@compras_bp.get("/ordenes-compra/<int:orden_id>/pdf")
@roles_requeridos("ADMIN")
def pdf_orden(orden_id):
    contenido, nombre = compras_service.pdf_orden(orden_id)
    return Response(
        contenido,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


@compras_bp.post("/recepciones")
@roles_requeridos("OPERATIVO")
def registrar_recepcion():
    datos = cuerpo(RecepcionCrearSchema())
    resultado = compras_service.registrar_recepcion(
        datos,
        usuario_actual().id,
        request.headers.get("Idempotency-Key"),
    )
    return jsonify(resultado), 201
