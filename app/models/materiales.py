"""Catalogo de materia prima, inventario por color, lotes y movimientos."""

from app.extensions import db
from app.models.base import ModeloBase, ahora_utc, entero_unsigned, tabla_args


class Material(ModeloBase):
    __tablename__ = "material"
    __table_args__ = tabla_args(
        db.UniqueConstraint("codigo", name="uq_material_codigo"),
        db.CheckConstraint(
            "unidad_base IN ('M2', 'M', 'PZA')", name="ck_material_unidad_base"
        ),
        db.CheckConstraint("factor_compra_base > 0", name="ck_material_factor"),
        db.CheckConstraint(
            "merma_estandar_pct >= 0 AND merma_estandar_pct < 100",
            name="ck_material_merma",
        ),
        db.Index("ix_material_categoria", "categoria_material_id", "activo"),
    )

    categoria_material_id = db.Column(
        entero_unsigned(), db.ForeignKey("categoria_material.id"), nullable=False
    )
    codigo = db.Column(db.String(12), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    unidad_base = db.Column(db.String(4), nullable=False)
    unidad_compra = db.Column(db.String(40), nullable=False)
    factor_compra_base = db.Column(db.Numeric(12, 4), nullable=False)
    costo_estandar_base = db.Column(db.Numeric(12, 6), nullable=False)
    merma_estandar_pct = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    por_color = db.Column(db.Boolean, nullable=False, default=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    eliminado_en = db.Column(db.DateTime, nullable=True)

    categoria = db.relationship("CategoriaMaterial", foreign_keys=[categoria_material_id])


class InventarioMaterial(ModeloBase):
    __tablename__ = "inventario_material"
    __table_args__ = tabla_args(
        db.UniqueConstraint("material_id", "color_id", name="uq_inventario_material"),
        db.CheckConstraint("stock_minimo >= 0", name="ck_inventario_material_minimo"),
        db.CheckConstraint("stock_seguridad >= 0", name="ck_inventario_material_seguridad"),
        db.Index("ix_inventario_material_material", "material_id", "activo"),
    )

    material_id = db.Column(entero_unsigned(), db.ForeignKey("material.id"), nullable=False)
    color_id = db.Column(entero_unsigned(), db.ForeignKey("color.id"), nullable=False)
    stock_minimo = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    stock_seguridad = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    consumo_diario_manual = db.Column(db.Numeric(12, 4), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    material = db.relationship("Material", foreign_keys=[material_id])
    color = db.relationship("Color", foreign_keys=[color_id])


class LoteMaterial(ModeloBase):
    __tablename__ = "lote_material"
    __table_args__ = tabla_args(
        db.UniqueConstraint("folio", name="uq_lote_material_folio"),
        db.CheckConstraint("cantidad_base_recibida >= 0", name="ck_lote_recibida"),
        db.CheckConstraint("cantidad_base_disponible >= 0", name="ck_lote_disponible"),
        db.CheckConstraint(
            "estado IN ('DISPONIBLE', 'AGOTADO')", name="ck_lote_material_estado"
        ),
        db.Index(
            "ix_lote_material_peps", "inventario_material_id", "fecha_entrada"
        ),
    )

    inventario_material_id = db.Column(
        entero_unsigned(), db.ForeignKey("inventario_material.id"), nullable=False
    )
    folio = db.Column(db.String(20), nullable=False)
    recepcion_linea_id = db.Column(
        entero_unsigned(), db.ForeignKey("recepcion_linea.id"), nullable=True
    )
    proveedor_id = db.Column(
        entero_unsigned(), db.ForeignKey("proveedor.id"), nullable=True
    )
    fecha_entrada = db.Column(db.Date, nullable=False)

    cantidad_base_recibida = db.Column(db.Numeric(12, 4), nullable=False)
    cantidad_base_disponible = db.Column(db.Numeric(12, 4), nullable=False)
    costo_total = db.Column(db.Numeric(12, 2), nullable=False)
    costo_unitario_base = db.Column(db.Numeric(12, 6), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="DISPONIBLE")

    inventario_material = db.relationship(
        "InventarioMaterial", foreign_keys=[inventario_material_id]
    )
    proveedor = db.relationship("Proveedor", foreign_keys=[proveedor_id])


class MovimientoMaterial(ModeloBase):
    __tablename__ = "movimiento_material"
    __table_args__ = tabla_args(
        db.CheckConstraint(
            "tipo IN ('ENTRADA', 'CONSUMO', 'MERMA', 'AJUSTE', 'SOBRANTE', 'REVERSA')",
            name="ck_movimiento_material_tipo",
        ),
        db.Index("ix_movimiento_material_lote", "lote_id", "fecha"),
    )

    lote_id = db.Column(entero_unsigned(), db.ForeignKey("lote_material.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    cantidad_base = db.Column(db.Numeric(12, 4), nullable=False)
    costo_unitario_base = db.Column(db.Numeric(12, 6), nullable=False)
    documento_tipo = db.Column(db.String(30), nullable=False)
    documento_id = db.Column(entero_unsigned(), nullable=False)
    motivo = db.Column(db.Text, nullable=True)
    usuario_id = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    fecha = db.Column(db.DateTime, nullable=False, default=ahora_utc)

    lote = db.relationship("LoteMaterial", foreign_keys=[lote_id])
    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])
