"""Esquemas de pedidos del cliente (M06) y administración (M09)."""

from marshmallow import EXCLUDE, Schema, fields, validate

ESTADOS_FILTRO = ["TODOS", "EN_PROCESO", "ENVIADOS", "ENTREGADOS"]
ESTADOS_ADMIN = ESTADOS_FILTRO + [
    "RECIBIDO",
    "CONFIRMADO",
    "EN_PRODUCCION",
    "EN_PREPARACION",
    "LISTO_ENVIO",
    "EN_REPARTO",
    "ENTREGADO",
    "CANCELADO",
]
SEMAFOROS = ["VERDE", "AMBAR", "ROJO"]


class PedidoAdminFiltrosSchema(Schema):
    estado = fields.Str(validate=validate.OneOf(ESTADOS_ADMIN))
    prioridad = fields.Str(validate=validate.OneOf(["NORMAL", "ALTA"]))
    desde = fields.DateTime(format="iso", allow_none=True)
    hasta = fields.DateTime(format="iso", allow_none=True)
    q = fields.Str(validate=validate.Length(max=120))

    class Meta:
        unknown = EXCLUDE


class PendienteProduccionFiltrosSchema(Schema):
    semaforo = fields.Str(validate=validate.OneOf(SEMAFOROS))
    sku = fields.Str(validate=validate.Length(max=12))

    class Meta:
        unknown = EXCLUDE


class PedidoAdminListaSchema(Schema):
    id = fields.Int()
    folio = fields.Str()
    cliente = fields.Dict()
    estado = fields.Str()
    estado_desde = fields.DateTime(format="iso")
    prioridad = fields.Str()
    semaforo = fields.Str(allow_none=True)
    articulos = fields.Int()
    total = fields.Decimal(as_string=True, places=2)
    guia = fields.Str(allow_none=True)


class PedidoAdminActualizarSchema(Schema):
    prioridad = fields.Str(validate=validate.OneOf(["NORMAL", "ALTA"]))
    nota = fields.Str(validate=validate.Length(min=1, max=500))


class PedidoFiltrosSchema(Schema):
    estado = fields.Str(load_default="TODOS", validate=validate.OneOf(ESTADOS_FILTRO))


class PedidoLineaSchema(Schema):
    id = fields.Int()
    venta_linea_id = fields.Int()
    variante_id = fields.Int()
    producto_id = fields.Int()
    sku = fields.Str()
    nombre_producto = fields.Str()
    talla = fields.Str()
    color = fields.Str()
    cantidad = fields.Int()
    cant_reservada = fields.Int()
    cant_pendiente = fields.Int()
    precio_unitario = fields.Decimal(as_string=True, places=2)
    subtotal = fields.Decimal(as_string=True, places=2)
    imagen = fields.Str(allow_none=True)


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
    imagen = fields.Str(allow_none=True)
    fecha_estimada = fields.Date(allow_none=True)
    fecha_entrega = fields.DateTime(format="iso", allow_none=True)


class PedidoDetalleSchema(Schema):
    id = fields.Int()
    folio = fields.Str()
    fecha = fields.DateTime(format="iso")
    estado = fields.Str()
    estado_desde = fields.DateTime(format="iso")
    fecha_promesa = fields.Date(allow_none=True)
    fecha_estimada = fields.Date(allow_none=True)
    fecha_entrega = fields.DateTime(format="iso", allow_none=True)
    total_articulos = fields.Int()
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


class PedidoAdminDetalleSchema(PedidoDetalleSchema):
    venta_id = fields.Int()
    cliente = fields.Dict()
    canal = fields.Str()
    semaforo = fields.Str(allow_none=True)
    ordenes = fields.List(fields.Dict())
    preparacion = fields.Dict(allow_none=True)
    entrega = fields.Dict(allow_none=True)


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
