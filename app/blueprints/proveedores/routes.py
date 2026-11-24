"""Endpoints del padrón de proveedores y su catálogo de materiales (M13)."""

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.schemas.proveedor import (
    ProveedorActualizarSchema,
    ProveedorCrearSchema,
    ProveedorEvaluacionResponseSchema,
    ProveedorFiltrosSchema,
    ProveedorMaterialActualizarSchema,
    ProveedorMaterialCrearSchema,
    ProveedorMaterialSchema,
    ProveedorSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import proveedor_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.validacion import cuerpo

proveedores_bp = Blueprint("proveedores", __name__, url_prefix="/api/v1")


def _filtros(schema):
    try:
        return schema.load(request.args)
    except ValidationError as error:
        detalle = [
            {"campo": campo, "mensaje": str(mensaje)}
            for campo, mensaje in error.messages.items()
        ]
        raise ApiError("VALIDACION", "Parámetros inválidos", 400, detalle)


@proveedores_bp.get("/proveedores/evaluacion")
@roles_requeridos("ADMIN")
def evaluar_proveedores():
    return jsonify(
        ProveedorEvaluacionResponseSchema().dump(proveedor_service.evaluacion())
    )


@proveedores_bp.get("/proveedores")
@roles_requeridos("ADMIN")
def listar_proveedores():
    filtros = ProveedorFiltrosSchema().load(request.args)
    pagina, por_pagina = parametros_paginacion()
    filtros.update(pagina=pagina, por_pagina=por_pagina)
    resultado = proveedor_service.listar(filtros)
    resultado["items"] = ProveedorSchema(many=True).dump(resultado["items"])
    return jsonify(resultado)


@proveedores_bp.post("/proveedores")
@roles_requeridos("ADMIN")
def crear_proveedor():
    datos = cuerpo(ProveedorCrearSchema())
    proveedor = proveedor_service.crear(
        datos, usuario_actual().id, ip=request.remote_addr
    )
    return jsonify(ProveedorSchema().dump(proveedor)), 201


@proveedores_bp.get("/proveedores/<int:proveedor_id>")
@roles_requeridos("ADMIN")
def obtener_proveedor(proveedor_id):
    return jsonify(
        ProveedorSchema().dump(proveedor_service.obtener(proveedor_id))
    )


@proveedores_bp.patch("/proveedores/<int:proveedor_id>")
@roles_requeridos("ADMIN")
def actualizar_proveedor(proveedor_id):
    datos = cuerpo(ProveedorActualizarSchema(), parcial=True)
    proveedor = proveedor_service.actualizar(
        proveedor_id, datos, usuario_actual().id, ip=request.remote_addr
    )
    return jsonify(ProveedorSchema().dump(proveedor))


@proveedores_bp.delete("/proveedores/<int:proveedor_id>")
@roles_requeridos("ADMIN")
def desactivar_proveedor(proveedor_id):
    proveedor_service.desactivar(
        proveedor_id, usuario_actual().id, ip=request.remote_addr
    )
    return "", 204


@proveedores_bp.get("/proveedores/<int:proveedor_id>/materiales")
@roles_requeridos("ADMIN")
def listar_materiales_proveedor(proveedor_id):
    materiales = proveedor_service.listar_materiales(proveedor_id)
    return jsonify(ProveedorMaterialSchema(many=True).dump(materiales))


@proveedores_bp.post("/proveedores/<int:proveedor_id>/materiales")
@roles_requeridos("ADMIN")
def agregar_material_proveedor(proveedor_id):
    datos = cuerpo(ProveedorMaterialCrearSchema())
    fila = proveedor_service.agregar_material(
        proveedor_id, datos, usuario_actual().id
    )
    return jsonify(ProveedorMaterialSchema().dump(proveedor_service.serializar_material(fila))), 201


@proveedores_bp.patch("/proveedores/<int:proveedor_id>/materiales/<int:material_id>")
@roles_requeridos("ADMIN")
def actualizar_material_proveedor(proveedor_id, material_id):
    datos = cuerpo(ProveedorMaterialActualizarSchema(), parcial=True)
    fila = proveedor_service.actualizar_material(
        proveedor_id, material_id, datos, usuario_actual().id
    )
    return jsonify(ProveedorMaterialSchema().dump(proveedor_service.serializar_material(fila)))


@proveedores_bp.delete("/proveedores/<int:proveedor_id>/materiales/<int:material_id>")
@roles_requeridos("ADMIN")
def eliminar_material_proveedor(proveedor_id, material_id):
    proveedor_service.eliminar_material(
        proveedor_id, material_id, usuario_actual().id
    )
    return "", 204
