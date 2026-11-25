"""Apertura, deduplicación, consulta y atención de alertas (M21)."""

from decimal import Decimal

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    Alerta,
    Configuracion,
    InventarioMaterial,
    LoteMaterial,
    OrdenCompra,
    OrdenProduccionLinea,
    PedidoLinea,
    StockVariante,
    Venta,
)
from app.models.base import ahora_utc
from app.utils.errores import ApiError

TIPOS = (
    "PT_AGOTADO_DEMANDA",
    "PT_STOCK_MINIMO",
    "MP_INSUFICIENTE",
    "MP_REORDEN",
    "ORDEN_ROJA",
    "OC_RETRASADA",
    "PEDIDO_ESTANCADO",
    "MERMA_ALTA",
    "DIFERENCIA_CONTEO",
    "ENTREGA_FALLIDA",
    "DEVOLUCION_PENDIENTE",
    "PAGO_PENDIENTE",
    "PROVEEDOR_EN_REVISION",
    "DISENO_PENDIENTE",
)

REGLAS = {
    "merma_meta_pct": "Umbral de merma para abrir MERMA_ALTA",
    "proveedor_minimo_a_tiempo_pct": "Entregas a tiempo mínimas por proveedor",
    "max_intentos_entrega": "Intentos fallidos antes de alerta crítica",
    "horas_max_recibido": "Horas máximas en RECIBIDO",
    "horas_max_confirmado": "Horas máximas en CONFIRMADO",
    "dias_max_en_produccion": "Días máximos en producción",
    "horas_max_en_preparacion": "Horas máximas en preparación",
    "horas_max_listo_envio": "Horas máximas en LISTO_ENVIO",
    "horas_max_en_reparto": "Horas máximas en reparto",
    "horas_alerta_devolucion": "Horas para alertar devolución sin atender",
    "dias_carrito_abandonado": "Días para abandono de carrito",
}


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
            if existente.estado == "ABIERTA":
                return existente
            existente.estado = "ABIERTA"
            existente.severidad = severidad
            existente.titulo = titulo
            existente.detalle = detalle
            existente.accion_sugerida = accion_sugerida
            existente.atendida_por = None
            existente.atendida_en = None
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


def cerrar(clave_unica: str) -> bool:
    """Cierra por clave de negocio cuando la condición desaparece."""
    alerta = db.session.execute(
        select(Alerta).where(Alerta.clave_unica == clave_unica)
    ).scalars().first()
    if alerta is None or alerta.estado != "ABIERTA":
        return False
    alerta.estado = "RESUELTA_AUTO"
    alerta.clave_unica = None
    return True


def elevar(clave_unica: str, severidad: str, detalle: str) -> bool:
    """Eleva la severidad de una alerta abierta sin duplicarla."""
    alerta = db.session.execute(
        select(Alerta).where(Alerta.clave_unica == clave_unica)
    ).scalars().first()
    if alerta is None or alerta.estado != "ABIERTA":
        return False
    alerta.severidad = severidad
    alerta.detalle = detalle
    return True


def atender(alerta_id: int, usuario_id: int) -> Alerta:
    alerta = db.session.get(Alerta, alerta_id)
    if alerta is None:
        raise ApiError("ALERTA_NO_ENCONTRADA", "Alerta no encontrada", 404)
    if alerta.estado != "ABIERTA":
        raise ApiError("ALERTA_NO_ABIERTA", "La alerta no está abierta", 409)
    alerta.estado = "ATENDIDA"
    alerta.atendida_por = usuario_id
    alerta.atendida_en = ahora_utc()
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


def _iso(valor):
    return valor.isoformat() if valor is not None else None


def serializar(alerta: Alerta) -> dict:
    return {
        "id": alerta.id,
        "tipo": alerta.tipo,
        "severidad": alerta.severidad,
        "titulo": alerta.titulo,
        "detalle": alerta.detalle,
        "entidad_tipo": alerta.entidad_tipo,
        "entidad_id": alerta.entidad_id,
        "rol_destino": alerta.rol_destino,
        "accion_sugerida": alerta.accion_sugerida,
        "estado": alerta.estado,
        "clave_unica": alerta.clave_unica,
        "atendida_por": alerta.atendida_por,
        "atendida_en": _iso(alerta.atendida_en),
        "creado_en": _iso(alerta.creado_en),
    }


def _consulta(filtros, rol=None, resueltas=False):
    consulta = select(Alerta)
    if resueltas:
        consulta = consulta.where(Alerta.estado == "RESUELTA_AUTO")
    else:
        consulta = consulta.where(Alerta.estado == "ABIERTA")
    if rol == "OPERATIVO":
        consulta = consulta.where(Alerta.rol_destino.in_(("OPERATIVO", "AMBOS")))
    estado = filtros.get("estado")
    if estado:
        consulta = consulta.where(Alerta.estado == estado)
    tipo = filtros.get("tipo")
    if tipo:
        consulta = consulta.where(Alerta.tipo == tipo)
    severidad = filtros.get("severidad")
    if severidad:
        consulta = consulta.where(Alerta.severidad == severidad)
    return consulta


