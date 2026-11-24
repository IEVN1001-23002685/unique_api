"""Carrito, descuentos, ventas e historial de pago (dominio M08)."""

from app.extensions import db
from app.models.base import ModeloBase, ahora_utc, entero_unsigned, tabla_args


class Carrito(ModeloBase):
    __tablename__ = "carrito"
    __table_args__ = tabla_args(
        db.CheckConstraint(
            "estado IN ('ABIERTO', 'CONVERTIDO', 'ABANDONADO')",
            name="ck_carrito_estado",
        ),
        db.Index("ix_carrito_usuario_estado", "usuario_id", "estado"),
    )

    usuario_id = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="ABIERTO")

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])


class CarritoLinea(ModeloBase):
    __tablename__ = "carrito_linea"
    __table_args__ = tabla_args(
        db.UniqueConstraint("carrito_id", "variante_id", name="uq_carrito_variante"),
        db.CheckConstraint("cantidad > 0", name="ck_carrito_linea_cantidad"),
    )

    carrito_id = db.Column(entero_unsigned(), db.ForeignKey("carrito.id"), nullable=False)
    variante_id = db.Column(
        entero_unsigned(), db.ForeignKey("variante_producto.id"), nullable=False
    )
    cantidad = db.Column(db.Integer, nullable=False)

    carrito = db.relationship("Carrito", foreign_keys=[carrito_id])
    variante = db.relationship("VarianteProducto", foreign_keys=[variante_id])


class Descuento(ModeloBase):
    __tablename__ = "descuento"
    __table_args__ = tabla_args(
        db.UniqueConstraint("codigo", name="uq_descuento_codigo"),
        db.CheckConstraint(
            "tipo IN ('PORCENTAJE', 'MONTO')", name="ck_descuento_tipo"
        ),
        db.CheckConstraint(
            "aplicacion IN ('CUPON', 'AUTOMATICO')", name="ck_descuento_aplicacion"
        ),
        db.CheckConstraint("valor >= 0", name="ck_descuento_valor"),
        db.Index("ix_descuento_activo", "activo", "vigente_desde"),
    )

    codigo = db.Column(db.String(20), nullable=True)
    nombre = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    valor = db.Column(db.Numeric(8, 2), nullable=False)
    aplicacion = db.Column(db.String(20), nullable=False)
    solo_primera_compra = db.Column(db.Boolean, nullable=False, default=False)
    monto_minimo = db.Column(db.Numeric(12, 2), nullable=True)
    min_articulos = db.Column(db.Integer, nullable=True)
    vigente_desde = db.Column(
        db.Date, nullable=False, default=lambda: ahora_utc().date()
    )
    vigente_hasta = db.Column(db.Date, nullable=True)
    usos_maximos = db.Column(db.Integer, nullable=True)
    usos_por_cliente = db.Column(db.Integer, nullable=False, default=1)
    usos_actuales = db.Column(db.Integer, nullable=False, default=0)
    activo = db.Column(db.Boolean, nullable=False, default=True)


class Venta(ModeloBase):
    __tablename__ = "venta"
    __table_args__ = tabla_args(
        db.UniqueConstraint("folio", name="uq_venta_folio"),
        db.CheckConstraint(
            "estado IN ('ACTIVA', 'CANCELADA')", name="ck_venta_estado"
        ),
        db.CheckConstraint(
            "estado_pago IN ('PENDIENTE', 'PAGADA', 'REEMBOLSADA_PARCIAL', "
            "'REEMBOLSADA')",
            name="ck_venta_estado_pago",
        ),
        db.CheckConstraint(
            "canal IN ('TIENDA', 'MANUAL', 'CAMBIO')", name="ck_venta_canal"
        ),
        db.CheckConstraint("total >= 0", name="ck_venta_total"),
        db.Index("ix_venta_fecha", "fecha", "estado"),
        db.Index("ix_venta_usuario", "usuario_id"),
    )

    folio = db.Column(db.String(20), nullable=False)
    usuario_id = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    canal = db.Column(db.String(20), nullable=False)
    fecha = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    estado = db.Column(db.String(20), nullable=False, default="ACTIVA")
    estado_pago = db.Column(db.String(30), nullable=False, default="PENDIENTE")
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    descuento_id = db.Column(entero_unsigned(), db.ForeignKey("descuento.id"), nullable=True)
    descuento_monto = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tarifa_envio_id = db.Column(
        entero_unsigned(), db.ForeignKey("tarifa_envio.id"), nullable=True
    )
    costo_envio = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(12, 2), nullable=False)
    iva_incluido = db.Column(db.Boolean, nullable=False, default=True)
    requiere_factura = db.Column(db.Boolean, nullable=False, default=False)
    fecha_promesa = db.Column(db.Date, nullable=True)
    cancelada_en = db.Column(db.DateTime, nullable=True)
    motivo_cancelacion = db.Column(db.Text, nullable=True)
    creada_por = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=True)
    notas = db.Column(db.Text, nullable=True)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])
    descuento = db.relationship("Descuento", foreign_keys=[descuento_id])
    tarifa_envio = db.relationship("TarifaEnvio", foreign_keys=[tarifa_envio_id])


