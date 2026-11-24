"""Esquemas de recetas, costeo y diseños de bordado (M11)."""

from marshmallow import EXCLUDE, Schema, ValidationError, fields, validate, validates_schema

from app.utils.dinero import material


class RecetaFiltrosSchema(Schema):
    producto_id = fields.Int(allow_none=True)
    talla_id = fields.Int(allow_none=True)
    estado = fields.Str(
        allow_none=True,
        validate=validate.OneOf(("BORRADOR", "VIGENTE", "ARCHIVADA")),
    )
    q = fields.Str(allow_none=True, validate=validate.Length(max=120))

    class Meta:
        unknown = EXCLUDE


class RecetaCrearSchema(Schema):
    producto_id = fields.Int(required=True, validate=validate.Range(min=1))
    talla_id = fields.Int(required=True, validate=validate.Range(min=1))
    mano_obra = fields.Decimal(as_string=True, places=2, load_default=0)
    costo_bordado = fields.Decimal(as_string=True, places=2, load_default=0)
    costos_indirectos = fields.Decimal(as_string=True, places=2, load_default=0)
    nota = fields.Str(allow_none=True, validate=validate.Length(max=1000))


class RecetaActualizarSchema(Schema):
    mano_obra = fields.Decimal(as_string=True, places=2)
    costo_bordado = fields.Decimal(as_string=True, places=2)
    costos_indirectos = fields.Decimal(as_string=True, places=2)
    nota = fields.Str(allow_none=True, validate=validate.Length(max=1000))


class RecetaLineaCrearSchema(Schema):
    material_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    diseno_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    cantidad_neta = fields.Decimal(as_string=True, places=4, allow_none=True)
    factor_consumo = fields.Decimal(as_string=True, places=3, allow_none=True)
    merma_pct = fields.Decimal(as_string=True, places=2, allow_none=True)
    aplicaciones = fields.Int(allow_none=True, validate=validate.Range(min=1, max=127))
    ubicacion = fields.Str(allow_none=True, validate=validate.Length(max=60))
    nota = fields.Str(allow_none=True, validate=validate.Length(max=300))

    @validates_schema
    def validar_destino(self, datos, **kwargs):
        material_id = datos.get("material_id")
        diseno_id = datos.get("diseno_id")
        if bool(material_id) == bool(diseno_id):
            raise ValidationError("Indique material_id o diseno_id, pero no ambos")
        if material_id and datos.get("cantidad_neta") is None:
            raise ValidationError({"cantidad_neta": ["Se requiere la cantidad neta"]})
        if material_id and datos.get("cantidad_neta") is not None and datos["cantidad_neta"] < 0:
            raise ValidationError({"cantidad_neta": ["No puede ser negativa"]})
        if material_id and datos.get("factor_consumo") is not None and datos["factor_consumo"] <= 0:
            raise ValidationError({"factor_consumo": ["Debe ser mayor a cero"]})
        if material_id and datos.get("merma_pct") is not None and datos["merma_pct"] >= 100:
            raise ValidationError({"merma_pct": ["Debe ser menor a 100"]})


class RecetaPrevisualizarSchema(Schema):
    producto_id = fields.Int(required=True, validate=validate.Range(min=1))
    talla_id = fields.Int(required=True, validate=validate.Range(min=1))
    mano_obra = fields.Decimal(as_string=True, places=2, load_default=0)
    costo_bordado = fields.Decimal(as_string=True, places=2, load_default=0)
    costos_indirectos = fields.Decimal(as_string=True, places=2, load_default=0)
    precio_venta = fields.Decimal(as_string=True, places=2, allow_none=True)
    lineas = fields.List(fields.Nested(RecetaLineaCrearSchema), load_default=list)


class RecetaCopiarSchema(Schema):
    producto_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    talla_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    nota = fields.Str(allow_none=True, validate=validate.Length(max=1000))


