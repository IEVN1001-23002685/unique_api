"""Endpoints de entregas, hojas de reparto y repartidores (M19)."""

from flask import Blueprint, Response, jsonify, request
from marshmallow import ValidationError

from app.schemas import (
    EntregaCrearSchema,
    EntregaFiltrosSchema,
    EntregaResultadoSchema,
    EntregaSchema,
    HojaRepartoSchema,
    PorAsignarFiltrosSchema,
    RepartidorActualizarSchema,
    RepartidorCrearSchema,
    RepartidorFiltrosSchema,
    RepartidorSchema,
    RepartidosFiltrosSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import entrega_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.pdf import generar_pdf
from app.utils.validacion import cuerpo

entregas_bp = Blueprint("entregas", __name__, url_prefix="/api/v1")


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


def _ip():
    return request.remote_addr


@entregas_bp.get("/entregas/por-asignar")
@roles_requeridos("OPERATIVO")
def por_asignar():
    pagina, por_pagina = parametros_paginacion()
    return jsonify(
        entrega_service.por_asignar(
            _filtros(PorAsignarFiltrosSchema()), pagina, por_pagina
        )
    )


@entregas_bp.get("/entregas/hoja-reparto")
@roles_requeridos("OPERATIVO")
def hoja_reparto():
    datos = _filtros(HojaRepartoSchema())
    resultado = entrega_service.hoja_reparto(
        datos["repartidor"], datos["fecha"], datos["pagina"], datos["por_pagina"]
    )
    lineas = [
        "UNIQUE · Hoja de reparto",
        f"Repartidor: {datos['repartidor']}",
        f"Fecha: {datos['fecha'].isoformat()}",
        f"Entregas programadas: {resultado['total']}",
    ]
    for entrega in resultado["items"]:
        lineas.append(f"{entrega['folio']} · {entrega['destinatario'] or ''}")
        lineas.append(f"  {entrega['direccion'] or ''}")
        for linea in entrega["lineas"]:
            lineas.append(
                f"  {linea['sku']} · {linea['nombre_producto']} x{linea['cantidad']}"
            )
    contenido, nombre = generar_pdf(
        lineas, f"hoja-reparto-{datos['fecha'].isoformat()}.pdf", tamano=9
    )
    return Response(
        contenido,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


@entregas_bp.get("/entregas/productos-repartidos")
@roles_requeridos("OPERATIVO")
def productos_repartidos():
    filtros = _filtros(RepartidosFiltrosSchema())
    if "repartidor" in filtros:
        filtros["repartidor_id"] = filtros.pop("repartidor")
    pagina, por_pagina = parametros_paginacion()
    return jsonify(
        entrega_service.productos_repartidos(filtros, pagina, por_pagina)
    )


@entregas_bp.get("/entregas")
@roles_requeridos("OPERATIVO")
def listar_entregas():
    filtros = _filtros(EntregaFiltrosSchema())
    pagina, por_pagina = parametros_paginacion()
    return jsonify(entrega_service.listar(filtros, pagina, por_pagina))


@entregas_bp.post("/entregas")
@roles_requeridos("OPERATIVO")
def asignar_entrega():
    datos = cuerpo(EntregaCrearSchema())
    resultado = entrega_service.asignar(datos, usuario_actual().id)
    return jsonify(EntregaSchema().dump(resultado)), 201


@entregas_bp.post("/entregas/<int:entrega_id>/salida")
@roles_requeridos("OPERATIVO")
def confirmar_salida(entrega_id):
    resultado = entrega_service.confirmar_salida(entrega_id, usuario_actual().id)
    return jsonify(EntregaSchema().dump(resultado))


@entregas_bp.post("/entregas/<int:entrega_id>/resultado")
@roles_requeridos("OPERATIVO")
def registrar_resultado(entrega_id):
    datos = cuerpo(EntregaResultadoSchema())
    resultado = entrega_service.registrar_resultado(
        entrega_id, datos, usuario_actual().id, _ip()
    )
    return jsonify(EntregaSchema().dump(resultado))


@entregas_bp.get("/repartidores")
@roles_requeridos("ADMIN")
def listar_repartidores():
    pagina, por_pagina = parametros_paginacion()
    resultado = entrega_service.listar_repartidores(
        _filtros(RepartidorFiltrosSchema()), pagina, por_pagina
    )
    resultado["items"] = RepartidorSchema(many=True).dump(resultado["items"])
    return jsonify(resultado)


@entregas_bp.post("/repartidores")
@roles_requeridos("ADMIN")
def crear_repartidor():
    datos = cuerpo(RepartidorCrearSchema())
    resultado = entrega_service.crear_repartidor(datos, usuario_actual().id, _ip())
    return jsonify(RepartidorSchema().dump(resultado)), 201


@entregas_bp.patch("/repartidores/<int:repartidor_id>")
@roles_requeridos("ADMIN")
def actualizar_repartidor(repartidor_id):
    datos = cuerpo(RepartidorActualizarSchema(), parcial=True)
    if not datos:
        raise ApiError("VALIDACION", "Se requiere al menos un campo", 400)
    resultado = entrega_service.actualizar_repartidor(
        repartidor_id, datos, usuario_actual().id, _ip()
    )
    return jsonify(RepartidorSchema().dump(resultado))


@entregas_bp.delete("/repartidores/<int:repartidor_id>")
@roles_requeridos("ADMIN")
def desactivar_repartidor(repartidor_id):
    entrega_service.desactivar_repartidor(
        repartidor_id, usuario_actual().id, _ip()
    )
    return "", 204
