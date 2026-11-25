"""Esquemas de alertas y reglas configurables (M21)."""

from marshmallow import Schema, fields, validate

from app.services.alertas_service import REGLAS, TIPOS

ESTADOS = ["ABIERTA", "ATENDIDA", "RESUELTA_AUTO"]
SEVERIDADES = ["INFORMATIVA", "PREVENTIVA", "CRITICA"]
ACCIONES = ["ATENDER", "GENERAR_PRODUCCION", "GENERAR_REQUISICION", "EVALUAR_PROVEEDOR"]


class AlertaFiltrosSchema(Schema):
    estado = fields.Str(allow_none=True, validate=validate.OneOf(ESTADOS))
    tipo = fields.Str(allow_none=True, validate=validate.OneOf(TIPOS))
    severidad = fields.Str(allow_none=True, validate=validate.OneOf(SEVERIDADES))


class AlertaSchema(Schema):
    id = fields.Int()
    tipo = fields.Str()
    severidad = fields.Str()
    titulo = fields.Str()
    detalle = fields.Str()
    entidad_tipo = fields.Str()
    entidad_id = fields.Int()
    rol_destino = fields.Str()
    accion_sugerida = fields.Str(allow_none=True)
    estado = fields.Str()
    clave_unica = fields.Str(allow_none=True)
    atendida_por = fields.Int(allow_none=True)
    atendida_en = fields.Str(allow_none=True)
    creado_en = fields.Str(allow_none=True)


class AlertaAccionSchema(Schema):
    accion = fields.Str(load_default="ATENDER", validate=validate.OneOf(ACCIONES))
    nota = fields.Str(allow_none=True, validate=validate.Length(max=500))


class ReglaSchema(Schema):
    clave = fields.Str()
    valor = fields.Str(allow_none=True)
    descripcion = fields.Str(allow_none=True)


class ReglaActualizarSchema(Schema):
    clave = fields.Str(required=True, validate=validate.OneOf(sorted(REGLAS)))
    valor = fields.Str(
        required=True,
        validate=validate.Regexp(r"^\d+(\.\d+)?$", error="La regla debe ser numérica"),
    )


class ReglasActualizarSchema(Schema):
    reglas = fields.Nested(ReglaActualizarSchema, many=True, required=True)
