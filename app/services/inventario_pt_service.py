"""Existencias, movimientos, ajustes y reposición de producto terminado (M12)."""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    CategoriaProducto,
    Color,
    MovimientoProducto,
    OrdenProduccion,
    OrdenProduccionLinea,
    Producto,
    Receta,
    StockVariante,
    Talla,
    VarianteProducto,
    Venta,
    VentaLinea,
)
from app.services import alertas_service, receta_service, stock_service
from app.services.bitacora_service import registrar_bitacora
from app.utils.errores import ApiError
from app.utils.folios import generar_folio

ESTADOS_ORDEN_ABIERTOS = ("PLANEADA", "LISTA", "EN_PROCESO", "EN_REVISION")


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _semaforo(disponible: int, minimo: int) -> str:
    if disponible <= 0:
        return "ROJO"
    if disponible <= minimo:
        return "AMBAR"
    return "VERDE"


def _ventas_30d() -> dict:
    desde = _ahora() - timedelta(days=30)
    filas = db.session.execute(
        select(VentaLinea.variante_id, func.sum(VentaLinea.cantidad))
        .join(Venta, Venta.id == VentaLinea.venta_id)
        .where(Venta.estado == "ACTIVA", Venta.fecha >= desde)
        .group_by(VentaLinea.variante_id)
    ).all()
    return {int(variante_id): int(cantidad or 0) for variante_id, cantidad in filas}


def _en_produccion() -> dict:
    filas = db.session.execute(
        select(
            OrdenProduccionLinea.variante_id,
            func.sum(
                OrdenProduccionLinea.cantidad_planeada
                - OrdenProduccionLinea.cantidad_aprobada
                - OrdenProduccionLinea.cantidad_merma
                - OrdenProduccionLinea.cantidad_reproceso
            ),
        )
        .join(OrdenProduccion, OrdenProduccion.id == OrdenProduccionLinea.orden_id)
        .where(OrdenProduccion.estado.in_(ESTADOS_ORDEN_ABIERTOS))
        .group_by(OrdenProduccionLinea.variante_id)
    ).all()
    return {int(variante_id): max(0, int(cantidad or 0)) for variante_id, cantidad in filas}


