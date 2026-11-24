"""Endpoints del carrito persistido del cliente (M04)."""

from flask import Blueprint, jsonify

from app.schemas import (
    CarritoFusionarSchema,
    CarritoLineaCrearSchema,
    CarritoSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import carrito_service
from app.utils.validacion import cuerpo

carrito_bp = Blueprint("carrito", __name__, url_prefix="/api/v1")


@carrito_bp.get("/carrito")
@roles_requeridos("CLIENTE")
def obtener_carrito():
    return jsonify(CarritoSchema().dump(carrito_service.obtener(usuario_actual().id)))


@carrito_bp.put("/carrito/lineas")
@roles_requeridos("CLIENTE")
def guardar_linea():
    datos = cuerpo(CarritoLineaCrearSchema())
    carrito = carrito_service.agregar_linea(
        usuario_actual().id, datos["variante_id"], datos["cantidad"]
    )
    return jsonify(CarritoSchema().dump(carrito))


@carrito_bp.delete("/carrito/lineas/<int:variante_id>")
@roles_requeridos("CLIENTE")
def quitar_linea(variante_id):
    carrito_service.eliminar_linea(usuario_actual().id, variante_id)
    return "", 204


@carrito_bp.post("/carrito/fusionar")
@roles_requeridos("CLIENTE")
def fusionar_carrito():
    datos = cuerpo(CarritoFusionarSchema())
    carrito = carrito_service.fusionar(usuario_actual().id, datos["lineas"])
    return jsonify(CarritoSchema().dump(carrito))