class VentaLinea(ModeloBase):
    __tablename__ = "venta_linea"
    __table_args__ = tabla_args(
        db.CheckConstraint("cantidad > 0", name="ck_venta_linea_cantidad"),
        db.Index("ix_venta_linea_venta", "venta_id"),
        db.Index("ix_venta_linea_sku", "sku"),
    )

    venta_id = db.Column(entero_unsigned(), db.ForeignKey("venta.id"), nullable=False)
    variante_id = db.Column(
        entero_unsigned(), db.ForeignKey("variante_producto.id"), nullable=False
    )
    sku = db.Column(db.String(12), nullable=False)
    nombre_producto = db.Column(db.String(120), nullable=False)
    talla = db.Column(db.String(20), nullable=False)
    color = db.Column(db.String(20), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Numeric(12, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    costo_estandar_unitario = db.Column(db.Numeric(12, 6), nullable=False)

    venta = db.relationship("Venta", foreign_keys=[venta_id])
    variante = db.relationship("VarianteProducto", foreign_keys=[variante_id])


class VentaDireccion(ModeloBase):
    __tablename__ = "venta_direccion"
    __table_args__ = tabla_args(
        db.UniqueConstraint("venta_id", "tipo", name="uq_venta_direccion_tipo")
    )

    venta_id = db.Column(entero_unsigned(), db.ForeignKey("venta.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    destinatario = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(10), nullable=False)
    calle = db.Column(db.String(120), nullable=False)
    numero_ext = db.Column(db.String(10), nullable=False)
    numero_int = db.Column(db.String(10), nullable=True)
    colonia = db.Column(db.String(80), nullable=False)
    municipio = db.Column(db.String(80), nullable=False)
    estado = db.Column(db.String(60), nullable=False)
    codigo_postal = db.Column(db.String(5), nullable=False)
    referencia = db.Column(db.Text, nullable=True)
    rfc = db.Column(db.String(13), nullable=True)
    razon_social = db.Column(db.String(120), nullable=True)

    venta = db.relationship("Venta", foreign_keys=[venta_id])


class Pago(ModeloBase):
    __tablename__ = "pago"
    __table_args__ = tabla_args(
        db.CheckConstraint("tipo IN ('COBRO', 'REEMBOLSO')", name="ck_pago_tipo"),
        db.CheckConstraint(
            "metodo IN ('TARJETA', 'CUENTA', 'TRANSFERENCIA', 'EFECTIVO')",
            name="ck_pago_metodo",
        ),
        db.CheckConstraint(
            "estado IN ('APROBADO', 'PENDIENTE', 'RECHAZADO')", name="ck_pago_estado"
        ),
        db.Index("ix_pago_venta", "venta_id", "fecha"),
    )

    venta_id = db.Column(entero_unsigned(), db.ForeignKey("venta.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    metodo = db.Column(db.String(20), nullable=False)
    estado = db.Column(db.String(20), nullable=False)
    medio_pago_id = db.Column(
        entero_unsigned(), db.ForeignKey("medio_pago.id"), nullable=True
    )
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    referencia = db.Column(db.String(40), nullable=False)
    ultimos4 = db.Column(db.String(4), nullable=True)
    titular = db.Column(db.String(100), nullable=True)
    motivo_rechazo = db.Column(db.Text, nullable=True)
    registrado_por = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=True)
    fecha = db.Column(db.DateTime, nullable=False, default=ahora_utc)

    venta = db.relationship("Venta", foreign_keys=[venta_id])
    medio_pago = db.relationship("MedioPago", foreign_keys=[medio_pago_id])
