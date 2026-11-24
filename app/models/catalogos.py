"""Catalogos basicos del sistema."""

from app.extensions import db
from app.models.base import ModeloBase, tabla_args


class Color(ModeloBase):
    __tablename__ = "color"
    __table_args__ = tabla_args(db.UniqueConstraint("codigo", name="uq_color_codigo"))

    codigo = db.Column(db.String(2), nullable=False)
    nombre = db.Column(db.String(40), nullable=False)
    hex = db.Column(db.String(7), nullable=False)
    es_comercial = db.Column(db.Boolean, nullable=False, default=False)


class Talla(ModeloBase):
    __tablename__ = "talla"
    __table_args__ = tabla_args(db.UniqueConstraint("codigo", name="uq_talla_codigo"))

    codigo = db.Column(db.String(2), nullable=False)
    nombre = db.Column(db.String(40), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)


class CategoriaProducto(ModeloBase):
    __tablename__ = "categoria_producto"
    __table_args__ = tabla_args(
        db.UniqueConstraint("nombre", name="uq_categoria_producto_nombre"),
        db.UniqueConstraint("prefijo_sku", name="uq_categoria_producto_prefijo"),
    )

    nombre = db.Column(db.String(60), nullable=False)
    prefijo_sku = db.Column(db.String(2), nullable=False)
    usa_tallas = db.Column(db.Boolean, nullable=False, default=True)
    activa = db.Column(db.Boolean, nullable=False, default=True)


class CategoriaMaterial(ModeloBase):
    __tablename__ = "categoria_material"
    __table_args__ = tabla_args(
        db.UniqueConstraint("nombre", name="uq_categoria_material_nombre")
    )

    nombre = db.Column(db.String(60), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)


class CausaMerma(ModeloBase):
    __tablename__ = "causa_merma"
    __table_args__ = tabla_args(
        db.UniqueConstraint("nombre", name="uq_causa_merma_nombre"),
        db.CheckConstraint(
            "aplica_a IN ('MATERIAL', 'PRODUCTO', 'AMBOS')",
            name="ck_causa_merma_aplica_a",
        ),
    )

    nombre = db.Column(db.String(80), nullable=False)
    aplica_a = db.Column(db.String(20), nullable=False)
    etapa_sugerida = db.Column(db.String(30), nullable=True)
    activa = db.Column(db.Boolean, nullable=False, default=True)


class TarifaEnvio(ModeloBase):
    __tablename__ = "tarifa_envio"
    __table_args__ = tabla_args(
        db.CheckConstraint("cp_inicio <= cp_fin", name="ck_tarifa_envio_rango"),
        db.CheckConstraint("costo >= 0", name="ck_tarifa_envio_costo"),
        db.Index("ix_tarifa_envio_cp", "cp_inicio", "cp_fin", "activa"),
    )

    nombre = db.Column(db.String(60), nullable=False)
    cp_inicio = db.Column(db.String(5), nullable=False)
    cp_fin = db.Column(db.String(5), nullable=False)
    costo = db.Column(db.Numeric(8, 2), nullable=False)
    dias_estimados = db.Column(db.Integer, nullable=False)
    activa = db.Column(db.Boolean, nullable=False, default=True)
