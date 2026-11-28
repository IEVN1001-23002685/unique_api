"""Indicadores del dashboard a partir de vistas y consultas agregadas (M20)."""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, true

from app.extensions import db
from app.models import (
    Alerta,
    Entrega,
    Merma,
    OrdenCompra,
    OrdenProduccion,
    OrdenProduccionLinea,
    Pedido,
    PedidoLinea,
    Preparacion,
    Recepcion,
    Repartidor,
    StockVariante,
    Venta,
)
from app.services.configuracion_service import valor_entero


ZONA_LOCAL = ZoneInfo("America/Mexico_City")


def _inicio_utc(dia):
    """Medianoche local de México convertida a UTC naive, como se guarda en MySQL."""
    local = datetime.combine(dia, time.min, tzinfo=ZONA_LOCAL)
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _inicio_dia():
    return _inicio_utc(date.today())


def _dinero(valor) -> str:
    return f"{Decimal(valor or 0):.2f}"


def _numero(valor) -> int:
    return int(valor or 0)


def _texto(valor) -> str:
    return str(valor or "")


def _rango(filtros, columna):
    """Rango de dias locales sobre columnas DATETIME almacenadas en UTC naive."""
    condicion = true()
    if filtros.get("desde"):
        condicion = condicion & (columna >= _inicio_utc(filtros["desde"]))
    if filtros.get("hasta"):
        condicion = condicion & (columna < _inicio_utc(filtros["hasta"] + timedelta(days=1)))
    return condicion


def _rango_fecha(filtros, columna):
    """Rango inclusivo sobre columnas DATE, que no requieren conversion de zona."""
    condicion = true()
    if filtros.get("desde"):
        condicion = condicion & (columna >= filtros["desde"])
    if filtros.get("hasta"):
        condicion = condicion & (columna <= filtros["hasta"])
    return condicion


def _conteos_estado(modelo, campo, estados, condicion=None):
    consulta = select(campo, func.count()).group_by(campo)
    if condicion is not None:
        consulta = consulta.where(condicion)
    filas = db.session.execute(consulta).all()
    conteo = {str(estado): 0 for estado in estados}
    for estado, total in filas:
        if str(estado) in conteo:
            conteo[str(estado)] = int(total)
    return conteo


def _kpis_base(filtros) -> dict:
    ventas_cond = _rango(filtros, Venta.fecha)
    activas = db.session.scalar(
        select(func.count()).select_from(Venta).where(ventas_cond, Venta.estado == "ACTIVA")
    ) or 0
    ingresos = db.session.scalar(
        select(func.coalesce(func.sum(Venta.total), 0)).where(
            ventas_cond, Venta.estado == "ACTIVA"
        )
    ) or Decimal("0")
    unidades = db.session.scalar(
        select(func.coalesce(func.sum(PedidoLinea.cantidad), 0))
        .join(Pedido, Pedido.id == PedidoLinea.pedido_id)
        .join(Venta, Venta.id == Pedido.venta_id)
        .where(ventas_cond, Venta.estado == "ACTIVA")
    ) or 0
    return {
        "periodo": {
            "desde": filtros["desde"].isoformat() if filtros.get("desde") else None,
            "hasta": filtros["hasta"].isoformat() if filtros.get("hasta") else None,
        },
        "ventas_activas": int(activas),
        "ingresos": _dinero(ingresos),
        "unidades_vendidas": _numero(unidades),
        "ticket_promedio": _dinero(Decimal(ingresos) / activas) if activas else "0.00",
        "pedidos_activos": _numero(
            db.session.scalar(
                select(func.count()).where(
                    _rango(filtros, Pedido.creado_en),
                    Pedido.estado.notin_(("ENTREGADO", "CANCELADO")),
                )
            )
        ),
        "pedidos_entregados": _numero(
            db.session.scalar(
                select(func.count()).where(
                    _rango(filtros, Pedido.creado_en), Pedido.estado == "ENTREGADO"
                )
            )
        ),
        "ordenes_produccion_activas": _numero(
            db.session.scalar(
                select(func.count()).where(
                    _rango(filtros, OrdenProduccion.creado_en),
                    OrdenProduccion.estado.in_(("PLANEADA", "LISTA", "EN_PROCESO", "EN_REVISION")),
                )
            )
        ),
        "alertas_abiertas": _numero(
            db.session.scalar(
                select(func.count()).where(
                    _rango(filtros, Alerta.creado_en), Alerta.estado == "ABIERTA"
                )
            )
        ),
        "variantes_bajo_minimo": _numero(
            db.session.scalar(
                select(func.count()).where(
                    StockVariante.existencia - StockVariante.reservado
                    <= StockVariante.stock_minimo
                )
            )
        ),
    }


