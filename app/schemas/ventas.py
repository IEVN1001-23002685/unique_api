"""Esquemas de ventas, pagos, reembolsos y descuentos (M08)."""

from marshmallow import EXCLUDE, Schema, fields, validate

from app.schemas.cuenta import DireccionCrearSchema

CANAL_VENTA = ["TIENDA", "MANUAL", "CAMBIO"]
ESTADO_PAGO = ["PENDIENTE", "PAGADA", "REEMBOLSADA_PARCIAL", "REEMBOLSADA"]
METODOS_MANUALES = ["TARJETA", "CUENTA", "TRANSFERENCIA", "EFECTIVO"]
TIPOS_DESCUENTO = ["PORCENTAJE", "MONTO"]
APLICACIONES_DESCUENTO = ["CUPON", "AUTOMATICO"]


class VentaFiltrosSchema(Schema):
    desde = fields.DateTime(format="iso", allow_none=True)
    hasta = fields.DateTime(format="iso", allow_none=True)
    canal = fields.Str(validate=validate.OneOf(CANAL_VENTA))
    estado = fields.Str(validate=validate.OneOf(["ACTIVA", "CANCELADA"]))
    estado_pago = fields.Str(validate=validate.OneOf(ESTADO_PAGO))
    q = fields.Str(validate=validate.Length(max=120))

    class Meta:
        unknown = EXCLUDE


class VentaLineaSchema(Schema):
    id = fields.Int()
    variante_id = fields.Int()
    sku = fields.Str()
    nombre_producto = fields.Str()
    talla = fields.Str()
    color = fields.Str()
    cantidad = fields.Int()
    precio_unitario = fields.Decimal(as_string=True, places=2)
    subtotal = fields.Decimal(as_string=True, places=2)
    costo_estandar_unitario = fields.Decimal(as_string=True, places=6)
    margen = fields.Decimal(as_string=True, places=2)


class PagoSchema(Schema):
    id = fields.Int()
    tipo = fields.Str()
    metodo = fields.Str()
    estado = fields.Str()
    monto = fields.Decimal(as_string=True, places=2)
    referencia = fields.Str()
    ultimos4 = fields.Str(allow_none=True)
    titular = fields.Str(allow_none=True)
    motivo_rechazo = fields.Str(allow_none=True)
    fecha = fields.Str(allow_none=True)


class VentaDireccionSchema(Schema):
    tipo = fields.Str()
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


class VentaListaSchema(Schema):
    id = fields.Int()
    folio = fields.Str()
    fecha = fields.Str()
    cliente = fields.Dict()
    canal = fields.Str()
    estado = fields.Str()
    estado_pago = fields.Str()
    total = fields.Decimal(as_string=True, places=2)
    pedido_estado = fields.Str(allow_none=True)


class VentaDetalleSchema(Schema):
    id = fields.Int()
    folio = fields.Str()
    fecha = fields.Str()
    cliente_id = fields.Int()
    cliente = fields.Dict()
    canal = fields.Str()
    estado = fields.Str()
    estado_pago = fields.Str()
    subtotal = fields.Decimal(as_string=True, places=2)
    descuento_monto = fields.Decimal(as_string=True, places=2)
    descuento_id = fields.Int(allow_none=True)
    costo_envio = fields.Decimal(as_string=True, places=2)
    total = fields.Decimal(as_string=True, places=2)
    iva_importe = fields.Decimal(as_string=True, places=2)
    iva_incluido = fields.Bool()
    requiere_factura = fields.Bool()
    fecha_promesa = fields.Str(allow_none=True)
    cancelada_en = fields.Str(allow_none=True)
    motivo_cancelacion = fields.Str(allow_none=True)
    creada_por = fields.Int(allow_none=True)
    notas = fields.Str(allow_none=True)
    pedido = fields.Dict(allow_none=True)
    lineas = fields.Nested(VentaLineaSchema, many=True)
    direcciones = fields.Nested(VentaDireccionSchema, many=True)
    pagos = fields.Nested(PagoSchema, many=True)
    costo_estandar_total = fields.Decimal(as_string=True, places=2)
    margen_total = fields.Decimal(as_string=True, places=2)


class ClienteManualSchema(Schema):
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    apellidos = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    correo = fields.Email(required=True, validate=validate.Length(max=150))
    telefono = fields.Str(required=True, validate=validate.Regexp(r"^\d{10}$"))


class VentaManualLineaSchema(Schema):
    sku = fields.Str(required=True, validate=validate.Length(min=3, max=12))
    cantidad = fields.Int(required=True, validate=validate.Range(min=1, max=100))


