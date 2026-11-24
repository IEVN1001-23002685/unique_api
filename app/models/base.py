"""Definiciones compartidas por todos los modelos de persistencia de UNIQUE."""

from datetime import datetime, timezone

from sqlalchemy.dialects.mysql import INTEGER as MySQLInteger

from app.extensions import db


def entero_unsigned():
    """Tipo entero UNSIGNED en MySQL y entero estándar en otros dialectos."""
    return db.Integer().with_variant(MySQLInteger(unsigned=True), "mysql")


OPCIONES_MYSQL = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


def ahora_utc() -> datetime:
    """Devuelve la hora UTC como ``datetime`` naive para columnas DATETIME de MySQL."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def tabla_args(*restricciones):
    """Combina restricciones de tabla con las opciones de almacenamiento MySQL."""
    opciones = OPCIONES_MYSQL.copy()
    if restricciones:
        return (*restricciones, opciones)
    return opciones


class ModeloBase(db.Model):
    __abstract__ = True
    __table_args__ = tabla_args()

    id = db.Column(entero_unsigned(), primary_key=True, autoincrement=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    actualizado_en = db.Column(
        db.DateTime, nullable=False, default=ahora_utc, onupdate=ahora_utc
    )
