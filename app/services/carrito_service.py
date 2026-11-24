"""Carrito persistido del cliente: revalidación, fusión y preparación al pago (M04)."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import (
    Carrito,
    CarritoLinea,
    Producto,
    ProductoImagen,
    StockVariante,
    VarianteProducto,
)
from app.services import configuracion_service
from app.services.disponibilidad_service import estado
from app.utils.errores import ApiError


def _carrito_abierto(usuario_id: int) -> Carrito | None:
    return db.session.execute(
        select(Carrito)
        .where(Carrito.usuario_id == usuario_id, Carrito.estado == "ABIERTO")
        .order_by(Carrito.id)
    ).scalars().first()


def _obtener_o_crear(usuario_id: int) -> Carrito:
    carrito = _carrito_abierto(usuario_id)
    if carrito is None:
        carrito = Carrito(usuario_id=usuario_id, estado="ABIERTO")
        db.session.add(carrito)
        db.session.flush()
    return carrito


def _max_piezas() -> int:
    return configuracion_service.valor_entero("max_piezas_por_linea", 10)


def _validar_variante(variante_id: int, cantidad: int) -> VarianteProducto:
    if cantidad > _max_piezas():
        raise ApiError(
            "CANTIDAD_MAXIMA",
            f"No se pueden agregar más de {_max_piezas()} piezas por línea",
            422,
        )
    variante = db.session.get(VarianteProducto, variante_id)
    if variante is None:
        raise ApiError("VARIANTE_NO_ENCONTRADA", "La variante no existe", 404)
    if not variante.activa or not variante.producto.activo:
        raise ApiError(
            "VARIANTE_NO_DISPONIBLE", "La variante no está disponible", 422
        )
    return variante


def _imagenes(producto_ids) -> dict:
    if not producto_ids:
        return {}
    filas = db.session.execute(
        select(ProductoImagen)
        .where(ProductoImagen.producto_id.in_(producto_ids))
        .order_by(ProductoImagen.producto_id, ProductoImagen.orden, ProductoImagen.id)
    ).scalars().all()
    resultado = {}
    for fila in filas:
        resultado.setdefault(fila.producto_id, fila.url)
    return resultado


def lineas_revalidadas(usuario_id: int) -> tuple[list, Carrito | None]:
    carrito = _carrito_abierto(usuario_id)
    if carrito is None:
        return [], None
    lineas = db.session.execute(
        select(CarritoLinea)
        .options(
            selectinload(CarritoLinea.variante).selectinload(VarianteProducto.producto),
            selectinload(CarritoLinea.variante).selectinload(VarianteProducto.talla),
            selectinload(CarritoLinea.variante).selectinload(VarianteProducto.color),
        )
        .where(CarritoLinea.carrito_id == carrito.id)
        .order_by(CarritoLinea.id)
    ).scalars().all()
    if not lineas:
        return [], carrito

    stocks = {
        fila.variante_id: fila
        for fila in db.session.execute(
            select(StockVariante).where(
                StockVariante.variante_id.in_([linea.variante_id for linea in lineas])
            )
        ).scalars().all()
    }
    from app.models import TarifaEnvio

    max_dias = db.session.scalar(
        select(db.func.max(TarifaEnvio.dias_estimados)).where(TarifaEnvio.activa.is_(True))
    )
    dias_envio = int(max_dias or 0)
    imagenes = _imagenes({linea.variante.producto_id for linea in lineas})

    resultado = []
    for linea in lineas:
        variante = linea.variante
        producto = variante.producto
        stock = stocks.get(variante.id)
        libre = max(0, stock.existencia - stock.reservado) if stock else 0
        minimo = stock.stock_minimo if stock else 0
        estado_variante = estado(
            libre, minimo, bool(producto.permite_bajo_pedido), dias_envio
        )
        activa = bool(variante.activa and producto.activo)
        resultado.append(
            {
                "id": linea.id,
                "variante_id": variante.id,
                "sku": variante.sku,
                "nombre_producto": producto.nombre,
                "talla": variante.talla.codigo,
                "color": variante.color.codigo,
                "precio_unitario": producto.precio_venta,
                "cantidad": linea.cantidad,
                "subtotal": Decimal(str(producto.precio_venta)) * linea.cantidad,
                "disponibilidad": estado_variante["disponibilidad"],
                "bajo_pedido": estado_variante["bajo_pedido"],
                "fecha_estimada": estado_variante["fecha_estimada"],
                "activa": activa,
                "comprable": activa and estado_variante["comprable"],
                "imagen": imagenes.get(producto.id),
            }
        )
    return resultado, carrito


def obtener(usuario_id: int) -> dict:
    lineas, carrito = lineas_revalidadas(usuario_id)
    if carrito is None:
        carrito = _obtener_o_crear(usuario_id)
        db.session.commit()
    subtotal = sum((linea["subtotal"] for linea in lineas), Decimal("0"))
    return {
        "items": lineas,
        "subtotal": subtotal,
        "total_articulos": sum(linea["cantidad"] for linea in lineas),
        "max_piezas_por_linea": _max_piezas(),
        "puede_pagar": bool(lineas) and all(linea["comprable"] for linea in lineas),
    }


def agregar_linea(usuario_id: int, variante_id: int, cantidad: int) -> dict:
    _validar_variante(variante_id, cantidad)
    carrito = _obtener_o_crear(usuario_id)
    linea = db.session.execute(
        select(CarritoLinea).where(
            CarritoLinea.carrito_id == carrito.id,
            CarritoLinea.variante_id == variante_id,
        )
    ).scalars().first()
    if linea is None:
        db.session.add(
            CarritoLinea(carrito_id=carrito.id, variante_id=variante_id, cantidad=cantidad)
        )
    else:
        linea.cantidad = cantidad
    db.session.commit()
    return obtener(usuario_id)


def eliminar_linea(usuario_id: int, variante_id: int) -> None:
    carrito = _carrito_abierto(usuario_id)
    if carrito is None:
        return
    linea = db.session.execute(
        select(CarritoLinea).where(
            CarritoLinea.carrito_id == carrito.id,
            CarritoLinea.variante_id == variante_id,
        )
    ).scalars().first()
    if linea is not None:
        db.session.delete(linea)
        db.session.commit()


def fusionar(usuario_id: int, lineas: list) -> dict:
    cantidades = {}
    for linea in lineas:
        variante_id = int(linea["variante_id"])
        cantidad = int(linea["cantidad"])
        cantidades[variante_id] = cantidades.get(variante_id, 0) + cantidad
    for variante_id, cantidad in cantidades.items():
        _validar_variante(variante_id, cantidad)
    carrito = _obtener_o_crear(usuario_id)
    existentes = {
        fila.variante_id: fila
        for fila in db.session.execute(
            select(CarritoLinea).where(CarritoLinea.carrito_id == carrito.id)
        ).scalars().all()
    }
    for variante_id, cantidad in cantidades.items():
        linea = existentes.get(variante_id)
        if linea is None:
            db.session.add(
                CarritoLinea(
                    carrito_id=carrito.id, variante_id=variante_id, cantidad=cantidad
                )
            )
        else:
            linea.cantidad += cantidad
            if linea.cantidad > _max_piezas():
                raise ApiError(
                    "CANTIDAD_MAXIMA",
                    f"No se pueden tener más de {_max_piezas()} piezas por línea",
                    422,
                )
    db.session.commit()
    return obtener(usuario_id)


def lineas_para_checkout(usuario_id: int) -> tuple[list, Carrito]:
    lineas, carrito = lineas_revalidadas(usuario_id)
    if carrito is None or not lineas:
        raise ApiError("CARRITO_VACIO", "El carrito está vacío", 422)
    rechazadas = [
        {"variante_id": linea["variante_id"], "motivo": linea["disponibilidad"]}
        for linea in lineas
        if not linea["comprable"]
    ]
    if rechazadas:
        raise ApiError(
            "CARRITO_NO_PAGABLE",
            "Hay líneas que no se pueden pagar",
            422,
            rechazadas,
        )
    return lineas, carrito


def convertir(carrito: Carrito) -> None:
    carrito.estado = "CONVERTIDO"
    db.session.flush()