class DisenoHiloEntradaSchema(Schema):
    material_id = fields.Int(required=True, validate=validate.Range(min=1))
    metros_por_aplicacion = fields.Decimal(
        required=True, as_string=True, places=3, validate=validate.Range(min=0)
    )


class DisenoFiltrosSchema(Schema):
    activo = fields.Bool(allow_none=True)
    estado = fields.Str(allow_none=True, validate=validate.OneOf(("PENDIENTE", "DIGITALIZADO")))

    class Meta:
        unknown = EXCLUDE


class DisenoCrearSchema(Schema):
    codigo = fields.Str(required=True, validate=validate.Length(min=2, max=20))
    nombre = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    ancho_cm = fields.Decimal(required=True, as_string=True, places=2, validate=validate.Range(min=0))
    alto_cm = fields.Decimal(required=True, as_string=True, places=2, validate=validate.Range(min=0))
    notas = fields.Str(allow_none=True, validate=validate.Length(max=1000))
    activo = fields.Bool(load_default=True)
    hilos = fields.List(fields.Nested(DisenoHiloEntradaSchema), load_default=list)


class DisenoActualizarSchema(Schema):
    codigo = fields.Str(validate=validate.Length(min=2, max=20))
    nombre = fields.Str(validate=validate.Length(min=2, max=100))
    ancho_cm = fields.Decimal(as_string=True, places=2, validate=validate.Range(min=0))
    alto_cm = fields.Decimal(as_string=True, places=2, validate=validate.Range(min=0))
    notas = fields.Str(allow_none=True, validate=validate.Length(max=1000))
    activo = fields.Bool()
    estado = fields.Str(validate=validate.OneOf(("PENDIENTE", "DIGITALIZADO")))
    hilos = fields.List(fields.Nested(DisenoHiloEntradaSchema), allow_none=True)


class DisenoHiloSchema(Schema):
    material_id = fields.Int()
    material_codigo = fields.Str()
    material_nombre = fields.Str()
    metros_por_aplicacion = fields.Function(lambda obj: material(obj["metros_por_aplicacion"]))


class DisenoSchema(Schema):
    id = fields.Int()
    codigo = fields.Str()
    nombre = fields.Str()
    ancho_cm = fields.Decimal(as_string=True, places=2)
    alto_cm = fields.Decimal(as_string=True, places=2)
    estado = fields.Str()
    notas = fields.Str(allow_none=True)
    activo = fields.Bool()
    hilos = fields.Nested(DisenoHiloSchema, many=True)


class RecetaLineaSchema(Schema):
    id = fields.Int()
    material_id = fields.Int()
    material_codigo = fields.Str()
    material_nombre = fields.Str()
    unidad_base = fields.Str()
    cantidad_neta = fields.Function(lambda obj: material(obj["cantidad_neta"]))
    factor_consumo = fields.Decimal(as_string=True, places=3)
    merma_pct = fields.Decimal(as_string=True, places=2)
    cantidad_bruta = fields.Function(lambda obj: material(obj["cantidad_bruta"]))
    costo_unitario_base = fields.Decimal(as_string=True, places=6)
    costo_linea = fields.Decimal(as_string=True, places=2)
    nota = fields.Str(allow_none=True)


class RecetaLineaOperativoSchema(Schema):
    id = fields.Int()
    material_id = fields.Int()
    material_codigo = fields.Str()
    material_nombre = fields.Str()
    unidad_base = fields.Str()
    cantidad_neta = fields.Function(lambda obj: material(obj["cantidad_neta"]))
    factor_consumo = fields.Decimal(as_string=True, places=3)
    merma_pct = fields.Decimal(as_string=True, places=2)
    cantidad_bruta = fields.Function(lambda obj: material(obj["cantidad_bruta"]))
    nota = fields.Str(allow_none=True)


