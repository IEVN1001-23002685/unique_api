"""Datos privados del cliente: direcciones y medios de pago simulados."""

from app.extensions import db
from app.models.base import ModeloBase, entero_unsigned, tabla_args


class Direccion(ModeloBase):
    __tablename__ = "direccion"
    __table_args__ = tabla_args(
        db.CheckConstraint(
            "tipo IN ('ENVIO', 'FACTURACION')", name="ck_direccion_tipo"
        ),
        db.Index("ix_direccion_usuario", "usuario_id", "activa"),
    )

    usuario_id = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    alias = db.Column(db.String(40), nullable=False)
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
    predeterminada = db.Column(db.Boolean, nullable=False, default=False)
    activa = db.Column(db.Boolean, nullable=False, default=True)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])


class MedioPago(ModeloBase):
    __tablename__ = "medio_pago"
    __table_args__ = tabla_args(
        db.CheckConstraint("tipo IN ('TARJETA', 'CUENTA')", name="ck_medio_pago_tipo"),
        db.CheckConstraint(
            "saldo_simulado IS NULL OR saldo_simulado >= 0",
            name="ck_medio_pago_saldo",
        ),
        db.Index("ix_medio_pago_usuario", "usuario_id", "activo"),
    )

    usuario_id = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    alias = db.Column(db.String(40), nullable=False)
    titular = db.Column(db.String(100), nullable=False)
    ultimos4 = db.Column(db.String(4), nullable=False)
    marca = db.Column(db.String(40), nullable=True)
    vence_mes = db.Column(db.SmallInteger, nullable=True)
    vence_anio = db.Column(db.SmallInteger, nullable=True)
    saldo_simulado = db.Column(db.Numeric(12, 2), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])
