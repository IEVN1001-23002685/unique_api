"""Esquemas de órdenes de producción, revisión y plan sugerido (M16)."""

from marshmallow import EXCLUDE, Schema, fields, validate

ESTADOS_ORDEN = (
    "PLANEADA",
    "LISTA",
    "EN_PROCESO",
    "EN_REVISION",
    "CERRADA",
    "CANCELADA",
)


class OrdenFiltrosSchema(Schema):
    estado = fields.Str(allow_none=True, validate=validate.OneOf(ESTADOS_ORDEN))
    semaforo = fields.Str(
        allow_none=True, validate=validate.OneOf(("VERDE", "AMBAR", "ROJO"))
    )
    origen = fields.Str(
        allow_none=True,
        validate=validate.OneOf(("PEDIDO", "STOCK_MINIMO", "MANUAL")),
    )
    q = fields.Str(allow_none=True, validate=validate.Length(max=40))
    desde = fields.Date(allow_none=True)
    hasta = fields.Date(allow_none=True)

    class Meta:
        unknown = EXCLUDE


class OrdenLineaSchema(Schema):
    variante_id = fields.Int(required=True, validate=validate.Range(min=1))
    cantidad = fields.Int(required=True, validate=validate.Range(min=1))


class OrdenCrearSchema(Schema):
    lineas = fields.Nested(OrdenLineaSchema, many=True, required=True)
    fecha_requerida = fields.Date(allow_none=True)
    notas = fields.Str(allow_none=True, validate=validate.Length(max=500))


class RevisionLineaSchema(Schema):
    orden_linea_id = fields.Int(required=True, validate=validate.Range(min=1))
    cantidad_revisada = fields.Int(required=True, validate=validate.Range(min=1))
    cantidad_aprobada = fields.Int(required=True, validate=validate.Range(min=0))
    cantidad_reproceso = fields.Int(load_default=0, validate=validate.Range(min=0))
    cantidad_merma = fields.Int(load_default=0, validate=validate.Range(min=0))
    medidas_ok = fields.Bool(required=True)
    costuras_ok = fields.Bool(required=True)
    bordado_ok = fields.Bool(required=True)
    etiquetas_ok = fields.Bool(required=True)
    observaciones = fields.Str(allow_none=True)
    causa_merma_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    etapa_merma = fields.Str(
        allow_none=True,
        validate=validate.OneOf(
            (
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
        ),
    )


class DictamenSchema(Schema):
    lineas = fields.Nested(RevisionLineaSchema, many=True, required=True)


class RevisionSchema(Schema):
    notas = fields.Str(allow_none=True, validate=validate.Length(max=300))


class CancelarOrdenSchema(Schema):
    motivo = fields.Str(required=True, validate=validate.Length(min=3, max=300))