def resumen(filtros=None) -> dict:
    filtros = filtros or {}
    datos = _kpis_base(filtros)
    datos["ventas_hoy"] = _dinero(
        db.session.scalar(
            select(func.coalesce(func.sum(Venta.total), 0)).where(
                Venta.fecha >= _inicio_dia(), Venta.estado == "ACTIVA"
            )
        )
    )
    datos["mermas"] = _numero(
        db.session.scalar(
            select(func.coalesce(func.sum(Merma.cantidad), 0)).where(
                _rango(filtros, Merma.fecha), Merma.reversa_de_id.is_(None)
            )
        )
    )
    datos["costo_mermas"] = _dinero(
        db.session.scalar(
            select(func.coalesce(func.sum(Merma.costo_perdido), 0)).where(
                _rango(filtros, Merma.fecha), Merma.reversa_de_id.is_(None)
            )
        )
    )
    return datos


def kpis(filtros=None) -> dict:
    return resumen(filtros)


def ventas(filtros=None) -> dict:
    filtros = filtros or {}
    datos = _kpis_base(filtros)
    condicion = _rango(filtros, Venta.fecha)
    datos["por_canal"] = [
        {"canal": canal, "ventas": int(total), "ingresos": _dinero(ingresos)}
        for canal, total, ingresos in db.session.execute(
            select(Venta.canal, func.count(), func.coalesce(func.sum(Venta.total), 0))
            .where(condicion, Venta.estado == "ACTIVA")
            .group_by(Venta.canal)
            .order_by(Venta.canal)
        ).all()
    ]
    datos["top_sku"] = [
        {
            "fecha": fila.fecha.isoformat() if hasattr(fila.fecha, "isoformat") else str(fila.fecha),
            "sku": fila.sku,
            "nombre_producto": fila.nombre_producto,
            "categoria": fila.categoria,
            "talla": fila.talla,
            "color": fila.color,
            "unidades": _numero(fila.unidades),
            "ingresos": _dinero(fila.ingresos),
        }
        for fila in db.session.execute(
            text(
                "SELECT fecha, sku, nombre_producto, categoria, talla, color, unidades, ingresos "
                "FROM v_ventas_sku WHERE (:desde IS NULL OR fecha >= :desde) "
                "AND (:hasta IS NULL OR fecha < :hasta_exclusivo) "
                "ORDER BY ingresos DESC, unidades DESC LIMIT 10"
            ),
            {
                "desde": filtros.get("desde"),
                "hasta_exclusivo": (
                    filtros["hasta"] + timedelta(days=1) if filtros.get("hasta") else None
                ),
            },
        ).all()
    ]
    return datos


def produccion(filtros=None, rol=None) -> dict:
    filtros = filtros or {}
    condicion = _rango(filtros, OrdenProduccion.creado_en)

    def total_lineas(columna):
        return _numero(
            db.session.scalar(
                select(func.coalesce(func.sum(columna), 0))
                .join(OrdenProduccion, OrdenProduccion.id == OrdenProduccionLinea.orden_id)
                .where(condicion)
            )
        )

    datos = {
        "por_estado": _conteos_estado(
            OrdenProduccion,
            OrdenProduccion.estado,
            ("PLANEADA", "LISTA", "EN_PROCESO", "EN_REVISION", "CERRADA", "CANCELADA"),
            condicion,
        ),
        "por_semaforo": _conteos_estado(
            OrdenProduccion,
            OrdenProduccion.semaforo,
            ("VERDE", "AMBAR", "ROJO"),
            condicion,
        ),
        "unidades_planeadas": total_lineas(OrdenProduccionLinea.cantidad_planeada),
        "unidades_aprobadas": total_lineas(OrdenProduccionLinea.cantidad_aprobada),
        "unidades_reproceso": total_lineas(OrdenProduccionLinea.cantidad_reproceso),
    }
    datos["ordenes_vencidas"] = _numero(
        db.session.scalar(
            select(func.count()).where(
                _rango_fecha(filtros, OrdenProduccion.fecha_requerida),
                OrdenProduccion.fecha_requerida < date.today(),
                OrdenProduccion.estado.in_(("PLANEADA", "LISTA", "EN_PROCESO", "EN_REVISION")),
            )
        )
    )
    return datos


