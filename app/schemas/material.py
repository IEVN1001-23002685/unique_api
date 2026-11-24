"""Esquemas de materiales, inventario base, lotes, kardex y ajustes (M15)."""

from marshmallow import EXCLUDE, Schema, fields, post_dump, validate

UNIDADES_BASE = ("M2", "M", "PZA")
TIPOS_MOVIMIENTO = (
    "ENTRADA",
    "CONSUMO",
    "MERMA",
    "AJUSTE",
    "SOBRANTE",
    "REVERSA",
)


class _SchemaConCostosOcultables(Schema):
    """Elimina campos financieros cuando la respuesta es para Operativo."""

    CAMPOS_COSTO = ()

    @post_dump
    def _ocultar_costos(self, datos, **_kwargs):
        if not self.context.get("incluir_costos", True):
            for campo in self.CAMPOS_COSTO:
                datos.pop(campo, None)
        return datos


class MaterialFiltrosSchema(Schema):
    categoria = fields.Str(allow_none=True, validate=validate.Length(max=60))
    codigo = fields.Str(allow_none=True, validate=validate.Length(max=12))
    q = fields.Str(allow_none=True, validate=validate.Length(max=120))
    por_color = fields.Bool(allow_none=True)
    incluir_inactivos = fields.Bool(load_default=False)

    class Meta:
        unknown = EXCLUDE


class MaterialCrearSchema(Schema):
    categoria_material_id = fields.Int(required=True)
    codigo = fields.Str(required=True, validate=validate.Length(min=1, max=12))
    nombre = fields.Str(required=True, validate=validate.Length(min=2, max=120))
    unidad_base = fields.Str(required=True, validate=validate.OneOf(UNIDADES_BASE))
    unidad_compra = fields.Str(required=True, validate=validate.Length(min=1, max=40))
    factor_compra_base = fields.Decimal(
        required=True, places=4, validate=validate.Range(min=0.0001)
    )
    costo_estandar_base = fields.Decimal(
        required=True, places=6, validate=validate.Range(min=0)
    )
    merma_estandar_pct = fields.Decimal(
        required=True, places=2, validate=validate.Range(min=0, max=99.99)
    )
    por_color = fields.Bool(load_default=False)
    activo = fields.Bool(load_default=True)

    class Meta:
        unknown = EXCLUDE


class MaterialActualizarSchema(MaterialCrearSchema):
    categoria_material_id = fields.Int()
    codigo = fields.Str(validate=validate.Length(min=1, max=12))
    nombre = fields.Str(validate=validate.Length(min=2, max=120))
    unidad_base = fields.Str(validate=validate.OneOf(UNIDADES_BASE))
    unidad_compra = fields.Str(validate=validate.Length(min=1, max=40))
    factor_compra_base = fields.Decimal(places=4, validate=validate.Range(min=0.0001))
    costo_estandar_base = fields.Decimal(places=6, validate=validate.Range(min=0))
    merma_estandar_pct = fields.Decimal(
        places=2, validate=validate.Range(min=0, max=99.99)
    )
    por_color = fields.Bool()
    activo = fields.Bool()


class MaterialSchema(_SchemaConCostosOcultables):
    CAMPOS_COSTO = ("costo_estandar_base",)

    id = fields.Int()
    categoria_material_id = fields.Int()
    categoria = fields.Method("_categoria")
    codigo = fields.Str()
    nombre = fields.Str()
    unidad_base = fields.Str()
    unidad_compra = fields.Str()
    factor_compra_base = fields.Decimal(as_string=True, places=4)
    costo_estandar_base = fields.Decimal(as_string=True, places=6)
    merma_estandar_pct = fields.Decimal(as_string=True, places=2)
    por_color = fields.Bool()
    activo = fields.Bool()
    eliminado_en = fields.DateTime(allow_none=True)

    def _categoria(self, fila):
        if isinstance(fila, dict):
            return fila.get("categoria")
        categoria = getattr(fila, "categoria", None)
        return getattr(categoria, "nombre", None) if categoria is not None else None


class InventarioFiltrosSchema(Schema):
    categoria = fields.Str(allow_none=True, validate=validate.Length(max=60))
    material_id = fields.Int(allow_none=True)
    color_id = fields.Int(allow_none=True)
    activo = fields.Bool(allow_none=True)
    incluir_inactivos = fields.Bool(load_default=False)

    class Meta:
        unknown = EXCLUDE


class InventarioMaterialSchema(_SchemaConCostosOcultables):
    CAMPOS_COSTO = ("costo_estandar_base", "minimo_compra")

    id = fields.Int()
    material_id = fields.Int()
    material_codigo = fields.Str()
    material_nombre = fields.Str()
    categoria = fields.Str(allow_none=True)
    color_id = fields.Int()
    color_codigo = fields.Str()
    unidad_base = fields.Str()
    fisico = fields.Str()
    reservado = fields.Str()
    disponible = fields.Str()
    en_compra = fields.Str()
    posicion = fields.Str()
    consumo_diario = fields.Str()
    punto_reorden = fields.Str(allow_none=True)
    cobertura_dias = fields.Str(allow_none=True)
    semaforo = fields.Str()
    stock_minimo = fields.Str()
    stock_seguridad = fields.Str()
    proveedor_principal_id = fields.Int(allow_none=True)
    plazo_dias = fields.Int()
    factor_compra_base = fields.Str(allow_none=True)
    minimo_compra = fields.Str(allow_none=True)
    costo_estandar_base = fields.Str(allow_none=True)
    activo = fields.Bool()