class VentaManualSchema(Schema):
    cliente_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    cliente = fields.Nested(ClienteManualSchema, allow_none=True)
    lineas = fields.Nested(VentaManualLineaSchema, many=True, required=True)
    direccion = fields.Nested(DireccionCrearSchema, required=True)
    metodo_pago = fields.Str(required=True, validate=validate.OneOf(METODOS_MANUALES))
    estado_pago = fields.Str(
        load_default="PAGADA", validate=validate.OneOf(["PAGADA", "PENDIENTE"])
    )
    medio_pago_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    numero_tarjeta = fields.Str(allow_none=True, validate=validate.Regexp(r"^\d{16}$"))
    titular = fields.Str(allow_none=True, validate=validate.Length(max=100))
    vence_mes = fields.Int(allow_none=True, validate=validate.Range(min=1, max=12))
    vence_anio = fields.Int(allow_none=True, validate=validate.Range(min=2000, max=2200))
    cvv = fields.Str(allow_none=True, validate=validate.Regexp(r"^\d{3,4}$"))
    descuento_codigo = fields.Str(allow_none=True, validate=validate.Length(max=20))
    requiere_factura = fields.Bool(load_default=False)
    rfc = fields.Str(allow_none=True, validate=validate.Length(min=12, max=13))
    razon_social = fields.Str(allow_none=True, validate=validate.Length(max=120))
    cp_fiscal = fields.Str(allow_none=True, validate=validate.Regexp(r"^\d{5}$"))
    notas = fields.Str(allow_none=True, validate=validate.Length(max=500))


class VentaPagoSchema(Schema):
    accion = fields.Str(
        load_default="APROBAR", validate=validate.OneOf(["APROBAR", "RECHAZAR"])
    )
    metodo_pago = fields.Str(validate=validate.OneOf(METODOS_MANUALES))
    medio_pago_id = fields.Int(allow_none=True, validate=validate.Range(min=1))
    numero_tarjeta = fields.Str(allow_none=True, validate=validate.Regexp(r"^\d{16}$"))
    titular = fields.Str(allow_none=True, validate=validate.Length(max=100))
    vence_mes = fields.Int(allow_none=True, validate=validate.Range(min=1, max=12))
    vence_anio = fields.Int(allow_none=True, validate=validate.Range(min=2000, max=2200))
    cvv = fields.Str(allow_none=True, validate=validate.Regexp(r"^\d{3,4}$"))
    motivo = fields.Str(allow_none=True, validate=validate.Length(max=300))


class VentaCancelarSchema(Schema):
    motivo = fields.Str(required=True, validate=validate.Length(min=3, max=300))


class VentaReembolsoSchema(Schema):
    monto = fields.Decimal(allow_none=True, places=2)
    motivo = fields.Str(required=True, validate=validate.Length(min=3, max=300))


class DescuentoFiltrosSchema(Schema):
    activo = fields.Bool(allow_none=True)
    aplicacion = fields.Str(validate=validate.OneOf(APLICACIONES_DESCUENTO))
    q = fields.Str(validate=validate.Length(max=100))

    class Meta:
        unknown = EXCLUDE


class DescuentoSchema(Schema):
    id = fields.Int()
    codigo = fields.Str(allow_none=True)
    nombre = fields.Str()
    tipo = fields.Str()
    valor = fields.Decimal(as_string=True, places=2)
    aplicacion = fields.Str()
    solo_primera_compra = fields.Bool()
    monto_minimo = fields.Decimal(as_string=True, places=2, allow_none=True)
    min_articulos = fields.Int(allow_none=True)
    usos_maximos = fields.Int(allow_none=True)
    usos_por_cliente = fields.Int()
    usos_actuales = fields.Int()
    activo = fields.Bool()
    vigente_desde = fields.Str()
    vigente_hasta = fields.Str(allow_none=True)


class DescuentoCrearSchema(Schema):
    codigo = fields.Str(allow_none=True, validate=validate.Length(min=1, max=20))
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    tipo = fields.Str(required=True, validate=validate.OneOf(TIPOS_DESCUENTO))
    valor = fields.Decimal(required=True, places=2)
    aplicacion = fields.Str(required=True, validate=validate.OneOf(APLICACIONES_DESCUENTO))
    solo_primera_compra = fields.Bool(load_default=False)
    monto_minimo = fields.Decimal(allow_none=True, places=2)
    min_articulos = fields.Int(allow_none=True, validate=validate.Range(min=1))
    vigente_desde = fields.Date(required=True)
    vigente_hasta = fields.Date(allow_none=True)
    usos_maximos = fields.Int(allow_none=True, validate=validate.Range(min=0))
    usos_por_cliente = fields.Int(load_default=1, validate=validate.Range(min=1))
    activo = fields.Bool(load_default=True)


class DescuentoActualizarSchema(Schema):
    codigo = fields.Str(allow_none=True, validate=validate.Length(min=1, max=20))
    nombre = fields.Str(validate=validate.Length(min=1, max=100))
    tipo = fields.Str(validate=validate.OneOf(TIPOS_DESCUENTO))
    valor = fields.Decimal(places=2)
    aplicacion = fields.Str(validate=validate.OneOf(APLICACIONES_DESCUENTO))
    solo_primera_compra = fields.Bool()
    monto_minimo = fields.Decimal(allow_none=True, places=2)
    min_articulos = fields.Int(allow_none=True, validate=validate.Range(min=1))
    vigente_desde = fields.Date()
    vigente_hasta = fields.Date(allow_none=True)
    usos_maximos = fields.Int(allow_none=True, validate=validate.Range(min=0))
    usos_por_cliente = fields.Int(validate=validate.Range(min=1))
    activo = fields.Bool()