def listar(filtros=None, pagina: int = 1, por_pagina: int = 20) -> dict:
    filtros = filtros or {}
    consulta = (
        select(VarianteProducto, StockVariante, Producto, CategoriaProducto, Talla, Color)
        .join(StockVariante, StockVariante.variante_id == VarianteProducto.id)
        .join(Producto, Producto.id == VarianteProducto.producto_id)
        .join(CategoriaProducto, CategoriaProducto.id == Producto.categoria_id)
        .join(Talla, Talla.id == VarianteProducto.talla_id)
        .join(Color, Color.id == VarianteProducto.color_id)
    )
    if filtros.get("categoria"):
        valor = str(filtros["categoria"]).upper()
        consulta = consulta.where(
            (CategoriaProducto.prefijo_sku == valor)
            | (func.upper(CategoriaProducto.nombre) == valor)
        )
    if filtros.get("sku"):
        consulta = consulta.where(VarianteProducto.sku.like(f"%{filtros['sku']}%"))
    if filtros.get("color"):
        consulta = consulta.where(func.upper(Color.codigo) == str(filtros["color"]).upper())
    if filtros.get("talla"):
        consulta = consulta.where(func.upper(Talla.codigo) == str(filtros["talla"]).upper())

    filas = db.session.execute(consulta.order_by(CategoriaProducto.nombre, Producto.nombre, Talla.orden, Color.codigo)).all()
    ventas = _ventas_30d()
    produccion = _en_produccion()
    items = []
    for variante, stock, producto, categoria, talla, color in filas:
        disponible = stock.existencia - stock.reservado
        semaforo = _semaforo(disponible, stock.stock_minimo)
        if filtros.get("semaforo") and filtros["semaforo"] != semaforo:
            continue
        unidades = ventas.get(variante.id, 0)
        dias = (
            (Decimal(str(disponible)) * Decimal("30") / Decimal(str(unidades))).quantize(
                Decimal("0.01")
            )
            if unidades
            else None
        )
        items.append(
            {
                "variante_id": variante.id,
                "sku": variante.sku,
                "producto": producto.nombre,
                "categoria": categoria.nombre,
                "talla": talla.codigo,
                "color": color.codigo,
                "existencia": stock.existencia,
                "reservado": stock.reservado,
                "disponible": disponible,
                "stock_minimo": stock.stock_minimo,
                "cantidad_reposicion": stock.cantidad_reposicion,
                "en_produccion": produccion.get(variante.id, 0),
                "ventas_30d": unidades,
                "dias_cobertura": dias,
                "semaforo": semaforo,
            }
        )
    inicio = (pagina - 1) * por_pagina
    return {
        "items": items[inicio : inicio + por_pagina],
        "total": len(items),
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def movimientos(filtros=None, pagina: int = 1, por_pagina: int = 20) -> dict:
    filtros = filtros or {}
    condiciones = []
    if filtros.get("sku"):
        condiciones.append(VarianteProducto.sku.like(f"%{filtros['sku']}%"))
    if filtros.get("tipo"):
        condiciones.append(MovimientoProducto.tipo == filtros["tipo"])
    if filtros.get("documento_tipo"):
        condiciones.append(MovimientoProducto.documento_tipo == filtros["documento_tipo"])
    if filtros.get("desde"):
        condiciones.append(
            MovimientoProducto.fecha >= datetime.combine(filtros["desde"], time.min)
        )
    if filtros.get("hasta"):
        condiciones.append(
            MovimientoProducto.fecha <= datetime.combine(filtros["hasta"], time.max)
        )
    consulta = (
        select(MovimientoProducto, VarianteProducto.sku)
        .join(VarianteProducto, VarianteProducto.id == MovimientoProducto.variante_id)
        .where(*condiciones)
        .order_by(MovimientoProducto.fecha.desc(), MovimientoProducto.id.desc())
    )
    total = db.session.scalar(
        select(func.count())
        .select_from(MovimientoProducto)
        .join(VarianteProducto, VarianteProducto.id == MovimientoProducto.variante_id)
        .where(*condiciones)
    )
    filas = db.session.execute(
        consulta.offset((pagina - 1) * por_pagina).limit(por_pagina)
    ).all()
    return {
        "items": [
            {
                "id": movimiento.id,
                "variante_id": movimiento.variante_id,
                "sku": sku,
                "tipo": movimiento.tipo,
                "delta_existencia": movimiento.delta_existencia,
                "delta_reservado": movimiento.delta_reservado,
                "documento_tipo": movimiento.documento_tipo,
                "documento_id": movimiento.documento_id,
                "motivo": movimiento.motivo,
                "usuario_id": movimiento.usuario_id,
                "fecha": movimiento.fecha,
            }
            for movimiento, sku in filas
        ],
        "total": int(total or 0),
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def _asegurar_orden_reposicion(variante, cantidad: int, usuario_id: int):
    abierta = db.session.execute(
        select(OrdenProduccionLinea, OrdenProduccion)
        .join(OrdenProduccion, OrdenProduccion.id == OrdenProduccionLinea.orden_id)
        .where(
            OrdenProduccionLinea.variante_id == variante.id,
            OrdenProduccion.estado.in_(ESTADOS_ORDEN_ABIERTOS),
        )
        .order_by(OrdenProduccion.id)
        .with_for_update()
    ).first()
    if abierta is not None:
        linea, orden = abierta
        linea.cantidad_planeada += cantidad
        return orden
    receta = db.session.execute(
        select(Receta).where(
            Receta.producto_id == variante.producto_id,
            Receta.talla_id == variante.talla_id,
            Receta.estado == "VIGENTE",
        )
    ).scalars().first()
    if receta is None:
        raise ApiError(
            "RECETA_NO_VIGENTE",
            "No hay receta vigente para programar la reposición",
            422,
        )
    orden = OrdenProduccion(
        folio=generar_folio("OP"),
        origen="STOCK_MINIMO",
        estado="PLANEADA",
        semaforo="VERDE",
        creada_por=usuario_id,
        notas="Reposición automática por stock mínimo",
    )
    db.session.add(orden)
    db.session.flush()
    db.session.add(
        OrdenProduccionLinea(
            orden_id=orden.id,
            variante_id=variante.id,
            receta_id=receta.id,
            cantidad_planeada=cantidad,
        )
    )
    db.session.flush()
    return orden


def ajuste(datos: dict, usuario_id: int) -> dict:
    try:
        variante_id = int(datos["variante_id"])
        contada = int(datos["cantidad_contada"])
        motivo = datos["motivo"]
        stocks = stock_service.bloquear([variante_id])
        stock = stocks[variante_id]
        variante = db.session.execute(
            select(VarianteProducto)
            .where(VarianteProducto.id == variante_id)
            .with_for_update()
        ).scalars().first()
        if variante is None:
            raise ApiError("VARIANTE_NO_ENCONTRADA", "Variante no encontrada", 404)
        anterior = stock.existencia
        diferencia = contada - anterior
        if "diferencia" in datos and int(datos["diferencia"]) != diferencia:
            raise ApiError(
                "DIFERENCIA_INCORRECTA", "La diferencia no coincide con el conteo", 422
            )
        if diferencia == 0:
            raise ApiError("SIN_DIFERENCIA", "El conteo no genera ninguna diferencia", 422)
        if contada < stock.reservado:
            raise ApiError(
                "RESERVA_SUPERA_EXISTENCIA",
                "La existencia contada no puede ser menor a la reservada",
                422,
            )
        disponible = contada - stock.reservado
        if disponible <= stock.stock_minimo and stock.cantidad_reposicion > 0:
            receta = db.session.execute(
                select(Receta).where(
                    Receta.producto_id == variante.producto_id,
                    Receta.talla_id == variante.talla_id,
                    Receta.estado == "VIGENTE",
                )
            ).scalars().first()
            if receta is None:
                raise ApiError(
                    "RECETA_NO_VIGENTE",
                    "No hay receta vigente para programar la reposición",
                    422,
                )

        stock.existencia = contada
        stock_service.registrar_movimiento(
            stock,
            "AJUSTE",
            diferencia,
            0,
            "AJUSTE",
            variante_id,
            usuario_id,
            motivo,
        )
        alerta = alertas_service.abrir(
            "DIFERENCIA_CONTEO",
            "INFORMATIVA",
            "Diferencia detectada en conteo físico",
            f"SKU {variante.sku}: existencia {anterior}, contada {contada}, diferencia {diferencia}. {motivo}",
            "variante_producto",
            variante_id,
            clave_unica=f"DIFERENCIA_CONTEO:{variante_id}",
            accion_sugerida="Verificar movimientos de producto terminado",
        )
        alertas_service.evaluar_variantes([variante_id])
        orden = None
        if disponible <= stock.stock_minimo and stock.cantidad_reposicion > 0:
            orden = _asegurar_orden_reposicion(
                variante, int(stock.cantidad_reposicion), usuario_id
            )
        registrar_bitacora(
            usuario_id,
            "AJUSTE_INVENTARIO_PT",
            "stock_variante",
            variante_id,
            {"anterior": anterior, "contada": contada, "diferencia": diferencia},
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return {
        "variante_id": variante_id,
        "sku": variante.sku,
        "existencia_anterior": anterior,
        "cantidad_contada": contada,
        "diferencia": diferencia,
        "existencia_actual": stock.existencia,
        "disponible": stock.existencia - stock.reservado,
        "semaforo": _semaforo(stock.existencia - stock.reservado, stock.stock_minimo),
        "alerta_id": alerta.id if alerta else None,
        "orden_produccion_id": orden.id if orden else None,
        "orden_produccion_folio": orden.folio if orden else None,
    }


def actualizar_reglas(variante_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    try:
        stock = stock_service.bloquear([variante_id])[variante_id]
        cambios = {}
        for campo in ("stock_minimo", "cantidad_reposicion"):
            if campo in datos and datos[campo] is not None:
                valor = int(datos[campo])
                if valor < 0:
                    raise ApiError("VALOR_NEGATIVO", f"{campo} no puede ser negativo", 400)
                if getattr(stock, campo) != valor:
                    cambios[campo] = {"anterior": getattr(stock, campo), "nuevo": valor}
                    setattr(stock, campo, valor)
        registrar_bitacora(
            usuario_id, "REGLAS_REPOSICION_ACTUALIZADAS", "stock_variante", variante_id, cambios, ip
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    variante = db.session.get(VarianteProducto, variante_id)
    return {
        "variante_id": variante_id,
        "sku": variante.sku if variante else None,
        "stock_minimo": stock.stock_minimo,
        "cantidad_reposicion": stock.cantidad_reposicion,
    }
