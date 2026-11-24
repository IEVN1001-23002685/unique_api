"""Preparacion, entregas, devoluciones y reglas de empaque."""

from app.extensions import db
from app.models.base import ModeloBase, ahora_utc, entero_unsigned, tabla_args


class Preparacion(ModeloBase):
    __tablename__ = "preparacion"
    __table_args__ = tabla_args(
        db.UniqueConstraint("pedido_id", name="uq_preparacion_pedido"),
        db.CheckConstraint(
            "estado IN ('POR_SURTIR', 'EN_PICKING', 'EN_VERIFICACION', "
            "'EN_EMPAQUE', 'LISTA')",
            name="ck_preparacion_estado",
        ),
    )

    pedido_id = db.Column(entero_unsigned(), db.ForeignKey("pedido.id"), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="POR_SURTIR")
    tomada_por = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=True)
    iniciada_en = db.Column(db.DateTime, nullable=True)
    terminada_en = db.Column(db.DateTime, nullable=True)
    notas = db.Column(db.Text, nullable=True)

    pedido = db.relationship("Pedido", foreign_keys=[pedido_id])
    operario = db.relationship("Usuario", foreign_keys=[tomada_por])


class PreparacionLinea(ModeloBase):
    __tablename__ = "preparacion_linea"
    __table_args__ = tabla_args(
        db.CheckConstraint("cantidad_requerida >= 0", name="ck_preparacion_requerida"),
        db.CheckConstraint("cantidad_surtida >= 0", name="ck_preparacion_surtida"),
        db.Index("ix_preparacion_linea_preparacion", "preparacion_id"),
        db.Index("ix_preparacion_linea_pedido", "pedido_linea_id"),
    )

    preparacion_id = db.Column(
        entero_unsigned(), db.ForeignKey("preparacion.id"), nullable=False
    )
    pedido_linea_id = db.Column(
        entero_unsigned(), db.ForeignKey("pedido_linea.id"), nullable=False
    )
    cantidad_requerida = db.Column(db.Integer, nullable=False)
    cantidad_surtida = db.Column(db.Integer, nullable=False, default=0)
    sku_verificado = db.Column(db.Boolean, nullable=False, default=False)
    diseno_verificado = db.Column(db.Boolean, nullable=False, default=False)
    etiquetas_verificadas = db.Column(db.Boolean, nullable=False, default=False)
    incidencia = db.Column(db.Text, nullable=True)

    preparacion = db.relationship("Preparacion", foreign_keys=[preparacion_id])
    pedido_linea = db.relationship("PedidoLinea", foreign_keys=[pedido_linea_id])


class EmpaqueRegla(ModeloBase):
    __tablename__ = "empaque_regla"
    __table_args__ = tabla_args(
        db.CheckConstraint(
            "base IN ('POR_PRENDA', 'POR_PEDIDO')", name="ck_empaque_regla_base"
        ),
        db.CheckConstraint("cantidad >= 0", name="ck_empaque_regla_cantidad"),
        db.Index("ix_empaque_regla_material", "material_id", "activa"),
    )

    material_id = db.Column(entero_unsigned(), db.ForeignKey("material.id"), nullable=False)
    base = db.Column(db.String(20), nullable=False)
    cantidad = db.Column(db.Numeric(8, 2), nullable=False)
    activa = db.Column(db.Boolean, nullable=False, default=True)

    material = db.relationship("Material", foreign_keys=[material_id])


