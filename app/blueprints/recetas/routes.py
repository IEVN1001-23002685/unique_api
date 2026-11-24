"""Endpoints de recetas, costeo y diseños de bordado (M11)."""

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError

from app.schemas.receta import (
    CosteoFilaSchema,
    DisenoActualizarSchema,
    DisenoCrearSchema,
    DisenoFiltrosSchema,
    DisenoSchema,
    RecetaActualizarSchema,
    RecetaCopiarSchema,
    RecetaCrearSchema,
    RecetaDetalleSchema,
    RecetaFiltrosSchema,
    RecetaLineaCrearSchema,
    RecetaListaSchema,
    RecetaOperativoSchema,
    RecetaPrevisualizarSchema,
    RecetaPreviewSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import diseno_service, receta_service
from app.utils.errores import ApiError
from app.utils.validacion import cuerpo

recetas_bp = Blueprint("recetas", __name__, url_prefix="/api/v1")


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


def _es_admin() -> bool:
    return usuario_actual().rol.codigo == "ADMIN"


@recetas_bp.get("/recetas")
@roles_requeridos("O")
def listar_recetas():
    filtros = _parametros(RecetaFiltrosSchema())
    admin = _es_admin()
    recetas = receta_service.listar(filtros, incluir_costos=admin)
    esquema = RecetaListaSchema(many=True) if admin else RecetaOperativoSchema(many=True)
    return jsonify(esquema.dump(recetas))


@recetas_bp.get("/recetas/costeo")
@roles_requeridos("A")
def costeo():
    return jsonify(CosteoFilaSchema(many=True).dump(receta_service.costeo()))


@recetas_bp.post("/recetas/previsualizar")
@roles_requeridos("A")
def previsualizar():
    datos = cuerpo(RecetaPrevisualizarSchema())
    return jsonify(
        RecetaPreviewSchema().dump(receta_service.previsualizar(datos, usuario_actual().id))
    )


@recetas_bp.post("/recetas")
@roles_requeridos("A")
def crear_receta():
    datos = cuerpo(RecetaCrearSchema())
    receta = receta_service.crear(datos, usuario_actual().id)
    return jsonify(RecetaDetalleSchema().dump(receta)), 201


@recetas_bp.get("/recetas/<int:receta_id>")
@roles_requeridos("O")
def obtener_receta(receta_id):
    admin = _es_admin()
    receta = receta_service.obtener(receta_id, incluir_costos=admin)
    esquema = RecetaDetalleSchema() if admin else RecetaOperativoSchema()
    return jsonify(esquema.dump(receta))


@recetas_bp.patch("/recetas/<int:receta_id>")
@roles_requeridos("A")
def actualizar_receta(receta_id):
    datos = cuerpo(RecetaActualizarSchema(), parcial=True)
    if not datos:
        raise ApiError("VALIDACION", "Se requiere al menos un campo", 400)
    receta = receta_service.actualizar(receta_id, datos, usuario_actual().id)
    return jsonify(RecetaDetalleSchema().dump(receta))


@recetas_bp.post("/recetas/<int:receta_id>/lineas")
@roles_requeridos("A")
def agregar_linea(receta_id):
    datos = cuerpo(RecetaLineaCrearSchema())
    receta = receta_service.agregar_linea(receta_id, datos, usuario_actual().id)
    return jsonify(RecetaDetalleSchema().dump(receta)), 201


@recetas_bp.post("/recetas/<int:receta_id>/copiar")
@roles_requeridos("A")
def copiar_receta(receta_id):
    datos = cuerpo(RecetaCopiarSchema(), parcial=True)
    receta = receta_service.copiar(receta_id, datos, usuario_actual().id)
    return jsonify(RecetaDetalleSchema().dump(receta)), 201


@recetas_bp.post("/recetas/<int:receta_id>/activar")
@roles_requeridos("A")
def activar_receta(receta_id):
    receta = receta_service.activar(
        receta_id, usuario_actual().id, ip=request.remote_addr
    )
    return jsonify(RecetaDetalleSchema().dump(receta))


@recetas_bp.get("/disenos")
@roles_requeridos("A")
def listar_disenos():
    filtros = _parametros(DisenoFiltrosSchema())
    return jsonify(DisenoSchema(many=True).dump(diseno_service.listar(filtros)))


@recetas_bp.post("/disenos")
@roles_requeridos("A")
def crear_diseno():
    datos = cuerpo(DisenoCrearSchema())
    diseno = diseno_service.crear(datos, usuario_actual().id, ip=request.remote_addr)
    return jsonify(DisenoSchema().dump(diseno)), 201


@recetas_bp.get("/disenos/<int:diseno_id>")
@roles_requeridos("A")
def obtener_diseno(diseno_id):
    return jsonify(DisenoSchema().dump(diseno_service.obtener(diseno_id)))


@recetas_bp.patch("/disenos/<int:diseno_id>")
@roles_requeridos("A")
def actualizar_diseno(diseno_id):
    datos = cuerpo(DisenoActualizarSchema(), parcial=True)
    if not datos:
        raise ApiError("VALIDACION", "Se requiere al menos un campo", 400)
    diseno = diseno_service.actualizar(
        diseno_id, datos, usuario_actual().id, ip=request.remote_addr
    )
    return jsonify(DisenoSchema().dump(diseno))


@recetas_bp.delete("/disenos/<int:diseno_id>")
@roles_requeridos("A")
def desactivar_diseno(diseno_id):
    diseno_service.desactivar(diseno_id, usuario_actual().id, ip=request.remote_addr)
    return "", 204