def listar(filtros=None, pagina=1, por_pagina=20, rol=None, resueltas=False) -> dict:
    filtros = filtros or {}
    consulta = _consulta(filtros, rol=rol, resueltas=resueltas)
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.session.execute(
        consulta.order_by(
            Alerta.estado,
            Alerta.creado_en.desc(),
            Alerta.id.desc(),
        )
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars().all()
    return {
        "items": [serializar(fila) for fila in filas],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def listar_reglas() -> list:
    filas = db.session.execute(
        select(Configuracion).where(Configuracion.clave.in_(REGLAS)).order_by(Configuracion.clave)
    ).scalars().all()
    por_clave = {fila.clave: fila for fila in filas}
    return [
        {
            "clave": clave,
            "valor": por_clave[clave].valor if clave in por_clave else None,
            "descripcion": descripcion,
        }
        for clave, descripcion in REGLAS.items()
    ]


def actualizar_reglas(cambios: dict, usuario_id: int, ip=None) -> list:
    from app.services import configuracion_service

    desconocidas = set(cambios) - set(REGLAS)
    if desconocidas:
        raise ApiError(
            "REGLA_NO_ENCONTRADA",
            "No existe la regla solicitada",
            404,
            [{"clave": clave} for clave in sorted(desconocidas)],
        )
    for clave, valor in cambios.items():
        configuracion_service.actualizar_configuracion(
            clave, str(valor), usuario_id, ip=ip, commit=False
        )
    db.session.commit()
    return listar_reglas()


def _faltante_inventario(inventario_id: int) -> dict | None:
    inventario = db.session.get(InventarioMaterial, inventario_id)
    if inventario is None:
        return None
    disponible = db.session.scalar(
        select(func.coalesce(func.sum(LoteMaterial.cantidad_base_disponible), 0)).where(
            LoteMaterial.inventario_material_id == inventario_id,
            LoteMaterial.estado == "DISPONIBLE",
        )
    ) or Decimal("0")
    objetivo = Decimal(inventario.stock_seguridad or 0) or Decimal(
        inventario.stock_minimo or 0
    )
    faltante = max(Decimal("0"), objetivo - Decimal(disponible))
    if faltante <= 0:
        return None
    return {
        "inventario_material_id": inventario_id,
        "cantidad_base_faltante": faltante,
    }


def _resultado_reorden(alerta: Alerta, usuario_id: int) -> dict:
    from app.services import compras_service

    if alerta.entidad_tipo == "orden_produccion":
        return {"requisicion": {"orden_produccion_id": alerta.entidad_id}}
    if alerta.entidad_tipo == "orden_compra":
        orden = db.session.get(OrdenCompra, alerta.entidad_id)
        if orden is None:
            raise ApiError("ORDEN_NO_ENCONTRADA", "Orden de compra no encontrada", 404)
        return {"orden_compra": orden.folio, "nota": "Orden en seguimiento"}
    if alerta.entidad_tipo != "inventario_material":
        return {"nota": "No existe acción automática para esta entidad"}
    faltante = _faltante_inventario(alerta.entidad_id)
    if faltante is None:
        return {"nota": "La condición de reorden ya no existe"}
    requisicion = compras_service.generar_requisicion(
        "ALERTA",
        [faltante],
        usuario_id,
        notas=f"Generada desde alerta {alerta.tipo}",
    )
    return {"requisicion": requisicion}


def ejecutar_accion(alerta_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    """Ejecuta la acción sugerida y marca la alerta como atendida."""
    from app.services import (
        produccion_service,
        proveedor_service,
    )
    from app.services.bitacora_service import registrar_bitacora

    alerta = db.session.get(Alerta, alerta_id)
    if alerta is None:
        raise ApiError("ALERTA_NO_ENCONTRADA", "Alerta no encontrada", 404)
    if alerta.estado != "ABIERTA":
        raise ApiError("ALERTA_NO_ABIERTA", "La alerta no está abierta", 409)

    accion = datos.get("accion") or "ATENDER"
    resultado = {"nota": "Alerta atendida sin acción automática"}
    if accion == "GENERAR_PRODUCCION" and alerta.tipo in (
        "PT_AGOTADO_DEMANDA",
        "PT_STOCK_MINIMO",
    ):
        stock = db.session.get(StockVariante, alerta.entidad_id)
        if stock is None:
            raise ApiError("VARIANTE_NO_ENCONTRADA", "Variante no encontrada", 404)
        pendiente = db.session.scalar(
            select(func.coalesce(func.sum(OrdenProduccionLinea.cantidad_planeada), 0)).where(
                OrdenProduccionLinea.variante_id == alerta.entidad_id
            )
        )
        cantidad = max(
            1,
            int(stock.cantidad_reposicion or 0),
            int(pendiente or 0),
        )
        resultado = produccion_service.crear(
            {"lineas": [{"variante_id": alerta.entidad_id, "cantidad": cantidad}]},
            usuario_id,
            ip,
        )
    elif accion == "GENERAR_REQUISICION" and alerta.tipo in (
        "MP_INSUFICIENTE",
        "MP_REORDEN",
        "ORDEN_ROJA",
        "OC_RETRASADA",
    ):
        resultado = _resultado_reorden(alerta, usuario_id)
    elif accion == "EVALUAR_PROVEEDOR" and alerta.tipo == "PROVEEDOR_EN_REVISION":
        resultado = proveedor_service.evaluacion(persistir=True)

    atender(alerta.id, usuario_id)
    registrar_bitacora(
        usuario_id,
        "ALERTA_ATENDIDA",
        "alerta",
        alerta.id,
        {"tipo": alerta.tipo, "accion": accion},
        ip,
    )
    db.session.commit()
    return {
        "alerta": serializar(alerta),
        "accion": accion,
        "resultado": resultado,
    }