class LoteFiltrosSchema(Schema):
    inventario_material_id = fields.Int(allow_none=True)
    material_id = fields.Int(allow_none=True)
    color_id = fields.Int(allow_none=True)
    proveedor_id = fields.Int(allow_none=True)
    folio = fields.Str(allow_none=True, validate=validate.Length(max=20))
    fecha_desde = fields.Date(allow_none=True)
    fecha_hasta = fields.Date(allow_none=True)

    class Meta:
        unknown = EXCLUDE


class LoteMaterialSchema(_SchemaConCostosOcultables):
    CAMPOS_COSTO = ("costo_total", "costo_unitario_base")

    id = fields.Int()
    inventario_material_id = fields.Int()
    folio = fields.Str()
    proveedor_id = fields.Int(allow_none=True)
    fecha_entrada = fields.Date()
    material_codigo = fields.Method("_material_codigo")
    color_codigo = fields.Method("_color_codigo")
    cantidad_base_recibida = fields.Decimal(as_string=True, places=4)
    cantidad_base_disponible = fields.Decimal(as_string=True, places=4)
    costo_total = fields.Decimal(as_string=True, places=2)
    costo_unitario_base = fields.Decimal(as_string=True, places=6)
    estado = fields.Str()

    @staticmethod
    def _valor(fila, nombre):
        if isinstance(fila, dict):
            return fila.get(nombre)
        inventario = getattr(fila, "inventario_material", None)
        return getattr(inventario, nombre) if inventario is not None else None

    def _material_codigo(self, fila):
        if isinstance(fila, dict):
            return fila.get("material_codigo")
        inventario = getattr(fila, "inventario_material", None)
        material = getattr(inventario, "material", None) if inventario else None
        return getattr(material, "codigo", None)

    def _color_codigo(self, fila):
        if isinstance(fila, dict):
            return fila.get("color_codigo")
        inventario = getattr(fila, "inventario_material", None)
        color = getattr(inventario, "color", None) if inventario else None
        return getattr(color, "codigo", None)


class MovimientoFiltrosSchema(Schema):
    inventario_material_id = fields.Int(allow_none=True)
    material_id = fields.Int(allow_none=True)
    color_id = fields.Int(allow_none=True)
    lote_id = fields.Int(allow_none=True)
    tipo = fields.Str(allow_none=True, validate=validate.OneOf(TIPOS_MOVIMIENTO))
    fecha_desde = fields.Date(allow_none=True)
    fecha_hasta = fields.Date(allow_none=True)

    class Meta:
        unknown = EXCLUDE


class MovimientoMaterialSchema(_SchemaConCostosOcultables):
    CAMPOS_COSTO = ("costo_unitario_base",)

    id = fields.Int()
    lote_id = fields.Int()
    lote_folio = fields.Method("_lote_folio")
    tipo = fields.Str()
    cantidad_base = fields.Decimal(as_string=True, places=4)
    costo_unitario_base = fields.Decimal(as_string=True, places=6)
    documento_tipo = fields.Str()
    documento_id = fields.Int()
    motivo = fields.Str(allow_none=True)
    fecha = fields.DateTime()
    usuario_id = fields.Int()

    def _lote_folio(self, fila):
        if isinstance(fila, dict):
            return fila.get("lote_folio")
        lote = getattr(fila, "lote", None)
        return getattr(lote, "folio", None) if lote is not None else None


class AjusteMaterialSchema(Schema):
    inventario_material_id = fields.Int(required=True)
    cantidad_contada = fields.Decimal(required=True, places=4, validate=validate.Range(min=0))
    motivo = fields.Str(required=True, validate=validate.Length(min=3, max=500))
    mandar_a_merma = fields.Bool(load_default=False)
    causa_merma_id = fields.Int(allow_none=True)

    class Meta:
        unknown = EXCLUDE


class PoliticaMaterialSchema(Schema):
    stock_minimo = fields.Decimal(places=4, validate=validate.Range(min=0))
    stock_seguridad = fields.Decimal(places=4, validate=validate.Range(min=0))
    consumo_diario_manual = fields.Decimal(
        allow_none=True, places=4, validate=validate.Range(min=0)
    )

    class Meta:
        unknown = EXCLUDE


class ConsumoPepsSchema(Schema):
    lote_id = fields.Int()
    folio = fields.Str()
    cantidad_base = fields.Str()
    costo_unitario_base = fields.Str()
    costo_total = fields.Str()
    fecha_entrada = fields.Str()


__all__ = [
    "AjusteMaterialSchema",
    "ConsumoPepsSchema",
    "InventarioFiltrosSchema",
    "InventarioMaterialSchema",
    "LoteFiltrosSchema",
    "LoteMaterialSchema",
    "MaterialActualizarSchema",
    "MaterialCrearSchema",
    "MaterialFiltrosSchema",
    "MaterialSchema",
    "MovimientoFiltrosSchema",
    "MovimientoMaterialSchema",
    "PoliticaMaterialSchema",
]
