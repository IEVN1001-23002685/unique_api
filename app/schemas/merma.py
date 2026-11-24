"""Esquemas de registro, reverso e indicadores de mermas (M17)."""

from marshmallow import EXCLUDE, Schema, fields, validate

ETAPAS = (
    "RECEPCION",
    "CORTE",
    "TEJIDO",
    "BORDADO",
    "CONFECCION",
    "ACABADOS",
    "ALMACEN",
    "ENTREGA",
    "DEVOLUCION",
)


class MermaFiltrosSchema(Schema):
    origen = fields.Str(
        allow_none=True, validate=validate.OneOf(("MATERIAL", "PRODUCTO"))
    )
    etapa = fields.Str(allow_none=True, validate=validate.OneOf(ETAPAS))
    causa_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    variante_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    inventario_material_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    orden_produccion_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    desde = fields.DateTime(allow_none=True)
    hasta = fields.DateTime(allow_none=True)

    class Meta:
        unknown = EXCLUDE


class IndicadoresFiltrosSchema(Schema):
    desde = fields.Date(allow_none=True)
    hasta = fields.Date(allow_none=True)
    etapa = fields.Str(allow_none=True, validate=validate.OneOf(ETAPAS))
    causa = fields.Str(allow_none=True)

    class Meta:
        unknown = EXCLUDE


class MermaCrearSchema(Schema):
    origen = fields.Str(
        required=True, validate=validate.OneOf(("MATERIAL", "PRODUCTO"))
    )
    inventario_material_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    lote_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    variante_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    orden_produccion_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    etapa = fields.Str(required=True, validate=validate.OneOf(ETAPAS))
    causa_id = fields.Int(required=True, validate=validate.Range(min=1))
    cantidad = fields.Decimal(required=True, validate=validate.Range(min=0))
    descripcion = fields.Str(allow_none=True, validate=validate.Length(max=500))
    evidencia_url = fields.Str(allow_none=True, validate=validate.Length(max=500))


class MermaReversarSchema(Schema):
    motivo = fields.Str(required=True, validate=validate.Length(min=3, max=300))
    evidencia_url = fields.Str(allow_none=True, validate=validate.Length(max=500))
