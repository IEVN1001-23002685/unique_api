"""Esquemas de consulta y seguimiento de pedidos del cliente (M06)."""

from marshmallow import Schema, fields, validate

ESTADOS_FILTRO = ["TODOS", "EN_PROCESO", "ENVIADOS", "ENTREGADOS"]


class PedidoFiltrosSchema(Schema):
    estado = fields.Str(load_default="TODOS", validate=validate.OneOf(ESTADOS_FILTRO))


class PedidoLineaSchema(Schema):
    id = fields.Int()
    sku = fields.Str()
    nombre_producto = fields.Str()
    talla = fields.Str()
    color = fields.Str()
    cantidad = fields.Int()
    cant_reservada = fields.Int()
    cant_pendiente = fields.Int()
    precio_unitario = fields.Decimal(as_string=True, places=2)
    subtotal = fields.Decimal(as_string=True, places=2)


class PedidoEventoSchema(Schema):
    estado = fields.Str()
    descripcion = fields.Str()
    fecha = fields.DateTime(format="iso")
    visible_cliente = fields.Bool()


class PedidoListaSchema(Schema):
    id = fields.Int()
    folio = fields.Str()
    fecha = fields.DateTime(format="iso")
    estado = fields.Str()
    total = fields.Decimal(as_string=True, places=2)
    articulos = fields.Int()
    guia = fields.Str(allow_none=True)


class PedidoDetalleSchema(Schema):
    id = fields.Int()
    folio = fields.Str()
    fecha = fields.DateTime(format="iso")
    estado = fields.Str()
    estado_desde = fields.DateTime(format="iso")
    fecha_promesa = fields.Date(allow_none=True)
    prioridad = fields.Str()
    estado_pago = fields.Str()
    subtotal = fields.Decimal(as_string=True, places=2)
    descuento_monto = fields.Decimal(as_string=True, places=2)
    costo_envio = fields.Decimal(as_string=True, places=2)
    total = fields.Decimal(as_string=True, places=2)
    direccion = fields.Dict(allow_none=True)
    articulos = fields.Nested(PedidoLineaSchema, many=True)
    eventos = fields.Nested(PedidoEventoSchema, many=True)
    guia = fields.Str(allow_none=True)
    repartidor = fields.Dict(allow_none=True)


class CancelarPedidoSchema(Schema):
    motivo = fields.Str(required=True, validate=validate.Length(min=3, max=300))


class ComprobanteSchema(Schema):
    folio = fields.Str()
    fecha = fields.DateTime(format="iso")
    estado_pago = fields.Str()
    cliente = fields.Dict()
    direccion = fields.Dict(allow_none=True)
    lineas = fields.Nested(PedidoLineaSchema, many=True)
    subtotal = fields.Decimal(as_string=True, places=2)
    descuento_monto = fields.Decimal(as_string=True, places=2)
    costo_envio = fields.Decimal(as_string=True, places=2)
    total = fields.Decimal(as_string=True, places=2)
