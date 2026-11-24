"""Endpoints de inventario de producto terminado y reglas de reposición (M12)."""

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.schemas.inventario_pt import (
    AjusteResponseSchema,
    AjusteSchema,
    InventarioFiltrosSchema,
    InventarioItemSchema,
    MovimientosFiltrosSchema,
    MovimientoProductoSchema,
    ReglasActualizarSchema,
    ReglasResponseSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import inventario_pt_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.validacion import cuerpo

inventario_pt_bp = Blueprint("inventario_pt", __name__, url_prefix="/api/v1")


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


def _paginar(resultado, esquema):
    items = esquema(many=True).dump(resultado["items"])
    return jsonify({**resultado, "items": items})


@inventario_pt_bp.get("/inventario/producto")
@roles_requeridos("OPERATIVO")
def listar_inventario():
    filtros = _parametros(InventarioFiltrosSchema())
    pagina, por_pagina = parametros_paginacion()
    return _paginar(
        inventario_pt_service.listar(filtros, pagina, por_pagina), InventarioItemSchema
    )


@inventario_pt_bp.get("/inventario/producto/movimientos")
@roles_requeridos("OPERATIVO")
def listar_movimientos():
    filtros = _parametros(MovimientosFiltrosSchema())
    pagina, por_pagina = parametros_paginacion()
    return _paginar(
        inventario_pt_service.movimientos(filtros, pagina, por_pagina),
        MovimientoProductoSchema,
    )


@inventario_pt_bp.post("/inventario/producto/ajuste")
@roles_requeridos("OPERATIVO")
def registrar_ajuste():
    datos = cuerpo(AjusteSchema())
    ajuste = inventario_pt_service.ajuste(datos, usuario_actual().id)
    return jsonify(AjusteResponseSchema().dump(ajuste))


@inventario_pt_bp.patch("/inventario/producto/<int:variante_id>/reglas")
@roles_requeridos("ADMIN")
def actualizar_reglas(variante_id):
    datos = cuerpo(ReglasActualizarSchema(), parcial=True)
    if not datos:
        raise ApiError("VALIDACION", "Se requiere al menos una regla", 400)
    reglas = inventario_pt_service.actualizar_reglas(
        variante_id, datos, usuario_actual().id, ip=request.remote_addr
    )
    return jsonify(ReglasResponseSchema().dump(reglas))
