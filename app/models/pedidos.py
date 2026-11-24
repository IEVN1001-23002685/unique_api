"""Pedidos y su seguimiento (dominio M09, separado de ventas)."""

from app.extensions import db
from app.models.base import ModeloBase, ahora_utc, entero_unsigned, tabla_args


class Pedido(ModeloBase):
    __tablename__ = "pedido"
    __table_args__ = tabla_args(
        db.UniqueConstraint("venta_id", name="uq_pedido_venta"),
        db.CheckConstraint(
            "estado IN ('RECIBIDO', 'CONFIRMADO', 'EN_PRODUCCION', 'EN_PREPARACION', "
            "'LISTO_ENVIO', 'EN_REPARTO', 'ENTREGADO', 'CANCELADO')",
            name="ck_pedido_estado",
        ),
        db.CheckConstraint(
            "prioridad IN ('NORMAL', 'ALTA')", name="ck_pedido_prioridad"
        ),
        db.Index("ix_pedido_estado_desde", "estado", "estado_desde"),
    )

    venta_id = db.Column(entero_unsigned(), db.ForeignKey("venta.id"), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="RECIBIDO")
    estado_desde = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    fecha_promesa = db.Column(db.Date, nullable=True)
    entregado_en = db.Column(db.DateTime, nullable=True)
    prioridad = db.Column(db.String(10), nullable=False, default="NORMAL")

    venta = db.relationship("Venta", foreign_keys=[venta_id])


class PedidoLinea(ModeloBase):
    __tablename__ = "pedido_linea"
    __table_args__ = tabla_args(
        db.UniqueConstraint("venta_linea_id", name="uq_pedido_linea_venta_linea"),
        db.CheckConstraint("cantidad >= 0", name="ck_pedido_linea_cantidad"),
        db.CheckConstraint("cant_reservada >= 0", name="ck_pedido_linea_reservada"),
        db.CheckConstraint("cant_pendiente >= 0", name="ck_pedido_linea_pendiente"),
        db.CheckConstraint("cant_preparada >= 0", name="ck_pedido_linea_preparada"),
        db.CheckConstraint(
            "cant_reservada + cant_pendiente = cantidad",
            name="ck_pedido_linea_reserva_pendiente",
        ),
        db.CheckConstraint(
            "cant_preparada <= cantidad", name="ck_pedido_linea_preparada_limite"
        ),
        db.Index("ix_pedido_linea_pedido", "pedido_id"),
    )

    pedido_id = db.Column(entero_unsigned(), db.ForeignKey("pedido.id"), nullable=False)
    venta_linea_id = db.Column(
        entero_unsigned(), db.ForeignKey("venta_linea.id"), nullable=False
    )
    cantidad = db.Column(db.Integer, nullable=False)
    cant_reservada = db.Column(db.Integer, nullable=False, default=0)
    cant_pendiente = db.Column(db.Integer, nullable=False, default=0)
    cant_preparada = db.Column(db.Integer, nullable=False, default=0)

    pedido = db.relationship("Pedido", foreign_keys=[pedido_id])
    venta_linea = db.relationship("VentaLinea", foreign_keys=[venta_linea_id])


class PedidoEvento(ModeloBase):
    __tablename__ = "pedido_evento"
    __table_args__ = tabla_args(
        db.Index("ix_pedido_evento_pedido", "pedido_id", "fecha")
    )

    pedido_id = db.Column(entero_unsigned(), db.ForeignKey("pedido.id"), nullable=False)
    estado = db.Column(db.String(20), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    usuario_id = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=True)
    visible_cliente = db.Column(db.Boolean, nullable=False, default=False)
    fecha = db.Column(db.DateTime, nullable=False, default=ahora_utc)

    pedido = db.relationship("Pedido", foreign_keys=[pedido_id])
    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])
