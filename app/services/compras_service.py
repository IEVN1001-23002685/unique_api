"""Requisiciones, cotizaciones, ordenes de compra y recepciones (M14)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

from sqlalchemy import select

from app.extensions import db
from app.models import (
    Alerta,
    CausaMerma,
    Cotizacion,
    CotizacionLinea,
    InventarioMaterial,
    OrdenCompra,
    OrdenCompraLinea,
    Proveedor,
    ProveedorMaterial,
    Recepcion,
    RecepcionLinea,
    Requisicion,
    RequisicionLinea,
)
from app.services import (
    bitacora_service,
    idempotencia_service,
    material_service,
)
from app.utils.errores import ApiError
from app.utils.folios import generar_folio

ALCANCE_IDEMPOTENCIA = "recepciones:registrar"
ORIGENES = ("ALERTA", "ORDEN_PRODUCCION", "MANUAL")
ESTADOS_REQUISICION_EDITABLES = ("PENDIENTE", "EN_COTIZACION")


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _d(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _dos(valor) -> str:
    return f"{_d(valor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def _cuatro(valor) -> str:
    return f"{_d(valor).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP):.4f}"


def _entero(valor) -> int:
    return int(_d(valor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _proveedor_material(inventario_id: int):
    inv = db.session.get(InventarioMaterial, inventario_id)
    if inv is None:
        raise ApiError("INVENTARIO_NO_ENCONTRADO", "Inventario de material no encontrado", 404)
    hoy = date.today()
    filas = db.session.execute(
        select(ProveedorMaterial)
        .where(
            ProveedorMaterial.material_id == inv.material_id,
            ProveedorMaterial.activo.is_(True),
        )
        .order_by(ProveedorMaterial.es_principal.desc(), ProveedorMaterial.id)
    ).scalars().all()
    vigentes = [
        fila
        for fila in filas
        if fila.vigencia_hasta is None or fila.vigencia_hasta >= hoy
    ]
    return vigentes[0] if vigentes else None


def _cantidad_compra_sugerida(inventario_id: int, faltante) -> Decimal:
    inv = db.session.get(InventarioMaterial, inventario_id)
    if inv is None:
        raise ApiError("INVENTARIO_NO_ENCONTRADO", "Inventario de material no encontrado", 404)
    factor = _d(inv.material.factor_compra_base)
    if factor <= 0:
        raise ApiError("FACTOR_COMPRA_INVALIDO", "El material no tiene factor de compra válido", 422)
    unidades = (_d(faltante) / factor).quantize(Decimal("1"), rounding=ROUND_CEILING)
    proveedor_material = _proveedor_material(inventario_id)
    minimo = _d(proveedor_material.minimo_compra) if proveedor_material else Decimal("0")
    return max(unidades, minimo).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _serializar_linea_requisicion(linea: RequisicionLinea) -> dict:
    inv = linea.inventario_material
    return {
        "id": linea.id,
        "inventario_material_id": linea.inventario_material_id,
        "material": inv.material.codigo,
        "nombre_material": inv.material.nombre,
        "color": inv.color.codigo,
        "unidad_base": inv.material.unidad_base,
        "cantidad_base_faltante": _cuatro(linea.cantidad_base_faltante),
        "cantidad_compra_sugerida": _dos(linea.cantidad_compra_sugerida),
        "cantidad_compra_atendida": _dos(linea.cantidad_compra_atendida),
    }


def _serializar_requisicion(requisicion: Requisicion, detallado=True) -> dict:
    resultado = {
        "id": requisicion.id,
        "folio": requisicion.folio,
        "origen": requisicion.origen,
        "orden_produccion_id": requisicion.orden_produccion_id,
        "estado": requisicion.estado,
        "prioridad": requisicion.prioridad,
        "solicitada_por": requisicion.solicitada_por,
        "fecha": requisicion.fecha.isoformat() if requisicion.fecha else None,
        "notas": requisicion.notas,
    }
    if detallado:
        lineas = db.session.execute(
            select(RequisicionLinea)
            .where(RequisicionLinea.requisicion_id == requisicion.id)
            .order_by(RequisicionLinea.id)
        ).scalars().all()
        resultado["lineas"] = [_serializar_linea_requisicion(linea) for linea in lineas]
    return resultado


def _serializar_linea_cotizacion(linea: CotizacionLinea) -> dict:
    return {
        "id": linea.id,
        "requisicion_linea_id": linea.requisicion_linea_id,
        "cantidad_compra": _dos(linea.cantidad_compra),
        "precio_unitario_compra": _dos(linea.precio_unitario_compra),
        "subtotal": _dos(linea.subtotal),
    }


def _serializar_cotizacion(cotizacion: Cotizacion) -> dict:
    lineas = db.session.execute(
        select(CotizacionLinea)
        .where(CotizacionLinea.cotizacion_id == cotizacion.id)
        .order_by(CotizacionLinea.id)
    ).scalars().all()
    return {
        "id": cotizacion.id,
        "requisicion_id": cotizacion.requisicion_id,
        "proveedor_id": cotizacion.proveedor_id,
        "proveedor": cotizacion.proveedor.nombre_comercial,
        "fecha": cotizacion.fecha.isoformat() if cotizacion.fecha else None,
        "vigencia_hasta": cotizacion.vigencia_hasta.isoformat() if cotizacion.vigencia_hasta else None,
        "plazo_dias": cotizacion.plazo_dias,
        "estado": cotizacion.estado,
        "total": _dos(cotizacion.total),
        "notas": cotizacion.notas,
        "lineas": [_serializar_linea_cotizacion(linea) for linea in lineas],
    }


def _serializar_linea_orden(linea: OrdenCompraLinea) -> dict:
    inv = linea.inventario_material
    return {
        "id": linea.id,
        "inventario_material_id": linea.inventario_material_id,
        "material": inv.material.codigo,
        "nombre_material": inv.material.nombre,
        "color": inv.color.codigo,
        "unidad_compra": inv.material.unidad_compra,
        "cantidad_compra": _dos(linea.cantidad_compra),
        "precio_unitario_compra": _dos(linea.precio_unitario_compra),
        "subtotal": _dos(linea.subtotal),
        "cantidad_base_aceptada": _cuatro(linea.cantidad_base_aceptada),
    }


def _serializar_orden(orden: OrdenCompra, detallado=True) -> dict:
    resultado = {
        "id": orden.id,
        "folio": orden.folio,
        "proveedor_id": orden.proveedor_id,
        "proveedor": orden.proveedor.nombre_comercial,
        "requisicion_id": orden.requisicion_id,
        "cotizacion_id": orden.cotizacion_id,
        "estado": orden.estado,
        "fecha_emision": orden.fecha_emision.isoformat() if orden.fecha_emision else None,
        "fecha_prometida": orden.fecha_prometida.isoformat() if orden.fecha_prometida else None,
        "total": _dos(orden.total),
        "condiciones_pago": orden.condiciones_pago,
        "notas": orden.notas,
    }
    if detallado:
        lineas = db.session.execute(
            select(OrdenCompraLinea)
            .where(OrdenCompraLinea.orden_compra_id == orden.id)
            .order_by(OrdenCompraLinea.id)
        ).scalars().all()
        resultado["lineas"] = [_serializar_linea_orden(linea) for linea in lineas]
    return resultado


def _serializar_recepcion(recepcion: Recepcion) -> dict:
    lineas = db.session.execute(
        select(RecepcionLinea)
        .where(RecepcionLinea.recepcion_id == recepcion.id)
        .order_by(RecepcionLinea.id)
    ).scalars().all()
    return {
        "id": recepcion.id,
        "folio": recepcion.folio,
        "orden_compra_id": recepcion.orden_compra_id,
        "fecha": recepcion.fecha.isoformat() if recepcion.fecha else None,
        "recibida_por": recepcion.recibida_por,
        "documento_proveedor": recepcion.documento_proveedor,
        "notas": recepcion.notas,
        "lineas": [
            {
                "id": linea.id,
                "orden_compra_linea_id": linea.orden_compra_linea_id,
                "cantidad_base_medida": _cuatro(linea.cantidad_base_medida),
                "cantidad_base_aceptada": _cuatro(linea.cantidad_base_aceptada),
                "cantidad_base_rechazada": _cuatro(linea.cantidad_base_rechazada),
                "motivo_rechazo": linea.motivo_rechazo,
            }
            for linea in lineas
        ],
    }


def _paginar(consulta, pagina: int, por_pagina: int):
    total = db.session.scalar(select(db.func.count()).select_from(consulta.subquery())) or 0
    filas = db.session.execute(
        consulta.offset((pagina - 1) * por_pagina).limit(por_pagina)
    ).scalars().all()
    return filas, total


# --- Requisiciones -------------------------------------------------------

def listar_requisiciones(filtros=None, pagina=1, por_pagina=20) -> dict:
    filtros = filtros or {}
    consulta = select(Requisicion)
    if filtros.get("estado"):
        consulta = consulta.where(Requisicion.estado == filtros["estado"])
    if filtros.get("origen"):
        consulta = consulta.where(Requisicion.origen == filtros["origen"])
    consulta = consulta.order_by(Requisicion.id.desc())
    filas, total = _paginar(consulta, pagina, por_pagina)
    return {
        "items": [_serializar_requisicion(fila, detallado=False) for fila in filas],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def obtener_requisicion(requisicion_id: int) -> dict:
    requisicion = db.session.get(Requisicion, requisicion_id)
    if requisicion is None:
        raise ApiError("REQUISICION_NO_ENCONTRADA", "Requisición no encontrada", 404)
    return _serializar_requisicion(requisicion)


def _reemplazar_lineas_requisicion(requisicion: Requisicion, lineas: list) -> None:
    if not lineas:
        raise ApiError("LINEAS_REQUERIDAS", "La requisición requiere al menos una línea", 422)
    actuales = db.session.execute(
        select(RequisicionLinea).where(RequisicionLinea.requisicion_id == requisicion.id)
    ).scalars().all()
    for linea in actuales:
        db.session.delete(linea)
    db.session.flush()
    vistos = set()
    for item in lineas:
        inventario_id = int(item["inventario_material_id"])
        if inventario_id in vistos:
            raise ApiError("LINEA_DUPLICADA", "El material/color está repetido", 422)
        vistos.add(inventario_id)
        faltante = _d(item["cantidad_base_faltante"])
        if faltante <= 0:
            raise ApiError("CANTIDAD_INVALIDA", "El faltante debe ser mayor que cero", 422)
        db.session.add(
            RequisicionLinea(
                requisicion_id=requisicion.id,
                inventario_material_id=inventario_id,
                cantidad_base_faltante=faltante,
                cantidad_compra_sugerida=_cantidad_compra_sugerida(inventario_id, faltante),
                cantidad_compra_atendida=0,
            )
        )


def crear_requisicion(datos: dict, usuario_id: int, ip=None, confirmar=True) -> dict:
    origen = datos.get("origen", "MANUAL")
    if origen not in ORIGENES:
        raise ApiError("ORIGEN_INVALIDO", "Origen de requisición inválido", 422)
    requisicion = Requisicion(
        folio=generar_folio("REQ"),
        origen=origen,
        orden_produccion_id=datos.get("orden_produccion_id"),
        estado="PENDIENTE",
        prioridad=datos.get("prioridad", "NORMAL"),
        solicitada_por=usuario_id,
        notas=datos.get("notas"),
        fecha=_ahora(),
    )
    db.session.add(requisicion)
    db.session.flush()
    _reemplazar_lineas_requisicion(requisicion, datos["lineas"])
    bitacora_service.registrar_bitacora(
        usuario_id,
        "REQUISICION_CREADA",
        "requisicion",
        requisicion.id,
        {"folio": requisicion.folio, "origen": origen},
        ip,
    )
    if confirmar:
        db.session.commit()
    return _serializar_requisicion(requisicion)


def generar_requisicion(
    origen,
    faltantes,
    usuario_id,
    orden_produccion_id=None,
    notas=None,
    confirmar=True,
):
    """Crea una requisición a partir de faltantes detectados por otro módulo."""
    return crear_requisicion(
        {
            "origen": origen,
            "orden_produccion_id": orden_produccion_id,
            "notas": notas,
            "lineas": faltantes,
        },
        usuario_id,
        confirmar=confirmar,
    )


def actualizar_requisicion(requisicion_id: int, datos: dict, usuario_id=None, ip=None) -> dict:
    requisicion = db.session.get(Requisicion, requisicion_id)
    if requisicion is None:
        raise ApiError("REQUISICION_NO_ENCONTRADA", "Requisición no encontrada", 404)
    if requisicion.estado not in ESTADOS_REQUISICION_EDITABLES:
        raise ApiError("ESTADO_INVALIDO", "La requisición ya no puede editarse", 409)
    if "lineas" in datos:
        _reemplazar_lineas_requisicion(requisicion, datos["lineas"])
    for campo in ("prioridad", "notas", "orden_produccion_id"):
        if campo in datos:
            setattr(requisicion, campo, datos[campo])
    bitacora_service.registrar_bitacora(
        usuario_id,
        "REQUISICION_ACTUALIZADA",
        "requisicion",
        requisicion.id,
        {"folio": requisicion.folio},
        ip,
    )
    db.session.commit()
    return _serializar_requisicion(requisicion)


def cancelar_requisicion(requisicion_id: int, usuario_id: int, ip=None) -> None:
    requisicion = db.session.get(Requisicion, requisicion_id)
    if requisicion is None:
        raise ApiError("REQUISICION_NO_ENCONTRADA", "Requisición no encontrada", 404)
    if requisicion.estado in ("ATENDIDA", "COMPRA_EMITIDA", "CANCELADA"):
        raise ApiError("ESTADO_INVALIDO", "La requisición ya no puede cancelarse", 409)
    requisicion.estado = "CANCELADA"
    bitacora_service.registrar_bitacora(
        usuario_id,
        "REQUISICION_CANCELADA",
        "requisicion",
        requisicion.id,
        {"folio": requisicion.folio},
        ip,
    )
    db.session.commit()


# --- Cotizaciones --------------------------------------------------------

def crear_cotizacion(requisicion_id: int, datos: dict, usuario_id: int) -> dict:
    requisicion = db.session.get(Requisicion, requisicion_id)
    if requisicion is None:
        raise ApiError("REQUISICION_NO_ENCONTRADA", "Requisición no encontrada", 404)
    if requisicion.estado not in ESTADOS_REQUISICION_EDITABLES:
        raise ApiError("ESTADO_INVALIDO", "La requisición no está en cotización", 409)
    proveedor = db.session.get(Proveedor, datos["proveedor_id"])
    if proveedor is None or proveedor.eliminado_en is not None or proveedor.estatus == "INACTIVO":
        raise ApiError("PROVEEDOR_NO_DISPONIBLE", "Proveedor no disponible", 404)

    lineas_req = {
        fila.id: fila
        for fila in db.session.execute(
            select(RequisicionLinea).where(
                RequisicionLinea.requisicion_id == requisicion.id
            )
        ).scalars().all()
    }
    if not datos.get("lineas"):
        raise ApiError("LINEAS_REQUERIDAS", "La cotización requiere líneas", 422)
    materiales = set(
        db.session.scalars(
            select(InventarioMaterial.material_id).where(
                InventarioMaterial.id.in_(
                    [linea.inventario_material_id for linea in lineas_req.values()]
                )
            )
        ).all()
    )
    surtidos = set(
        db.session.scalars(
            select(ProveedorMaterial.material_id).where(
                ProveedorMaterial.proveedor_id == proveedor.id,
                ProveedorMaterial.activo.is_(True),
                ProveedorMaterial.material_id.in_(materiales),
            )
        ).all()
    )
    if materiales - surtidos:
        raise ApiError(
            "PROVEEDOR_NO_SURTE_MATERIAL",
            "El proveedor no tiene en su catálogo todos los materiales solicitados",
            422,
            sorted(materiales - surtidos),
        )
    cotizacion = Cotizacion(
        requisicion_id=requisicion.id,
        proveedor_id=proveedor.id,
        fecha=_ahora(),
        vigencia_hasta=datos.get("vigencia_hasta"),
        plazo_dias=int(datos["plazo_dias"]),
        estado="PENDIENTE",
        total=0,
        notas=datos.get("notas"),
    )
    db.session.add(cotizacion)
    db.session.flush()
    total = Decimal("0")
    vistos = set()
    for item in datos["lineas"]:
        linea_id = int(item["requisicion_linea_id"])
        if linea_id not in lineas_req or linea_id in vistos:
            raise ApiError("LINEA_REQUISICION_INVALIDA", "Línea de requisición inválida", 422)
        vistos.add(linea_id)
        cantidad = _d(item["cantidad_compra"])
        precio = _d(item["precio_unitario_compra"])
        if cantidad <= 0 or precio < 0:
            raise ApiError("COTIZACION_INVALIDA", "Cantidad o precio inválido", 422)
        subtotal = _dos(cantidad * precio)
        total += _d(subtotal)
        db.session.add(
            CotizacionLinea(
                cotizacion_id=cotizacion.id,
                requisicion_linea_id=linea_id,
                cantidad_compra=cantidad,
                precio_unitario_compra=precio,
                subtotal=_d(subtotal),
            )
        )
    cotizacion.total = _d(total)
    requisicion.estado = "EN_COTIZACION"
    db.session.commit()
    return _serializar_cotizacion(cotizacion)


def listar_cotizaciones(requisicion_id: int = None) -> list:
    consulta = select(Cotizacion)
    if requisicion_id:
        consulta = consulta.where(Cotizacion.requisicion_id == requisicion_id)
    filas = db.session.execute(consulta.order_by(Cotizacion.id)).scalars().all()
    return [_serializar_cotizacion(fila) for fila in filas]


def elegir_cotizacion(cotizacion_id: int, usuario_id: int, ip=None) -> dict:
    cotizacion = db.session.get(Cotizacion, cotizacion_id)
    if cotizacion is None:
        raise ApiError("COTIZACION_NO_ENCONTRADA", "Cotización no encontrada", 404)
    if cotizacion.estado != "PENDIENTE":
        raise ApiError("ESTADO_INVALIDO", "La cotización ya fue resuelta", 409)
    if cotizacion.vigencia_hasta is not None and cotizacion.vigencia_hasta < date.today():
        raise ApiError("COTIZACION_VENCIDA", "La cotización ya no es vigente", 409)
    requisicion = cotizacion.requisicion
    if requisicion.estado in ("CANCELADA", "ATENDIDA", "COMPRA_EMITIDA"):
        raise ApiError("ESTADO_INVALIDO", "La requisición no permite emitir orden", 409)

    orden = OrdenCompra(
        folio=generar_folio("OC"),
        proveedor_id=cotizacion.proveedor_id,
        requisicion_id=requisicion.id,
        cotizacion_id=cotizacion.id,
        estado="BORRADOR",
        fecha_emision=None,
        fecha_prometida=date.today() + timedelta(days=cotizacion.plazo_dias),
        total=cotizacion.total,
        condiciones_pago=cotizacion.proveedor.condiciones_pago,
        notas=cotizacion.notas,
        creada_por=usuario_id,
    )
    db.session.add(orden)
    db.session.flush()
    lineas = db.session.execute(
        select(CotizacionLinea).where(CotizacionLinea.cotizacion_id == cotizacion.id)
    ).scalars().all()
    for linea in lineas:
        db.session.add(
            OrdenCompraLinea(
                orden_compra_id=orden.id,
                inventario_material_id=linea.requisicion_linea.inventario_material_id,
                cantidad_compra=linea.cantidad_compra,
                precio_unitario_compra=linea.precio_unitario_compra,
                subtotal=linea.subtotal,
                cantidad_base_aceptada=0,
            )
        )
        linea.requisicion_linea.cantidad_compra_atendida += linea.cantidad_compra
    cotizacion.estado = "ELEGIDA"
    otras = db.session.execute(
        select(Cotizacion).where(
            Cotizacion.requisicion_id == requisicion.id,
            Cotizacion.id != cotizacion.id,
            Cotizacion.estado == "PENDIENTE",
        )
    ).scalars().all()
    for otra in otras:
        otra.estado = "DESCARTADA"
    requisicion.estado = "COMPRA_EMITIDA"
    bitacora_service.registrar_bitacora(
        usuario_id,
        "COTIZACION_ELEGIDA",
        "orden_compra",
        orden.id,
        {"cotizacion_id": cotizacion.id, "folio": orden.folio},
        ip,
    )
    db.session.commit()
    return _serializar_orden(orden)


# --- Órdenes de compra ---------------------------------------------------

def listar_ordenes(filtros=None, pagina=1, por_pagina=20) -> dict:
    filtros = filtros or {}
    consulta = select(OrdenCompra)
    if filtros.get("estado"):
        consulta = consulta.where(OrdenCompra.estado == filtros["estado"])
    if filtros.get("proveedor_id"):
        consulta = consulta.where(OrdenCompra.proveedor_id == filtros["proveedor_id"])
    consulta = consulta.order_by(OrdenCompra.id.desc())
    filas, total = _paginar(consulta, pagina, por_pagina)
    return {
        "items": [_serializar_orden(fila, detallado=False) for fila in filas],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def obtener_orden(orden_id: int) -> dict:
    orden = db.session.get(OrdenCompra, orden_id)
    if orden is None:
        raise ApiError("ORDEN_COMPRA_NO_ENCONTRADA", "Orden de compra no encontrada", 404)
    return _serializar_orden(orden)


def _reemplazar_lineas_orden(orden: OrdenCompra, lineas: list) -> None:
    if not lineas:
        raise ApiError("LINEAS_REQUERIDAS", "La orden requiere al menos una línea", 422)
    actuales = db.session.execute(
        select(OrdenCompraLinea).where(OrdenCompraLinea.orden_compra_id == orden.id)
    ).scalars().all()
    for linea in actuales:
        db.session.delete(linea)
    db.session.flush()
    total = Decimal("0")
    vistos = set()
    plazos = []
    for item in lineas:
        inventario_id = int(item["inventario_material_id"])
        if inventario_id in vistos:
            raise ApiError("LINEA_DUPLICADA", "El material/color está repetido", 422)
        vistos.add(inventario_id)
        cantidad = _d(item["cantidad_compra"])
        precio = _d(item["precio_unitario_compra"])
        if cantidad <= 0 or precio < 0:
            raise ApiError("ORDEN_INVALIDA", "Cantidad o precio inválido", 422)
        subtotal = _dos(cantidad * precio)
        total += _d(subtotal)
        db.session.add(
            OrdenCompraLinea(
                orden_compra_id=orden.id,
                inventario_material_id=inventario_id,
                cantidad_compra=cantidad,
                precio_unitario_compra=precio,
                subtotal=_d(subtotal),
                cantidad_base_aceptada=0,
            )
        )
        proveedor_material = _proveedor_material(inventario_id)
        if proveedor_material:
            plazos.append(proveedor_material.plazo_dias)
    orden.total = _d(total)
    if plazos and orden.estado == "BORRADOR":
        orden.fecha_prometida = date.today() + timedelta(days=max(plazos))


def crear_orden(datos: dict, usuario_id: int, ip=None) -> dict:
    proveedor = db.session.get(Proveedor, datos["proveedor_id"])
    if proveedor is None or proveedor.eliminado_en is not None or proveedor.estatus == "INACTIVO":
        raise ApiError("PROVEEDOR_NO_DISPONIBLE", "Proveedor no disponible", 404)
    orden = OrdenCompra(
        folio=generar_folio("OC"),
        proveedor_id=proveedor.id,
        requisicion_id=datos.get("requisicion_id"),
        estado="BORRADOR",
        total=0,
        condiciones_pago=datos.get("condiciones_pago") or proveedor.condiciones_pago,
        notas=datos.get("notas"),
        creada_por=usuario_id,
    )
    db.session.add(orden)
    db.session.flush()
    _reemplazar_lineas_orden(orden, datos["lineas"])
    bitacora_service.registrar_bitacora(
        usuario_id, "ORDEN_COMPRA_CREADA", "orden_compra", orden.id, {"folio": orden.folio}, ip
    )
    db.session.commit()
    return _serializar_orden(orden)


def actualizar_orden(orden_id: int, datos: dict, usuario_id=None, ip=None) -> dict:
    orden = db.session.get(OrdenCompra, orden_id)
    if orden is None:
        raise ApiError("ORDEN_COMPRA_NO_ENCONTRADA", "Orden de compra no encontrada", 404)
    if orden.estado != "BORRADOR":
        raise ApiError("ESTADO_INVALIDO", "Solo se editan órdenes en borrador", 409)
    if "proveedor_id" in datos:
        proveedor = db.session.get(Proveedor, datos["proveedor_id"])
        if proveedor is None or proveedor.estatus == "INACTIVO":
            raise ApiError("PROVEEDOR_NO_DISPONIBLE", "Proveedor no disponible", 404)
        orden.proveedor_id = proveedor.id
    for campo in ("condiciones_pago", "notas", "fecha_prometida"):
        if campo in datos:
            setattr(orden, campo, datos[campo])
    if "lineas" in datos:
        _reemplazar_lineas_orden(orden, datos["lineas"])
    bitacora_service.registrar_bitacora(
        usuario_id,
        "ORDEN_COMPRA_ACTUALIZADA",
        "orden_compra",
        orden.id,
        {"folio": orden.folio},
        ip,
    )
    db.session.commit()
    return _serializar_orden(orden)


def emitir_orden(orden_id: int, usuario_id: int, ip=None) -> dict:
    orden = db.session.get(OrdenCompra, orden_id)
    if orden is None:
        raise ApiError("ORDEN_COMPRA_NO_ENCONTRADA", "Orden de compra no encontrada", 404)
    if orden.estado != "BORRADOR":
        raise ApiError("ESTADO_INVALIDO", "La orden ya fue emitida o cancelada", 409)
    orden.estado = "EMITIDA"
    orden.fecha_emision = _ahora()
    if orden.fecha_prometida is None:
        orden.fecha_prometida = date.today() + timedelta(days=7)
    bitacora_service.registrar_bitacora(
        usuario_id, "ORDEN_COMPRA_EMITIDA", "orden_compra", orden.id, {"folio": orden.folio}, ip
    )
    db.session.commit()
    return _serializar_orden(orden)


def cancelar_orden(orden_id: int, usuario_id: int, ip=None) -> dict:
    orden = db.session.get(OrdenCompra, orden_id)
    if orden is None:
        raise ApiError("ORDEN_COMPRA_NO_ENCONTRADA", "Orden de compra no encontrada", 404)
    if orden.estado in ("CANCELADA", "RECIBIDA"):
        raise ApiError("ESTADO_INVALIDO", "La orden ya está cerrada", 409)
    if db.session.scalar(
        select(db.func.count()).select_from(Recepcion).where(Recepcion.orden_compra_id == orden.id)
    ):
        raise ApiError("ORDEN_CON_RECEPCIONES", "La orden ya tiene recepciones", 409)
    orden.estado = "CANCELADA"
    if orden.requisicion_id:
        requisicion = db.session.get(Requisicion, orden.requisicion_id)
        if requisicion and requisicion.estado == "COMPRA_EMITIDA":
            requisicion.estado = "CANCELADA"
    bitacora_service.registrar_bitacora(
        usuario_id, "ORDEN_COMPRA_CANCELADA", "orden_compra", orden.id, {"folio": orden.folio}, ip
    )
    db.session.commit()
    return _serializar_orden(orden)


def _pdf_escapar(texto) -> str:
    plano = str(texto or "").encode("latin-1", "replace").decode("latin-1")
    return plano.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_orden(orden_id: int) -> tuple[bytes, str]:
    orden = db.session.get(OrdenCompra, orden_id)
    if orden is None:
        raise ApiError("ORDEN_COMPRA_NO_ENCONTRADA", "Orden de compra no encontrada", 404)
    datos = _serializar_orden(orden)
    lineas = [
        f"Orden de compra {datos['folio']}",
        f"Proveedor: {datos['proveedor']}",
        f"Estado: {datos['estado']}",
        f"Fecha prometida: {datos['fecha_prometida'] or 'Por definir'}",
        f"Condiciones de pago: {datos['condiciones_pago']}",
        "",
        "Material          Unidad de compra   Cantidad   Precio    Subtotal",
    ]
    for linea in datos["lineas"]:
        lineas.append(
            f"{linea['material']:<17} {linea['unidad_compra'][:16]:<17} "
            f"{linea['cantidad_compra']:>9} {linea['precio_unitario_compra']:>9} "
            f"{linea['subtotal']:>10}"
        )
    lineas.extend(["", f"Total: {datos['total']}", "Documento generado por UNIQUE."])
    contenido = "BT /F1 10 Tf 50 790 Td 14 TL\n"
    for linea in lineas[:55]:
        contenido += f"({_pdf_escapar(linea)}) Tj T*\n"
    contenido += "ET\n"
    cuerpo = contenido.encode("latin-1", "replace")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(cuerpo)).encode() + b" >>\nstream\n" + cuerpo + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    desplazamientos = []
    for indice, objeto in enumerate(objetos, start=1):
        desplazamientos.append(len(pdf))
        pdf += f"{indice} 0 obj\n".encode() + objeto + b"\nendobj\n"
    inicio_xref = len(pdf)
    pdf += f"xref\n0 {len(objetos) + 1}\n".encode()
    pdf += b"0000000000 65535 f \n"
    for desplazamiento in desplazamientos:
        pdf += f"{desplazamiento:010d} 00000 n \n".encode()
    pdf += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF\n"
    ).encode()
    return bytes(pdf), f"orden-compra-{datos['folio']}.pdf"


# --- Recepciones ---------------------------------------------------------

def _cerrar_alerta_orden_retrasada(orden_id: int) -> None:
    alerta = db.session.execute(
        select(Alerta).where(Alerta.clave_unica == f"OC_RETRASADA:{orden_id}")
    ).scalars().first()
    if alerta is not None:
        alerta.estado = "RESUELTA_AUTO"


def _registrar_recepcion_transaccion(usuario_id, datos, registro) -> dict:
    orden = db.session.get(OrdenCompra, datos["orden_compra_id"], with_for_update=True)
    if orden is None:
        raise ApiError("ORDEN_COMPRA_NO_ENCONTRADA", "Orden de compra no encontrada", 404)
    if orden.estado not in ("EMITIDA", "PARCIAL"):
        raise ApiError("ESTADO_INVALIDO", "La orden no puede recibir mercancía", 409)
    lineas_orden = {
        fila.id: fila
        for fila in db.session.execute(
            select(OrdenCompraLinea)
            .where(OrdenCompraLinea.orden_compra_id == orden.id)
            .order_by(OrdenCompraLinea.id)
            .with_for_update()
        ).scalars().all()
    }
    if not datos.get("lineas"):
        raise ApiError("LINEAS_REQUERIDAS", "La recepción requiere líneas", 422)

    recepcion = Recepcion(
        folio=generar_folio("REC"),
        orden_compra_id=orden.id,
        fecha=_ahora(),
        recibida_por=usuario_id,
        documento_proveedor=datos.get("documento_proveedor"),
        notas=datos.get("notas"),
    )
    db.session.add(recepcion)
    db.session.flush()

    causa_rechazo = db.session.execute(
        select(CausaMerma).where(CausaMerma.nombre == "Rechazo en recepción")
    ).scalars().first()
    hoy = date.today()
    vistos = set()
    for item in datos["lineas"]:
        linea_id = int(item["orden_compra_linea_id"])
        if linea_id not in lineas_orden or linea_id in vistos:
            raise ApiError("LINEA_ORDEN_INVALIDA", "Línea de orden inválida o repetida", 422)
        vistos.add(linea_id)
        linea_orden = lineas_orden[linea_id]
        inventario = material_service.obtener_inventario(linea_orden.inventario_material_id)
        factor = _d(inventario.material.factor_compra_base)
        if factor <= 0:
            raise ApiError("FACTOR_COMPRA_INVALIDO", "El material no tiene factor de compra válido", 422)
        base_pedida = _d(linea_orden.cantidad_compra) * factor
        pendiente = base_pedida - _d(linea_orden.cantidad_base_aceptada)
        medida = _d(item["cantidad_base_medida"])
        aceptada = _d(item["cantidad_base_aceptada"])
        rechazada = _d(item["cantidad_base_rechazada"])
        if medida <= 0 or aceptada < 0 or rechazada < 0:
            raise ApiError("CANTIDAD_INVALIDA", "Las cantidades deben ser no negativas", 422)
        if aceptada + rechazada != medida:
            raise ApiError(
                "CANTIDADES_NO_CONCUADRAN",
                "Aceptado más rechazado debe igualar la cantidad medida",
                422,
            )
        if aceptada > pendiente:
            raise ApiError("EXCEDE_ORDEN", "La cantidad aceptada excede lo pendiente de la orden", 409)
        if rechazada > 0 and causa_rechazo is None:
            raise ApiError("CAUSA_MERMA_NO_DISPONIBLE", "No existe la causa de merma configurada", 422)

        linea_recepcion = RecepcionLinea(
            recepcion_id=recepcion.id,
            orden_compra_linea_id=linea_id,
            peso_kg=item.get("peso_kg"),
            ancho_cm=item.get("ancho_cm"),
            largo_m=item.get("largo_m"),
            cantidad_base_medida=medida,
            cantidad_base_aceptada=aceptada,
            cantidad_base_rechazada=rechazada,
            motivo_rechazo=item.get("motivo_rechazo"),
        )
        db.session.add(linea_recepcion)
        db.session.flush()
        costo_unitario_base = _d(linea_orden.precio_unitario_compra) / factor
        if aceptada > 0:
            material_service.registrar_entrada(
                inventario.id,
                aceptada,
                costo_unitario_base,
                hoy,
                orden.proveedor_id,
                linea_recepcion.id,
                usuario_id,
                f"Recepción {recepcion.folio}",
            )
        if rechazada > 0:
            material_service.registrar_rechazo_recepcion(
                inventario.id,
                rechazada,
                costo_unitario_base,
                linea_recepcion.id,
                usuario_id,
                item.get("motivo_rechazo") or f"Rechazo en {recepcion.folio}",
            )
        linea_orden.cantidad_base_aceptada = _d(linea_orden.cantidad_base_aceptada) + aceptada

    todas = all(
        _d(linea.cantidad_base_aceptada)
        >= _d(linea.cantidad_compra) * _d(linea.inventario_material.material.factor_compra_base)
        for linea in lineas_orden.values()
    )
    orden.estado = "RECIBIDA" if todas else "PARCIAL"
    _cerrar_alerta_orden_retrasada(orden.id)
    from app.services import produccion_service

    produccion_service.reevaluar_ordenes_por_recepcion(
        usuario_id, [linea.inventario_material_id for linea in lineas_orden.values()]
    )
    respuesta = {
        "recepcion": _serializar_recepcion(recepcion),
        "orden_compra": {
            "id": orden.id,
            "folio": orden.folio,
            "estado": orden.estado,
        },
    }
    idempotencia_service.completar(registro, respuesta)
    db.session.commit()
    return respuesta


def registrar_recepcion(datos: dict, usuario_id: int, clave: str) -> dict:
    if not clave:
        raise ApiError("IDEMPOTENCIA_REQUERIDA", "Se requiere Idempotency-Key", 400)
    peticion = {"usuario_id": usuario_id, **datos}
    try:
        registro, respuesta_previa = idempotencia_service.iniciar(
            clave, ALCANCE_IDEMPOTENCIA, peticion
        )
    except ApiError:
        db.session.rollback()
        raise
    if respuesta_previa is not None:
        return respuesta_previa
    try:
        return _registrar_recepcion_transaccion(usuario_id, datos, registro)
    except ApiError as error:
        db.session.rollback()
        idempotencia_service.registrar_error(
            clave,
            ALCANCE_IDEMPOTENCIA,
            peticion,
            {
                "codigo": error.codigo,
                "mensaje": error.mensaje,
                "detalle": error.detalle,
                "status_code": error.status_code,
            },
        )
        raise
    except Exception:
        db.session.rollback()
        raise
