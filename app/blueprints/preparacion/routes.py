"""Endpoints de preparación, verificación y empaque (M18)."""

from flask import Blueprint, Response, jsonify, request
from marshmallow import ValidationError

from app.schemas import (
    EtiquetaSchema,
    PreparacionFiltrosSchema,
    PreparacionIncidenciaSchema,
    PreparacionLineasActualizarSchema,
    PreparacionSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import preparacion_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.pdf import generar_pdf
from app.utils.validacion import cuerpo

preparacion_bp = Blueprint("preparacion", __name__, url_prefix="/api/v1")


def _filtros():
    try:
        return PreparacionFiltrosSchema().load(request.args)
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


@preparacion_bp.get("/preparacion/cola")
@roles_requeridos("OPERATIVO")
def cola_preparacion():
    pagina, por_pagina = parametros_paginacion()
    resultado = preparacion_service.cola(_filtros(), pagina, por_pagina)
    resultado["items"] = PreparacionSchema(many=True).dump(resultado["items"])
    return jsonify(resultado)


@preparacion_bp.post("/preparacion/<int:pedido_id>/tomar")
@roles_requeridos("OPERATIVO")
def tomar_preparacion(pedido_id):
    resultado = preparacion_service.tomar_pedido(pedido_id, usuario_actual().id)
    return jsonify(PreparacionSchema().dump(resultado))


@preparacion_bp.patch("/preparacion/<int:preparacion_id>/lineas")
@roles_requeridos("OPERATIVO")
def actualizar_lineas(preparacion_id):
    datos = cuerpo(PreparacionLineasActualizarSchema())
    resultado = preparacion_service.actualizar_lineas(
        preparacion_id, datos, usuario_actual().id
    )
    return jsonify(PreparacionSchema().dump(resultado))


@preparacion_bp.post("/preparacion/<int:preparacion_id>/incidencia")
@roles_requeridos("OPERATIVO")
def incidencia_preparacion(preparacion_id):
    datos = cuerpo(PreparacionIncidenciaSchema())
    resultado = preparacion_service.registrar_incidencia(
        preparacion_id, datos, usuario_actual().id, _ip()
    )
    return jsonify(PreparacionSchema().dump(resultado)), 201


@preparacion_bp.post("/preparacion/<int:preparacion_id>/empacar")
@roles_requeridos("OPERATIVO")
def empacar_preparacion(preparacion_id):
    resultado = preparacion_service.marcar_empaque(
        preparacion_id, usuario_actual().id
    )
    return jsonify(PreparacionSchema().dump(resultado))


@preparacion_bp.get("/preparacion/<int:preparacion_id>/etiqueta")
@roles_requeridos("OPERATIVO")
def etiqueta_preparacion(preparacion_id):
    datos = EtiquetaSchema().dump(preparacion_service.etiqueta(preparacion_id))
    lineas = [
        f"UNIQUE · Etiqueta de envío",
        f"Folio: {datos['folio']}",
        f"Destinatario: {datos['destinatario'] or ''}",
        f"Dirección: {datos['direccion'] or ''}",
        f"CP: {datos['codigo_postal'] or ''}",
        f"Teléfono: {datos['telefono'] or ''}",
        f"QR: {datos['qr']}",
    ]
    contenido, nombre = generar_pdf(lineas, f"etiqueta-{datos['folio']}.pdf")
    return Response(
        contenido,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )
