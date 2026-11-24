"""Almacen persistente de claves idempotentes de operaciones criticas."""

from app.extensions import db
from app.models.base import ahora_utc, tabla_args


class IdempotenciaOperacion(db.Model):
    __tablename__ = "idempotencia_operacion"
    __table_args__ = tabla_args(
        db.Index("ix_idempotencia_alcance_estado", "alcance", "estado")
    )

    clave = db.Column(db.String(255), primary_key=True)
    alcance = db.Column(db.String(80), nullable=False)
    hash_peticion = db.Column(db.String(64), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="PENDIENTE")
    respuesta = db.Column(db.JSON, nullable=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    actualizado_en = db.Column(
        db.DateTime, nullable=False, default=ahora_utc, onupdate=ahora_utc
    )