class RecetaBordadoSchema(Schema):
    id = fields.Int()
    diseno_id = fields.Int()
    diseno_codigo = fields.Str()
    diseno_nombre = fields.Str()
    estado_diseno = fields.Str()
    aplicaciones = fields.Int()
    ubicacion = fields.Str(allow_none=True)


class CostosRecetaSchema(Schema):
    mano_obra = fields.Decimal(as_string=True, places=2)
    costo_bordado = fields.Decimal(as_string=True, places=2)
    costos_indirectos = fields.Decimal(as_string=True, places=2)
    costo_materia_prima = fields.Decimal(as_string=True, places=2)
    costo_hilo_bordado = fields.Decimal(as_string=True, places=2)
    costo_empaque = fields.Decimal(as_string=True, places=2)
    costo_estandar = fields.Decimal(as_string=True, places=2)
    precio_sugerido = fields.Decimal(as_string=True, places=2)
    margen_real = fields.Decimal(as_string=True, places=6, allow_none=True)


class RecetaListaSchema(CostosRecetaSchema):
    id = fields.Int()
    producto_id = fields.Int()
    producto = fields.Str()
    categoria = fields.Str()
    talla_id = fields.Int()
    talla = fields.Str()
    version = fields.Int()
    estado = fields.Str()
    creada_por = fields.Int(allow_none=True)
    activada_en = fields.DateTime(format="iso", allow_none=True)
    actualizado_en = fields.DateTime(format="iso")
    nota = fields.Str(allow_none=True)
    precio_venta = fields.Decimal(as_string=True, places=2, allow_none=True)


class RecetaDetalleSchema(RecetaListaSchema):
    lineas = fields.Nested(RecetaLineaSchema, many=True)
    bordados = fields.Nested(RecetaBordadoSchema, many=True)


class RecetaOperativoSchema(Schema):
    id = fields.Int()
    producto_id = fields.Int()
    producto = fields.Str()
    categoria = fields.Str()
    talla_id = fields.Int()
    talla = fields.Str()
    version = fields.Int()
    estado = fields.Str()
    creada_por = fields.Int(allow_none=True)
    activada_en = fields.DateTime(format="iso", allow_none=True)
    actualizado_en = fields.DateTime(format="iso")
    nota = fields.Str(allow_none=True)
    lineas = fields.Nested(RecetaLineaOperativoSchema, many=True)
    bordados = fields.Nested(RecetaBordadoSchema, many=True)


class LineaPreviewSchema(Schema):
    material_id = fields.Int()
    material_codigo = fields.Str()
    cantidad_neta = fields.Function(lambda obj: material(obj["cantidad_neta"]))
    factor_consumo = fields.Decimal(as_string=True, places=3)
    merma_pct = fields.Decimal(as_string=True, places=2)
    cantidad_bruta = fields.Function(lambda obj: material(obj["cantidad_bruta"]))
    costo_linea = fields.Decimal(as_string=True, places=2)


class RecetaPreviewSchema(CostosRecetaSchema):
    producto_id = fields.Int()
    talla_id = fields.Int()
    capacidad = fields.Int()
    lineas = fields.Nested(LineaPreviewSchema, many=True)


class CosteoFilaSchema(Schema):
    producto_id = fields.Int()
    producto = fields.Str()
    talla_id = fields.Int()
    talla = fields.Str()
    receta_id = fields.Int()
    mano_obra = fields.Decimal(as_string=True, places=2)
    costo_bordado = fields.Decimal(as_string=True, places=2)
    costos_indirectos = fields.Decimal(as_string=True, places=2)
    costo_materia_prima = fields.Decimal(as_string=True, places=2)
    costo_hilo_bordado = fields.Decimal(as_string=True, places=2)
    costo_empaque = fields.Decimal(as_string=True, places=2)
    costo_estandar = fields.Decimal(as_string=True, places=2)
    precio_sugerido = fields.Decimal(as_string=True, places=2)
    precio_venta = fields.Decimal(as_string=True, places=2)
    margen_real = fields.Decimal(as_string=True, places=6)
