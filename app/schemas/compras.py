"""Esquemas de requisiciones, cotizaciones, órdenes y recepciones (M14)."""

from marshmallow import EXCLUDE, Schema, fields, validate

ORIGENES = ("ALERTA", "ORDEN_PRODUCCION", "MANUAL")
PRIORIDADES = ("NORMAL", "URGENTE")


class FiltrosRequisicionSchema(Schema):
    estado = fields.Str(allow_none=True, validate=validate.OneOf(
        ("PENDIENTE", "EN_COTIZACION", "COMPRA_EMITIDA", "ATENDIDA", "CANCELADA")
    ))
    origen = fields.Str(allow_none=True, validate=validate.OneOf(ORIGENES))

    class Meta:
        unknown = EXCLUDE


class FiltrosOrdenSchema(Schema):
    estado = fields.Str(allow_none=True, validate=validate.OneOf(
        ("BORRADOR", "EMITIDA", "PARCIAL", "RECIBIDA", "CANCELADA")
    ))
    proveedor_id = fields.Int(allow_none=True, validate=validate.Range(min=1))

    class Meta:
        unknown = EXCLUDE


class RequisicionLineaCrearSchema(Schema):
    inventario_material_id = fields.Int(required=True, validate=validate.Range(min=1))
    cantidad_base_faltante = fields.Decimal(required=True, validate=validate.Range(min=0))


class RequisicionCrearSchema(Schema):
    origen = fields.Str(load_default="MANUAL", validate=validate.OneOf(ORIGENES))
    orden_produccion_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    prioridad = fields.Str(load_default="NORMAL", validate=validate.OneOf(PRIORIDADES))
    notas = fields.Str(allow_none=True)
    lineas = fields.Nested(RequisicionLineaCrearSchema, many=True, required=True)


class RequisicionActualizarSchema(Schema):
    prioridad = fields.Str(allow_none=True, validate=validate.OneOf(PRIORIDADES))
    notas = fields.Str(allow_none=True)
    orden_produccion_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    lineas = fields.Nested(RequisicionLineaCrearSchema, many=True, allow_none=True)


class CotizacionLineaCrearSchema(Schema):
    requisicion_linea_id = fields.Int(required=True, validate=validate.Range(min=1))
    cantidad_compra = fields.Decimal(required=True, validate=validate.Range(min=0))
    precio_unitario_compra = fields.Decimal(required=True, validate=validate.Range(min=0))


class CotizacionCrearSchema(Schema):
    proveedor_id = fields.Int(required=True, validate=validate.Range(min=1))
    plazo_dias = fields.Int(required=True, validate=validate.Range(min=0))
    vigencia_hasta = fields.Date(allow_none=True)
    notas = fields.Str(allow_none=True)
    lineas = fields.Nested(CotizacionLineaCrearSchema, many=True, required=True)


class OrdenCompraLineaCrearSchema(Schema):
    inventario_material_id = fields.Int(required=True, validate=validate.Range(min=1))
    cantidad_compra = fields.Decimal(required=True, validate=validate.Range(min=0))
    precio_unitario_compra = fields.Decimal(required=True, validate=validate.Range(min=0))


class OrdenCompraCrearSchema(Schema):
    proveedor_id = fields.Int(required=True, validate=validate.Range(min=1))
    requisicion_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    condiciones_pago = fields.Str(allow_none=True, validate=validate.Length(max=200))
    notas = fields.Str(allow_none=True)
    lineas = fields.Nested(OrdenCompraLineaCrearSchema, many=True, required=True)


class OrdenCompraActualizarSchema(Schema):
    proveedor_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    condiciones_pago = fields.Str(allow_none=True, validate=validate.Length(max=200))
    notas = fields.Str(allow_none=True)
    fecha_prometida = fields.Date(allow_none=True)
    lineas = fields.Nested(OrdenCompraLineaCrearSchema, many=True, allow_none=True)


class RecepcionLineaCrearSchema(Schema):
    orden_compra_linea_id = fields.Int(required=True, validate=validate.Range(min=1))
    cantidad_base_medida = fields.Decimal(required=True, validate=validate.Range(min=0))
    cantidad_base_aceptada = fields.Decimal(required=True, validate=validate.Range(min=0))
    cantidad_base_rechazada = fields.Decimal(load_default=0, validate=validate.Range(min=0))
    peso_kg = fields.Decimal(allow_none=True, validate=validate.Range(min=0))
    ancho_cm = fields.Decimal(allow_none=True, validate=validate.Range(min=0))
    largo_m = fields.Decimal(allow_none=True, validate=validate.Range(min=0))
    motivo_rechazo = fields.Str(allow_none=True)


class RecepcionCrearSchema(Schema):
    orden_compra_id = fields.Int(required=True, validate=validate.Range(min=1))
    documento_proveedor = fields.Str(allow_none=True, validate=validate.Length(max=60))
    notas = fields.Str(allow_none=True)
    lineas = fields.Nested(RecepcionLineaCrearSchema, many=True, required=True)