class Repartidor(ModeloBase):
    __tablename__ = "repartidor"
    __table_args__ = tabla_args(db.Index("ix_repartidor_activo", "activo", "eliminado_en"))

    nombre = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(15), nullable=False)
    vehiculo = db.Column(db.String(60), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    eliminado_en = db.Column(db.DateTime, nullable=True)


class Entrega(ModeloBase):
    __tablename__ = "entrega"
    __table_args__ = tabla_args(
        db.UniqueConstraint("folio", name="uq_entrega_folio"),
        db.UniqueConstraint("pedido_id", "intento", name="uq_entrega_pedido_intento"),
        db.CheckConstraint("intento >= 1", name="ck_entrega_intento"),
        db.CheckConstraint(
            "estado IN ('PROGRAMADA', 'EN_RUTA', 'ENTREGADA', 'FALLIDA', 'CANCELADA')",
            name="ck_entrega_estado",
        ),
        db.CheckConstraint(
            "motivo_fallo IS NULL OR motivo_fallo IN "
            "('AUSENTE', 'DIRECCION_INCORRECTA', 'RECHAZADO', 'OTRO')",
            name="ck_entrega_motivo_fallo",
        ),
        db.Index("ix_entrega_repartidor", "repartidor_id", "fecha_programada"),
    )

    folio = db.Column(db.String(20), nullable=False)
    pedido_id = db.Column(entero_unsigned(), db.ForeignKey("pedido.id"), nullable=False)
    repartidor_id = db.Column(
        entero_unsigned(), db.ForeignKey("repartidor.id"), nullable=False
    )
    intento = db.Column(db.SmallInteger, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="PROGRAMADA")
    fecha_programada = db.Column(db.Date, nullable=False)
    salida_en = db.Column(db.DateTime, nullable=True)
    resultado_en = db.Column(db.DateTime, nullable=True)
    receptor = db.Column(db.String(100), nullable=True)
    motivo_fallo = db.Column(db.String(30), nullable=True)
    notas = db.Column(db.Text, nullable=True)

    pedido = db.relationship("Pedido", foreign_keys=[pedido_id])
    repartidor = db.relationship("Repartidor", foreign_keys=[repartidor_id])


class Devolucion(ModeloBase):
    __tablename__ = "devolucion"
    __table_args__ = tabla_args(
        db.UniqueConstraint("folio", name="uq_devolucion_folio"),
        db.CheckConstraint(
            "tipo IN ('DEVOLUCION', 'CAMBIO')", name="ck_devolucion_tipo"
        ),
        db.CheckConstraint(
            "motivo IN ('DEFECTO', 'AJUSTE', 'DANO_ENVIO', 'PRODUCTO_EQUIVOCADO', "
            "'ARREPENTIMIENTO')",
            name="ck_devolucion_motivo",
        ),
        db.CheckConstraint(
            "estado IN ('SOLICITADA', 'APROBADA', 'RECHAZADA', 'RECIBIDA', "
            "'RESUELTA')",
            name="ck_devolucion_estado",
        ),
        db.CheckConstraint(
            "resolucion IS NULL OR resolucion IN ('REEMBOLSO', 'CAMBIO', 'RECHAZO')",
            name="ck_devolucion_resolucion",
        ),
        db.CheckConstraint("reembolso_monto >= 0", name="ck_devolucion_reembolso"),
        db.Index("ix_devolucion_estado", "estado", "resuelta_en"),
    )

    folio = db.Column(db.String(20), nullable=False)
    venta_id = db.Column(entero_unsigned(), db.ForeignKey("venta.id"), nullable=False)
    usuario_id = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    motivo = db.Column(db.String(30), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="SOLICITADA")
    resolucion = db.Column(db.String(20), nullable=True)
    reembolso_monto = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    venta_reemplazo_id = db.Column(entero_unsigned(), db.ForeignKey("venta.id"), nullable=True)
    motivo_rechazo = db.Column(db.Text, nullable=True)
    resuelta_por = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=True)
    resuelta_en = db.Column(db.DateTime, nullable=True)

    venta = db.relationship("Venta", foreign_keys=[venta_id])
    venta_reemplazo = db.relationship("Venta", foreign_keys=[venta_reemplazo_id])
    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])
    resolvedor = db.relationship("Usuario", foreign_keys=[resuelta_por])


class DevolucionLinea(ModeloBase):
    __tablename__ = "devolucion_linea"
    __table_args__ = tabla_args(
        db.CheckConstraint("cantidad > 0", name="ck_devolucion_linea_cantidad"),
        db.CheckConstraint(
            "dictamen IN ('PENDIENTE', 'REINGRESO', 'MERMA')",
            name="ck_devolucion_linea_dictamen",
        ),
        db.Index("ix_devolucion_linea_devolucion", "devolucion_id"),
        db.Index("ix_devolucion_linea_venta", "venta_linea_id"),
    )

    devolucion_id = db.Column(
        entero_unsigned(), db.ForeignKey("devolucion.id"), nullable=False
    )
    venta_linea_id = db.Column(
        entero_unsigned(), db.ForeignKey("venta_linea.id"), nullable=False
    )
    cantidad = db.Column(db.Integer, nullable=False)
    variante_cambio_id = db.Column(
        entero_unsigned(), db.ForeignKey("variante_producto.id"), nullable=True
    )
    dictamen = db.Column(db.String(20), nullable=False, default="PENDIENTE")

    devolucion = db.relationship("Devolucion", foreign_keys=[devolucion_id])
    venta_linea = db.relationship("VentaLinea", foreign_keys=[venta_linea_id])
    variante_cambio = db.relationship("VarianteProducto", foreign_keys=[variante_cambio_id])


class DevolucionEvidencia(ModeloBase):
    __tablename__ = "devolucion_evidencia"
    __table_args__ = tabla_args(
        db.Index("ix_devolucion_evidencia_devolucion", "devolucion_id")
    )

    devolucion_id = db.Column(
        entero_unsigned(), db.ForeignKey("devolucion.id"), nullable=False
    )
    url = db.Column(db.String(500), nullable=False)

    devolucion = db.relationship("Devolucion", foreign_keys=[devolucion_id])
