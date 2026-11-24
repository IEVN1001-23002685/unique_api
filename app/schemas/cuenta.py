"""Esquemas de direcciones, medios de pago y cobertura (M02)."""

from marshmallow import Schema, fields, validate

TIPOS_DIRECCION = ["ENVIO", "FACTURACION"]
TIPOS_MEDIO_PAGO = ["TARJETA", "CUENTA"]


class DireccionCrearSchema(Schema):
    tipo = fields.Str(required=True, validate=validate.OneOf(TIPOS_DIRECCION))
    alias = fields.Str(required=True, validate=validate.Length(min=1, max=40))
    destinatario = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    telefono = fields.Str(required=True, validate=validate.Regexp(r"^\d{10}$"))
    calle = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    numero_ext = fields.Str(required=True, validate=validate.Length(min=1, max=10))
    numero_int = fields.Str(allow_none=True, validate=validate.Length(max=10))
    colonia = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    municipio = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    estado = fields.Str(required=True, validate=validate.Length(min=1, max=60))
    codigo_postal = fields.Str(required=True, validate=validate.Regexp(r"^\d{5}$"))
    referencia = fields.Str(allow_none=True)
    rfc = fields.Str(allow_none=True, validate=validate.Length(min=12, max=13))
    razon_social = fields.Str(allow_none=True, validate=validate.Length(max=120))
    predeterminada = fields.Bool(load_default=False)


class DireccionActualizarSchema(Schema):
    tipo = fields.Str(validate=validate.OneOf(TIPOS_DIRECCION))
    alias = fields.Str(validate=validate.Length(min=1, max=40))
    destinatario = fields.Str(validate=validate.Length(min=1, max=100))
    telefono = fields.Str(validate=validate.Regexp(r"^\d{10}$"))
    calle = fields.Str(validate=validate.Length(min=1, max=120))
    numero_ext = fields.Str(validate=validate.Length(min=1, max=10))
    numero_int = fields.Str(allow_none=True, validate=validate.Length(max=10))
    colonia = fields.Str(validate=validate.Length(min=1, max=80))
    municipio = fields.Str(validate=validate.Length(min=1, max=80))
    estado = fields.Str(validate=validate.Length(min=1, max=60))
    codigo_postal = fields.Str(validate=validate.Regexp(r"^\d{5}$"))
    referencia = fields.Str(allow_none=True)
    rfc = fields.Str(allow_none=True, validate=validate.Length(min=12, max=13))
    razon_social = fields.Str(allow_none=True, validate=validate.Length(max=120))
    predeterminada = fields.Bool()


class DireccionSchema(Schema):
    id = fields.Int()
    tipo = fields.Str()
    alias = fields.Str()
    destinatario = fields.Str()
    telefono = fields.Str()
    calle = fields.Str()
    numero_ext = fields.Str()
    numero_int = fields.Str(allow_none=True)
    colonia = fields.Str()
    municipio = fields.Str()
    estado = fields.Str()
    codigo_postal = fields.Str()
    referencia = fields.Str(allow_none=True)
    rfc = fields.Str(allow_none=True)
    razon_social = fields.Str(allow_none=True)
    predeterminada = fields.Bool()
    activa = fields.Bool()
    cobertura = fields.Dict(allow_none=True)


class MedioPagoCrearSchema(Schema):
    tipo = fields.Str(required=True, validate=validate.OneOf(TIPOS_MEDIO_PAGO))
    alias = fields.Str(required=True, validate=validate.Length(min=1, max=40))
    titular = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    numero_tarjeta = fields.Str(allow_none=True, validate=validate.Regexp(r"^\d{16}$"))
    vence_mes = fields.Int(allow_none=True, validate=validate.Range(min=1, max=12))
    vence_anio = fields.Int(allow_none=True, validate=validate.Range(min=2000, max=2200))
    cvv = fields.Str(allow_none=True, validate=validate.Regexp(r"^\d{3,4}$"))
    saldo_inicial = fields.Decimal(allow_none=True, places=2)


class MedioPagoActualizarSchema(Schema):
    alias = fields.Str(required=True, validate=validate.Length(min=1, max=40))


class MedioPagoSchema(Schema):
    id = fields.Int()
    tipo = fields.Str()
    alias = fields.Str()
    titular = fields.Str()
    ultimos4 = fields.Str()
    marca = fields.Str(allow_none=True)
    vence_mes = fields.Int(allow_none=True)
    vence_anio = fields.Int(allow_none=True)
    saldo_simulado = fields.Decimal(as_string=True, places=2, allow_none=True)
    activo = fields.Bool()


class CoberturaSchema(Schema):
    codigo_postal = fields.Str()
    cobertura = fields.Bool()
    tarifa = fields.Dict(allow_none=True)
    costo = fields.Decimal(as_string=True, places=2, allow_none=True)
    dias_estimados = fields.Int(allow_none=True)
