"""Alertas operativas y administrativas del sistema."""

from app.extensions import db
from app.models.base import ModeloBase, ahora_utc, entero_unsigned, tabla_args


class Alerta(ModeloBase):
    __tablename__ = "alerta"
    __table_args__ = tabla_args(
        db.UniqueConstraint("clave_unica", name="uq_alerta_clave_unica"),
        db.CheckConstraint(
            "severidad IN ('INFORMATIVA', 'PREVENTIVA', 'CRITICA')",
            name="ck_alerta_severidad",
        ),
        db.CheckConstraint(
            "rol_destino IN ('ADMIN', 'OPERATIVO', 'AMBOS')",
            name="ck_alerta_rol_destino",
        ),
        db.CheckConstraint(
            "estado IN ('ABIERTA', 'ATENDIDA', 'RESUELTA_AUTO')",
            name="ck_alerta_estado",
        ),
        db.Index("ix_alerta_estado_tipo", "estado", "tipo"),
        db.Index("ix_alerta_entidad", "entidad_tipo", "entidad_id"),
    )

    tipo = db.Column(db.String(30), nullable=False)
    severidad = db.Column(db.String(20), nullable=False)
    titulo = db.Column(db.String(150), nullable=False)
    detalle = db.Column(db.Text, nullable=False)
    entidad_tipo = db.Column(db.String(40), nullable=False)
    entidad_id = db.Column(entero_unsigned(), nullable=False)
    rol_destino = db.Column(db.String(20), nullable=False)
    accion_sugerida = db.Column(db.String(100), nullable=True)
    estado = db.Column(db.String(20), nullable=False, default="ABIERTA")
    clave_unica = db.Column(db.String(80), nullable=True)
    atendida_por = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=True)
    atendida_en = db.Column(db.DateTime, nullable=True)

    atendedor = db.relationship("Usuario", foreign_keys=[atendida_por])
