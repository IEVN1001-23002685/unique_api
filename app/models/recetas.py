"""Recetas de produccion, sus lineas de material y aplicaciones de bordado."""

from app.extensions import db
from app.models.base import ModeloBase, ahora_utc, entero_unsigned, tabla_args


class Receta(ModeloBase):
    __tablename__ = "receta"
    __table_args__ = tabla_args(
        db.UniqueConstraint(
            "producto_id", "talla_id", "version", name="uq_receta_producto_talla_version"
        ),
        db.CheckConstraint(
            "estado IN ('BORRADOR', 'VIGENTE', 'ARCHIVADA')", name="ck_receta_estado"
        ),
        db.Index("ix_receta_producto_talla", "producto_id", "talla_id", "estado"),
    )

    producto_id = db.Column(entero_unsigned(), db.ForeignKey("producto.id"), nullable=False)
    talla_id = db.Column(entero_unsigned(), db.ForeignKey("talla.id"), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="BORRADOR")
    origen_receta_id = db.Column(entero_unsigned(), db.ForeignKey("receta.id"), nullable=True)
    mano_obra = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    costo_bordado = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    costos_indirectos = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    nota = db.Column(db.Text, nullable=True)
    creada_por = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=True)
    activada_en = db.Column(db.DateTime, nullable=True)

    producto = db.relationship("Producto", foreign_keys=[producto_id])
    talla = db.relationship("Talla", foreign_keys=[talla_id])


class RecetaLinea(ModeloBase):
    __tablename__ = "receta_linea"
    __table_args__ = tabla_args(
        db.CheckConstraint("cantidad_neta >= 0", name="ck_receta_linea_neta"),
        db.CheckConstraint("factor_consumo > 0", name="ck_receta_linea_factor"),
        db.CheckConstraint(
            "merma_pct >= 0 AND merma_pct < 100", name="ck_receta_linea_merma"
        ),
        db.Index("ix_receta_linea_receta", "receta_id"),
        db.Index("ix_receta_linea_material", "material_id"),
    )

    receta_id = db.Column(entero_unsigned(), db.ForeignKey("receta.id"), nullable=False)
    material_id = db.Column(entero_unsigned(), db.ForeignKey("material.id"), nullable=False)
    cantidad_neta = db.Column(db.Numeric(12, 4), nullable=False)
    factor_consumo = db.Column(db.Numeric(6, 3), nullable=False, default=1)
    merma_pct = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    cantidad_bruta = db.Column(db.Numeric(12, 4), nullable=False)
    nota = db.Column(db.Text, nullable=True)

    receta = db.relationship("Receta", foreign_keys=[receta_id])
    material = db.relationship("Material", foreign_keys=[material_id])


class RecetaBordado(ModeloBase):
    __tablename__ = "receta_bordado"
    __table_args__ = tabla_args(
        db.CheckConstraint("aplicaciones >= 1", name="ck_receta_bordado_aplicaciones"),
        db.Index("ix_receta_bordado_receta", "receta_id"),
    )

    receta_id = db.Column(entero_unsigned(), db.ForeignKey("receta.id"), nullable=False)
    diseno_id = db.Column(
        entero_unsigned(), db.ForeignKey("diseno_bordado.id"), nullable=False
    )
    aplicaciones = db.Column(db.SmallInteger, nullable=False, default=1)
    ubicacion = db.Column(db.String(60), nullable=True)

    receta = db.relationship("Receta", foreign_keys=[receta_id])
    diseno = db.relationship("DisenoBordado", foreign_keys=[diseno_id])
