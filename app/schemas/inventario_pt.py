"""Esquemas de inventario de producto terminado y reglas de reposición (M12)."""

from marshmallow import EXCLUDE, Schema, fields, validate

TIPOS_MOVIMIENTO = (
    "PRODUCCION",
    "RESERVA",
    "LIBERA_RESERVA",
    "SALIDA_ENVIO",
    "REINGRESO",
    "MERMA",
    "AJUSTE",
)


class InventarioFiltrosSchema(Schema):
    categoria = fields.Str(allow_none=True)
    sku = fields.Str(allow_none=True, validate=validate.Length(max=12))
    color = fields.Str(allow_none=True, validate=validate.Length(equal=2))
    talla = fields.Str(allow_none=True, validate=validate.Length(equal=2))
    semaforo = fields.Str(
        allow_none=True, validate=validate.OneOf(("ROJO", "AMBAR", "VERDE"))
    )

    class Meta:
        unknown = EXCLUDE


class MovimientosFiltrosSchema(Schema):
    sku = fields.Str(allow_none=True, validate=validate.Length(max=12))
    tipo = fields.Str(allow_none=True, validate=validate.OneOf(TIPOS_MOVIMIENTO))
    documento_tipo = fields.Str(allow_none=True, validate=validate.Length(max=30))
    desde = fields.Date(allow_none=True)
    hasta = fields.Date(allow_none=True)

    class Meta:
        unknown = EXCLUDE


class AjusteSchema(Schema):
    variante_id = fields.Int(required=True, validate=validate.Range(min=1))
    cantidad_contada = fields.Int(required=True, validate=validate.Range(min=0))
    diferencia = fields.Int(allow_none=True)
    motivo = fields.Str(required=True, validate=validate.Length(min=3, max=300))


class ReglasActualizarSchema(Schema):
    stock_minimo = fields.Int(allow_none=True, validate=validate.Range(min=0))
    cantidad_reposicion = fields.Int(allow_none=True, validate=validate.Range(min=0))


class InventarioItemSchema(Schema):
    variante_id = fields.Int()
    sku = fields.Str()
    producto = fields.Str()
    categoria = fields.Str()
    talla = fields.Str()
    color = fields.Str()
    existencia = fields.Int()
    reservado = fields.Int()
    disponible = fields.Int()
    stock_minimo = fields.Int()
    cantidad_reposicion = fields.Int()
    en_produccion = fields.Int()
    ventas_30d = fields.Int()
    dias_cobertura = fields.Decimal(as_string=True, places=2, allow_none=True)
    semaforo = fields.Str()


class MovimientoProductoSchema(Schema):
    id = fields.Int()
    variante_id = fields.Int()
    sku = fields.Str()
    tipo = fields.Str()
    delta_existencia = fields.Int()
    delta_reservado = fields.Int()
    documento_tipo = fields.Str()
    documento_id = fields.Int()
    motivo = fields.Str(allow_none=True)
    usuario_id = fields.Int()
    fecha = fields.DateTime(format="iso")


class AjusteResponseSchema(Schema):
    variante_id = fields.Int()
    sku = fields.Str()
    existencia_anterior = fields.Int()
    cantidad_contada = fields.Int()
    diferencia = fields.Int()
    existencia_actual = fields.Int()
    disponible = fields.Int()
    semaforo = fields.Str()
    alerta_id = fields.Int(allow_none=True)
    orden_produccion_id = fields.Int(allow_none=True)
    orden_produccion_folio = fields.Str(allow_none=True)


class ReglasResponseSchema(Schema):
    variante_id = fields.Int()
    sku = fields.Str(allow_none=True)
    stock_minimo = fields.Int()
    cantidad_reposicion = fields.Int()
