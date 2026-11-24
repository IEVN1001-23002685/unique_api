"""Esquemas de productos, variantes, imágenes y activación (M10)."""

from marshmallow import EXCLUDE, Schema, fields, validate


class ProductoFiltrosSchema(Schema):
    categoria = fields.Str(allow_none=True)
    activo = fields.Bool(allow_none=True)
    q = fields.Str(allow_none=True, validate=validate.Length(max=120))

    class Meta:
        unknown = EXCLUDE


class ProductoCrearSchema(Schema):
    categoria_id = fields.Int(required=True, validate=validate.Range(min=1))
    nombre = fields.Str(required=True, validate=validate.Length(min=2, max=120))
    descripcion = fields.Str(required=True, validate=validate.Length(max=2000))
    composicion_textil = fields.Str(required=True, validate=validate.Length(max=1000))
    guia_medidas = fields.Str(required=True, validate=validate.Length(max=1000))
    precio_venta = fields.Decimal(required=True, as_string=True, places=2, validate=validate.Range(min=0))
    permite_bajo_pedido = fields.Bool(load_default=False)
    colores = fields.List(fields.Str(validate=validate.Length(equal=2)), allow_none=True)
    tallas = fields.List(fields.Str(validate=validate.Length(equal=2)), allow_none=True)
    stock_minimo = fields.Int(load_default=5, validate=validate.Range(min=0))
    cantidad_reposicion = fields.Int(load_default=20, validate=validate.Range(min=0))


class ProductoActualizarSchema(Schema):
    nombre = fields.Str(validate=validate.Length(min=2, max=120))
    descripcion = fields.Str(validate=validate.Length(max=2000))
    composicion_textil = fields.Str(validate=validate.Length(max=1000))
    guia_medidas = fields.Str(validate=validate.Length(max=1000))
    precio_venta = fields.Decimal(as_string=True, places=2, validate=validate.Range(min=0))
    permite_bajo_pedido = fields.Bool()
    colores = fields.List(fields.Str(validate=validate.Length(equal=2)))
    tallas = fields.List(fields.Str(validate=validate.Length(equal=2)))


class ImagenSubirFormSchema(Schema):
    color = fields.Str(allow_none=True, validate=validate.Length(equal=2))
    orden = fields.Int(load_default=0, validate=validate.Range(min=0))

    class Meta:
        unknown = EXCLUDE


class VarianteActualizarSchema(Schema):
    activa = fields.Bool(required=True)


class VarianteAdminSchema(Schema):
    id = fields.Int()
    sku = fields.Str()
    talla = fields.Str()
    color = fields.Str()
    activa = fields.Bool()
    existencia = fields.Int()
    reservado = fields.Int()
    disponible = fields.Int()
    stock_minimo = fields.Int()
    cantidad_reposicion = fields.Int()


class ProductoImagenAdminSchema(Schema):
    id = fields.Int()
    color = fields.Str(allow_none=True)
    url = fields.Str()
    orden = fields.Int()


class RecetaResumenAdminSchema(Schema):
    id = fields.Int()
    talla = fields.Str()
    version = fields.Int()
    estado = fields.Str()
    activada_en = fields.DateTime(format="iso", allow_none=True)


class ProductoListaAdminSchema(Schema):
    id = fields.Int()
    codigo_sku = fields.Str()
    nombre = fields.Str()
    categoria = fields.Str()
    precio_venta = fields.Decimal(as_string=True, places=2)
    activo = fields.Bool()
    eliminado_en = fields.DateTime(format="iso", allow_none=True)
    permite_bajo_pedido = fields.Bool()
    numero_variantes = fields.Int()
    costo_estandar = fields.Decimal(as_string=True, places=2, allow_none=True)
    margen_real = fields.Decimal(as_string=True, places=6, allow_none=True)


class ProductoDetalleAdminSchema(Schema):
    id = fields.Int()
    codigo_sku = fields.Str()
    categoria = fields.Str()
    categoria_id = fields.Int()
    nombre = fields.Str()
    descripcion = fields.Str()
    composicion_textil = fields.Str()
    guia_medidas = fields.Str()
    precio_venta = fields.Decimal(as_string=True, places=2)
    permite_bajo_pedido = fields.Bool()
    activo = fields.Bool()
    eliminado_en = fields.DateTime(format="iso", allow_none=True)
    variantes = fields.Nested(VarianteAdminSchema, many=True)
    imagenes = fields.Nested(ProductoImagenAdminSchema, many=True)
    recetas = fields.Nested(RecetaResumenAdminSchema, many=True)
    costo_estandar = fields.Decimal(as_string=True, places=2, allow_none=True)
    margen_real = fields.Decimal(as_string=True, places=6, allow_none=True)
