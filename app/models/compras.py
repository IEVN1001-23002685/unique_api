"""Proveedores, requisiciones, cotizaciones, ordenes de compra y recepciones."""

from app.extensions import db
from app.models.base import ModeloBase, ahora_utc, entero_unsigned, tabla_args


class Proveedor(ModeloBase):
    __tablename__ = "proveedor"
    __table_args__ = tabla_args(
        db.CheckConstraint(
            "estatus IN ('ACTIVO', 'EN_REVISION', 'INACTIVO')",
            name="ck_proveedor_estatus",
        ),
        db.Index("ix_proveedor_estatus", "estatus", "eliminado_en"),
    )

    razon_social = db.Column(db.String(150), nullable=False)
    nombre_comercial = db.Column(db.String(120), nullable=False)
    rfc = db.Column(db.String(13), nullable=True)
    contacto = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(15), nullable=False)
    correo = db.Column(db.String(120), nullable=False)
    direccion = db.Column(db.Text, nullable=False)
    condiciones_pago = db.Column(db.Text, nullable=False)
    estatus = db.Column(db.String(20), nullable=False, default="ACTIVO")
    notas = db.Column(db.Text, nullable=True)
    eliminado_en = db.Column(db.DateTime, nullable=True)


class ProveedorMaterial(ModeloBase):
    __tablename__ = "proveedor_material"
    __table_args__ = tabla_args(
        db.UniqueConstraint("proveedor_id", "material_id", name="uq_proveedor_material"),
        db.CheckConstraint("precio_compra >= 0", name="ck_proveedor_material_precio"),
        db.CheckConstraint("minimo_compra >= 0", name="ck_proveedor_material_minimo"),
    )

    proveedor_id = db.Column(entero_unsigned(), db.ForeignKey("proveedor.id"), nullable=False)
    material_id = db.Column(entero_unsigned(), db.ForeignKey("material.id"), nullable=False)
    precio_compra = db.Column(db.Numeric(12, 2), nullable=False)
    minimo_compra = db.Column(db.Numeric(10, 2), nullable=False)
    plazo_dias = db.Column(db.Integer, nullable=False)
    es_principal = db.Column(db.Boolean, nullable=False, default=False)
    vigencia_hasta = db.Column(db.Date, nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    proveedor = db.relationship("Proveedor", foreign_keys=[proveedor_id])
    material = db.relationship("Material", foreign_keys=[material_id])


class Requisicion(ModeloBase):
    __tablename__ = "requisicion"
    __table_args__ = tabla_args(
        db.UniqueConstraint("folio", name="uq_requisicion_folio"),
        db.CheckConstraint(
            "origen IN ('ALERTA', 'ORDEN_PRODUCCION', 'MANUAL')",
            name="ck_requisicion_origen",
        ),
        db.CheckConstraint(
            "estado IN ('PENDIENTE', 'EN_COTIZACION', 'COMPRA_EMITIDA', "
            "'ATENDIDA', 'CANCELADA')",
            name="ck_requisicion_estado",
        ),
        db.CheckConstraint(
            "prioridad IN ('NORMAL', 'URGENTE')", name="ck_requisicion_prioridad"
        ),
        db.Index("ix_requisicion_estado", "estado", "fecha"),
    )

    folio = db.Column(db.String(20), nullable=False)
    origen = db.Column(db.String(20), nullable=False)
    orden_produccion_id = db.Column(
        entero_unsigned(), db.ForeignKey("orden_produccion.id"), nullable=True
    )
    estado = db.Column(db.String(20), nullable=False, default="PENDIENTE")
    prioridad = db.Column(db.String(10), nullable=False, default="NORMAL")
    solicitada_por = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    fecha = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    notas = db.Column(db.Text, nullable=True)

    solicitante = db.relationship("Usuario", foreign_keys=[solicitada_por])


class RequisicionLinea(ModeloBase):
    __tablename__ = "requisicion_linea"
    __table_args__ = tabla_args(
        db.Index("ix_requisicion_linea_requisicion", "requisicion_id"),
        db.Index(
            "ix_requisicion_linea_inventario", "inventario_material_id"
        ),
    )

    requisicion_id = db.Column(
        entero_unsigned(), db.ForeignKey("requisicion.id"), nullable=False
    )
    inventario_material_id = db.Column(
        entero_unsigned(), db.ForeignKey("inventario_material.id"), nullable=False
    )
    cantidad_base_faltante = db.Column(db.Numeric(12, 4), nullable=False)
    cantidad_compra_sugerida = db.Column(db.Numeric(10, 2), nullable=False)
    cantidad_compra_atendida = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    requisicion = db.relationship("Requisicion", foreign_keys=[requisicion_id])
    inventario_material = db.relationship(
        "InventarioMaterial", foreign_keys=[inventario_material_id]
    )


class Cotizacion(ModeloBase):
    __tablename__ = "cotizacion"
    __table_args__ = tabla_args(
        db.CheckConstraint(
            "estado IN ('PENDIENTE', 'ELEGIDA', 'DESCARTADA')",
            name="ck_cotizacion_estado",
        ),
        db.CheckConstraint("total >= 0", name="ck_cotizacion_total"),
        db.Index("ix_cotizacion_requisicion", "requisicion_id", "proveedor_id"),
    )

    requisicion_id = db.Column(
        entero_unsigned(), db.ForeignKey("requisicion.id"), nullable=False
    )
    proveedor_id = db.Column(entero_unsigned(), db.ForeignKey("proveedor.id"), nullable=False)
    fecha = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    vigencia_hasta = db.Column(db.Date, nullable=True)
    plazo_dias = db.Column(db.Integer, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="PENDIENTE")
    total = db.Column(db.Numeric(12, 2), nullable=False)
    notas = db.Column(db.Text, nullable=True)

    requisicion = db.relationship("Requisicion", foreign_keys=[requisicion_id])
    proveedor = db.relationship("Proveedor", foreign_keys=[proveedor_id])


class CotizacionLinea(ModeloBase):
    __tablename__ = "cotizacion_linea"
    __table_args__ = tabla_args(
        db.Index("ix_cotizacion_linea_cotizacion", "cotizacion_id"),
        db.Index("ix_cotizacion_linea_requisicion", "requisicion_linea_id"),
    )

    cotizacion_id = db.Column(
        entero_unsigned(), db.ForeignKey("cotizacion.id"), nullable=False
    )
    requisicion_linea_id = db.Column(
        entero_unsigned(), db.ForeignKey("requisicion_linea.id"), nullable=False
    )
    cantidad_compra = db.Column(db.Numeric(10, 2), nullable=False)
    precio_unitario_compra = db.Column(db.Numeric(12, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)

    cotizacion = db.relationship("Cotizacion", foreign_keys=[cotizacion_id])
    requisicion_linea = db.relationship(
        "RequisicionLinea", foreign_keys=[requisicion_linea_id]
    )


class OrdenCompra(ModeloBase):
    __tablename__ = "orden_compra"
    __table_args__ = tabla_args(
        db.UniqueConstraint("folio", name="uq_orden_compra_folio"),
        db.CheckConstraint(
            "estado IN ('BORRADOR', 'EMITIDA', 'PARCIAL', 'RECIBIDA', 'CANCELADA')",
            name="ck_orden_compra_estado",
        ),
        db.CheckConstraint("total >= 0", name="ck_orden_compra_total"),
        db.Index("ix_orden_compra_proveedor", "proveedor_id", "estado"),
    )

    folio = db.Column(db.String(20), nullable=False)
    proveedor_id = db.Column(entero_unsigned(), db.ForeignKey("proveedor.id"), nullable=False)
    requisicion_id = db.Column(
        entero_unsigned(), db.ForeignKey("requisicion.id"), nullable=True
    )
    cotizacion_id = db.Column(
        entero_unsigned(), db.ForeignKey("cotizacion.id"), nullable=True
    )
    estado = db.Column(db.String(20), nullable=False, default="BORRADOR")
    fecha_emision = db.Column(db.DateTime, nullable=True)
    fecha_prometida = db.Column(db.Date, nullable=True)
    total = db.Column(db.Numeric(12, 2), nullable=False)
    condiciones_pago = db.Column(db.Text, nullable=False)
    notas = db.Column(db.Text, nullable=True)
    creada_por = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)

    proveedor = db.relationship("Proveedor", foreign_keys=[proveedor_id])
    creador = db.relationship("Usuario", foreign_keys=[creada_por])


class OrdenCompraLinea(ModeloBase):
    __tablename__ = "orden_compra_linea"
    __table_args__ = tabla_args(
        db.CheckConstraint("cantidad_base_aceptada >= 0", name="ck_oc_linea_aceptada"),
        db.Index("ix_orden_compra_linea_orden", "orden_compra_id"),
        db.Index("ix_orden_compra_linea_inventario", "inventario_material_id"),
    )

    orden_compra_id = db.Column(
        entero_unsigned(), db.ForeignKey("orden_compra.id"), nullable=False
    )
    inventario_material_id = db.Column(
        entero_unsigned(), db.ForeignKey("inventario_material.id"), nullable=False
    )
    cantidad_compra = db.Column(db.Numeric(10, 2), nullable=False)
    precio_unitario_compra = db.Column(db.Numeric(12, 2), nullable=False)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    cantidad_base_aceptada = db.Column(db.Numeric(12, 4), nullable=False, default=0)

    orden_compra = db.relationship("OrdenCompra", foreign_keys=[orden_compra_id])
    inventario_material = db.relationship(
        "InventarioMaterial", foreign_keys=[inventario_material_id]
    )


class Recepcion(ModeloBase):
    __tablename__ = "recepcion"
    __table_args__ = tabla_args(
        db.UniqueConstraint("folio", name="uq_recepcion_folio"),
        db.Index("ix_recepcion_orden", "orden_compra_id", "fecha"),
    )

    folio = db.Column(db.String(20), nullable=False)
    orden_compra_id = db.Column(
        entero_unsigned(), db.ForeignKey("orden_compra.id"), nullable=False
    )
    fecha = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    recibida_por = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    documento_proveedor = db.Column(db.String(60), nullable=True)
    notas = db.Column(db.Text, nullable=True)

    orden_compra = db.relationship("OrdenCompra", foreign_keys=[orden_compra_id])
    receptor = db.relationship("Usuario", foreign_keys=[recibida_por])


class RecepcionLinea(ModeloBase):
    __tablename__ = "recepcion_linea"
    __table_args__ = tabla_args(
        db.CheckConstraint(
            "cantidad_base_medida = cantidad_base_aceptada + cantidad_base_rechazada",
            name="ck_recepcion_linea_medida",
        ),
        db.Index("ix_recepcion_linea_recepcion", "recepcion_id"),
        db.Index("ix_recepcion_linea_orden", "orden_compra_linea_id"),
    )

    recepcion_id = db.Column(entero_unsigned(), db.ForeignKey("recepcion.id"), nullable=False)
    orden_compra_linea_id = db.Column(
        entero_unsigned(), db.ForeignKey("orden_compra_linea.id"), nullable=False
    )
    peso_kg = db.Column(db.Numeric(10, 3), nullable=True)
    ancho_cm = db.Column(db.Numeric(10, 3), nullable=True)
    largo_m = db.Column(db.Numeric(10, 3), nullable=True)
    cantidad_base_medida = db.Column(db.Numeric(12, 4), nullable=False)
    cantidad_base_aceptada = db.Column(db.Numeric(12, 4), nullable=False)
    cantidad_base_rechazada = db.Column(db.Numeric(12, 4), nullable=False, default=0)
    motivo_rechazo = db.Column(db.Text, nullable=True)

    recepcion = db.relationship("Recepcion", foreign_keys=[recepcion_id])
    orden_compra_linea = db.relationship(
        "OrdenCompraLinea", foreign_keys=[orden_compra_linea_id]
    )
