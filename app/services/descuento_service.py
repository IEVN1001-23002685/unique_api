"""Selección y validación del descuento aplicable a una compra (M05, M08)."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, or_, select

from app.extensions import db
from app.models import Descuento, Venta
from app.utils.errores import ApiError


def _hoy():
    return datetime.now(timezone.utc).date()


def _importe(descuento: Descuento, subtotal: Decimal) -> Decimal:
    valor = Decimal(str(descuento.valor))
    if descuento.tipo == "PORCENTAJE":
        calculado = subtotal * valor / Decimal("100")
    else:
        calculado = valor
    calculado = calculado.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return min(calculado, subtotal)


def _ventas_previas(usuario_id: int) -> int:
    return (
        db.session.scalar(
            select(func.count())
            .select_from(Venta)
            .where(Venta.usuario_id == usuario_id, Venta.estado == "ACTIVA")
        )
        or 0
    )


def _usos_cliente(descuento_id: int, usuario_id: int) -> int:
    return (
        db.session.scalar(
            select(func.count())
            .select_from(Venta)
            .where(Venta.usuario_id == usuario_id, Venta.descuento_id == descuento_id)
        )
        or 0
    )


def _es_elegible(descuento: Descuento, subtotal: Decimal, articulos: int, usuario_id: int) -> bool:
    hoy = _hoy()
    if not descuento.activo or descuento.vigente_desde > hoy:
        return False
    if descuento.vigente_hasta is not None and descuento.vigente_hasta < hoy:
        return False
    if descuento.usos_maximos is not None and descuento.usos_actuales >= descuento.usos_maximos:
        return False
    if _usos_cliente(descuento.id, usuario_id) >= descuento.usos_por_cliente:
        return False
    if descuento.monto_minimo is not None and subtotal < Decimal(str(descuento.monto_minimo)):
        return False
    if descuento.min_articulos is not None and articulos < descuento.min_articulos:
        return False
    if descuento.solo_primera_compra and _ventas_previas(usuario_id) > 0:
        return False
    return True


def mejor(usuario_id: int, subtotal: Decimal, articulos: int, codigo: str | None = None) -> dict | None:
    """Devuelve el descuento de mayor ahorro; un solo descuento por compra."""
    subtotal = Decimal(str(subtotal)).quantize(Decimal("0.01"))
    hoy = _hoy()
    consulta = select(Descuento).where(
        Descuento.activo.is_(True), Descuento.vigente_desde <= hoy
    )
    consulta = consulta.where(
        or_(Descuento.vigente_hasta.is_(None), Descuento.vigente_hasta >= hoy)
    )
    disponibles = db.session.execute(consulta.order_by(Descuento.id)).scalars().all()

    if codigo:
        encontrados = [d for d in disponibles if d.codigo == codigo]
        if not encontrados:
            raise ApiError(
                "DESCUENTO_NO_VALIDO", "El cupón no existe o no está vigente", 422
            )
        candidatos = [
            d
            for d in disponibles
            if d.codigo == codigo or d.aplicacion == "AUTOMATICO"
        ]
    else:
        candidatos = [d for d in disponibles if d.aplicacion == "AUTOMATICO"]

    elegibles = [
        d for d in candidatos if _es_elegible(d, subtotal, articulos, usuario_id)
    ]
    if codigo and not any(d.codigo == codigo for d in elegibles):
        raise ApiError(
            "DESCUENTO_NO_APLICABLE", "El cupón no cumple las condiciones de uso", 422
        )
    if not elegibles:
        return None

    ganador = max(elegibles, key=lambda d: (_importe(d, subtotal), -d.id))
    monto = _importe(ganador, subtotal)
    if monto <= 0:
        return None
    return {
        "descuento_id": ganador.id,
        "codigo": ganador.codigo,
        "nombre": ganador.nombre,
        "tipo": ganador.tipo,
        "valor": f"{Decimal(str(ganador.valor)):.2f}",
        "monto": monto,
        "monto_texto": f"{monto:.2f}",
    }


def aplicable(usuario_id: int, subtotal: Decimal, articulos: int, codigo: str) -> dict:
    resultado = mejor(usuario_id, subtotal, articulos, codigo=codigo)
    if resultado is None:
        raise ApiError(
            "DESCUENTO_NO_APLICABLE", "El cupón no cumple las condiciones de uso", 422
        )
    return resultado
