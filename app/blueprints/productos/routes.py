"""Endpoints administrativos de productos y variantes (M10)."""

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.schemas.producto import (
    ImagenSubirFormSchema,
    ProductoActualizarSchema,
    ProductoCrearSchema,
    ProductoDetalleAdminSchema,
    ProductoFiltrosSchema,
    ProductoImagenAdminSchema,
    ProductoListaAdminSchema,
    VarianteActualizarSchema,
    VarianteAdminSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import producto_service
from app.utils.errores import ApiError
from app.utils.paginacion import paginar_lista, parametros_paginacion
from app.utils.validacion import cuerpo

productos_bp = Blueprint("productos", __name__, url_prefix="/api/v1")


def _parametros(schema):
    try:
        return schema.load(request.args)
    except ValidationError as error:
        raise ApiError(
            "VALIDACION",
            "Parámetros inválidos",
            400,
            [{"campo": str(campo), "mensaje": str(mensaje)} for campo, mensaje in error.messages.items()],
        )


def _formulario(schema):
    try:
        return schema.load(request.form)
    except ValidationError as error:
        raise ApiError(
            "VALIDACION",
            "Formulario inválido",
            400,
            [{"campo": str(campo), "mensaje": str(mensaje)} for campo, mensaje in error.messages.items()],
        )


@productos_bp.get("/productos")
@roles_requeridos("ADMIN")
def listar_productos():
    filtros = _parametros(ProductoFiltrosSchema())
    pagina, por_pagina = parametros_paginacion()
    items = ProductoListaAdminSchema(many=True).dump(producto_service.listar(filtros))
    return jsonify(paginar_lista(items, pagina, por_pagina))


@productos_bp.post("/productos")
@roles_requeridos("ADMIN")
def crear_producto():
    datos = cuerpo(ProductoCrearSchema())
    producto = producto_service.crear_producto(
        datos, usuario_actual().id, ip=request.remote_addr
    )
    return jsonify(ProductoDetalleAdminSchema().dump(producto)), 201


@productos_bp.get("/productos/<int:producto_id>")
@roles_requeridos("ADMIN")
def obtener_producto(producto_id):
    return jsonify(
        ProductoDetalleAdminSchema().dump(producto_service.obtener(producto_id))
    )


@productos_bp.patch("/productos/<int:producto_id>")
@roles_requeridos("ADMIN")
def actualizar_producto(producto_id):
    datos = cuerpo(ProductoActualizarSchema(), parcial=True)
    if not datos:
        raise ApiError("VALIDACION", "Se requiere al menos un campo", 400)
    producto = producto_service.actualizar(
        producto_id, datos, usuario_actual().id, ip=request.remote_addr
    )
    return jsonify(ProductoDetalleAdminSchema().dump(producto))


@productos_bp.delete("/productos/<int:producto_id>")
@roles_requeridos("ADMIN")
def desactivar_producto(producto_id):
    producto_service.desactivar(
        producto_id, usuario_actual().id, ip=request.remote_addr
    )
    return "", 204


@productos_bp.post("/productos/<int:producto_id>/imagenes")
@roles_requeridos("ADMIN")
def agregar_imagen(producto_id):
    archivo = request.files.get("archivo") or request.files.get("imagen")
    if archivo is None or not archivo.filename:
        raise ApiError("ARCHIVO_REQUERIDO", "Se requiere el campo archivo o imagen", 400)
    datos = _formulario(ImagenSubirFormSchema())
    imagen = producto_service.agregar_imagen(
        producto_id,
        archivo,
        usuario_actual().id,
        ip=request.remote_addr,
        datos=datos,
    )
    return jsonify(ProductoImagenAdminSchema().dump(imagen)), 201


@productos_bp.patch("/variantes/<int:variante_id>")
@roles_requeridos("ADMIN")
def actualizar_variante(variante_id):
    datos = cuerpo(VarianteActualizarSchema())
    variante = producto_service.actualizar_variante(
        variante_id, datos, usuario_actual().id, ip=request.remote_addr
    )
    return jsonify(VarianteAdminSchema().dump(variante))


@productos_bp.post("/productos/<int:producto_id>/activar")
@roles_requeridos("ADMIN")
def activar_producto(producto_id):
    producto = producto_service.activar(
        producto_id, usuario_actual().id, ip=request.remote_addr
    )
    return jsonify(ProductoDetalleAdminSchema().dump(producto))
