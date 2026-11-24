"""Endpoints de registro, reverso e indicadores de mermas (M17)."""

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.schemas import (
    IndicadoresFiltrosSchema,
    MermaCrearSchema,
    MermaFiltrosSchema,
    MermaReversarSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import merma_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.validacion import cuerpo

mermas_bp = Blueprint("mermas", __name__, url_prefix="/api/v1")


def _filtros(schema):
    pagina, por_pagina = parametros_paginacion()
    try:
        datos = schema.load(request.args)
    except ValidationError as error:
        raise ApiError(
            "VALIDACION",
            "Parámetros inválidos",
            400,
            [
                {"campo": campo, "mensaje": str(mensaje)}
                for campo, mensaje in error.messages.items()
            ],
        )
    datos["pagina"] = pagina
    datos["por_pagina"] = por_pagina
    return datos


def _con_costos():
    from app.security import tiene_rol

    return tiene_rol("ADMIN")


@mermas_bp.get("/mermas/indicadores")
@roles_requeridos("ADMIN")
def indicadores():
    filtros = _filtros(IndicadoresFiltrosSchema())
    return jsonify(merma_service.indicadores(filtros))


@mermas_bp.get("/mermas")
@roles_requeridos("OPERATIVO")
def listar_mermas():
    filtros = _filtros(MermaFiltrosSchema())
    return jsonify(
        merma_service.listar(filtros, incluir_costos=_con_costos())
    )


@mermas_bp.post("/mermas")
@roles_requeridos("OPERATIVO")
def crear_merma():
    datos = cuerpo(MermaCrearSchema())
    merma = merma_service.registrar_merma(
        datos, usuario_actual().id, request.remote_addr
    )
    return jsonify(
        merma_service.serializar(merma, incluir_costos=_con_costos())
    ), 201


@mermas_bp.get("/mermas/<int:merma_id>")
@roles_requeridos("OPERATIVO")
def detalle_merma(merma_id):
    return jsonify(merma_service.obtener(merma_id, incluir_costos=_con_costos()))


@mermas_bp.post("/mermas/<int:merma_id>/reversar")
@roles_requeridos("ADMIN")
def reversar_merma(merma_id):
    datos = cuerpo(MermaReversarSchema())
    return jsonify(
        merma_service.reversar(
            merma_id, datos, usuario_actual().id, request.remote_addr
        )
    )
