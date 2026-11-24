"""Ordenes de produccion, explosion de materiales y revision de calidad."""

from app.extensions import db
from app.models.base import ModeloBase, ahora_utc, entero_unsigned, tabla_args


class OrdenProduccion(ModeloBase):
    __tablename__ = "orden_produccion"
    __table_args__ = tabla_args(
        db.UniqueConstraint("folio", name="uq_orden_produccion_folio"),
        db.CheckConstraint(
            "origen IN ('PEDIDO', 'STOCK_MINIMO', 'MANUAL')",
            name="ck_orden_produccion_origen",
        ),
        db.CheckConstraint(
            "estado IN ('PLANEADA', 'LISTA', 'EN_PROCESO', 'EN_REVISION', "
            "'CERRADA', 'CANCELADA')",
            name="ck_orden_produccion_estado",
        ),
        db.CheckConstraint(
            "semaforo IN ('VERDE', 'AMBAR', 'ROJO')", name="ck_orden_produccion_semaforo"
        ),
        db.Index("ix_orden_produccion_estado", "estado", "semaforo"),
    )

    folio = db.Column(db.String(20), nullable=False)
    origen = db.Column(db.String(20), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="PLANEADA")
    semaforo = db.Column(db.String(10), nullable=False, default="VERDE")
    fecha_requerida = db.Column(db.Date, nullable=True)
    iniciada_en = db.Column(db.DateTime, nullable=True)
    cerrada_en = db.Column(db.DateTime, nullable=True)
    creada_por = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    notas = db.Column(db.Text, nullable=True)

    creador = db.relationship("Usuario", foreign_keys=[creada_por])


class OrdenProduccionLinea(ModeloBase):
    __tablename__ = "orden_produccion_linea"
    __table_args__ = tabla_args(
        db.CheckConstraint("cantidad_planeada >= 0", name="ck_op_linea_planeada"),
        db.CheckConstraint("cantidad_aprobada >= 0", name="ck_op_linea_aprobada"),
        db.CheckConstraint("cantidad_merma >= 0", name="ck_op_linea_merma"),
        db.CheckConstraint("cantidad_reproceso >= 0", name="ck_op_linea_reproceso"),
        db.CheckConstraint(
            "cantidad_aprobada + cantidad_merma + cantidad_reproceso "
            "<= cantidad_planeada",
            name="ck_op_linea_conteo",
        ),
        db.Index("ix_op_linea_orden", "orden_id"),
        db.Index("ix_op_linea_variante", "variante_id"),
    )

    orden_id = db.Column(
        entero_unsigned(), db.ForeignKey("orden_produccion.id"), nullable=False
    )
    variante_id = db.Column(
        entero_unsigned(), db.ForeignKey("variante_producto.id"), nullable=False
    )
    receta_id = db.Column(entero_unsigned(), db.ForeignKey("receta.id"), nullable=False)
    cantidad_planeada = db.Column(db.Integer, nullable=False)
    cantidad_aprobada = db.Column(db.Integer, nullable=False, default=0)
    cantidad_merma = db.Column(db.Integer, nullable=False, default=0)
    cantidad_reproceso = db.Column(db.Integer, nullable=False, default=0)

    orden = db.relationship("OrdenProduccion", foreign_keys=[orden_id])
    variante = db.relationship("VarianteProducto", foreign_keys=[variante_id])
    receta = db.relationship("Receta", foreign_keys=[receta_id])


class OrdenMaterial(ModeloBase):
    __tablename__ = "orden_material"
    __table_args__ = tabla_args(
        db.CheckConstraint("cantidad_requerida >= 0", name="ck_orden_material_requerida"),
        db.CheckConstraint("cantidad_reservada >= 0", name="ck_orden_material_reservada"),
        db.CheckConstraint("cantidad_consumida >= 0", name="ck_orden_material_consumida"),
        db.CheckConstraint(
            "estado IN ('COMPLETO', 'PARCIAL', 'FALTANTE')",
            name="ck_orden_material_estado",
        ),
        db.Index("ix_orden_material_orden", "orden_id"),
        db.Index("ix_orden_material_inventario", "inventario_material_id"),
    )

    orden_id = db.Column(
        entero_unsigned(), db.ForeignKey("orden_produccion.id"), nullable=False
    )
    inventario_material_id = db.Column(
        entero_unsigned(), db.ForeignKey("inventario_material.id"), nullable=False
    )
    cantidad_requerida = db.Column(db.Numeric(12, 4), nullable=False)
    cantidad_reservada = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    cantidad_consumida = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    estado = db.Column(db.String(20), nullable=False, default="FALTANTE")

    orden = db.relationship("OrdenProduccion", foreign_keys=[orden_id])
    inventario_material = db.relationship(
        "InventarioMaterial", foreign_keys=[inventario_material_id]
    )


class ProduccionPedido(ModeloBase):
    __tablename__ = "produccion_pedido"
    __table_args__ = tabla_args(
        db.CheckConstraint("cantidad >= 0", name="ck_produccion_pedido_cantidad"),
        db.Index("ix_produccion_pedido_orden", "orden_linea_id"),
        db.Index("ix_produccion_pedido_linea", "pedido_linea_id"),
    )

    orden_linea_id = db.Column(
        entero_unsigned(), db.ForeignKey("orden_produccion_linea.id"), nullable=False
    )
    pedido_linea_id = db.Column(
        entero_unsigned(), db.ForeignKey("pedido_linea.id"), nullable=False
    )
    cantidad = db.Column(db.Integer, nullable=False)

    orden_linea = db.relationship("OrdenProduccionLinea", foreign_keys=[orden_linea_id])
    pedido_linea = db.relationship("PedidoLinea", foreign_keys=[pedido_linea_id])


class RevisionCalidad(ModeloBase):
    __tablename__ = "revision_calidad"
    __table_args__ = tabla_args(
        db.CheckConstraint(
            "cantidad_aprobada + cantidad_reproceso + cantidad_merma "
            "= cantidad_revisada",
            name="ck_revision_calidad_conteo",
        ),
        db.Index("ix_revision_calidad_linea", "orden_linea_id", "fecha"),
    )

    orden_linea_id = db.Column(
        entero_unsigned(), db.ForeignKey("orden_produccion_linea.id"), nullable=False
    )
    revisada_por = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    fecha = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    medidas_ok = db.Column(db.Boolean, nullable=False)
    costuras_ok = db.Column(db.Boolean, nullable=False)
    bordado_ok = db.Column(db.Boolean, nullable=False)
    etiquetas_ok = db.Column(db.Boolean, nullable=False)
    cantidad_revisada = db.Column(db.Integer, nullable=False)
    cantidad_aprobada = db.Column(db.Integer, nullable=False)
    cantidad_reproceso = db.Column(db.Integer, nullable=False, default=0)
    cantidad_merma = db.Column(db.Integer, nullable=False, default=0)
    observaciones = db.Column(db.Text, nullable=True)

    orden_linea = db.relationship("OrdenProduccionLinea", foreign_keys=[orden_linea_id])
    revisor = db.relationship("Usuario", foreign_keys=[revisada_por])
