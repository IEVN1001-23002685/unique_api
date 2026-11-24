"""Endpoints de cotización, descuentos y pago simulado (M05)."""

from flask import Blueprint, jsonify, request

from app.schemas import (
    CheckoutResponseSchema,
    CotizarSchema,
    DescuentoAplicarSchema,
    PagarSchema,
    ResumenCheckoutSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import checkout_service
from app.utils.validacion import cuerpo

checkout_bp = Blueprint("checkout", __name__, url_prefix="/api/v1")


@checkout_bp.post("/checkout/cotizar")
@roles_requeridos("CLIENTE")
def cotizar():
    datos = cuerpo(CotizarSchema())
    resumen = checkout_service.cotizar(usuario_actual().id, datos)
    return jsonify(ResumenCheckoutSchema().dump(resumen))


@checkout_bp.post("/checkout/descuento")
@roles_requeridos("CLIENTE")
def aplicar_descuento():
    datos = cuerpo(DescuentoAplicarSchema())
    return jsonify(checkout_service.validar_descuento(usuario_actual().id, datos))


@checkout_bp.post("/checkout/pagar")
@roles_requeridos("CLIENTE")
def pagar():
    datos = cuerpo(PagarSchema())
    resultado = checkout_service.pagar(
        usuario_actual().id,
        datos,
        request.headers.get("Idempotency-Key"),
    )
    return jsonify(CheckoutResponseSchema().dump(resultado)), 201
