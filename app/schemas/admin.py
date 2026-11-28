"""Esquemas de catálogos administrativos y filtros de bitácora (M22)."""

from marshmallow import Schema, fields, pre_load, validate

CP = validate.Regexp(r"^\d{5}$", error="El código postal debe tener 5 dígitos")
CODIGO = validate.Regexp(r"^[A-Z]{2}$", error="El código debe tener 2 letras mayúsculas")
HEX = validate.Regexp(r"^#[0-9A-Fa-f]{6}$", error="El color debe ser hexadecimal #RRGGBB")


class CodigoMayusculas:
    @pre_load
    def normalizar_codigo(self, datos, **kwargs):
        normalizados = dict(datos)
        for campo in ("codigo", "prefijo_sku"):
            valor = normalizados.get(campo)
            if isinstance(valor, str):
                normalizados[campo] = valor.strip().upper()
        return normalizados


class ColorCrearSchema(CodigoMayusculas, Schema):
    codigo = fields.Str(required=True, validate=CODIGO)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=40))
    hex = fields.Str(required=True, validate=HEX)
    es_comercial = fields.Bool(load_default=False)


class ColorActualizarSchema(CodigoMayusculas, Schema):
    codigo = fields.Str(validate=CODIGO)
    nombre = fields.Str(validate=validate.Length(min=1, max=40))
    hex = fields.Str(validate=HEX)
    es_comercial = fields.Bool()


class TallaCrearSchema(CodigoMayusculas, Schema):
    codigo = fields.Str(required=True, validate=CODIGO)
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=40))
    orden = fields.Int(load_default=0, validate=validate.Range(min=0))


class TallaActualizarSchema(CodigoMayusculas, Schema):
    codigo = fields.Str(validate=CODIGO)
    nombre = fields.Str(validate=validate.Length(min=1, max=40))
    orden = fields.Int(validate=validate.Range(min=0))


class CategoriaProductoCrearSchema(CodigoMayusculas, Schema):
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=60))
    prefijo_sku = fields.Str(required=True, validate=CODIGO)
    usa_tallas = fields.Bool(load_default=True)
    activa = fields.Bool(load_default=True)


class CategoriaProductoActualizarSchema(CodigoMayusculas, Schema):
    nombre = fields.Str(validate=validate.Length(min=1, max=60))
    prefijo_sku = fields.Str(validate=CODIGO)
    usa_tallas = fields.Bool()
    activa = fields.Bool()


class CategoriaMaterialCrearSchema(Schema):
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=60))
    descripcion = fields.Str(allow_none=True)


class CategoriaMaterialActualizarSchema(Schema):
    nombre = fields.Str(validate=validate.Length(min=1, max=60))
    descripcion = fields.Str(allow_none=True)


class CausaMermaCrearSchema(Schema):
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    aplica_a = fields.Str(
        required=True, validate=validate.OneOf(("MATERIAL", "PRODUCTO", "AMBOS"))
    )
    etapa_sugerida = fields.Str(allow_none=True, validate=validate.Length(max=30))
    activa = fields.Bool(load_default=True)


class CausaMermaActualizarSchema(Schema):
    nombre = fields.Str(validate=validate.Length(min=1, max=80))
    aplica_a = fields.Str(validate=validate.OneOf(("MATERIAL", "PRODUCTO", "AMBOS")))
    etapa_sugerida = fields.Str(allow_none=True, validate=validate.Length(max=30))
    activa = fields.Bool()


class TarifaEnvioCrearSchema(Schema):
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=60))
    cp_inicio = fields.Str(required=True, validate=CP)
    cp_fin = fields.Str(required=True, validate=CP)
    costo = fields.Decimal(required=True, places=2, validate=validate.Range(min=0))
    dias_estimados = fields.Int(required=True, validate=validate.Range(min=0))
    activa = fields.Bool(load_default=True)


class TarifaEnvioActualizarSchema(Schema):
    nombre = fields.Str(validate=validate.Length(min=1, max=60))
    cp_inicio = fields.Str(validate=CP)
    cp_fin = fields.Str(validate=CP)
    costo = fields.Decimal(places=2, validate=validate.Range(min=0))
    dias_estimados = fields.Int(validate=validate.Range(min=0))
    activa = fields.Bool()


class CatalogoFiltrosSchema(Schema):
    activa = fields.Bool(allow_none=True)
    q = fields.Str(allow_none=True, validate=validate.Length(max=80))


class BitacoraFiltrosSchema(Schema):
    accion = fields.Str(allow_none=True, validate=validate.Length(max=80))
    entidad = fields.Str(allow_none=True, validate=validate.Length(max=60))
    usuario_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    desde = fields.Date(allow_none=True)
    hasta = fields.Date(allow_none=True)
