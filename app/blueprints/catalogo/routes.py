"""Endpoints públicos del catálogo (M03)."""

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.schemas import CatalogoFiltrosSchema, ProductoDetalleSchema, ProductoListaSchema
from app.services import catalogo_service
from app.utils.errores import ApiError

catalogo_bp = Blueprint("catalogo", __name__, url_prefix="/api/v1")


@catalogo_bp.get("/catalogo")
def listar_catalogo():
    try:
        filtros = CatalogoFiltrosSchema().load(request.args)
    except ValidationError as error:
        detalle = [
            {"campo": campo, "mensaje": str(mensaje)}
            for campo, mensaje in error.messages.items()
        ]
        raise ApiError("VALIDACION", "Parámetros inválidos", 400, detalle)
    return jsonify(ProductoListaSchema(many=True).dump(catalogo_service.listar(filtros)))


@catalogo_bp.get("/catalogo/<int:producto_id>")
def detalle_producto(producto_id):
    return jsonify(
        ProductoDetalleSchema().dump(catalogo_service.obtener(producto_id))
    )
