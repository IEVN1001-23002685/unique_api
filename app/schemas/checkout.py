"""Esquemas de cotización, descuentos y pago simulado (M05)."""

from marshmallow import Schema, fields, validate

from app.schemas.cuenta import DireccionCrearSchema

METODOS_PAGO = ["TARJETA", "CUENTA"]


class CotizarSchema(Schema):
    direccion_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    codigo_postal = fields.Str(allow_none=True, validate=validate.Regexp(r"^\d{5}$"))
    descuento_codigo = fields.Str(allow_none=True, validate=validate.Length(max=20))
    requiere_factura = fields.Bool(load_default=False)
    rfc = fields.Str(allow_none=True, validate=validate.Length(max=13))
    razon_social = fields.Str(allow_none=True, validate=validate.Length(max=120))
    cp_fiscal = fields.Str(allow_none=True, validate=validate.Regexp(r"^\d{5}$"))


class DescuentoAplicarSchema(Schema):
    codigo = fields.Str(required=True, validate=validate.Length(min=1, max=20))


class PagarSchema(Schema):
    direccion_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    direccion = fields.Nested(DireccionCrearSchema, allow_none=True)
    medio_pago_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    metodo_pago = fields.Str(required=True, validate=validate.OneOf(METODOS_PAGO))
    numero_tarjeta = fields.Str(allow_none=True, validate=validate.Regexp(r"^\d{16}$"))
    titular = fields.Str(allow_none=True, validate=validate.Length(max=100))
    vence_mes = fields.Int(allow_none=True, validate=validate.Range(min=1, max=12))
    vence_anio = fields.Int(allow_none=True, validate=validate.Range(min=2000, max=2200))
    cvv = fields.Str(allow_none=True, validate=validate.Regexp(r"^\d{3,4}$"))
    descuento_codigo = fields.Str(allow_none=True, validate=validate.Length(max=20))
    requiere_factura = fields.Bool(load_default=False)
    rfc = fields.Str(allow_none=True, validate=validate.Length(max=13))
    razon_social = fields.Str(allow_none=True, validate=validate.Length(max=120))
    cp_fiscal = fields.Str(allow_none=True, validate=validate.Regexp(r"^\d{5}$"))
    notas = fields.Str(allow_none=True)


class ResumenCheckoutSchema(Schema):
    subtotal = fields.Decimal(as_string=True, places=2)
    descuento_monto = fields.Decimal(as_string=True, places=2)
    costo_envio = fields.Decimal(as_string=True, places=2)
    iva_importe = fields.Decimal(as_string=True, places=2)
    total = fields.Decimal(as_string=True, places=2)
    monto_articulos = fields.Int()
    descuento = fields.Dict(allow_none=True)
    tarifa = fields.Dict(allow_none=True)
    lineas = fields.List(fields.Dict())
    fecha_promesa = fields.Str(allow_none=True)


class VentaResumenSchema(Schema):
    id = fields.Int()
    folio = fields.Str()
    estado = fields.Str()
    estado_pago = fields.Str()
    total = fields.Decimal(as_string=True, places=2)


class PedidoResumenSchema(Schema):
    id = fields.Int()
    folio = fields.Str()
    estado = fields.Str()


class CheckoutResponseSchema(Schema):
    venta = fields.Nested(VentaResumenSchema)
    pedido = fields.Nested(PedidoResumenSchema)
    resumen = fields.Nested(ResumenCheckoutSchema)
