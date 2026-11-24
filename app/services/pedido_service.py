"""Casos de uso de pedidos propios, cancelación y vínculo con production (M06, M09)."""

import secrets
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select

from app.extensions import db
from app.models import (
    Entrega,
    MedioPago,
    OrdenProduccion,
    OrdenProduccionLinea,
    Pago,
    Pedido,
    PedidoEvento,
    PedidoLinea,
    Preparacion,
    PreparacionLinea,
    ProduccionPedido,
    Repartidor,
    Venta,
    VentaDireccion,
    VentaLinea,
)
from app.services import receta_service, stock_service
from app.services.bitacora_service import registrar_bitacora
from app.utils.errores import ApiError
from app.utils.folios import generar_folio

CANCELABLES = ("RECIBIDO", "CONFIRMADO", "EN_PRODUCCION")
GRUPOS_ESTADO = {
    "TODOS": None,
    "EN_PROCESO": ("RECIBIDO", "CONFIRMADO", "EN_PRODUCCION", "EN_PREPARACION"),
    "ENVIADOS": ("LISTO_ENVIO", "EN_REPARTO"),
    "ENTREGADOS": ("ENTREGADO",),
}


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def agregar_evento(pedido, estado, descripcion, visible_cliente=True, usuario_id=None):
    db.session.add(
        PedidoEvento(
            pedido_id=pedido.id,
            estado=estado,
            descripcion=descripcion,
            visible_cliente=visible_cliente,
            usuario_id=usuario_id,
        )
    )


def pedido_de_usuario(pedido_id: int, usuario_id: int) -> Pedido:
    pedido = db.session.execute(
        select(Pedido)
        .join(Venta, Venta.id == Pedido.venta_id)
        .where(Pedido.id == pedido_id, Venta.usuario_id == usuario_id)
    ).scalars().first()
    if pedido is None:
        raise ApiError("PEDIDO_NO_ENCONTRADO", "Pedido no encontrado", 404)
    return pedido


def _lineas(pedido_id: int) -> list:
    filas = db.session.execute(
        select(PedidoLinea, VentaLinea)
        .join(VentaLinea, VentaLinea.id == PedidoLinea.venta_linea_id)
        .where(PedidoLinea.pedido_id == pedido_id)
        .order_by(PedidoLinea.id)
    ).all()
    return [
        {
            "id": pedido_linea.id,
            "variante_id": venta_linea.variante_id,
            "sku": venta_linea.sku,
            "nombre_producto": venta_linea.nombre_producto,
            "talla": venta_linea.talla,
            "color": venta_linea.color,
            "cantidad": pedido_linea.cantidad,
            "cant_reservada": pedido_linea.cant_reservada,
            "cant_pendiente": pedido_linea.cant_pendiente,
            "precio_unitario": venta_linea.precio_unitario,
            "subtotal": venta_linea.subtotal,
        }
        for pedido_linea, venta_linea in filas
    ]


def _envio(pedido_id: int):
    return db.session.execute(
        select(Entrega, Repartidor)
        .join(Repartidor, Repartidor.id == Entrega.repartidor_id)
        .where(Entrega.pedido_id == pedido_id)
        .order_by(Entrega.intento.desc())
    ).first()


def _direccion_envio(venta_id: int) -> dict | None:
    direccion = db.session.execute(
        select(VentaDireccion).where(
            VentaDireccion.venta_id == venta_id, VentaDireccion.tipo == "ENVIO"
        )
    ).scalars().first()
    if direccion is None:
        return None
    return {
        "destinatario": direccion.destinatario,
        "telefono": direccion.telefono,
        "calle": direccion.calle,
        "numero_ext": direccion.numero_ext,
        "numero_int": direccion.numero_int,
        "colonia": direccion.colonia,
        "municipio": direccion.municipio,
        "estado": direccion.estado,
        "codigo_postal": direccion.codigo_postal,
        "referencia": direccion.referencia,
    }


