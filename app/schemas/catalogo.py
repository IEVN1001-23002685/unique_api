"""Esquemas de consulta y respuesta del catálogo público (M03)."""

from marshmallow import EXCLUDE, Schema, fields, validate


class CatalogoFiltrosSchema(Schema):
    categoria = fields.Str(allow_none=True)
    color = fields.Str(allow_none=True)
    talla = fields.Str(allow_none=True)
    q = fields.Str(allow_none=True, validate=validate.Length(max=120))
    disponibles = fields.Bool(allow_none=True)

    class Meta:
        unknown = EXCLUDE


class VarianteDisponibilidadSchema(Schema):
    id = fields.Int()
    sku = fields.Str()
    talla = fields.Str()
    color = fields.Str()
    disponibilidad = fields.Str()
    bajo_pedido = fields.Bool()
    fecha_estimada = fields.Date(allow_none=True)


class ProductoImagenSchema(Schema):
    url = fields.Str()
    color = fields.Str(allow_none=True)


class ProductoListaSchema(Schema):
    id = fields.Int()
    nombre = fields.Str()
    descripcion = fields.Str()
    precio_venta = fields.Decimal(as_string=True, places=2)
    categoria = fields.Str()
    imagen = fields.Str(allow_none=True)
    mas_buscado = fields.Bool()
    variantes = fields.Nested(VarianteDisponibilidadSchema, many=True)


class ProductoDetalleSchema(Schema):
    id = fields.Int()
    nombre = fields.Str()
    descripcion = fields.Str()
    composicion_textil = fields.Str()
    guia_medidas = fields.Str()
    precio_venta = fields.Decimal(as_string=True, places=2)
    iva_incluido = fields.Bool()
    categoria = fields.Str()
    imagenes = fields.Nested(ProductoImagenSchema, many=True)
    variantes = fields.Nested(VarianteDisponibilidadSchema, many=True)
