"""Esquemas de cambios y devoluciones (M07)."""

from marshmallow import Schema, fields, validate

TIPOS = ["DEVOLUCION", "CAMBIO"]
MOTIVOS = ["DEFECTO", "AJUSTE", "DANO_ENVIO", "PRODUCTO_EQUIVOCADO", "ARREPENTIMIENTO"]
DICTAMENES = ["REINGRESO", "MERMA"]
RESOLUCIONES = ["REEMBOLSO", "CAMBIO"]
ESTADOS = ["SOLICITADA", "APROBADA", "RECHAZADA", "RECIBIDA", "RESUELTA"]


class DevolucionLineaCrearSchema(Schema):
    venta_linea_id = fields.Int(required=True, validate=validate.Range(min=1))
    cantidad = fields.Int(required=True, validate=validate.Range(min=1, max=100))
    variante_cambio_id = fields.Int(allow_none=True, validate=validate.Range(min=1))


class DevolucionCrearSchema(Schema):
    pedido_id = fields.Int(required=True, validate=validate.Range(min=1))
    tipo = fields.Str(required=True, validate=validate.OneOf(TIPOS))
    motivo = fields.Str(required=True, validate=validate.OneOf(MOTIVOS))
    descripcion = fields.Str(required=True, validate=validate.Length(min=3, max=500))
    lineas = fields.Nested(DevolucionLineaCrearSchema, many=True, required=True)


class DevolucionFiltrosSchema(Schema):
    estado = fields.Str(validate=validate.OneOf(ESTADOS))
    tipo = fields.Str(validate=validate.OneOf(TIPOS))
    motivo = fields.Str(validate=validate.OneOf(MOTIVOS))
    desde = fields.DateTime(format="iso", allow_none=True)
    hasta = fields.DateTime(format="iso", allow_none=True)
    q = fields.Str(validate=validate.Length(max=120))


class DevolucionLineaSchema(Schema):
    id = fields.Int()
    venta_linea_id = fields.Int()
    sku = fields.Str(allow_none=True)
    cantidad = fields.Int()
    variante_cambio_id = fields.Int(allow_none=True)
    dictamen = fields.Str()


class DevolucionSchema(Schema):
    id = fields.Int()
    folio = fields.Str()
    venta_id = fields.Int()
    venta_folio = fields.Str(allow_none=True)
    pedido_id = fields.Int(allow_none=True)
    usuario_id = fields.Int()
    tipo = fields.Str()
    motivo = fields.Str()
    descripcion = fields.Str()
    estado = fields.Str()
    resolucion = fields.Str(allow_none=True)
    reembolso_monto = fields.Decimal(as_string=True, places=2, allow_none=True)
    venta_reemplazo_id = fields.Int(allow_none=True)
    motivo_rechazo = fields.Str(allow_none=True)
    resuelta_por = fields.Int(allow_none=True)
    resuelta_en = fields.Str(allow_none=True)
    creado_en = fields.Str()
    lineas = fields.Nested(DevolucionLineaSchema, many=True)
    evidencias = fields.List(fields.Str())


class DevolucionRechazarSchema(Schema):
    motivo = fields.Str(required=True, validate=validate.Length(min=3, max=300))


class DevolucionDictamenLineaSchema(Schema):
    devolucion_linea_id = fields.Int(required=True, validate=validate.Range(min=1))
    dictamen = fields.Str(required=True, validate=validate.OneOf(DICTAMENES))
    causa_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    causa_nombre = fields.Str(allow_none=True, validate=validate.Length(max=100))
    descripcion = fields.Str(allow_none=True, validate=validate.Length(max=300))


class DevolucionDictamenSchema(Schema):
    descripcion = fields.Str(allow_none=True, validate=validate.Length(max=500))
    lineas = fields.Nested(DevolucionDictamenLineaSchema, many=True, required=True)


class DevolucionResolverSchema(Schema):
    resolucion = fields.Str(required=True, validate=validate.OneOf(RESOLUCIONES))