def listar_propios(usuario_id: int, filtro: str, pagina: int, por_pagina: int) -> dict:
    estados = GRUPOS_ESTADO.get(filtro or "TODOS")
    if estados is None and filtro not in GRUPOS_ESTADO:
        raise ApiError("FILTRO_INVALIDO", "Filtro de pedidos no válido", 400)
    condiciones = [Venta.usuario_id == usuario_id]
    if estados:
        condiciones.append(Pedido.estado.in_(estados))
    total = db.session.scalar(
        select(func.count())
        .select_from(Pedido)
        .join(Venta, Venta.id == Pedido.venta_id)
        .where(*condiciones)
    )
    pedidos = db.session.execute(
        select(Pedido, Venta)
        .join(Venta, Venta.id == Pedido.venta_id)
        .where(*condiciones)
        .order_by(Pedido.creado_en.desc(), Pedido.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    ids = [pedido.id for pedido, _ in pedidos]
    guias = {}
    if ids:
        for entrega in db.session.execute(
            select(Entrega)
            .where(Entrega.pedido_id.in_(ids))
            .order_by(Entrega.intento.desc())
        ).scalars().all():
            guias.setdefault(entrega.pedido_id, entrega.folio)
    items = [
        {
            "id": pedido.id,
            "folio": venta.folio,
            "fecha": venta.fecha,
            "estado": pedido.estado,
            "total": venta.total,
            "articulos": sum(linea["cantidad"] for linea in _lineas(pedido.id)),
            "guia": guias.get(pedido.id),
        }
        for pedido, venta in pedidos
    ]
    return {
        "items": items,
        "total": total or 0,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def detalle_propio(pedido_id: int, usuario_id: int) -> dict:
    pedido = pedido_de_usuario(pedido_id, usuario_id)
    venta = pedido.venta
    eventos = db.session.execute(
        select(PedidoEvento)
        .where(
            PedidoEvento.pedido_id == pedido.id,
            PedidoEvento.visible_cliente.is_(True),
        )
        .order_by(PedidoEvento.fecha, PedidoEvento.id)
    ).scalars().all()
    envio = _envio(pedido.id)
    return {
        "id": pedido.id,
        "folio": venta.folio,
        "fecha": venta.fecha,
        "estado": pedido.estado,
        "estado_desde": pedido.estado_desde,
        "fecha_promesa": pedido.fecha_promesa,
        "prioridad": pedido.prioridad,
        "estado_pago": venta.estado_pago,
        "subtotal": venta.subtotal,
        "descuento_monto": venta.descuento_monto,
        "costo_envio": venta.costo_envio,
        "total": venta.total,
        "direccion": _direccion_envio(venta.id),
        "articulos": _lineas(pedido.id),
        "eventos": [
            {
                "estado": evento.estado,
                "descripcion": evento.descripcion,
                "fecha": evento.fecha,
                "visible_cliente": evento.visible_cliente,
            }
            for evento in eventos
        ],
        "guia": envio[0].folio if envio else None,
        "repartidor": (
            {"nombre": envio[1].nombre, "telefono": envio[1].telefono}
            if envio
            else None
        ),
    }


def comprobante(pedido_id: int, usuario_id: int) -> dict:
    pedido = pedido_de_usuario(pedido_id, usuario_id)
    venta = pedido.venta
    return {
        "folio": venta.folio,
        "fecha": venta.fecha,
        "estado_pago": venta.estado_pago,
        "cliente": {
            "nombre": venta.usuario.nombre,
            "apellidos": venta.usuario.apellidos,
            "correo": venta.usuario.correo,
        },
        "direccion": _direccion_envio(venta.id),
        "lineas": _lineas(pedido.id),
        "subtotal": venta.subtotal,
        "descuento_monto": venta.descuento_monto,
        "costo_envio": venta.costo_envio,
        "total": venta.total,
    }


def vincular_o_crear_orden(
    variante, cantidad: int, pedido_linea, usuario_id: int, fecha_requerida=None
) -> None:
    orden_linea = db.session.execute(
        select(OrdenProduccionLinea)
        .join(OrdenProduccion, OrdenProduccion.id == OrdenProduccionLinea.orden_id)
        .where(
            OrdenProduccionLinea.variante_id == variante.id,
            OrdenProduccion.estado.in_(["PLANEADA", "LISTA"]),
        )
        .order_by(OrdenProduccion.id)
    ).scalars().first()

    if orden_linea is None:
        receta = receta_service.receta_para_variante(variante.id)
        if receta is None:
            raise ApiError(
                "RECETA_NO_DISPONIBLE",
                "No hay receta disponible para programar la producción",
                422,
            )
        orden = OrdenProduccion(
            folio=generar_folio("OP"),
            origen="PEDIDO",
            estado="PLANEADA",
            semaforo="VERDE",
            fecha_requerida=fecha_requerida,
            creada_por=usuario_id,
        )
        db.session.add(orden)
        db.session.flush()
        orden_linea = OrdenProduccionLinea(
            orden_id=orden.id,
            variante_id=variante.id,
            receta_id=receta.id,
            cantidad_planeada=0,
        )
        db.session.add(orden_linea)
        db.session.flush()

    orden_linea.cantidad_planeada += cantidad
    db.session.add(
        ProduccionPedido(
            orden_linea_id=orden_linea.id,
            pedido_linea_id=pedido_linea.id,
            cantidad=cantidad,
        )
    )
    db.session.flush()


def _ajustar_ordenes(pedido_lineas: list) -> None:
    ordenes_afectadas = set()
    for pedido_linea in pedido_lineas:
        vinculos = db.session.execute(
            select(ProduccionPedido).where(
                ProduccionPedido.pedido_linea_id == pedido_linea.id
            )
        ).scalars().all()
        for vinculo in vinculos:
            ordenes_afectadas.add(vinculo.orden_linea.orden_id)
            vinculo.orden_linea.cantidad_planeada = max(
                0, vinculo.orden_linea.cantidad_planeada - vinculo.cantidad
            )
            db.session.delete(vinculo)
    for orden_id in ordenes_afectadas:
        lineas = db.session.execute(
            select(OrdenProduccionLinea).where(
                OrdenProduccionLinea.orden_id == orden_id
            )
        ).scalars().all()
        for linea in lineas:
            if linea.cantidad_planeada > 0:
                continue
            restantes = db.session.scalar(
                select(func.count()).select_from(ProduccionPedido).where(
                    ProduccionPedido.orden_linea_id == linea.id
                )
            )
            if not restantes:
                db.session.delete(linea)
        pendientes = db.session.scalar(
            select(func.count()).select_from(OrdenProduccionLinea).where(
                OrdenProduccionLinea.orden_id == orden_id
            )
        )
        if not pendientes:
            orden = db.session.get(OrdenProduccion, orden_id)
            if orden is not None and orden.estado in ("PLANEADA", "LISTA"):
                orden.estado = "CANCELADA"
                orden.cerrada_en = _ahora()


def cancelar(pedido_id: int, usuario_id: int, motivo: str) -> dict:
    pedido = pedido_de_usuario(pedido_id, usuario_id)
    if pedido.estado not in CANCELABLES:
        raise ApiError(
            "ESTADO_NO_CANCELABLE",
            "El pedido ya no puede ser cancelado",
            422,
        )
    venta = pedido.venta
    lineas = _lineas(pedido.id)
    stocks = stock_service.bloquear([linea["variante_id"] for linea in lineas])

    for linea in lineas:
        reservada = linea["cant_reservada"]
        if reservada:
            stock_service.liberar(
                stocks[linea["variante_id"]],
                reservada,
                "PEDIDO",
                pedido.id,
                usuario_id,
                motivo=f"Cancelación: {motivo}",
            )
        objeto = db.session.get(PedidoLinea, linea["id"])
        objeto.cant_reservada = 0
        objeto.cant_pendiente = 0
        objeto.cant_preparada = 0
        objeto.cantidad = 0

    _ajustar_ordenes(
        db.session.execute(
            select(PedidoLinea).where(PedidoLinea.pedido_id == pedido.id)
        ).scalars().all()
    )

    preparacion = db.session.execute(
        select(Preparacion).where(Preparacion.pedido_id == pedido.id)
    ).scalars().first()
    if preparacion is not None:
        db.session.execute(
            delete(PreparacionLinea).where(
                PreparacionLinea.preparacion_id == preparacion.id
            )
        )
        db.session.delete(preparacion)

    cobro = db.session.execute(
        select(Pago).where(
            Pago.venta_id == venta.id,
            Pago.tipo == "COBRO",
            Pago.estado == "APROBADO",
        )
    ).scalars().first()
    if cobro is not None:
        reembolso = Pago(
            venta_id=venta.id,
            tipo="REEMBOLSO",
            metodo=cobro.metodo,
            estado="APROBADO",
            medio_pago_id=cobro.medio_pago_id,
            monto=Decimal(str(venta.total)),
            referencia=f"RE-{secrets.token_hex(5).upper()}",
            ultimos4=cobro.ultimos4,
            titular=cobro.titular,
            registrado_por=usuario_id,
        )
        db.session.add(reembolso)
        if cobro.metodo == "CUENTA" and cobro.medio_pago_id:
            medio = db.session.get(MedioPago, cobro.medio_pago_id)
            if medio is not None:
                medio.saldo_simulado = Decimal(str(medio.saldo_simulado or 0)) + Decimal(
                    str(venta.total)
                )
        venta.estado_pago = "REEMBOLSADA"

    venta.estado = "CANCELADA"
    venta.cancelada_en = _ahora()
    venta.motivo_cancelacion = motivo
    pedido.estado = "CANCELADO"
    pedido.estado_desde = _ahora()
    agregar_evento(
        pedido,
        "CANCELADO",
        "El cliente canceló el pedido; se liberaron reservas y se aplicó el reembolso",
        usuario_id=usuario_id,
    )
    registrar_bitacora(
        usuario_id,
        "PEDIDO_CANCELADO",
        "pedido",
        pedido.id,
        {"motivo": motivo, "folio": venta.folio},
    )
    db.session.commit()
    return detalle_propio(pedido.id, usuario_id)
