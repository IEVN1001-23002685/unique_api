"""Esquemas del padrón de proveedores y su catálogo de materiales (M13)."""

from marshmallow import EXCLUDE, Schema, fields, validate

ESTATUS = ("ACTIVO", "EN_REVISION", "INACTIVO")
ESTATUS_EDITABLE = ("ACTIVO", "EN_REVISION")


class ProveedorFiltrosSchema(Schema):
    q = fields.Str(allow_none=True, validate=validate.Length(max=120))
    estatus = fields.Str(allow_none=True, validate=validate.OneOf(ESTATUS))
    material_id = fields.Int(allow_none=True)
    incluir_inactivos = fields.Bool(load_default=False)

    class Meta:
        unknown = EXCLUDE


class ProveedorCrearSchema(Schema):
    razon_social = fields.Str(required=True, validate=validate.Length(min=2, max=150))
    nombre_comercial = fields.Str(required=True, validate=validate.Length(min=2, max=120))
    rfc = fields.Str(allow_none=True, validate=validate.Length(max=13))
    contacto = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    telefono = fields.Str(required=True, validate=validate.Length(min=5, max=15))
    correo = fields.Email(required=True, validate=validate.Length(max=120))
    direccion = fields.Str(required=True, validate=validate.Length(min=5))
    condiciones_pago = fields.Str(required=True, validate=validate.Length(min=2))
    notas = fields.Str(allow_none=True)

    class Meta:
        unknown = EXCLUDE


class ProveedorActualizarSchema(ProveedorCrearSchema):
    razon_social = fields.Str(validate=validate.Length(min=2, max=150))
    nombre_comercial = fields.Str(validate=validate.Length(min=2, max=120))
    contacto = fields.Str(validate=validate.Length(min=2, max=100))
    telefono = fields.Str(validate=validate.Length(min=5, max=15))
    correo = fields.Email(validate=validate.Length(max=120))
    direccion = fields.Str(validate=validate.Length(min=5))
    condiciones_pago = fields.Str(validate=validate.Length(min=2))
    estatus = fields.Str(validate=validate.OneOf(ESTATUS_EDITABLE))


class ProveedorSchema(Schema):
    id = fields.Int()
    razon_social = fields.Str()
    nombre_comercial = fields.Str()
    rfc = fields.Str(allow_none=True)
    contacto = fields.Str()
    telefono = fields.Str()
    correo = fields.Str()
    direccion = fields.Str()
    condiciones_pago = fields.Str()
    estatus = fields.Str()
    notas = fields.Str(allow_none=True)
    eliminado_en = fields.DateTime(allow_none=True)


class ProveedorMaterialCrearSchema(Schema):
    material_id = fields.Int(required=True)
    precio_compra = fields.Decimal(required=True, places=2, validate=validate.Range(min=0))
    minimo_compra = fields.Decimal(required=True, places=2, validate=validate.Range(min=0))
    plazo_dias = fields.Int(required=True, validate=validate.Range(min=0, max=365))
    es_principal = fields.Bool(load_default=False)
    vigencia_hasta = fields.Date(allow_none=True)
    activo = fields.Bool(load_default=True)

    class Meta:
        unknown = EXCLUDE


class ProveedorMaterialActualizarSchema(ProveedorMaterialCrearSchema):
    material_id = fields.Int()
    precio_compra = fields.Decimal(places=2, validate=validate.Range(min=0))
    minimo_compra = fields.Decimal(places=2, validate=validate.Range(min=0))
    plazo_dias = fields.Int(validate=validate.Range(min=0, max=365))
    es_principal = fields.Bool()
    vigencia_hasta = fields.Date(allow_none=True)
    activo = fields.Bool()


class ProveedorMaterialSchema(Schema):
    id = fields.Int()
    proveedor_id = fields.Int()
    material_id = fields.Int()
    material_codigo = fields.Str(allow_none=True)
    material_nombre = fields.Str(allow_none=True)
    unidad_compra = fields.Str(allow_none=True)
    precio_compra = fields.Str()
    minimo_compra = fields.Str()
    plazo_dias = fields.Int()
    es_principal = fields.Bool()
    vigencia_hasta = fields.Str(allow_none=True)
    activo = fields.Bool()


class ProveedorEvaluacionSchema(Schema):
    proveedor_id = fields.Int()
    razon_social = fields.Str()
    nombre_comercial = fields.Str()
    estatus = fields.Str()
    ordenes_recibidas = fields.Int()
    ordenes_evaluadas = fields.Int()
    entregas_a_tiempo = fields.Int()
    porcentaje_a_tiempo = fields.Str()
    cantidad_medida = fields.Str()
    cantidad_aceptada = fields.Str()
    porcentaje_aceptacion = fields.Str()
    advertencias = fields.List(fields.Str())


class ProveedorEvaluacionResponseSchema(Schema):
    items = fields.Nested(ProveedorEvaluacionSchema, many=True)
    advertencias = fields.List(fields.Str())
    umbral_a_tiempo_pct = fields.Str()


__all__ = [
    "ProveedorActualizarSchema",
    "ProveedorCrearSchema",
    "ProveedorEvaluacionResponseSchema",
    "ProveedorEvaluacionSchema",
    "ProveedorFiltrosSchema",
    "ProveedorMaterialActualizarSchema",
    "ProveedorMaterialCrearSchema",
    "ProveedorMaterialSchema",
    "ProveedorSchema",
]
