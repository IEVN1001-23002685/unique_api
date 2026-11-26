"""Modelos de seguridad, auditoria y configuracion del sistema."""

from app.extensions import db
from app.models.base import ModeloBase, ahora_utc, entero_unsigned, tabla_args


class Rol(ModeloBase):
    __tablename__ = "rol"
    __table_args__ = tabla_args(db.UniqueConstraint("codigo", name="uq_rol_codigo"))

    codigo = db.Column(db.String(20), nullable=False)
    nombre = db.Column(db.String(60), nullable=False)


class Usuario(ModeloBase):
    __tablename__ = "usuario"
    __table_args__ = tabla_args(
        db.UniqueConstraint("correo", name="uq_usuario_correo"),
        db.CheckConstraint(
            "estado_cuenta IN ('ACTIVA', 'SIN_ACCESO', 'BLOQUEADA', 'INACTIVA')",
            name="ck_usuario_estado_cuenta",
        ),
        db.CheckConstraint("intentos_fallidos >= 0", name="ck_usuario_intentos"),
        db.Index("ix_usuario_rol", "rol_id"),
        db.Index("ix_usuario_estado", "estado_cuenta"),
    )

    rol_id = db.Column(entero_unsigned(), db.ForeignKey("rol.id"), nullable=False)
    nombre = db.Column(db.String(80), nullable=False)
    apellidos = db.Column(db.String(120), nullable=False)
    correo = db.Column(db.String(150), nullable=False)
    telefono = db.Column(db.String(10), nullable=False)
    password_hash = db.Column(db.Text, nullable=True)
    estado_cuenta = db.Column(db.String(20), nullable=False, default="ACTIVA")
    intentos_fallidos = db.Column(db.Integer, nullable=False, default=0)
    bloqueado_hasta = db.Column(db.DateTime, nullable=True)
    ultimo_acceso = db.Column(db.DateTime, nullable=True)
    acepta_privacidad = db.Column(db.Boolean, nullable=False, default=False)
    acepta_promociones = db.Column(db.Boolean, nullable=False, default=False)

    rol = db.relationship("Rol", foreign_keys=[rol_id])


class TokenRefresco(ModeloBase):
    __tablename__ = "token_refresco"
    __table_args__ = tabla_args(
        db.UniqueConstraint("token_hash", name="uq_token_refresco_hash"),
        db.Index("ix_token_refresco_usuario", "usuario_id"),
    )

    usuario_id = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False)
    expira_en = db.Column(db.DateTime, nullable=False)
    revocado = db.Column(db.Boolean, nullable=False, default=False)
    ip = db.Column(db.String(45), nullable=True)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])


class RecuperacionContrasena(ModeloBase):
    __tablename__ = "recuperacion_contrasena"
    __table_args__ = tabla_args(
        db.UniqueConstraint("token_hash", name="uq_recuperacion_hash"),
        db.Index("ix_recuperacion_usuario", "usuario_id"),
    )

    usuario_id = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False)
    expira_en = db.Column(db.DateTime, nullable=False)
    usado = db.Column(db.Boolean, nullable=False, default=False)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])


class Bitacora(ModeloBase):
    __tablename__ = "bitacora"
    __table_args__ = tabla_args(
        db.Index("ix_bitacora_entidad", "entidad", "entidad_id"),
        db.Index("ix_bitacora_fecha", "fecha"),
    )

    usuario_id = db.Column(
        entero_unsigned(), db.ForeignKey("usuario.id"), nullable=True
    )
    accion = db.Column(db.String(80), nullable=False)
    entidad = db.Column(db.String(60), nullable=False)
    entidad_id = db.Column(entero_unsigned(), nullable=True)
    detalle = db.Column(db.JSON, nullable=False, default=dict)
    ip = db.Column(db.String(45), nullable=True)
    fecha = db.Column(db.DateTime, nullable=False, default=ahora_utc)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])


class Configuracion(db.Model):
    __tablename__ = "configuracion"
    __table_args__ = tabla_args()

    clave = db.Column(db.String(60), primary_key=True)
    valor = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    actualizado_en = db.Column(
        db.DateTime, nullable=False, default=ahora_utc, onupdate=ahora_utc
    )


class SecuenciaFolio(db.Model):
    __tablename__ = "secuencia_folio"
    __table_args__ = tabla_args()

    prefijo = db.Column(db.String(20), primary_key=True)
    anio = db.Column(db.SmallInteger, primary_key=True)
    ultimo = db.Column(db.Integer, nullable=False, default=0)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    actualizado_en = db.Column(
        db.DateTime, nullable=False, default=ahora_utc, onupdate=ahora_utc
    )
