"""Bloqueo, reserva y liberación de existencias de producto terminado (M12)."""

from sqlalchemy import select

from app.extensions import db
from app.models import MovimientoProducto, StockVariante
from app.utils.errores import ApiError


def bloquear(variante_ids) -> dict:
    """Bloquea las filas de stock en orden ascendente por ID de variante."""
    ids = sorted({int(variante_id) for variante_id in variante_ids})
    if not ids:
        return {}
    filas = db.session.execute(
        select(StockVariante)
        .where(StockVariante.variante_id.in_(ids))
        .order_by(StockVariante.variante_id)
        .with_for_update()
    ).scalars().all()
    if len(filas) != len(ids):
        raise ApiError(
            "STOCK_NO_DISPONIBLE", "Una variante no tiene registro de inventario", 409
        )
    return {fila.variante_id: fila for fila in filas}


def disponible(stock: StockVariante) -> int:
    return max(0, stock.existencia - stock.reservado)


def registrar_movimiento(
    stock,
    tipo,
    delta_existencia,
    delta_reservado,
    documento_tipo,
    documento_id,
    usuario_id,
    motivo=None,
):
    db.session.add(
        MovimientoProducto(
            variante_id=stock.variante_id,
            tipo=tipo,
            delta_existencia=delta_existencia,
            delta_reservado=delta_reservado,
            documento_tipo=documento_tipo,
            documento_id=documento_id,
            motivo=motivo,
            usuario_id=usuario_id,
        )
    )


def reservar(
    stock, cantidad, documento_tipo, documento_id, usuario_id, motivo=None
) -> int:
    if cantidad <= 0:
        return 0
    cantidad_reservada = min(disponible(stock), cantidad)
    if cantidad_reservada > 0:
        stock.reservado += cantidad_reservada
        registrar_movimiento(
            stock,
            "RESERVA",
            0,
            cantidad_reservada,
            documento_tipo,
            documento_id,
            usuario_id,
            motivo,
        )
    return cantidad_reservada


def liberar(
    stock, cantidad, documento_tipo, documento_id, usuario_id, motivo=None
) -> int:
    if cantidad <= 0:
        return 0
    cantidad_liberada = min(stock.reservado, cantidad)
    if cantidad_liberada > 0:
        stock.reservado -= cantidad_liberada
        registrar_movimiento(
            stock,
            "LIBERA_RESERVA",
            0,
            -cantidad_liberada,
            documento_tipo,
            documento_id,
            usuario_id,
            motivo,
        )
    return cantidad_liberada
