"""Endpoints de ventas, pagos, reembolsos y descuentos (M08)."""

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.schemas import (
    DescuentoActualizarSchema,
    DescuentoCrearSchema,
    DescuentoFiltrosSchema,
    DescuentoSchema,
    VentaCancelarSchema,
    VentaDetalleSchema,
    VentaFiltrosSchema,
    VentaListaSchema,
    VentaManualSchema,
    VentaPagoSchema,
    VentaReembolsoSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import venta_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.validacion import cuerpo

ventas_bp = Blueprint("ventas", __name__, url_prefix="/api/v1")


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


@ventas_bp.get("/ventas")
@roles_requeridos("ADMIN")
def listar_ventas():
    filtros = _filtros(VentaFiltrosSchema())
    pagina, por_pagina = parametros_paginacion()
    resultado = venta_service.listar(filtros, pagina, por_pagina)
    resultado["items"] = VentaListaSchema(many=True).dump(resultado["items"])
    return jsonify(resultado)


@ventas_bp.post("/ventas/manual")
@roles_requeridos("ADMIN")
def crear_venta_manual():
    datos = cuerpo(VentaManualSchema())
    venta = venta_service.crear_manual(
        datos, usuario_actual().id, request.remote_addr
    )
    return jsonify(VentaDetalleSchema().dump(venta)), 201


@ventas_bp.get("/ventas/<int:venta_id>")
@roles_requeridos("ADMIN")
def detalle_venta(venta_id):
    return jsonify(VentaDetalleSchema().dump(venta_service.detalle(venta_id)))


@ventas_bp.post("/ventas/<int:venta_id>/pago")
@roles_requeridos("ADMIN")
def pagar_venta(venta_id):
    datos = cuerpo(VentaPagoSchema())
    venta = venta_service.validar_pago(
        venta_id, datos, usuario_actual().id, request.remote_addr
    )
    return jsonify(VentaDetalleSchema().dump(venta))


@ventas_bp.post("/ventas/<int:venta_id>/cancelar")
@roles_requeridos("ADMIN")
def cancelar_venta(venta_id):
    datos = cuerpo(VentaCancelarSchema())
    venta = venta_service.cancelar(
        venta_id, datos, usuario_actual().id, request.remote_addr
    )
    return jsonify(VentaDetalleSchema().dump(venta))


@ventas_bp.post("/ventas/<int:venta_id>/reembolso")
@roles_requeridos("ADMIN")
def reembolsar_venta(venta_id):
    datos = cuerpo(VentaReembolsoSchema())
    venta_service.reembolsar(
        venta_id, datos, usuario_actual().id, request.remote_addr
    )
    return jsonify(VentaDetalleSchema().dump(venta_service.detalle(venta_id)))


@ventas_bp.get("/descuentos")
@roles_requeridos("ADMIN")
def listar_descuentos():
    filtros = _filtros(DescuentoFiltrosSchema())
    pagina, por_pagina = parametros_paginacion()
    resultado = venta_service.listar_descuentos(filtros, pagina, por_pagina)
    resultado["items"] = DescuentoSchema(many=True).dump(resultado["items"])
    return jsonify(resultado)


@ventas_bp.post("/descuentos")
@roles_requeridos("ADMIN")
def crear_descuento():
    datos = cuerpo(DescuentoCrearSchema())
    descuento = venta_service.crear_descuento(
        datos, usuario_actual().id, request.remote_addr
    )
    return jsonify(DescuentoSchema().dump(descuento)), 201


@ventas_bp.patch("/descuentos/<int:descuento_id>")
@roles_requeridos("ADMIN")
def actualizar_descuento(descuento_id):
    datos = cuerpo(DescuentoActualizarSchema(), parcial=True)
    if not datos:
        raise ApiError("VALIDACION", "Se requiere al menos un campo", 400)
    descuento = venta_service.actualizar_descuento(
        descuento_id, datos, usuario_actual().id, request.remote_addr
    )
    return jsonify(DescuentoSchema().dump(descuento))


@ventas_bp.delete("/descuentos/<int:descuento_id>")
@roles_requeridos("ADMIN")
def desactivar_descuento(descuento_id):
    venta_service.desactivar_descuento(
        descuento_id, usuario_actual().id, request.remote_addr
    )
    return "", 204
