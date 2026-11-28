"""Órdenes de producción, explosión y reserva de materiales y calidad (M16).

Todas las operaciones usan transacciones explícitas y llaman a los servicios
propietarios de los datos que modifican (M14, M15, M17 y M12).
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    Color,
    InventarioMaterial,
    LoteMaterial,
    OrdenCompra,
    OrdenCompraLinea,
    OrdenMaterial,
    OrdenProduccion,
    OrdenProduccionLinea,
    Pedido,
    PedidoLinea,
    ProduccionPedido,
    Receta,
    RecetaBordado,
    RecetaLinea,
    Requisicion,
    RequisicionLinea,
    RevisionCalidad,
    StockVariante,
    VarianteProducto,
    VentaLinea,
)
from app.models.base import ahora_utc
from app.services import (
    alertas_service,
    bitacora_service,
    idempotencia_service,
    material_service,
    merma_service,
    pedido_service,
    receta_service,
    stock_service,
)
from app.utils.dinero import decimal_valor, material as material_texto
from app.utils.errores import ApiError
from app.utils.folios import generar_folio

ESTADOS_ABIERTOS = ("PLANEADA", "LISTA", "EN_PROCESO", "EN_REVISION")
ESTADOS_REQUISICION_VIGENTES = ("PENDIENTE", "EN_COTIZACION", "COMPRA_EMITIDA")
ALCANCE_IDEMPOTENCIA = "produccion:iniciar"


def _d(valor) -> Decimal:
    return decimal_valor(valor)


def _ahora():
    return ahora_utc()


def _color_na_id() -> int:
    color_id = db.session.scalar(select(Color.id).where(Color.codigo == "NA"))
    if color_id is None:
        raise ApiError("COLOR_NA_NO_DISPONIBLE", "No existe el color NA", 422)
    return color_id


def _orden(orden_id: int, bloquear=False) -> OrdenProduccion:
    consulta = select(OrdenProduccion).where(OrdenProduccion.id == orden_id)
    if bloquear:
        consulta = consulta.with_for_update()
    orden = db.session.scalar(consulta)
    if orden is None:
        raise ApiError("ORDEN_NO_ENCONTRADA", "Orden de producción no encontrada", 404)
    return orden


def _lineas(orden_id: int, bloquear=False) -> list:
    consulta = (
        select(OrdenProduccionLinea)
        .where(OrdenProduccionLinea.orden_id == orden_id)
        .order_by(OrdenProduccionLinea.id)
    )
    if bloquear:
        consulta = consulta.with_for_update()
    return db.session.execute(consulta).scalars().all()


def _materiales(orden_id: int, bloquear=False) -> list:
    consulta = (
        select(OrdenMaterial)
        .where(OrdenMaterial.orden_id == orden_id)
        .order_by(OrdenMaterial.inventario_material_id, OrdenMaterial.id)
    )
    if bloquear:
        consulta = consulta.with_for_update()
    return db.session.execute(consulta).scalars().all()


def _receta_vigente(variante_id: int) -> Receta:
    receta = receta_service.receta_para_variante(variante_id)
    if receta is None or receta.estado != "VIGENTE":
        raise ApiError(
            "RECETA_NO_VIGENTE",
            "La variante no tiene una receta vigente para producir",
            422,
        )
    return receta


def _lineas_receta(receta_id: int) -> list:
    materiales = db.session.execute(
        select(RecetaLinea).where(RecetaLinea.receta_id == receta_id)
    ).scalars().all()
    bordados = db.session.execute(
        select(RecetaBordado).where(RecetaBordado.receta_id == receta_id)
    ).scalars().all()
    propuestas = [
        {
            "material_id": fila.material_id,
            "cantidad_neta": fila.cantidad_neta,
            "factor_consumo": fila.factor_consumo,
            "merma_pct": fila.merma_pct,
        }
        for fila in materiales
    ]
    propuestas.extend(
        {"diseno_id": fila.diseno_id, "aplicaciones": fila.aplicaciones}
        for fila in bordados
    )
    return receta_service.lineas_calculadas(propuestas)


def _explosionar(orden: OrdenProduccion, lineas: list) -> None:
    """Suma la receta copiada de cada línea por material y color."""
    color_na = _color_na_id()
    necesidades = {}
    for linea in lineas:
        variante = db.session.get(VarianteProducto, linea.variante_id)
        for calculada in _lineas_receta(linea.receta_id):
            color_id = variante.color_id if calculada["por_color"] else color_na
            inventario = db.session.scalar(
                select(InventarioMaterial).where(
                    InventarioMaterial.material_id == calculada["material_id"],
                    InventarioMaterial.color_id == color_id,
                    InventarioMaterial.activo.is_(True),
                )
            )
            if inventario is None:
                raise ApiError(
                    "INVENTARIO_MATERIAL_NO_DISPONIBLE",
                    "No hay inventario activo para un material de la receta",
                    422,
                )
            cantidad = _d(calculada["cantidad_bruta"]) * int(linea.cantidad_planeada)
            necesidades[inventario.id] = necesidades.get(inventario.id, Decimal("0")) + cantidad

    for inventario_id, cantidad in sorted(necesidades.items()):
        db.session.add(
            OrdenMaterial(
                orden_id=orden.id,
                inventario_material_id=inventario_id,
                cantidad_requerida=cantidad,
                cantidad_reservada=0,
                cantidad_consumida=0,
                estado="FALTANTE",
            )
        )
    db.session.flush()


def crear(datos: dict, usuario_id: int, ip=None) -> dict:
    propuestas = datos.get("lineas") or []
    if not propuestas:
        raise ApiError("LINEAS_REQUERIDAS", "La orden requiere al menos una línea", 422)
    vistos = set()
    preparadas = []
    for item in propuestas:
        variante_id = int(item["variante_id"])
        if variante_id in vistos:
            raise ApiError("LINEA_DUPLICADA", "La variante está repetida", 422)
        vistos.add(variante_id)
        variante = db.session.get(VarianteProducto, variante_id)
        if variante is None or not variante.activa:
            raise ApiError("VARIANTE_NO_DISPONIBLE", "La variante no está activa", 422)
        preparadas.append((variante, _receta_vigente(variante_id), int(item["cantidad"])))

    orden = OrdenProduccion(
        folio=generar_folio("OP"),
        origen="MANUAL",
        estado="PLANEADA",
        semaforo="VERDE",
        fecha_requerida=datos.get("fecha_requerida"),
        creada_por=usuario_id,
        notas=datos.get("notas"),
    )
    db.session.add(orden)
    db.session.flush()
    lineas = []
    for variante, receta, cantidad in preparadas:
        linea = OrdenProduccionLinea(
            orden_id=orden.id,
            variante_id=variante.id,
            receta_id=receta.id,
            cantidad_planeada=cantidad,
        )
        db.session.add(linea)
        db.session.flush()
        lineas.append(linea)
    _explosionar(orden, lineas)
    orden.semaforo = calcular_semaforo_orden(orden.id)
    bitacora_service.registrar_bitacora(
        usuario_id,
        "ORDEN_PRODUCCION_CREADA",
        "orden_produccion",
        orden.id,
        {"folio": orden.folio, "lineas": len(lineas)},
        ip,
    )
    db.session.commit()
    return detalle(orden.id)


def _resumen(orden: OrdenProduccion) -> dict:
    lineas = _lineas(orden.id)
    materiales = _materiales(orden.id)
    return {
        "id": orden.id,
        "folio": orden.folio,
        "origen": orden.origen,
        "estado": orden.estado,
        "semaforo": orden.semaforo,
        "fecha_requerida": orden.fecha_requerida.isoformat() if orden.fecha_requerida else None,
        "iniciada_en": orden.iniciada_en.isoformat() if orden.iniciada_en else None,
        "cerrada_en": orden.cerrada_en.isoformat() if orden.cerrada_en else None,
        "total_planeado": sum(linea.cantidad_planeada for linea in lineas),
        "total_aprobado": sum(linea.cantidad_aprobada for linea in lineas),
        "total_merma": sum(linea.cantidad_merma for linea in lineas),
        "total_reproceso": sum(linea.cantidad_reproceso for linea in lineas),
        "materiales": len(materiales),
        "creada_por": orden.creada_por,
        "notas": orden.notas,
    }


def listar(filtros=None, pagina=1, por_pagina=20) -> dict:
    filtros = filtros or {}
    consulta = select(OrdenProduccion)
    if filtros.get("estado"):
        consulta = consulta.where(OrdenProduccion.estado == filtros["estado"])
    if filtros.get("semaforo"):
        consulta = consulta.where(OrdenProduccion.semaforo == filtros["semaforo"])
    if filtros.get("origen"):
        consulta = consulta.where(OrdenProduccion.origen == filtros["origen"])
    if filtros.get("desde"):
        consulta = consulta.where(OrdenProduccion.creado_en >= filtros["desde"])
    if filtros.get("hasta"):
        consulta = consulta.where(OrdenProduccion.creado_en < filtros["hasta"])
    if filtros.get("q"):
        patron = f"%{filtros['q']}%"
        consulta = consulta.where(
            db.or_(
                OrdenProduccion.folio.like(patron),
                OrdenProduccion.id.in_(
                    select(OrdenProduccionLinea.orden_id)
                    .join(VarianteProducto, VarianteProducto.id == OrdenProduccionLinea.variante_id)
                    .where(VarianteProducto.sku.like(patron))
                ),
            )
        )
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    ordenes = db.session.execute(
        consulta.order_by(OrdenProduccion.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars().all()
    return {
        "items": [_resumen(orden) for orden in ordenes],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def detalle(orden_id: int) -> dict:
    orden = _orden(orden_id)
    respuesta = _resumen(orden)
    lineas = _lineas(orden.id)
    respuesta["lineas"] = []
    for linea in lineas:
        variante = db.session.get(VarianteProducto, linea.variante_id)
        producto = db.session.get(VarianteProducto, linea.variante_id).producto
        respuesta["lineas"].append(
            {
                "id": linea.id,
                "variante_id": linea.variante_id,
                "sku": variante.sku,
                "producto": producto.nombre,
                "receta_id": linea.receta_id,
                "cantidad_planeada": linea.cantidad_planeada,
                "cantidad_aprobada": linea.cantidad_aprobada,
                "cantidad_merma": linea.cantidad_merma,
                "cantidad_reproceso": linea.cantidad_reproceso,
            }
        )
    respuesta["materiales"] = []
    for fila in _materiales(orden.id):
        inventario = db.session.get(InventarioMaterial, fila.inventario_material_id)
        requerida = _d(fila.cantidad_requerida)
        cubierta = _d(fila.cantidad_reservada) + _d(fila.cantidad_consumida)
        respuesta["materiales"].append(
            {
                "id": fila.id,
                "inventario_material_id": fila.inventario_material_id,
                "material_codigo": inventario.material.codigo,
                "material_nombre": inventario.material.nombre,
                "color_codigo": inventario.color.codigo if inventario.color else None,
                "unidad_base": inventario.material.unidad_base,
                "cantidad_requerida": material_texto(requerida),
                "cantidad_reservada": material_texto(fila.cantidad_reservada),
                "cantidad_consumida": material_texto(fila.cantidad_consumida),
                "cantidad_faltante": material_texto(max(Decimal("0"), requerida - cubierta)),
                "estado": fila.estado,
            }
        )
    respuesta["pedidos"] = []
    vinculos = db.session.execute(
        select(ProduccionPedido, Pedido, VentaLinea)
        .join(OrdenProduccionLinea, OrdenProduccionLinea.id == ProduccionPedido.orden_linea_id)
        .join(PedidoLinea, PedidoLinea.id == ProduccionPedido.pedido_linea_id)
        .join(Pedido, Pedido.id == PedidoLinea.pedido_id)
        .join(VentaLinea, VentaLinea.id == PedidoLinea.venta_linea_id)
        .where(OrdenProduccionLinea.orden_id == orden.id)
        .order_by(Pedido.id)
    ).all()
    for vinculo, pedido, venta_linea in vinculos:
        respuesta["pedidos"].append(
            {
                "pedido_id": pedido.id,
                "pedido_estado": pedido.estado,
                "sku": venta_linea.sku,
                "cantidad": vinculo.cantidad,
            }
        )
    respuesta["revisiones"] = [
        {
            "id": revision.id,
            "orden_linea_id": revision.orden_linea_id,
            "fecha": revision.fecha.isoformat() if revision.fecha else None,
            "cantidad_revisada": revision.cantidad_revisada,
            "cantidad_aprobada": revision.cantidad_aprobada,
            "cantidad_reproceso": revision.cantidad_reproceso,
            "cantidad_merma": revision.cantidad_merma,
            "observaciones": revision.observaciones,
        }
        for revision in db.session.execute(
            select(RevisionCalidad)
            .join(OrdenProduccionLinea, OrdenProduccionLinea.id == RevisionCalidad.orden_linea_id)
            .where(OrdenProduccionLinea.orden_id == orden.id)
            .order_by(RevisionCalidad.id)
        ).scalars().all()
    ]
    return respuesta


def _pendiente_linea():
    return (
        OrdenProduccionLinea.cantidad_planeada
        - OrdenProduccionLinea.cantidad_aprobada
        - OrdenProduccionLinea.cantidad_merma
    )


def pendientes_produccion(filtros=None, pagina=1, por_pagina=20) -> dict:
    filtros = filtros or {}
    consulta = (
        select(OrdenProduccion)
        .distinct()
        .join(OrdenProduccionLinea, OrdenProduccionLinea.orden_id == OrdenProduccion.id)
        .where(
            OrdenProduccion.estado.in_(ESTADOS_ABIERTOS),
            _pendiente_linea() > 0,
        )
    )
    if filtros.get("semaforo"):
        consulta = consulta.where(OrdenProduccion.semaforo == filtros["semaforo"])
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    ordenes = db.session.execute(
        consulta.order_by(OrdenProduccion.fecha_requerida.asc(), OrdenProduccion.id.asc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars().all()
    return {
        "items": [_resumen(orden) for orden in ordenes],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def pendientes_lineas(filtros=None, pagina=1, por_pagina=20) -> dict:
    """Demanda pendiente agrupada por SKU; fuente única de M09 y M16."""
    filtros = filtros or {}
    consulta = (
        select(
            VarianteProducto.id,
            VarianteProducto.sku,
            OrdenProduccion.id,
            OrdenProduccion.folio,
            OrdenProduccion.fecha_requerida,
            OrdenProduccion.semaforo,
            func.sum(ProduccionPedido.cantidad).label("demanda"),
        )
        .join(
            OrdenProduccionLinea,
            OrdenProduccionLinea.id == ProduccionPedido.orden_linea_id,
        )
        .join(OrdenProduccion, OrdenProduccion.id == OrdenProduccionLinea.orden_id)
        .join(VarianteProducto, VarianteProducto.id == OrdenProduccionLinea.variante_id)
        .where(
            OrdenProduccion.estado.in_(ESTADOS_ABIERTOS),
            _pendiente_linea() > 0,
        )
        .group_by(
            VarianteProducto.id,
            VarianteProducto.sku,
            OrdenProduccion.id,
            OrdenProduccion.folio,
            OrdenProduccion.fecha_requerida,
            OrdenProduccion.semaforo,
        )
        .order_by(
            OrdenProduccion.fecha_requerida.asc(),
            OrdenProduccion.id,
            VarianteProducto.id,
        )
    )
    if filtros.get("semaforo"):
        consulta = consulta.where(OrdenProduccion.semaforo == filtros["semaforo"])
    if filtros.get("sku"):
        consulta = consulta.where(VarianteProducto.sku.like(f"%{filtros['sku']}%"))
    filas = db.session.execute(consulta).all()
    items = [
        {
            "variante_id": variante_id,
            "sku": sku,
            "orden_id": orden_id,
            "orden_folio": folio,
            "demanda": int(demanda or 0),
            "fecha_estimada": fecha.isoformat() if fecha else None,
            "semaforo": semaforo,
        }
        for variante_id, sku, orden_id, folio, fecha, semaforo, demanda in filas
    ]
    total = len(items)
    inicio = (pagina - 1) * por_pagina
    return {
        "items": items[inicio : inicio + por_pagina],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def calcular_semaforo_orden(orden_id: int) -> str:
    orden = _orden(orden_id)
    hoy = date.today()
    if orden.fecha_requerida and orden.fecha_requerida < hoy:
        return "ROJO"
    materiales = _materiales(orden.id)
    faltantes = [
        fila
        for fila in materiales
        if _d(fila.cantidad_reservada) + _d(fila.cantidad_consumida)
        < _d(fila.cantidad_requerida)
    ]
    if not faltantes:
        return "VERDE"

    requisiciones = db.session.execute(
        select(Requisicion.id).where(
            Requisicion.orden_produccion_id == orden.id,
            Requisicion.estado.in_(ESTADOS_REQUISICION_VIGENTES),
        )
    ).scalars().all()
    for fila in faltantes:
        falta = _d(fila.cantidad_requerida) - _d(fila.cantidad_reservada) - _d(fila.cantidad_consumida)
        cubierto = Decimal("0")
        if requisiciones:
            cubierto += _d(
                db.session.scalar(
                    select(
                        func.coalesce(func.sum(RequisicionLinea.cantidad_base_faltante), 0)
                    ).where(
                        RequisicionLinea.requisicion_id.in_(requisiciones),
                        RequisicionLinea.inventario_material_id == fila.inventario_material_id,
                    )
                )
                or 0
            )
            ocs = db.session.execute(
                select(OrdenCompra, OrdenCompraLinea)
                .join(OrdenCompraLinea, OrdenCompraLinea.orden_compra_id == OrdenCompra.id)
                .where(
                    OrdenCompra.requisicion_id.in_(requisiciones),
                    OrdenCompra.estado.in_(("EMITIDA", "PARCIAL")),
                    OrdenCompraLinea.inventario_material_id == fila.inventario_material_id,
                )
            ).all()
            for orden_compra, linea_oc in ocs:
                if orden_compra.fecha_prometida and orden_compra.fecha_prometida < hoy:
                    return "ROJO"
                inventario = db.session.get(
                    InventarioMaterial, fila.inventario_material_id
                )
                factor = _d(inventario.material.factor_compra_base)
                cubierto += max(
                    Decimal("0"),
                    _d(linea_oc.cantidad_compra) * factor
                    - _d(linea_oc.cantidad_base_aceptada),
                )
        if cubierto < falta:
            return "ROJO"
    return "AMBAR"


def _disponible_por_inventario(inventario_ids, orden_id):
    lotes = db.session.execute(
        select(LoteMaterial)
        .where(
            LoteMaterial.inventario_material_id.in_(inventario_ids),
            LoteMaterial.estado == "DISPONIBLE",
            LoteMaterial.cantidad_base_disponible > 0,
        )
        .order_by(
            LoteMaterial.inventario_material_id,
            LoteMaterial.fecha_entrada,
            LoteMaterial.id,
        )
        .with_for_update()
    ).scalars().all()
    fisico = {}
    for lote in lotes:
        clave = lote.inventario_material_id
        fisico[clave] = fisico.get(clave, Decimal("0")) + _d(lote.cantidad_base_disponible)
    reservado = {}
    filas = db.session.execute(
        select(OrdenMaterial.inventario_material_id, OrdenMaterial.cantidad_reservada)
        .join(OrdenProduccion, OrdenProduccion.id == OrdenMaterial.orden_id)
        .where(
            OrdenMaterial.inventario_material_id.in_(inventario_ids),
            OrdenProduccion.estado.in_(ESTADOS_ABIERTOS),
            OrdenProduccion.id != orden_id,
        )
    ).all()
    for inventario_id, cantidad in filas:
        reservado[inventario_id] = reservado.get(inventario_id, Decimal("0")) + _d(cantidad)
    return {
        inventario_id: max(
            Decimal("0"), fisico.get(inventario_id, Decimal("0")) - reservado.get(inventario_id, Decimal("0"))
        )
        for inventario_id in inventario_ids
    }


def _reservar_transaccion(orden_id: int, usuario_id: int, ip=None) -> dict:
    orden = _orden(orden_id, bloquear=True)
    if orden.estado not in ("PLANEADA", "LISTA"):
        raise ApiError(
            "ESTADO_INVALIDO", "La orden ya no admite reserva de materiales", 409
        )
    materiales = _materiales(orden.id, bloquear=True)
    if not materiales:
        raise ApiError("ORDEN_SIN_MATERIALES", "La orden no tiene explosión de materiales", 422)
    disponible = _disponible_por_inventario(
        [fila.inventario_material_id for fila in materiales], orden.id
    )
    reservados = []
    for fila in materiales:
        requerida = _d(fila.cantidad_requerida)
        ya_reservada = _d(fila.cantidad_reservada)
        falta = max(Decimal("0"), requerida - ya_reservada)
        tomada = min(falta, disponible.get(fila.inventario_material_id, Decimal("0")))
        disponible[fila.inventario_material_id] = (
            disponible.get(fila.inventario_material_id, Decimal("0")) - tomada
        )
        fila.cantidad_reservada = ya_reservada + tomada
        total_cubierta = _d(fila.cantidad_reservada) + _d(fila.cantidad_consumida)
        if total_cubierta >= requerida:
            fila.estado = "COMPLETO"
        elif total_cubierta > 0:
            fila.estado = "PARCIAL"
        else:
            fila.estado = "FALTANTE"
        reservados.append(
            {
                "inventario_material_id": fila.inventario_material_id,
                "reservada": material_texto(tomada),
                "estado": fila.estado,
            }
        )
    completo = all(
        _d(fila.cantidad_reservada) + _d(fila.cantidad_consumida)
        >= _d(fila.cantidad_requerida)
        for fila in materiales
    )
    orden.estado = "LISTA" if completo else "PLANEADA"
    orden.semaforo = calcular_semaforo_orden(orden.id)
    bitacora_service.registrar_bitacora(
        usuario_id,
        "MATERIALES_RESERVADOS",
        "orden_produccion",
        orden.id,
        {"folio": orden.folio, "completo": completo},
        ip,
    )
    return {"orden": detalle(orden.id), "reservas": reservados}


def reservar_materiales(orden_id: int, usuario_id: int, ip=None) -> dict:
    respuesta = _reservar_transaccion(orden_id, usuario_id, ip)
    db.session.commit()
    return respuesta


def solicitar_compra(orden_id: int, usuario_id: int, ip=None) -> dict:
    from app.services import compras_service

    orden = _orden(orden_id, bloquear=True)
    if orden.estado not in ESTADOS_ABIERTOS:
        raise ApiError("ESTADO_INVALIDO", "La orden no está abierta", 409)
    faltantes = []
    for fila in _materiales(orden.id):
        falta = _d(fila.cantidad_requerida) - _d(fila.cantidad_reservada) - _d(fila.cantidad_consumida)
        if falta > 0:
            faltantes.append(
                {
                    "inventario_material_id": fila.inventario_material_id,
                    "cantidad_base_faltante": falta,
                }
            )
    if not faltantes:
        raise ApiError("SIN_FALTANTES", "La orden no tiene materiales faltantes", 422)
    existente = db.session.scalar(
        select(Requisicion)
        .where(
            Requisicion.orden_produccion_id == orden.id,
            Requisicion.estado.in_(ESTADOS_REQUISICION_VIGENTES),
        )
        .order_by(Requisicion.id.desc())
    )
    if existente is not None:
        return {
            "requisicion": compras_service.obtener_requisicion(existente.id),
            "duplicada": True,
        }
    requisicion = compras_service.generar_requisicion(
        "ORDEN_PRODUCCION",
        faltantes,
        usuario_id,
        orden.id,
        f"Faltantes de {orden.folio}",
        confirmar=False,
    )
    orden.semaforo = calcular_semaforo_orden(orden.id)
    db.session.commit()
    return {"requisicion": requisicion, "duplicada": False}


def _validar_materiales_para_iniciar(orden: OrdenProduccion, materiales: list) -> list:
    preparados = []
    for fila in materiales:
        pendiente = _d(fila.cantidad_reservada) - _d(fila.cantidad_consumida)
        if pendiente <= 0:
            continue
        preparados.append((fila, pendiente))
    if not preparados:
        raise ApiError(
            "SIN_RESERVA", "La orden no tiene materiales reservados para consumir", 422
        )
    inventarios = [fila.inventario_material_id for fila, _ in preparados]
    disponible = _disponible_por_inventario(inventarios, orden.id)
    faltantes = []
    for fila, pendiente in preparados:
        libre = disponible.get(fila.inventario_material_id, Decimal("0"))
        if libre < pendiente:
            faltantes.append(
                {
                    "inventario_material_id": fila.inventario_material_id,
                    "requerido": material_texto(pendiente),
                    "disponible": material_texto(libre),
                    "faltante": material_texto(pendiente - libre),
                }
            )
    if faltantes:
        raise ApiError(
            "MATERIAL_INSUFICIENTE",
            "No hay material suficiente para iniciar la producción",
            409,
            faltantes,
        )
    return preparados


def _iniciar_transaccion(orden_id, datos, usuario_id, registro):
    orden = _orden(orden_id, bloquear=True)
    if orden.estado != "LISTA":
        raise ApiError(
            "ESTADO_INVALIDO", "La orden debe estar LISTA para iniciar producción", 409
        )
    materiales = _materiales(orden.id, bloquear=True)
    preparados = _validar_materiales_para_iniciar(orden, materiales)
    consumo = []
    for fila, pendiente in preparados:
        lotes = material_service.consumir_peps(
            fila.inventario_material_id,
            pendiente,
            "ORDEN_PRODUCCION",
            orden.id,
            usuario_id,
            f"Inicio de {orden.folio}",
        )
        fila.cantidad_consumida = _d(fila.cantidad_consumida) + pendiente
        fila.estado = (
            "COMPLETO"
            if _d(fila.cantidad_consumida) >= _d(fila.cantidad_requerida)
            else "PARCIAL"
        )
        consumo.append(
            {
                "inventario_material_id": fila.inventario_material_id,
                "cantidad": material_texto(pendiente),
                "lotes": lotes,
            }
        )
    orden.estado = "EN_PROCESO"
    orden.iniciada_en = _ahora()
    orden.semaforo = "VERDE"
    respuesta = {"orden": detalle(orden.id), "consumo": consumo}
    bitacora_service.registrar_bitacora(
        usuario_id,
        "PRODUCCION_INICIADA",
        "orden_produccion",
        orden.id,
        {"folio": orden.folio, "materiales": len(consumo)},
    )
    idempotencia_service.completar(registro, respuesta)
    return respuesta


def iniciar_produccion(orden_id, datos, usuario_id, clave, ip=None) -> dict:
    if not clave:
        raise ApiError("IDEMPOTENCIA_REQUERIDA", "Se requiere Idempotency-Key", 400)
    peticion = {"orden_id": orden_id, "usuario_id": usuario_id, **(datos or {})}
    try:
        registro, previa = idempotencia_service.iniciar(
            clave, ALCANCE_IDEMPOTENCIA, peticion
        )
    except ApiError:
        db.session.rollback()
        raise
    if previa is not None:
        return previa
    try:
        respuesta = _iniciar_transaccion(orden_id, datos, usuario_id, registro)
        db.session.commit()
        return respuesta
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


def enviar_revision(orden_id: int, datos, usuario_id: int, ip=None) -> dict:
    orden = _orden(orden_id, bloquear=True)
    if orden.estado != "EN_PROCESO":
        raise ApiError(
            "ESTADO_INVALIDO", "Solo una orden EN_PROCESO puede enviarse a revisión", 409
        )
    orden.estado = "EN_REVISION"
    bitacora_service.registrar_bitacora(
        usuario_id,
        "ORDEN_EN_REVISION",
        "orden_produccion",
        orden.id,
        {"folio": orden.folio, "notas": (datos or {}).get("notas")},
        ip,
    )
    db.session.commit()
    return detalle(orden.id)


def asignar_pt_a_pedidos(variante_id, cantidad, usuario_id, orden_id=None) -> list:
    """Asigna unidades producidas a pedidos pendientes por antigüedad (FIFO)."""
    if int(cantidad) <= 0:
        return []
    stocks = stock_service.bloquear([variante_id])
    stock = stocks[variante_id]
    restante = int(cantidad)
    filas = db.session.execute(
        select(PedidoLinea, Pedido)
        .join(Pedido, Pedido.id == PedidoLinea.pedido_id)
        .join(VentaLinea, VentaLinea.id == PedidoLinea.venta_linea_id)
        .where(
            VentaLinea.variante_id == variante_id,
            PedidoLinea.cant_pendiente > 0,
            Pedido.estado.in_(("CONFIRMADO", "EN_PRODUCCION")),
        )
        .order_by(Pedido.creado_en, Pedido.id, PedidoLinea.id)
        .with_for_update(of=PedidoLinea)
    ).all()
    asignaciones = []
    for pedido_linea, pedido in filas:
        if restante <= 0:
            break
        solicitadas = min(restante, pedido_linea.cant_pendiente)
        reservadas = stock_service.reservar(
            stock,
            solicitadas,
            "PEDIDO",
            pedido.id,
            usuario_id,
            f"Producción aprobada orden {orden_id or ''}".strip(),
        )
        if reservadas <= 0:
            continue
        pedido_linea.cant_pendiente -= reservadas
        pedido_linea.cant_reservada += reservadas
        restante -= reservadas
        asignaciones.append(
            {"pedido_id": pedido.id, "pedido_linea_id": pedido_linea.id, "cantidad": reservadas}
        )
        if pedido_linea.cant_pendiente == 0 and pedido.estado == "EN_PRODUCCION":
            pedido.estado = "CONFIRMADO"
            pedido.estado_desde = _ahora()
            pedido_service.agregar_evento(
                pedido,
                "CONFIRMADO",
                "Producción aprobada: la cantidad pendiente quedó reservada",
                True,
                usuario_id,
            )
            pedido_service.crear_preparacion(pedido)
    return asignaciones


def registrar_dictamen(orden_id, datos, usuario_id, ip=None) -> dict:
    orden = _orden(orden_id, bloquear=True)
    if orden.estado != "EN_REVISION":
        raise ApiError(
            "ESTADO_INVALIDO", "La orden debe estar EN_REVISION para dictaminar", 409
        )
    propuestas = datos.get("lineas") or []
    if not propuestas:
        raise ApiError("LINEAS_REQUERIDAS", "Se requiere al menos una línea de dictamen", 422)
    lineas = {linea.id: linea for linea in _lineas(orden.id, bloquear=True)}
    asignaciones = []
    vistos = set()
    for item in propuestas:
        linea_id = int(item["orden_linea_id"])
        if linea_id in vistos:
            raise ApiError("LINEA_DUPLICADA", "La línea está repetida", 422)
        vistos.add(linea_id)
        linea = lineas.get(linea_id)
        if linea is None:
            raise ApiError("LINEA_NO_ENCONTRADA", "La línea no pertenece a la orden", 404)
        revisada = int(item["cantidad_revisada"])
        aprobadas = int(item["cantidad_aprobada"])
        reproceso = int(item["cantidad_reproceso"])
        merma = int(item["cantidad_merma"])
        if aprobadas + reproceso + merma != revisada:
            raise ApiError(
                "CANTIDADES_NO_CONCUADRAN",
                "Aprobadas, reproceso y merma deben igualar la cantidad revisada",
                422,
            )
        procesado = linea.cantidad_aprobada + linea.cantidad_merma + linea.cantidad_reproceso
        if revisada + procesado > linea.cantidad_planeada:
            raise ApiError(
                "EXCEDE_PLANIFICADO", "La revisión excede la cantidad planeada", 409
            )
        if aprobadas > 0 and not all(
            item[campo] for campo in ("medidas_ok", "costuras_ok", "bordado_ok", "etiquetas_ok")
        ):
            raise ApiError(
                "CHECKLIST_INCOMPLETO",
                "No se pueden aprobar unidades con el checklist incompleto",
                422,
            )
        revision = RevisionCalidad(
            orden_linea_id=linea.id,
            revisada_por=usuario_id,
            fecha=_ahora(),
            medidas_ok=bool(item["medidas_ok"]),
            costuras_ok=bool(item["costuras_ok"]),
            bordado_ok=bool(item["bordado_ok"]),
            etiquetas_ok=bool(item["etiquetas_ok"]),
            cantidad_revisada=revisada,
            cantidad_aprobada=aprobadas,
            cantidad_reproceso=reproceso,
            cantidad_merma=merma,
            observaciones=item.get("observaciones"),
        )
        db.session.add(revision)
        linea.cantidad_aprobada += aprobadas
        linea.cantidad_reproceso += reproceso
        linea.cantidad_merma += merma
        db.session.flush()

        if aprobadas:
            stocks = stock_service.bloquear([linea.variante_id])
            stock = stocks[linea.variante_id]
            stock.existencia += aprobadas
            stock_service.registrar_movimiento(
                stock,
                "PRODUCCION",
                aprobadas,
                0,
                "ORDEN_PRODUCCION",
                orden.id,
                usuario_id,
                f"Dictamen de {orden.folio}",
            )
            asignaciones.extend(
                asignar_pt_a_pedidos(
                    linea.variante_id, aprobadas, usuario_id, orden.id
                )
            )
        if merma:
            merma_service.registrar_merma(
                {
                    "origen": "PRODUCTO",
                    "variante_id": linea.variante_id,
                    "orden_produccion_id": orden.id,
                    "etapa": item.get("etapa_merma") or "ACABADOS",
                    "causa_id": item.get("causa_merma_id"),
                    "causa_nombre": "Defecto de acabado",
                    "cantidad": merma,
                    "descripcion": item.get("observaciones") or f"Dictamen de {orden.folio}",
                    "folio_origen": orden.folio,
                },
                usuario_id,
                ip,
                descontar=False,
                confirmar=False,
            )

    todas = db.session.execute(
        select(OrdenProduccionLinea).where(OrdenProduccionLinea.orden_id == orden.id)
    ).scalars().all()
    cerrada = all(
        fila.cantidad_aprobada + fila.cantidad_merma == fila.cantidad_planeada
        for fila in todas
    )
    hay_reproceso = any(fila.cantidad_reproceso > 0 for fila in todas)
    if cerrada:
        orden.estado = "CERRADA"
        orden.cerrada_en = _ahora()
        alertas_service.cerrar(f"ORDEN_ROJA:{orden.id}")
    elif hay_reproceso:
        orden.estado = "EN_PROCESO"
    else:
        orden.estado = "EN_REVISION"
    orden.semaforo = calcular_semaforo_orden(orden.id)
    bitacora_service.registrar_bitacora(
        usuario_id,
        "DICTAMEN_PRODUCCION",
        "orden_produccion",
        orden.id,
        {"folio": orden.folio, "estado": orden.estado, "lineas": len(propuestas)},
        ip,
    )
    respuesta = detalle(orden.id)
    respuesta["asignaciones"] = asignaciones
    db.session.commit()
    return respuesta


def cancelar(orden_id: int, datos, usuario_id: int, ip=None) -> dict:
    orden = _orden(orden_id, bloquear=True)
    if orden.estado not in ("PLANEADA", "LISTA"):
        raise ApiError(
            "ESTADO_INVALIDO", "Solo órdenes PLANEADA o LISTA pueden cancelarse", 409
        )
    lineas = _lineas(orden.id, bloquear=True)
    ids_lineas = [linea.id for linea in lineas]
    if ids_lineas:
        db.session.execute(
            text_delete("produccion_pedido", "orden_linea_id", ids_lineas)
        )
    for fila in _materiales(orden.id, bloquear=True):
        fila.cantidad_reservada = 0
        fila.estado = "FALTANTE"
    if ids_lineas:
        db.session.execute(text_delete("orden_material", "orden_id", [orden.id]))
        db.session.execute(text_delete("orden_produccion_linea", "orden_id", [orden.id]))
    orden.estado = "CANCELADA"
    orden.cerrada_en = _ahora()
    alertas_service.cerrar(f"ORDEN_ROJA:{orden.id}")
    bitacora_service.registrar_bitacora(
        usuario_id,
        "ORDEN_PRODUCCION_CANCELADA",
        "orden_produccion",
        orden.id,
        {"folio": orden.folio, "motivo": datos.get("motivo")},
        ip,
    )
    db.session.commit()
    return detalle(orden.id)


def text_delete(tabla, columna, ids):
    from sqlalchemy import text

    return text(f"DELETE FROM {tabla} WHERE {columna} IN :ids").bindparams(
        db.bindparam("ids", ids, expanding=True)
    )


def reevaluar_ordenes_por_recepcion(usuario_id: int, inventario_ids=None) -> None:
    """Reintenta reservas de órdenes PLANEADA tras una recepción (M14)."""
    ordenes = db.session.execute(
        select(OrdenProduccion)
        .where(OrdenProduccion.estado == "PLANEADA")
        .order_by(OrdenProduccion.fecha_requerida.asc(), OrdenProduccion.id.asc())
    ).scalars().all()
    for orden in ordenes:
        materiales = _materiales(orden.id)
        if not materiales:
            continue
        if inventario_ids is not None and not any(
            fila.inventario_material_id in inventario_ids for fila in materiales
        ):
            continue
        falta = any(
            _d(fila.cantidad_reservada) + _d(fila.cantidad_consumida)
            < _d(fila.cantidad_requerida)
            for fila in materiales
        )
        if falta:
            _reservar_transaccion(orden.id, usuario_id)
    for inventario_id in inventario_ids or []:
        alertas_service.cerrar(f"MP_REORDEN:{inventario_id}")


def plan_sugerido(filtros=None, pagina=1, por_pagina=20) -> dict:
    filtros = filtros or {}
    consulta = (
        select(StockVariante, VarianteProducto)
        .join(VarianteProducto, VarianteProducto.id == StockVariante.variante_id)
        .where(VarianteProducto.activa.is_(True))
    )
    if filtros.get("sku"):
        consulta = consulta.where(VarianteProducto.sku.like(f"%{filtros['sku']}%"))
    filas = db.session.execute(
        consulta.order_by(VarianteProducto.sku, VarianteProducto.id)
    ).all()
    items = []
    for stock, variante in filas:
        disponible = max(0, stock.existencia - stock.reservado)
        pendiente = int(
            db.session.scalar(
                select(func.coalesce(func.sum(PedidoLinea.cant_pendiente), 0))
                .join(Pedido, Pedido.id == PedidoLinea.pedido_id)
                .join(VentaLinea, VentaLinea.id == PedidoLinea.venta_linea_id)
                .where(
                    VentaLinea.variante_id == variante.id,
                    Pedido.estado.in_(("CONFIRMADO", "EN_PRODUCCION")),
                )
            )
            or 0
        )
        en_curso = int(
            db.session.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            OrdenProduccionLinea.cantidad_planeada
                            - OrdenProduccionLinea.cantidad_aprobada
                            - OrdenProduccionLinea.cantidad_merma
                        ),
                        0,
                    )
                )
                .join(OrdenProduccion, OrdenProduccion.id == OrdenProduccionLinea.orden_id)
                .where(
                    OrdenProduccionLinea.variante_id == variante.id,
                    OrdenProduccion.estado.in_(ESTADOS_ABIERTOS),
                )
            )
            or 0
        )
        sugerida = max(0, pendiente - en_curso)
        if disponible <= stock.stock_minimo:
            sugerida = max(sugerida, stock.cantidad_reposicion)
        if sugerida == 0 and not filtros.get("incluir_ceros"):
            continue
        items.append(
            {
                "variante_id": variante.id,
                "sku": variante.sku,
                "disponible": disponible,
                "stock_minimo": stock.stock_minimo,
                "pendiente_pedidos": pendiente,
                "produccion_en_curso": en_curso,
                "cantidad_sugerida": sugerida,
            }
        )
    total = len(items)
    inicio = (pagina - 1) * por_pagina
    return {
        "items": items[inicio : inicio + por_pagina],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


__all__ = [
    "ALCANCE_IDEMPOTENCIA",
    "asignar_pt_a_pedidos",
    "calcular_semaforo_orden",
    "cancelar",
    "crear",
    "detalle",
    "enviar_revision",
    "iniciar_produccion",
    "listar",
    "pendientes_produccion",
    "plan_sugerido",
    "reevaluar_ordenes_por_recepcion",
    "registrar_dictamen",
    "reservar_materiales",
    "solicitar_compra",
]
