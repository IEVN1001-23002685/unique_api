"""Endpoints de seguimiento de pedidos del cliente (M06)."""

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.schemas import (
    CancelarPedidoSchema,
    ComprobanteSchema,
    PedidoDetalleSchema,
    PedidoFiltrosSchema,
    PedidoListaSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import pedido_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.validacion import cuerpo

mis_pedidos_bp = Blueprint("mis_pedidos", __name__, url_prefix="/api/v1")


@mis_pedidos_bp.get("/mis-pedidos")
@roles_requeridos("CLIENTE")
def listar_mis_pedidos():
    try:
        filtros = PedidoFiltrosSchema().load(request.args)
    except ValidationError as error:
        raise ApiError("VALIDACION", "Filtro no válido", 400)
    pagina, por_pagina = parametros_paginacion()
    resultado = pedido_service.listar_propios(
        usuario_actual().id, filtros["estado"], pagina, por_pagina
    )
    resultado["items"] = PedidoListaSchema(many=True).dump(resultado["items"])
    return jsonify(resultado)


@mis_pedidos_bp.get("/mis-pedidos/<int:pedido_id>")
@roles_requeridos("CLIENTE")
def detalle_mi_pedido(pedido_id):
    return jsonify(
        PedidoDetalleSchema().dump(
            pedido_service.detalle_propio(pedido_id, usuario_actual().id)
        )
    )


@mis_pedidos_bp.post("/mis-pedidos/<int:pedido_id>/cancelar")
@roles_requeridos("CLIENTE")
def cancelar_mi_pedido(pedido_id):
    datos = cuerpo(CancelarPedidoSchema())
    pedido = pedido_service.cancelar(
        pedido_id, usuario_actual().id, datos["motivo"]
    )
    return jsonify(PedidoDetalleSchema().dump(pedido))


@mis_pedidos_bp.get("/mis-pedidos/<int:pedido_id>/comprobante")
@roles_requeridos("CLIENTE")
def comprobante_mi_pedido(pedido_id):
    return jsonify(
        ComprobanteSchema().dump(
            pedido_service.comprobante(pedido_id, usuario_actual().id)
        )
    )
