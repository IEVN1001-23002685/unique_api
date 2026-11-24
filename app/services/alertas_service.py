"""Apertura, deduplicación y cierre de alertas del sistema (M21)."""

from sqlalchemy import select

from app.extensions import db
from app.models import Alerta, PedidoLinea, StockVariante


def abrir(
    tipo,
    severidad,
    titulo,
    detalle,
    entidad_tipo,
    entidad_id,
    rol_destino="AMBOS",
    clave_unica=None,
    accion_sugerida=None,
) -> Alerta | None:
    if clave_unica:
        existente = db.session.execute(
            select(Alerta).where(Alerta.clave_unica == clave_unica)
        ).scalars().first()
        if existente is not None:
            return existente
    alerta = Alerta(
        tipo=tipo,
        severidad=severidad,
        titulo=titulo,
        detalle=detalle,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        rol_destino=rol_destino,
        clave_unica=clave_unica,
        accion_sugerida=accion_sugerida,
        estado="ABIERTA",
    )
    db.session.add(alerta)
    db.session.flush()
    return alerta


def evaluar_variantes(variante_ids) -> None:
    """Abre alertas de producto terminado después de reservar existencias."""
    if not variante_ids:
        return
    stocks = db.session.execute(
        select(StockVariante).where(StockVariante.variante_id.in_(variante_ids))
    ).scalars().all()
    for stock in stocks:
        libre = max(0, stock.existencia - stock.reservado)
        pendiente = db.session.scalar(
            select(db.func.coalesce(db.func.sum(PedidoLinea.cant_pendiente), 0)).where(
                PedidoLinea.pedido.has(estado="EN_PRODUCCION"),
                PedidoLinea.venta_linea.has(variante_id=stock.variante_id),
            )
        )
        if libre == 0 and int(pendiente or 0) > 0:
            abrir(
                "PT_AGOTADO_DEMANDA",
                "CRITICA",
                "Producto agotado con pedidos en espera",
                f"La variante {stock.variante_id} tiene pedidos pendientes de producción.",
                "variante_producto",
                stock.variante_id,
                clave_unica=f"PT_AGOTADO_DEMANDA:{stock.variante_id}",
                accion_sugerida="Generar orden de producción",
            )
        elif 0 < libre <= stock.stock_minimo:
            abrir(
                "PT_STOCK_MINIMO",
                "PREVENTIVA",
                "Existencia en o por debajo del mínimo",
                f"La variante {stock.variante_id} alcanzó su stock mínimo.",
                "variante_producto",
                stock.variante_id,
                clave_unica=f"PT_STOCK_MINIMO:{stock.variante_id}",
                accion_sugerida="Generar orden de producción",
            )
