"""Consultas públicas del catálogo con disponibilidad por variante (M03)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import (
    CategoriaProducto,
    Color,
    Producto,
    ProductoImagen,
    StockVariante,
    Talla,
    TarifaEnvio,
    VarianteProducto,
    Venta,
    VentaLinea,
)
from app.services.disponibilidad_service import estado
from app.utils.errores import ApiError


def _dias_envio() -> int:
    dias = db.session.scalar(
        select(func.max(TarifaEnvio.dias_estimados)).where(TarifaEnvio.activa.is_(True))
    )
    return int(dias or 0)


def _mas_buscado_ids() -> set:
    desde = datetime.now(timezone.utc) - timedelta(days=30)
    filas = db.session.execute(
        select(VarianteProducto.producto_id, func.sum(VentaLinea.cantidad))
        .join(VentaLinea, VentaLinea.variante_id == VarianteProducto.id)
        .join(Venta, Venta.id == VentaLinea.venta_id)
        .where(Venta.estado == "ACTIVA", Venta.fecha >= desde)
        .group_by(VarianteProducto.producto_id)
        .order_by(func.sum(VentaLinea.cantidad).desc())
    ).all()
    if not filas:
        return set()
    maximo = filas[0][1]
    return {int(fila[0]) for fila in filas if fila[1] == maximo}


def _variantes(producto_ids, dias_envio: int) -> dict:
    if not producto_ids:
        return {}
    variantes = db.session.execute(
        select(VarianteProducto)
        .options(
            selectinload(VarianteProducto.producto),
            selectinload(VarianteProducto.talla),
            selectinload(VarianteProducto.color),
        )
        .where(
            VarianteProducto.producto_id.in_(producto_ids),
            VarianteProducto.activa.is_(True),
        )
        .order_by(VarianteProducto.id)
    ).scalars().all()
    if not variantes:
        return {}
    stocks = {
        fila.variante_id: fila
        for fila in db.session.execute(
            select(StockVariante).where(
                StockVariante.variante_id.in_([v.id for v in variantes])
            )
        ).scalars().all()
    }

    resultado = {int(producto_id): [] for producto_id in producto_ids}
    for variante in variantes:
        stock = stocks.get(variante.id)
        libre = max(0, stock.existencia - stock.reservado) if stock else 0
        minimo = stock.stock_minimo if stock else 0
        estado_variante = estado(
            libre,
            minimo,
            bool(variante.producto.permite_bajo_pedido),
            dias_envio,
        )
        resultado[variante.producto_id].append(
            {
                "id": variante.id,
                "sku": variante.sku,
                "talla": variante.talla.codigo,
                "color": variante.color.codigo,
                "disponibilidad": estado_variante["disponibilidad"],
                "bajo_pedido": estado_variante["bajo_pedido"],
                "fecha_estimada": estado_variante["fecha_estimada"],
                "comprable": estado_variante["comprable"],
            }
        )
    return resultado


def _imagenes(producto_ids) -> dict:
    if not producto_ids:
        return {}
    filas = db.session.execute(
        select(ProductoImagen)
        .options(selectinload(ProductoImagen.color))
        .where(ProductoImagen.producto_id.in_(producto_ids))
        .order_by(ProductoImagen.producto_id, ProductoImagen.orden, ProductoImagen.id)
    ).scalars().all()
    resultado = {int(producto_id): [] for producto_id in producto_ids}
    for imagen in filas:
        resultado[imagen.producto_id].append(
            {
                "url": imagen.url,
                "color": imagen.color.codigo if imagen.color else None,
            }
        )
    return resultado


def listar(filtros=None) -> list:
    filtros = filtros or {}
    consulta = (
        select(Producto)
        .join(CategoriaProducto, Producto.categoria_id == CategoriaProducto.id)
        .where(Producto.activo.is_(True), Producto.eliminado_en.is_(None))
    )

    if filtros.get("categoria"):
        valor = str(filtros["categoria"]).strip().upper()
        consulta = consulta.where(
            or_(
                func.upper(CategoriaProducto.nombre) == valor,
                CategoriaProducto.prefijo_sku == valor,
            )
        )
    if filtros.get("color"):
        codigo = str(filtros["color"]).strip().upper()
        consulta = consulta.where(
            Producto.id.in_(
                select(VarianteProducto.producto_id)
                .join(Color, Color.id == VarianteProducto.color_id)
                .where(VarianteProducto.activa.is_(True), Color.codigo == codigo)
            )
        )
    if filtros.get("talla"):
        codigo = str(filtros["talla"]).strip().upper()
        consulta = consulta.where(
            Producto.id.in_(
                select(VarianteProducto.producto_id)
                .join(Talla, Talla.id == VarianteProducto.talla_id)
                .where(VarianteProducto.activa.is_(True), Talla.codigo == codigo)
            )
        )
    if filtros.get("q"):
        patron = f"%{str(filtros['q']).strip()}%"
        consulta = consulta.where(
            or_(
                Producto.nombre.like(patron),
                Producto.descripcion.like(patron),
                Producto.id.in_(
                    select(VarianteProducto.producto_id).where(
                        VarianteProducto.sku.like(patron)
                    )
                ),
            )
        )
    if filtros.get("disponibles"):
        consulta = consulta.where(
            Producto.id.in_(
                select(VarianteProducto.producto_id)
                .join(StockVariante, StockVariante.variante_id == VarianteProducto.id)
                .where(
                    VarianteProducto.activa.is_(True),
                    StockVariante.existencia > StockVariante.reservado,
                )
            )
        )

    productos = db.session.execute(consulta.order_by(Producto.nombre)).scalars().all()
    if not productos:
        return []
    ids = [producto.id for producto in productos]
    dias_envio = _dias_envio()
    variantes = _variantes(ids, dias_envio)
    imagenes = _imagenes(ids)
    buscados = _mas_buscado_ids()

    respuesta = []
    for producto in productos:
        items = variantes.get(producto.id, [])
        if not items:
            continue
        galeria = imagenes.get(producto.id, [])
        respuesta.append(
            {
                "id": producto.id,
                "nombre": producto.nombre,
                "descripcion": producto.descripcion,
                "precio_venta": producto.precio_venta,
                "categoria": producto.categoria.nombre,
                "imagen": galeria[0]["url"] if galeria else None,
                "mas_buscado": producto.id in buscados,
                "variantes": items,
            }
        )
    return respuesta


def obtener(producto_id: int) -> dict:
    producto = db.session.get(Producto, producto_id)
    if (
        producto is None
        or not producto.activo
        or producto.eliminado_en is not None
    ):
        raise ApiError("PRODUCTO_NO_ENCONTRADO", "Producto no encontrado", 404)
    variantes = _variantes([producto_id], _dias_envio()).get(producto_id, [])
    if not variantes:
        raise ApiError("PRODUCTO_NO_ENCONTRADO", "Producto no encontrado", 404)
    return {
        "id": producto.id,
        "nombre": producto.nombre,
        "descripcion": producto.descripcion,
        "composicion_textil": producto.composicion_textil,
        "guia_medidas": producto.guia_medidas,
        "precio_venta": producto.precio_venta,
        "iva_incluido": True,
        "categoria": producto.categoria.nombre,
        "imagenes": _imagenes([producto_id]).get(producto_id, []),
        "variantes": variantes,
    }
