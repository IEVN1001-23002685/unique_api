"""Tareas programadas que invocan servicios de dominio, sin duplicar reglas."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select, text

from app.extensions import db
from app.models import (
    Alerta,
    Carrito,
    Devolucion,
    DisenoBordado,
    OrdenCompra,
    OrdenMaterial,
    OrdenProduccion,
    Pedido,
    RecuperacionContrasena,
    StockVariante,
    TokenRefresco,
    Venta,
)
from app.services import (
    alertas_service,
    configuracion_service,
    produccion_service,
    proveedor_service,
)


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _cerrar_entidad(tipo, entidad_tipo, entidad_id) -> int:
    alertas = db.session.execute(
        select(Alerta).where(
            Alerta.tipo == tipo,
            Alerta.entidad_tipo == entidad_tipo,
            Alerta.entidad_id == entidad_id,
            Alerta.estado == "ABIERTA",
        )
    ).scalars().all()
    for alerta in alertas:
        alerta.estado = "RESUELTA_AUTO"
        alerta.clave_unica = None
        alerta.atendida_en = _ahora()
    return len(alertas)


def evaluar_estancamientos() -> dict:
    """Abre alertas de pedidos, órdenes y compras retrasadas."""
    estancados = db.session.execute(
        text(
            "SELECT pedido_id, estado, horas_en_estado, umbral_horas "
            "FROM v_pedidos_estancados "
            "WHERE umbral_horas IS NOT NULL AND horas_en_estado > umbral_horas"
        )
    ).all()
    for fila in estancados:
        alertas_service.abrir(
            "PEDIDO_ESTANCADO",
            "PREVENTIVA",
            "Pedido estancado",
            f"El pedido {fila.pedido_id} lleva {fila.horas_en_estado} h en {fila.estado}.",
            "pedido",
            fila.pedido_id,
            rol_destino="AMBOS",
            clave_unica=f"PEDIDO_ESTANCADO:{fila.pedido_id}",
            accion_sugerida="Revisar avance del pedido",
        )
    hoy = date.today()
    ordenes = db.session.execute(
        select(OrdenProduccion).where(
            OrdenProduccion.estado.in_(("PLANEADA", "LISTA", "EN_PROCESO", "EN_REVISION")),
            OrdenProduccion.fecha_requerida < hoy,
        )
    ).scalars().all()
    for orden in ordenes:
        alertas_service.abrir(
            "ORDEN_ROJA",
            "CRITICA",
            "Orden de producción vencida",
            f"La orden {orden.folio} superó su fecha requerida.",
            "orden_produccion",
            orden.id,
            rol_destino="AMBOS",
            clave_unica=f"ORDEN_ROJA:{orden.id}",
            accion_sugerida="Generar solicitud de compra",
        )
    compras = db.session.execute(
        select(OrdenCompra).where(
            OrdenCompra.estado.in_(("EMITIDA", "PARCIAL")),
            OrdenCompra.fecha_prometida < hoy,
        )
    ).scalars().all()
    for orden in compras:
        alertas_service.abrir(
            "OC_RETRASADA",
            "PREVENTIVA",
            "Orden de compra retrasada",
            f"La orden {orden.folio} superó la fecha prometida.",
            "orden_compra",
            orden.id,
            rol_destino="ADMIN",
            clave_unica=f"OC_RETRASADA:{orden.id}",
            accion_sugerida="Contactar al proveedor",
        )
    disenos = db.session.execute(
        select(DisenoBordado).where(
            DisenoBordado.estado == "PENDIENTE", DisenoBordado.activo.is_(True)
        )
    ).scalars().all()
    for diseno in disenos:
        alertas_service.abrir(
            "DISENO_PENDIENTE",
            "INFORMATIVA",
            "Diseño de bordado pendiente",
            f"El diseño {diseno.codigo} está pendiente de digitalizar.",
            "diseno_bordado",
            diseno.id,
            rol_destino="ADMIN",
            clave_unica=f"DISENO_PENDIENTE:{diseno.id}",
            accion_sugerida="Digitalizar diseño",
        )
    db.session.commit()
    return {
        "pedidos_estancados": len(estancados),
        "ordenes_vencidas": len(ordenes),
        "compras_retrasadas": len(compras),
        "disenos_pendientes": len(disenos),
    }


def recalcular_semaforos() -> dict:
    """Actualiza semáforos y abre alertas por materiales insuficientes."""
    ordenes = db.session.execute(
        select(OrdenProduccion).where(
            OrdenProduccion.estado.in_(("PLANEADA", "LISTA", "EN_PROCESO", "EN_REVISION"))
        )
    ).scalars().all()
    actualizadas = 0
    insuficientes = 0
    for orden in ordenes:
        semaforo = produccion_service.calcular_semaforo_orden(orden.id)
        if orden.semaforo != semaforo:
            orden.semaforo = semaforo
            actualizadas += 1
        if semaforo == "ROJO":
            alertas_service.abrir(
                "ORDEN_ROJA",
                "CRITICA",
                "Orden en rojo",
                f"La orden {orden.folio} tiene materiales o fechas en rojo.",
                "orden_produccion",
                orden.id,
                rol_destino="AMBOS",
                clave_unica=f"ORDEN_ROJA:{orden.id}",
                accion_sugerida="Generar solicitud de compra",
            )
        else:
            alertas_service.cerrar(f"ORDEN_ROJA:{orden.id}")
        materiales = db.session.execute(
            select(
                func.coalesce(
                    OrdenMaterial.cantidad_requerida
                    - OrdenMaterial.cantidad_reservada
                    - OrdenMaterial.cantidad_consumida,
                    0,
                )
            ).where(OrdenMaterial.orden_id == orden.id)
        )
        for (faltante,) in materiales:
            if Decimal(faltante) > 0:
                insuficientes += 1
                break
    db.session.commit()
    return {"ordenes": len(ordenes), "actualizadas": actualizadas, "con_faltantes": insuficientes}


def cerrar_alertas_resueltas() -> dict:
    """Cierra alertas cuya condición ya no existe."""
    cerradas = 0
    pedidos = db.session.execute(
        select(Pedido.id).where(Pedido.estado.in_(("ENTREGADO", "CANCELADO")))
    ).scalars().all()
    for pedido_id in pedidos:
        cerradas += int(alertas_service.cerrar(f"PEDIDO_ESTANCADO:{pedido_id}"))
        cerradas += int(alertas_service.cerrar(f"ENTREGA_FALLIDA:{pedido_id}"))

    ordenes = db.session.execute(
        select(OrdenProduccion.id).where(
            OrdenProduccion.estado.in_(("CERRADA", "CANCELADA"))
        )
    ).scalars().all()
    for orden_id in ordenes:
        cerradas += int(alertas_service.cerrar(f"ORDEN_ROJA:{orden_id}"))

    compras = db.session.execute(
        select(OrdenCompra.id).where(
            OrdenCompra.estado.in_(("RECIBIDA", "CANCELADA"))
        )
    ).scalars().all()
    for orden_id in compras:
        cerradas += int(alertas_service.cerrar(f"OC_RETRASADA:{orden_id}"))

    ventas = db.session.execute(
        select(Venta.id).where(Venta.estado_pago.in_(("PAGADA", "REEMBOLSADA")))
    ).scalars().all()
    for venta_id in ventas:
        cerradas += int(alertas_service.cerrar(f"PAGO_PENDIENTE:{venta_id}"))

    devoluciones = db.session.execute(
        select(Devolucion.id).where(Devolucion.estado != "SOLICITADA")
    ).scalars().all()
    for devolucion_id in devoluciones:
        cerradas += int(alertas_service.cerrar(f"DEVOLUCION_PENDIENTE:{devolucion_id}"))

    stocks = db.session.execute(select(StockVariante)).scalars().all()
    for stock in stocks:
        libre = stock.existencia - stock.reservado
        if libre > stock.stock_minimo:
            cerradas += _cerrar_entidad(
                "PT_STOCK_MINIMO", "variante_producto", stock.variante_id
            )

    disenos = db.session.execute(
        select(DisenoBordado.id).where(DisenoBordado.estado != "PENDIENTE")
    ).scalars().all()
    for diseno_id in disenos:
        cerradas += int(alertas_service.cerrar(f"DISENO_PENDIENTE:{diseno_id}"))

    db.session.commit()
    return {"cerradas": cerradas}


def abandonar_carritos() -> dict:
    dias = configuracion_service.valor_entero("dias_carrito_abandonado", 7)
    limite = _ahora() - timedelta(days=dias)
    carritos = db.session.execute(
        select(Carrito).where(Carrito.estado == "ABIERTO", Carrito.actualizado_en < limite)
    ).scalars().all()
    for carrito in carritos:
        carrito.estado = "ABANDONADO"
    db.session.commit()
    return {"carritos": len(carritos)}


def evaluar_proveedores() -> dict:
    resultado = proveedor_service.evaluacion(persistir=True)
    return {"proveedores": len(resultado["items"])}


def limpiar_tokens() -> dict:
    ahora = _ahora()
    refrescos = db.session.execute(
        select(func.count()).select_from(TokenRefresco).where(
            (TokenRefresco.expira_en < ahora) | (TokenRefresco.revocado.is_(True))
        )
    ).scalar() or 0
    db.session.execute(
        TokenRefresco.__table__.delete().where(
            (TokenRefresco.expira_en < ahora) | (TokenRefresco.revocado.is_(True))
        )
    )
    recuperaciones = db.session.execute(
        select(func.count()).select_from(RecuperacionContrasena).where(
            (RecuperacionContrasena.expira_en < ahora) | (RecuperacionContrasena.usado.is_(True))
        )
    ).scalar() or 0
    db.session.execute(
        RecuperacionContrasena.__table__.delete().where(
            (RecuperacionContrasena.expira_en < ahora) | (RecuperacionContrasena.usado.is_(True))
        )
    )
    db.session.commit()
    return {"tokens_refresco": int(refrescos), "recuperaciones": int(recuperaciones)}


TAREAS = {
    "evaluar_estancamientos": evaluar_estancamientos,
    "recalcular_semaforos": recalcular_semaforos,
    "cerrar_alertas_resueltas": cerrar_alertas_resueltas,
    "abandonar_carritos": abandonar_carritos,
    "evaluar_proveedores": evaluar_proveedores,
    "limpiar_tokens": limpiar_tokens,
}
