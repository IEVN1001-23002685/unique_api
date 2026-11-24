"""Endpoints de materiales, inventario base, lotes, kardex y ajustes (M15)."""

from flask import Blueprint, jsonify, request

from app.schemas.material import (
    AjusteMaterialSchema,
    InventarioFiltrosSchema,
    InventarioMaterialSchema,
    LoteFiltrosSchema,
    LoteMaterialSchema,
    MaterialActualizarSchema,
    MaterialCrearSchema,
    MaterialFiltrosSchema,
    MaterialSchema,
    MovimientoFiltrosSchema,
    MovimientoMaterialSchema,
    PoliticaMaterialSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import material_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.validacion import cuerpo

inventario_mp_bp = Blueprint("inventario_mp", __name__, url_prefix="/api/v1")


def _con_costos():
    """El Administrador ve costos; el Operativo nunca recibe datos financieros."""
    return usuario_actual().rol.codigo == "ADMIN"


def _filtros(schema):
    filtros = schema.load(request.args)
    pagina, por_pagina = parametros_paginacion()
    filtros.update(pagina=pagina, por_pagina=por_pagina)
    return filtros


@inventario_mp_bp.get("/inventario/material/lotes")
@roles_requeridos("OPERATIVO")
def listar_lotes():
    filtros = _filtros(LoteFiltrosSchema())
    contexto = {"incluir_costos": _con_costos()}
    resultado = material_service.listar_lotes(filtros)
    resultado["items"] = LoteMaterialSchema(many=True, context=contexto).dump(
        resultado["items"]
    )
    return jsonify(resultado)


@inventario_mp_bp.get("/inventario/material/movimientos")
@roles_requeridos("OPERATIVO")
def listar_movimientos():
    filtros = _filtros(MovimientoFiltrosSchema())
    contexto = {"incluir_costos": _con_costos()}
    resultado = material_service.listar_movimientos(filtros)
    resultado["items"] = MovimientoMaterialSchema(many=True, context=contexto).dump(
        resultado["items"]
    )
    return jsonify(resultado)


@inventario_mp_bp.post("/inventario/material/ajuste")
@roles_requeridos("OPERATIVO")
def ajustar_inventario():
    datos = cuerpo(AjusteMaterialSchema())
    inventario = material_service.ajustar(datos, usuario_actual().id)
    serializer = InventarioMaterialSchema(context={"incluir_costos": _con_costos()})
    return jsonify(
        serializer.dump(material_service.serializar_inventario(inventario, _con_costos()))
    )


@inventario_mp_bp.patch("/inventario/material/<int:inventario_id>/politica")
@roles_requeridos("ADMIN")
def actualizar_politica(inventario_id):
    datos = cuerpo(PoliticaMaterialSchema(), parcial=True)
    if not datos:
        raise ApiError("VALIDACION", "Se requiere al menos un campo", 400)
    inventario = material_service.actualizar_politica(
        inventario_id, datos, usuario_actual().id, ip=request.remote_addr
    )
    serializer = InventarioMaterialSchema(context={"incluir_costos": True})
    return jsonify(
        serializer.dump(material_service.serializar_inventario(inventario))
    )


@inventario_mp_bp.get("/inventario/material")
@roles_requeridos("OPERATIVO")
def listar_inventario():
    filtros = _filtros(InventarioFiltrosSchema())
    con_costos = _con_costos()
    contexto = {"incluir_costos": con_costos}
    resultado = material_service.listar_inventario(filtros, con_costos)
    resultado["items"] = InventarioMaterialSchema(many=True, context=contexto).dump(
        resultado["items"]
    )
    return jsonify(resultado)


@inventario_mp_bp.get("/materiales")
@roles_requeridos("OPERATIVO")
def listar_materiales():
    filtros = _filtros(MaterialFiltrosSchema())
    con_costos = _con_costos()
    contexto = {"incluir_costos": con_costos}
    resultado = material_service.listar(filtros, con_costos)
    resultado["items"] = MaterialSchema(many=True, context=contexto).dump(
        resultado["items"]
    )
    return jsonify(resultado)


@inventario_mp_bp.post("/materiales")
@roles_requeridos("ADMIN")
def crear_material():
    datos = cuerpo(MaterialCrearSchema())
    material = material_service.crear(
        datos, usuario_actual().id, ip=request.remote_addr
    )
    return jsonify(
        MaterialSchema(context={"incluir_costos": True}).dump(material)
    ), 201


@inventario_mp_bp.get("/materiales/<int:material_id>")
@roles_requeridos("OPERATIVO")
def obtener_material(material_id):
    material = material_service.obtener(material_id)
    contexto = {"incluir_costos": _con_costos()}
    return jsonify(MaterialSchema(context=contexto).dump(material))


@inventario_mp_bp.patch("/materiales/<int:material_id>")
@roles_requeridos("ADMIN")
def actualizar_material(material_id):
    datos = cuerpo(MaterialActualizarSchema(), parcial=True)
    if not datos:
        raise ApiError("VALIDACION", "Se requiere al menos un campo", 400)
    material = material_service.actualizar(
        material_id, datos, usuario_actual().id, ip=request.remote_addr
    )
    return jsonify(
        MaterialSchema(context={"incluir_costos": True}).dump(material)
    )


@inventario_mp_bp.delete("/materiales/<int:material_id>")
@roles_requeridos("ADMIN")
def desactivar_material(material_id):
    material_service.desactivar(
        material_id, usuario_actual().id, ip=request.remote_addr
    )
    return "", 204