def abastecimiento(filtros=None, rol=None) -> dict:
    filtros = filtros or {}
    filas = db.session.execute(
        text(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN disponible < stock_minimo THEN 1 ELSE 0 END) AS bajo_minimo, "
            "SUM(CASE WHEN disponible <= 0 THEN 1 ELSE 0 END) AS agotados, "
            "SUM(en_compra) AS en_compra "
            "FROM v_inventario_material"
        )
    ).one()
    datos = {
        "materiales_activos": _numero(filas.total),
        "bajo_minimo": _numero(filas.bajo_minimo),
        "agotados": _numero(filas.agotados),
        "en_compra": _texto(filas.en_compra),
        "ordenes_compra": _conteos_estado(
            OrdenCompra,
            OrdenCompra.estado,
            ("PENDIENTE", "EMITIDA", "PARCIAL", "RECIBIDA", "CANCELADA"),
            _rango(filtros, OrdenCompra.fecha_emision),
        ),
        "recepciones": _numero(
            db.session.scalar(
                select(func.count())
                .select_from(Recepcion)
                .where(_rango(filtros, Recepcion.fecha))
            )
        ),
    }
    datos["dias_abastecimiento"] = valor_entero("dias_produccion_estandar", 5)
    return datos


def logistica(filtros=None, rol=None) -> dict:
    filtros = filtros or {}
    datos = {
        "preparacion": _conteos_estado(
            Preparacion,
            Preparacion.estado,
            ("POR_SURTIR", "EN_PICKING", "EN_VERIFICACION", "EN_EMPAQUE", "LISTA"),
            _rango(filtros, Preparacion.creado_en),
        ),
        "entregas": _conteos_estado(
            Entrega,
            Entrega.estado,
            ("PROGRAMADA", "EN_RUTA", "ENTREGADA", "FALLIDA", "CANCELADA"),
            _rango(filtros, Entrega.creado_en),
        ),
        "pedidos_listo_envio": _numero(
            db.session.scalar(
                select(func.count()).where(
                    _rango(filtros, Pedido.creado_en), Pedido.estado == "LISTO_ENVIO"
                )
            )
        ),
        "repartidores_activos": _numero(
            db.session.scalar(
                select(func.count()).where(
                    Repartidor.activo.is_(True), Repartidor.eliminado_en.is_(None)
                )
            )
        ),
        "intentos_maximos": valor_entero("max_intentos_entrega", 2),
    }
    datos["entregas_programadas_hoy"] = _numero(
        db.session.scalar(
            select(func.count()).where(Entrega.fecha_programada == date.today())
        )
    )
    datos["entregas_programadas_periodo"] = _numero(
        db.session.scalar(
            select(func.count()).where(_rango_fecha(filtros, Entrega.fecha_programada))
        )
    )
    return datos


def exportar(filtros=None) -> str:
    """Genera un CSV con los indicadores administrativos del periodo."""
    import csv
    import io

    filtros = filtros or {}
    secciones = {
        "resumen": resumen(filtros),
        "ventas": ventas(filtros),
        "produccion": produccion(filtros),
        "abastecimiento": abastecimiento(filtros),
        "logistica": logistica(filtros),
    }
    buf = io.StringIO()
    escritor = csv.writer(buf)
    escritor.writerow(["seccion", "indicador", "valor"])
    for seccion, valores in secciones.items():
        for clave, valor in valores.items():
            if isinstance(valor, dict):
                for subclave, subvalor in valor.items():
                    escritor.writerow([seccion, f"{clave}.{subclave}", _texto(subvalor)])
            elif isinstance(valor, list):
                for indice, item in enumerate(valor, start=1):
                    escritor.writerow([seccion, f"{clave}[{indice}]", _texto(item)])
            else:
                escritor.writerow([seccion, clave, _texto(valor)])
    return buf.getvalue()
