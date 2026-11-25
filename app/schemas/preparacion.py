"""Esquemas de preparación y empaque (M18)."""

from marshmallow import Schema, fields, validate

ESTADOS = ["POR_SURTIR", "EN_PICKING", "EN_VERIFICACION", "EN_EMPAQUE", "LISTA"]
TIPOS_INCIDENCIA = ["SKU", "CANTIDAD", "CALIDAD"]


class PreparacionFiltrosSchema(Schema):
    estado = fields.Str(allow_none=True, validate=validate.OneOf(ESTADOS))


class PreparacionLineaSchema(Schema):
    id = fields.Int()
    pedido_linea_id = fields.Int()
    sku = fields.Str(allow_none=True)
    nombre_producto = fields.Str(allow_none=True)
    talla = fields.Str(allow_none=True)
    color = fields.Str(allow_none=True)
    cantidad_requerida = fields.Int()
    cantidad_surtida = fields.Int()
    sku_verificado = fields.Bool()
    diseno_verificado = fields.Bool()
    etiquetas_verificadas = fields.Bool()
    incidencia = fields.Str(allow_none=True)


class PreparacionSchema(Schema):
    id = fields.Int()
    pedido_id = fields.Int()
    folio = fields.Str(allow_none=True)
    estado = fields.Str()
    prioridad = fields.Str(allow_none=True)
    fecha_promesa = fields.Str(allow_none=True)
    destinatario = fields.Str(allow_none=True)
    codigo_postal = fields.Str(allow_none=True)
    tomada_por = fields.Int(allow_none=True)
    iniciada_en = fields.Str(allow_none=True)
    terminada_en = fields.Str(allow_none=True)
    notas = fields.Str(allow_none=True)
    lineas = fields.Nested(PreparacionLineaSchema, many=True)


class PreparacionLineaActualizarSchema(Schema):
    preparacion_linea_id = fields.Int(required=True, validate=validate.Range(min=1))
    sku = fields.Str(allow_none=True, validate=validate.Length(max=30))
    cantidad_surtida = fields.Int(allow_none=True, validate=validate.Range(min=0))
    sku_verificado = fields.Bool(allow_none=True)
    diseno_verificado = fields.Bool(allow_none=True)
    etiquetas_verificadas = fields.Bool(allow_none=True)


class PreparacionLineasActualizarSchema(Schema):
    lineas = fields.Nested(PreparacionLineaActualizarSchema, many=True, required=True)


class PreparacionIncidenciaSchema(Schema):
    preparacion_linea_id = fields.Int(required=True, validate=validate.Range(min=1))
    tipo = fields.Str(required=True, validate=validate.OneOf(TIPOS_INCIDENCIA))
    descripcion = fields.Str(required=True, validate=validate.Length(min=3, max=500))
    cantidad = fields.Int(allow_none=True, validate=validate.Range(min=1))


class EtiquetaSchema(Schema):
    folio = fields.Str()
    pedido_id = fields.Int()
    destinatario = fields.Str(allow_none=True)
    direccion = fields.Str(allow_none=True)
    codigo_postal = fields.Str(allow_none=True)
    telefono = fields.Str(allow_none=True)
    qr = fields.Str()
