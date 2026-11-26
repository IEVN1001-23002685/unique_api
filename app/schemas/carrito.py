"""Esquemas del carrito del servidor (M04)."""

from marshmallow import Schema, fields, validate


class CarritoLineaCrearSchema(Schema):
    variante_id = fields.Int(required=True, validate=validate.Range(min=1))
    cantidad = fields.Int(required=True, validate=validate.Range(min=1))


class CarritoFusionarSchema(Schema):
    lineas = fields.List(
        fields.Nested(CarritoLineaCrearSchema), required=True, validate=validate.Length(min=1)
    )


class CarritoLineaSchema(Schema):
    id = fields.Int()
    variante_id = fields.Int()
    sku = fields.Str()
    nombre_producto = fields.Str()
    talla = fields.Str()
    color = fields.Str()
    precio_unitario = fields.Decimal(as_string=True, places=2)
    cantidad = fields.Int()
    subtotal = fields.Decimal(as_string=True, places=2)
    disponibilidad = fields.Str()
    bajo_pedido = fields.Bool()
    fecha_estimada = fields.Date(allow_none=True)
    activa = fields.Bool()
    comprable = fields.Bool()
    imagen = fields.Str(allow_none=True)


class CarritoSchema(Schema):
    items = fields.Nested(CarritoLineaSchema, many=True)
    subtotal = fields.Decimal(as_string=True, places=2)
    total_articulos = fields.Int()
    max_piezas_por_linea = fields.Int()
    puede_pagar = fields.Bool()
