"""Endpoints administrativos y operativos de pedidos (M09)."""

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.schemas import (
    CancelarPedidoSchema,
    PedidoAdminActualizarSchema,
    PedidoAdminDetalleSchema,
    PedidoAdminFiltrosSchema,
    PedidoAdminListaSchema,
    PendienteProduccionFiltrosSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import pedido_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.validacion import cuerpo

pedidos_bp = Blueprint("pedidos", __name__, url_prefix="/api/v1")


def _filtros(schema):
    try:
        return schema.load(request.args)
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


@pedidos_bp.get("/pedidos")
@roles_requeridos("ADMIN", "OPERATIVO")
def listar_pedidos():
    filtros = _filtros(PedidoAdminFiltrosSchema())
    pagina, por_pagina = parametros_paginacion()
    resultado = pedido_service.listar_admin(filtros, pagina, por_pagina)
    resultado["items"] = PedidoAdminListaSchema(many=True).dump(resultado["items"])
    return jsonify(resultado)


@pedidos_bp.get("/pedidos/pendientes-produccion")
@roles_requeridos("ADMIN", "OPERATIVO")
def pendientes_produccion():
    filtros = _filtros(PendienteProduccionFiltrosSchema())
    pagina, por_pagina = parametros_paginacion()
    resultado = pedido_service.pendientes_produccion(filtros, pagina, por_pagina)
    return jsonify(resultado)


@pedidos_bp.get("/pedidos/<int:pedido_id>")
@roles_requeridos("ADMIN", "OPERATIVO")
def detalle_pedido(pedido_id):
    return jsonify(
        PedidoAdminDetalleSchema().dump(pedido_service.detalle_admin(pedido_id))
    )


@pedidos_bp.patch("/pedidos/<int:pedido_id>")
@roles_requeridos("ADMIN")
def actualizar_pedido(pedido_id):
    datos = cuerpo(PedidoAdminActualizarSchema(), parcial=True)
    if not datos:
        raise ApiError("VALIDACION", "Se requiere prioridad o nota", 400)
    resultado = pedido_service.actualizar_admin(
        pedido_id, datos, usuario_actual().id, request.remote_addr
    )
    return jsonify(PedidoAdminDetalleSchema().dump(resultado))


@pedidos_bp.post("/pedidos/<int:pedido_id>/cancelar")
@roles_requeridos("ADMIN")
def cancelar_pedido(pedido_id):
    datos = cuerpo(CancelarPedidoSchema())
    resultado = pedido_service.cancelar_admin(
        pedido_id, usuario_actual().id, datos["motivo"], request.remote_addr
    )
    return jsonify(PedidoAdminDetalleSchema().dump(resultado))
