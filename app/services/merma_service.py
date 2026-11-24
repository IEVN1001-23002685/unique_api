"""Registro central de mermas, reversos e indicadores (M17).

Los módulos M14, M15 y M16 no escriben en ``merma``: invocan este servicio.
Las funciones no confirman la transacción cuando ``confirmar=False`` para que el
módulo propietario de la operación pueda confirmar todo de forma atómica.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, text

from app.extensions import db
from app.models import (
    CausaMerma,
    Configuracion,
    InventarioMaterial,
    LoteMaterial,
    MovimientoMaterial,
    MovimientoProducto,
    Merma,
    StockVariante,
    VarianteProducto,
)
from app.models.base import ahora_utc
from app.services import alertas_service, bitacora_service, receta_service, stock_service
from app.utils.dinero import decimal_valor, dinero, material as material_texto, redondear
from app.utils.errores import ApiError


ESTADOS_MERMA_ETAPA = (
    "RECEPCION",
    "CORTE",
    "TEJIDO",
    "BORDADO",
    "CONFECCION",
    "ACABADOS",
    "ALMACEN",
    "ENTREGA",
    "DEVOLUCION",
)


def _d(valor) -> Decimal:
    return decimal_valor(valor)


def _ahora():
    return ahora_utc()


def _causa(causa_id=None, nombre=None, origen=None) -> CausaMerma:
    aplica = None
    if origen == "MATERIAL":
        aplica = ("MATERIAL", "AMBOS")
    elif origen == "PRODUCTO":
        aplica = ("PRODUCTO", "AMBOS")

    def valida(causa):
        return causa is not None and causa.activa and (aplica is None or causa.aplica_a in aplica)

    if causa_id is not None:
        causa = db.session.get(CausaMerma, causa_id)
        if valida(causa):
            return causa
    if nombre:
        consulta = select(CausaMerma).where(
            CausaMerma.nombre == nombre, CausaMerma.activa.is_(True)
        )
        if aplica:
            consulta = consulta.where(CausaMerma.aplica_a.in_(aplica))
        causa = db.session.execute(consulta).scalars().first()
        if causa is not None:
            return causa
    consulta = select(CausaMerma).where(
        CausaMerma.nombre == "Otro", CausaMerma.activa.is_(True)
    )
    if aplica:
        consulta = consulta.where(CausaMerma.aplica_a.in_(aplica))
    causa = db.session.execute(consulta).scalars().first()
    if causa is None:
        raise ApiError("CAUSA_MERMA_NO_DISPONIBLE", "No hay causas de merma activas", 422)
    return causa


def serializar(fila: Merma, incluir_costos: bool = True) -> dict:
    salida = {
        "id": fila.id,
        "origen": fila.origen,
        "inventario_material_id": fila.inventario_material_id,
        "lote_id": fila.lote_id,
        "variante_id": fila.variante_id,
        "orden_produccion_id": fila.orden_produccion_id,
        "recepcion_linea_id": fila.recepcion_linea_id,
        "devolucion_linea_id": fila.devolucion_linea_id,
        "reversa_de_id": fila.reversa_de_id,
        "etapa": fila.etapa,
        "causa_id": fila.causa_id,
        "causa_nombre": fila.causa.nombre if fila.causa else None,
        "cantidad": material_texto(fila.cantidad),
        "descripcion": fila.descripcion,
        "evidencia_url": fila.evidencia_url,
        "registrada_por": fila.registrada_por,
        "fecha": fila.fecha.isoformat() if fila.fecha else None,
    }
    if fila.variante_id:
        variante = db.session.get(VarianteProducto, fila.variante_id)
        salida["sku"] = variante.sku if variante else None
    if fila.inventario_material_id:
        inventario = db.session.get(InventarioMaterial, fila.inventario_material_id)
        salida["material_codigo"] = inventario.material.codigo if inventario else None
    if incluir_costos:
        salida["costo_perdido"] = dinero(fila.costo_perdido)
    return salida


def listar(filtros=None, incluir_costos=True) -> dict:
    filtros = filtros or {}
    pagina = int(filtros.get("pagina") or 1)
    por_pagina = int(filtros.get("por_pagina") or 20)
    consulta = select(Merma)
    if filtros.get("origen"):
        consulta = consulta.where(Merma.origen == filtros["origen"])
    if filtros.get("etapa"):
        consulta = consulta.where(Merma.etapa == filtros["etapa"])
    if filtros.get("causa_id"):
        consulta = consulta.where(Merma.causa_id == filtros["causa_id"])
    if filtros.get("variante_id"):
        consulta = consulta.where(Merma.variante_id == filtros["variante_id"])
    if filtros.get("inventario_material_id"):
        consulta = consulta.where(
            Merma.inventario_material_id == filtros["inventario_material_id"]
        )
    if filtros.get("orden_produccion_id"):
        consulta = consulta.where(
            Merma.orden_produccion_id == filtros["orden_produccion_id"]
        )
    if filtros.get("desde"):
        consulta = consulta.where(Merma.fecha >= filtros["desde"])
    if filtros.get("hasta"):
        consulta = consulta.where(Merma.fecha < filtros["hasta"])
    consulta = consulta.where(Merma.reversa_de_id.is_(None))
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.session.execute(
        consulta.order_by(Merma.fecha.desc(), Merma.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars().all()
    return {
        "items": [serializar(fila, incluir_costos) for fila in filas],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def obtener(merma_id: int, incluir_costos=True) -> dict:
    fila = db.session.get(Merma, merma_id)
    if fila is None:
        raise ApiError("MERMA_NO_ENCONTRADA", "Merma no encontrada", 404)
    return serializar(fila, incluir_costos)


def _costo_unitario_producto(variante_id: int) -> Decimal:
    return receta_service.costo_estandar_unitario(variante_id)


def registrar_merma(
    datos: dict,
    usuario_id: int,
    ip=None,
    descontar: bool = True,
    confirmar: bool = True,
) -> Merma:
    """Crea la merma. Cuando ``descontar`` es verdadero mueve el inventario."""
    origen = datos.get("origen")
    if origen not in ("MATERIAL", "PRODUCTO"):
        raise ApiError("ORIGEN_INVALIDO", "El origen de la merma es inválido", 422)
    etapa = datos.get("etapa")
    if etapa not in ESTADOS_MERMA_ETAPA:
        raise ApiError("ETAPA_INVALIDA", "La etapa de la merma es inválida", 422)
    cantidad = _d(datos.get("cantidad"))
    if cantidad <= 0:
        raise ApiError("CANTIDAD_INVALIDA", "La cantidad de merma debe ser mayor a cero", 422)
    if origen == "PRODUCTO" and cantidad != int(cantidad):
        raise ApiError(
            "CANTIDAD_INVALIDA", "La merma de producto debe ser en unidades enteras", 422
        )
    causa = _causa(datos.get("causa_id"), datos.get("causa_nombre"), origen)

    inventario_id = datos.get("inventario_material_id")
    variante_id = datos.get("variante_id")
    lote_id = datos.get("lote_id")
    if origen == "MATERIAL" and not inventario_id:
        raise ApiError(
            "INVENTARIO_MATERIAL_REQUERIDO", "La merma de material requiere inventario", 422
        )
    if origen == "PRODUCTO" and not variante_id:
        raise ApiError("VARIANTE_REQUERIDA", "La merma de producto requiere una variante", 422)

    stock = None
    lote = None
    if descontar and origen == "PRODUCTO":
        stocks = stock_service.bloquear([variante_id])
        stock = stocks[variante_id]
        if stock.existencia - int(cantidad) < stock.reservado:
            raise ApiError(
                "STOCK_INSUFICIENTE",
                "No hay suficientes unidades sin reservar para registrar la merma",
                409,
            )
    if descontar and origen == "MATERIAL" and lote_id:
        lote = db.session.get(LoteMaterial, lote_id, with_for_update=True)
        if lote is None or lote.estado != "DISPONIBLE":
            raise ApiError("LOTE_NO_DISPONIBLE", "El lote no está disponible", 409)
        if _d(lote.cantidad_base_disponible) < cantidad:
            raise ApiError("MATERIAL_INSUFICIENTE", "El lote no tiene suficiente material", 409)

    costo_linea = datos.get("costo_total")
    if costo_linea is None:
        if origen == "PRODUCTO":
            costo_unitario = _costo_unitario_producto(variante_id)
        elif lote is not None:
            costo_unitario = _d(lote.costo_unitario_base)
        elif inventario_id:
            inventario = db.session.get(InventarioMaterial, inventario_id)
            costo_unitario = (
                _d(inventario.material.costo_estandar_base) if inventario else Decimal("0")
            )
        else:
            costo_unitario = Decimal("0")
        costo_linea = redondear(cantidad * costo_unitario, "0.01")
    else:
        costo_linea = redondear(_d(costo_linea), "0.01")

    merma = Merma(
        origen=origen,
        inventario_material_id=inventario_id if origen == "MATERIAL" else None,
        lote_id=lote_id if origen == "MATERIAL" else None,
        variante_id=variante_id if origen == "PRODUCTO" else None,
        orden_produccion_id=datos.get("orden_produccion_id"),
        recepcion_linea_id=datos.get("recepcion_linea_id"),
        devolucion_linea_id=datos.get("devolucion_linea_id"),
        etapa=etapa,
        causa_id=causa.id,
        cantidad=cantidad,
        costo_perdido=costo_linea,
        descripcion=datos.get("descripcion"),
        evidencia_url=datos.get("evidencia_url"),
        registrada_por=usuario_id,
        fecha=datos.get("fecha") or _ahora(),
    )
    db.session.add(merma)
    db.session.flush()

    if descontar and origen == "PRODUCTO":
        stock.existencia -= int(cantidad)
        stock_service.registrar_movimiento(
            stock,
            "MERMA",
            -int(cantidad),
            0,
            "MERMA",
            merma.id,
            usuario_id,
            merma.descripcion or "Merma de producto terminado",
        )
    elif descontar and origen == "MATERIAL":
        if lote is not None:
            lote.cantidad_base_disponible = _d(lote.cantidad_base_disponible) - cantidad
            if lote.cantidad_base_disponible == 0:
                lote.estado = "AGOTADO"
            db.session.add(
                MovimientoMaterial(
                    lote_id=lote.id,
                    tipo="MERMA",
                    cantidad_base=-cantidad,
                    costo_unitario_base=_d(lote.costo_unitario_base),
                    documento_tipo="MERMA",
                    documento_id=merma.id,
                    motivo=merma.descripcion,
                    usuario_id=usuario_id,
                    fecha=_ahora(),
                )
            )
        else:
            from app.services import material_service

            material_service.consumir_peps(
                inventario_id,
                cantidad,
                "MERMA",
                merma.id,
                usuario_id,
                merma.descripcion,
                tipo="MERMA",
            )

    bitacora_service.registrar_bitacora(
        usuario_id,
        "MERMA_REGISTRADA",
        "merma",
        merma.id,
        {
            "folio_origen": datos.get("folio_origen"),
            "origen": origen,
            "etapa": etapa,
            "cantidad": material_texto(cantidad),
        },
        ip,
    )
    _alerta_meta(merma, datos.get("fecha") or _ahora())
    if confirmar:
        db.session.commit()
    return merma


def _alerta_meta(merma: Merma, fecha) -> None:
    if isinstance(fecha, date) and not hasattr(fecha, "hour"):
        fecha = _ahora()
    inicio = fecha.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    perdidas = _d(
        db.session.scalar(
            select(func.coalesce(func.sum(Merma.cantidad), 0)).where(
                Merma.fecha >= inicio,
                Merma.reversa_de_id.is_(None),
                Merma.etapa == merma.etapa,
            )
        )
        or 0
    )
    if merma.origen == "MATERIAL":
        producidas = _d(
            db.session.scalar(
                select(func.coalesce(func.sum(-MovimientoMaterial.cantidad_base), 0)).where(
                    MovimientoMaterial.fecha >= inicio,
                    MovimientoMaterial.tipo == "CONSUMO",
                )
            )
            or 0
        )
    else:
        producidas = _d(
            db.session.scalar(
                select(func.coalesce(func.sum(MovimientoProducto.delta_existencia), 0)).where(
                    MovimientoProducto.fecha >= inicio,
                    MovimientoProducto.tipo == "PRODUCCION",
                )
            )
            or 0
        )
    meta = db.session.scalar(
        select(Configuracion.valor).where(Configuracion.clave == "merma_meta_pct")
    )
    limite = _d(meta or "5")
    if producidas > 0 and limite > 0 and 100 * perdidas / producidas > limite:
        alertas_service.abrir(
            "MERMA_ALTA",
            "PREVENTIVA",
            "Merma por encima de la meta",
            f"La merma acumulada de {merma.etapa} superó la meta mensual.",
            "merma",
            merma.id,
            clave_unica=f"MERMA_ALTA:{merma.etapa}:{inicio.date().isoformat()}",
            accion_sugerida="Revisar causa y etapa de la merma",
        )


def reversar(merma_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    original = db.session.get(Merma, merma_id, with_for_update=True)
    if original is None:
        raise ApiError("MERMA_NO_ENCONTRADA", "Merma no encontrada", 404)
    if original.reversa_de_id is not None:
        raise ApiError("REVERSO_INVALIDO", "Un reverso no puede reversarse", 422)
    duplicada = db.session.execute(
        select(Merma.id).where(Merma.reversa_de_id == merma_id)
    ).first()
    if duplicada is not None:
        raise ApiError("MERMA_YA_REVERSADA", "La merma ya fue reversada", 409)
    motivo = datos.get("motivo") or "Reverso de merma"
    reverso = Merma(
        origen=original.origen,
        inventario_material_id=original.inventario_material_id,
        lote_id=original.lote_id,
        variante_id=original.variante_id,
        orden_produccion_id=original.orden_produccion_id,
        recepcion_linea_id=original.recepcion_linea_id,
        devolucion_linea_id=original.devolucion_linea_id,
        reversa_de_id=original.id,
        etapa=original.etapa,
        causa_id=original.causa_id,
        cantidad=original.cantidad,
        costo_perdido=original.costo_perdido,
        descripcion=f"Reverso de merma {original.id}: {motivo}",
        evidencia_url=datos.get("evidencia_url"),
        registrada_por=usuario_id,
        fecha=_ahora(),
    )
    db.session.add(reverso)
    db.session.flush()

    if original.origen == "MATERIAL":
        movimientos = db.session.execute(
            select(MovimientoMaterial)
            .where(
                MovimientoMaterial.tipo == "MERMA",
                MovimientoMaterial.documento_tipo == "MERMA",
                MovimientoMaterial.documento_id == original.id,
            )
            .order_by(MovimientoMaterial.id)
        ).scalars().all()
        for movimiento in movimientos:
            lote = db.session.get(LoteMaterial, movimiento.lote_id, with_for_update=True)
            if lote is None:
                continue
            devuelto = -_d(movimiento.cantidad_base)
            lote.cantidad_base_disponible = _d(lote.cantidad_base_disponible) + devuelto
            if lote.estado == "AGOTADO" and lote.cantidad_base_disponible > 0:
                lote.estado = "DISPONIBLE"
            db.session.add(
                MovimientoMaterial(
                    lote_id=lote.id,
                    tipo="REVERSA",
                    cantidad_base=devuelto,
                    costo_unitario_base=movimiento.costo_unitario_base,
                    documento_tipo="MERMA",
                    documento_id=reverso.id,
                    motivo=motivo,
                    usuario_id=usuario_id,
                    fecha=_ahora(),
                )
            )
    elif original.origen == "PRODUCTO":
        stocks = stock_service.bloquear([original.variante_id])
        stock = stocks[original.variante_id]
        stock.existencia += int(original.cantidad)
        stock_service.registrar_movimiento(
            stock,
            "AJUSTE",
            int(original.cantidad),
            0,
            "MERMA",
            reverso.id,
            usuario_id,
            motivo,
        )

    bitacora_service.registrar_bitacora(
        usuario_id,
        "MERMA_REVERSADA",
        "merma",
        original.id,
        {"motivo": motivo, "reverso_id": reverso.id},
        ip,
    )
    db.session.commit()
    return {
        "merma": obtener(original.id),
        "reverso": serializar(reverso),
    }


def indicadores(filtros=None) -> dict:
    filtros = filtros or {}
    clauses = []
    parametros = {}
    if filtros.get("desde"):
        clauses.append("fecha >= :desde")
        parametros["desde"] = filtros["desde"]
    if filtros.get("hasta"):
        clauses.append("fecha < :hasta")
        parametros["hasta"] = filtros["hasta"]
    if filtros.get("etapa"):
        clauses.append("etapa = :etapa")
        parametros["etapa"] = filtros["etapa"]
    if filtros.get("causa"):
        clauses.append("causa = :causa")
        parametros["causa"] = filtros["causa"]
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    filas = db.session.execute(
        text(
            "SELECT fecha, etapa, causa, producto, material, cantidad, "
            "costo_perdido, porcentaje_etapa FROM v_merma_resumen "
            f"{where} ORDER BY fecha DESC"
        ),
        parametros,
    ).mappings().all()
    resumen = [
        {
            "fecha": str(fila["fecha"]),
            "etapa": fila["etapa"],
            "causa": fila["causa"],
            "producto": fila["producto"],
            "material": fila["material"],
            "cantidad": material_texto(_d(fila["cantidad"])),
            "costo_perdido": dinero(fila["costo_perdido"]),
            "porcentaje_etapa": str(fila["porcentaje_etapa"] or 0),
        }
        for fila in filas
    ]

    def total(campo, valor=None, columna=None):
        consulta = select(func.coalesce(func.sum(campo), 0)).where(
            Merma.reversa_de_id.is_(None)
        )
        if valor is not None and columna is not None:
            consulta = consulta.where(columna == valor)
        if filtros.get("desde"):
            consulta = consulta.where(Merma.fecha >= filtros["desde"])
        if filtros.get("hasta"):
            consulta = consulta.where(Merma.fecha < filtros["hasta"])
        return _d(db.session.scalar(consulta) or 0)

    meta = db.session.scalar(
        select(Configuracion.valor).where(Configuracion.clave == "merma_meta_pct")
    )
    producidas = _d(
        db.session.scalar(
            select(func.coalesce(func.sum(MovimientoProducto.delta_existencia), 0)).where(
                MovimientoProducto.tipo == "PRODUCCION"
            )
        )
        or 0
    )
    consumido = _d(
        db.session.scalar(
            select(func.coalesce(func.sum(-MovimientoMaterial.cantidad_base), 0)).where(
                MovimientoMaterial.tipo == "CONSUMO"
            )
        )
        or 0
    )
    merma_producto = total(Merma.cantidad, "PRODUCTO", Merma.origen)
    merma_material = total(Merma.cantidad, "MATERIAL", Merma.origen)
    por_etapa = {}
    for fila in resumen:
        actual = por_etapa.setdefault(
            fila["etapa"], {"cantidad": Decimal("0"), "costo_perdido": Decimal("0")}
        )
        actual["cantidad"] += _d(fila["cantidad"])
        actual["costo_perdido"] += _d(fila["costo_perdido"])
    causas = {}
    for fila in resumen:
        causas[fila["causa"]] = causas.get(fila["causa"], Decimal("0")) + _d(fila["cantidad"])
    return {
        "meta_pct": str(_d(meta or "5")),
        "merma_producto": material_texto(merma_producto),
        "merma_material": material_texto(merma_material),
        "unidades_producidas": str(producidas),
        "material_consumido": material_texto(consumido),
        "merma_producto_pct": str(
            redondear(100 * merma_producto / producidas, "0.01") if producidas else "0.00"
        ),
        "merma_material_pct": str(
            redondear(100 * merma_material / consumido, "0.01") if consumido else "0.00"
        ),
        "costo_perdido": dinero(
            sum((_d(fila["costo_perdido"]) for fila in resumen), Decimal("0"))
        ),
        "por_etapa": {
            clave: {
                "cantidad": material_texto(valor["cantidad"]),
                "costo_perdido": dinero(valor["costo_perdido"]),
            }
            for clave, valor in por_etapa.items()
        },
        "top_causas": [
            {"causa": clave, "cantidad": material_texto(valor)}
            for clave, valor in sorted(causas.items(), key=lambda item: item[1], reverse=True)[:5]
        ],
        "detalle": resumen,
    }


__all__ = [
    "indicadores",
    "listar",
    "obtener",
    "registrar_merma",
    "reversar",
    "serializar",
]
