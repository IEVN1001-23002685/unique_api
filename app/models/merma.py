"""Registro inmutable de mermas de material y de producto terminado."""

from app.extensions import db
from app.models.base import ModeloBase, ahora_utc, entero_unsigned, tabla_args


class Merma(ModeloBase):
    __tablename__ = "merma"
    __table_args__ = tabla_args(
        db.CheckConstraint("origen IN ('MATERIAL', 'PRODUCTO')", name="ck_merma_origen"),
        db.CheckConstraint(
            "(origen = 'MATERIAL' AND inventario_material_id IS NOT NULL) OR "
            "(origen = 'PRODUCTO' AND variante_id IS NOT NULL)",
            name="ck_merma_origen_entidad",
        ),
        db.CheckConstraint(
            "etapa IN ('RECEPCION', 'CORTE', 'TEJIDO', 'BORDADO', 'CONFECCION', "
            "'ACABADOS', 'ALMACEN', 'ENTREGA', 'DEVOLUCION')",
            name="ck_merma_etapa",
        ),
        db.CheckConstraint("cantidad >= 0", name="ck_merma_cantidad"),
        db.CheckConstraint("costo_perdido >= 0", name="ck_merma_costo"),
        db.Index("ix_merma_fecha", "fecha"),
        db.Index("ix_merma_causa", "causa_id", "etapa"),
    )

    origen = db.Column(db.String(20), nullable=False)
    inventario_material_id = db.Column(
        entero_unsigned(), db.ForeignKey("inventario_material.id"), nullable=True
    )
    lote_id = db.Column(entero_unsigned(), db.ForeignKey("lote_material.id"), nullable=True)
    variante_id = db.Column(
        entero_unsigned(), db.ForeignKey("variante_producto.id"), nullable=True
    )
    orden_produccion_id = db.Column(
        entero_unsigned(), db.ForeignKey("orden_produccion.id"), nullable=True
    )
    recepcion_linea_id = db.Column(
        entero_unsigned(), db.ForeignKey("recepcion_linea.id"), nullable=True
    )
    devolucion_linea_id = db.Column(
        entero_unsigned(), db.ForeignKey("devolucion_linea.id"), nullable=True
    )
    etapa = db.Column(db.String(20), nullable=False)
    causa_id = db.Column(entero_unsigned(), db.ForeignKey("causa_merma.id"), nullable=False)
    cantidad = db.Column(db.Numeric(12, 4), nullable=False)
    costo_perdido = db.Column(db.Numeric(12, 2), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    evidencia_url = db.Column(db.String(500), nullable=True)
    registrada_por = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    fecha = db.Column(db.DateTime, nullable=False, default=ahora_utc)

    causa = db.relationship("CausaMerma", foreign_keys=[causa_id])
    registrador = db.relationship("Usuario", foreign_keys=[registrada_por])
