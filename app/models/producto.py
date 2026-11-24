"""Catalogo de productos, variantes, imagenes y movimientos de producto terminado."""

from app.extensions import db
from app.models.base import ModeloBase, ahora_utc, entero_unsigned, tabla_args


class DisenoBordado(ModeloBase):
    __tablename__ = "diseno_bordado"
    __table_args__ = tabla_args(
        db.UniqueConstraint("codigo", name="uq_diseno_bordado_codigo"),
        db.CheckConstraint(
            "estado IN ('PENDIENTE', 'DIGITALIZADO')", name="ck_diseno_bordado_estado"
        ),
    )

    codigo = db.Column(db.String(20), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    ancho_cm = db.Column(db.Numeric(8, 2), nullable=False)
    alto_cm = db.Column(db.Numeric(8, 2), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="PENDIENTE")
    notas = db.Column(db.Text, nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)


class DisenoBordadoHilo(ModeloBase):
    __tablename__ = "diseno_bordado_hilo"
    __table_args__ = tabla_args(
        db.UniqueConstraint("diseno_id", "material_id", name="uq_diseno_hilo")
    )

    diseno_id = db.Column(
        entero_unsigned(), db.ForeignKey("diseno_bordado.id"), nullable=False
    )
    material_id = db.Column(entero_unsigned(), db.ForeignKey("material.id"), nullable=False)
    metros_por_aplicacion = db.Column(db.Numeric(10, 3), nullable=False)

    diseno = db.relationship("DisenoBordado", foreign_keys=[diseno_id])
    material = db.relationship("Material", foreign_keys=[material_id])


class Producto(ModeloBase):
    __tablename__ = "producto"
    __table_args__ = tabla_args(
        db.UniqueConstraint("codigo_sku", name="uq_producto_codigo_sku"),
        db.CheckConstraint("precio_venta >= 0", name="ck_producto_precio"),
        db.Index("ix_producto_categoria", "categoria_id", "activo"),
    )

    categoria_id = db.Column(
        entero_unsigned(), db.ForeignKey("categoria_producto.id"), nullable=False
    )
    codigo_sku = db.Column(db.String(4), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    composicion_textil = db.Column(db.Text, nullable=False)
    guia_medidas = db.Column(db.Text, nullable=False)
    precio_venta = db.Column(db.Numeric(10, 2), nullable=False)
    permite_bajo_pedido = db.Column(db.Boolean, nullable=False, default=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    eliminado_en = db.Column(db.DateTime, nullable=True)

    categoria = db.relationship("CategoriaProducto", foreign_keys=[categoria_id])


class ProductoImagen(ModeloBase):
    __tablename__ = "producto_imagen"
    __table_args__ = tabla_args(db.Index("ix_producto_imagen_producto", "producto_id"))

    producto_id = db.Column(entero_unsigned(), db.ForeignKey("producto.id"), nullable=False)
    color_id = db.Column(entero_unsigned(), db.ForeignKey("color.id"), nullable=True)
    url = db.Column(db.String(500), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)

    producto = db.relationship("Producto", foreign_keys=[producto_id])
    color = db.relationship("Color", foreign_keys=[color_id])


class VarianteProducto(ModeloBase):
    __tablename__ = "variante_producto"
    __table_args__ = tabla_args(
        db.UniqueConstraint("sku", name="uq_variante_sku"),
        db.UniqueConstraint(
            "producto_id", "talla_id", "color_id", name="uq_variante_producto_talla_color"
        ),
        db.Index("ix_variante_producto", "producto_id", "activa"),
    )

    producto_id = db.Column(entero_unsigned(), db.ForeignKey("producto.id"), nullable=False)
    talla_id = db.Column(entero_unsigned(), db.ForeignKey("talla.id"), nullable=False)
    color_id = db.Column(entero_unsigned(), db.ForeignKey("color.id"), nullable=False)
    sku = db.Column(db.String(12), nullable=False)
    activa = db.Column(db.Boolean, nullable=False, default=True)

    producto = db.relationship("Producto", foreign_keys=[producto_id])
    talla = db.relationship("Talla", foreign_keys=[talla_id])
    color = db.relationship("Color", foreign_keys=[color_id])


class StockVariante(db.Model):
    __tablename__ = "stock_variante"
    __table_args__ = tabla_args(
        db.CheckConstraint("existencia >= 0", name="ck_stock_variante_existencia"),
        db.CheckConstraint("reservado >= 0", name="ck_stock_variante_reservado"),
        db.CheckConstraint(
            "reservado <= existencia", name="ck_stock_variante_reservado_existencia"
        ),
        db.CheckConstraint("stock_minimo >= 0", name="ck_stock_variante_minimo"),
        db.CheckConstraint(
            "cantidad_reposicion >= 0", name="ck_stock_variante_reposicion"
        ),
    )

    variante_id = db.Column(
        entero_unsigned(), db.ForeignKey("variante_producto.id"), primary_key=True
    )
    existencia = db.Column(db.Integer, nullable=False, default=0)
    reservado = db.Column(db.Integer, nullable=False, default=0)
    stock_minimo = db.Column(db.Integer, nullable=False, default=0)
    cantidad_reposicion = db.Column(db.Integer, nullable=False, default=0)
    creado_en = db.Column(db.DateTime, nullable=False, default=ahora_utc)
    actualizado_en = db.Column(
        db.DateTime, nullable=False, default=ahora_utc, onupdate=ahora_utc
    )

    variante = db.relationship("VarianteProducto", foreign_keys=[variante_id])


class MovimientoProducto(ModeloBase):
    __tablename__ = "movimiento_producto"
    __table_args__ = tabla_args(
        db.CheckConstraint(
            "tipo IN ('PRODUCCION', 'RESERVA', 'LIBERA_RESERVA', 'SALIDA_ENVIO', "
            "'REINGRESO', 'MERMA', 'AJUSTE')",
            name="ck_movimiento_producto_tipo",
        ),
        db.Index("ix_movimiento_producto_variante", "variante_id", "fecha"),
    )

    variante_id = db.Column(
        entero_unsigned(), db.ForeignKey("variante_producto.id"), nullable=False
    )
    tipo = db.Column(db.String(30), nullable=False)
    delta_existencia = db.Column(db.Integer, nullable=False)
    delta_reservado = db.Column(db.Integer, nullable=False)
    documento_tipo = db.Column(db.String(30), nullable=False)
    documento_id = db.Column(entero_unsigned(), nullable=False)
    motivo = db.Column(db.Text, nullable=True)
    usuario_id = db.Column(entero_unsigned(), db.ForeignKey("usuario.id"), nullable=False)
    fecha = db.Column(db.DateTime, nullable=False, default=ahora_utc)

    variante = db.relationship("VarianteProducto", foreign_keys=[variante_id])
    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])
