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
    ProductoImagen,
    Preparacion,
    PreparacionLinea,
    ProduccionPedido,
    Repartidor,
    Usuario,
    VarianteProducto,
    Venta,
    VentaDireccion,
    VentaLinea,
)
from app.services import configuracion_service, receta_service, stock_service
from app.services.bitacora_service import registrar_bitacora
from app.utils.errores import ApiError
from app.utils.folios import generar_folio

CANCELABLES = ("RECIBIDO", "CONFIRMADO", "EN_PRODUCCION")
CANCELABLES_ADMIN = CANCELABLES + ("EN_PREPARACION", "LISTO_ENVIO")
ESTADOS_PEDIDO = (
    "RECIBIDO",
    "CONFIRMADO",
    "EN_PRODUCCION",
    "EN_PREPARACION",
    "LISTO_ENVIO",
    "EN_REPARTO",
    "ENTREGADO",
    "CANCELADO",
)
UMBRALES = {
    "RECIBIDO": ("horas_max_recibido", "horas"),
    "CONFIRMADO": ("horas_max_confirmado", "horas"),
    "EN_PRODUCCION": ("dias_max_en_produccion", "dias"),
    "EN_PREPARACION": ("horas_max_en_preparacion", "horas"),
    "LISTO_ENVIO": ("horas_max_listo_envio", "horas"),
    "EN_REPARTO": ("horas_max_en_reparto", "horas"),
}
GRUPOS_ESTADO = {
    "TODOS": None,
    "EN_PROCESO": ("RECIBIDO", "CONFIRMADO", "EN_PRODUCCION", "EN_PREPARACION"),
    "ENVIADOS": ("LISTO_ENVIO", "EN_REPARTO"),
    "ENTREGADOS": ("ENTREGADO",),
}
TRANSICIONES = {
    "CONFIRMADO": ("EN_PREPARACION",),
    "EN_PREPARACION": ("LISTO_ENVIO", "EN_PRODUCCION"),
    "LISTO_ENVIO": ("EN_REPARTO",),
    "EN_REPARTO": ("ENTREGADO", "LISTO_ENVIO"),
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


def cambiar_estado(
    pedido, estado, descripcion, usuario_id=None, visible_cliente=True
):
    """Aplica una transición válida y registra el evento del pedido."""
    permitidos = TRANSICIONES.get(pedido.estado, ())
    if estado not in permitidos:
        raise ApiError(
            "TRANSICION_NO_VALIDA",
            f"No se puede pasar de {pedido.estado} a {estado}",
            409,
        )
    pedido.estado = estado
    pedido.estado_desde = _ahora()
    if estado == "ENTREGADO" and pedido.entregado_en is None:
        pedido.entregado_en = _ahora()
    agregar_evento(
        pedido,
        estado,
        descripcion,
        visible_cliente=visible_cliente,
        usuario_id=usuario_id,
    )
    return pedido


def crear_preparacion(pedido, pedido_lineas=None):
    """Crea la preparación de un pedido totalmente reservado, si aún no existe."""
    existente = db.session.execute(
        select(Preparacion).where(Preparacion.pedido_id == pedido.id)
    ).scalars().first()
    if existente is not None:
        return existente
    preparacion = Preparacion(pedido_id=pedido.id, estado="POR_SURTIR")
    db.session.add(preparacion)
    db.session.flush()
    lineas = pedido_lineas
    if lineas is None:
        lineas = db.session.execute(
            select(PedidoLinea).where(PedidoLinea.pedido_id == pedido.id)
        ).scalars().all()
    for pedido_linea in lineas:
        db.session.add(
            PreparacionLinea(
                preparacion_id=preparacion.id,
                pedido_linea_id=pedido_linea.id,
                cantidad_requerida=pedido_linea.cantidad,
            )
        )
    db.session.flush()
    return preparacion


def pedido_de_usuario(pedido_id: int, usuario_id: int) -> Pedido:
    pedido = db.session.execute(
        select(Pedido)
        .join(Venta, Venta.id == Pedido.venta_id)
        .where(Pedido.id == pedido_id, Venta.usuario_id == usuario_id)
    ).scalars().first()
    if pedido is None:
        raise ApiError("PEDIDO_NO_ENCONTRADO", "Pedido no encontrado", 404)
    return pedido


def _imagenes_productos(producto_ids) -> dict:
    """Primera imagen de cada producto, en el mismo orden que el catálogo."""
    if not producto_ids:
        return {}
    filas = db.session.execute(
        select(ProductoImagen.producto_id, ProductoImagen.url)
        .where(ProductoImagen.producto_id.in_(producto_ids))
        .order_by(ProductoImagen.producto_id, ProductoImagen.orden, ProductoImagen.id)
    ).all()
    imagenes = {}
    for producto_id, url in filas:
        imagenes.setdefault(producto_id, url)
    return imagenes


def _lineas(pedido_id: int) -> list:
    filas = db.session.execute(
        select(PedidoLinea, VentaLinea, VarianteProducto)
        .join(VentaLinea, VentaLinea.id == PedidoLinea.venta_linea_id)
        .join(VarianteProducto, VarianteProducto.id == VentaLinea.variante_id)
        .where(PedidoLinea.pedido_id == pedido_id)
        .order_by(PedidoLinea.id)
    ).all()
    imagenes = _imagenes_productos({variante.producto_id for _, _, variante in filas})
    return [
        {
            "id": pedido_linea.id,
            "venta_linea_id": venta_linea.id,
            "variante_id": _variante.id,
            "producto_id": _variante.producto_id,
            "sku": venta_linea.sku,
            "nombre_producto": venta_linea.nombre_producto,
            "talla": venta_linea.talla,
            "color": venta_linea.color,
            "cantidad": pedido_linea.cantidad,
            "cant_reservada": pedido_linea.cant_reservada,
            "cant_pendiente": pedido_linea.cant_pendiente,
            "precio_unitario": venta_linea.precio_unitario,
            "subtotal": venta_linea.subtotal,
            "imagen": imagenes.get(_variante.producto_id),
        }
        for pedido_linea, venta_linea, _variante in filas
    ]


def _fecha_entrega(pedido_id: int):
    return db.session.execute(
        select(Entrega.resultado_en)
        .where(Entrega.pedido_id == pedido_id, Entrega.estado == "ENTREGADA")
        .order_by(Entrega.intento.desc())
    ).scalars().first()


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
    items = []
    for pedido, venta in pedidos:
        lineas = _lineas(pedido.id)
        items.append(
            {
                "id": pedido.id,
                "folio": venta.folio,
                "fecha": venta.fecha,
                "estado": pedido.estado,
                "total": venta.total,
                "articulos": sum(linea["cantidad"] for linea in lineas),
                "guia": guias.get(pedido.id),
                "imagen": lineas[0]["imagen"] if lineas else None,
                "fecha_estimada": pedido.fecha_promesa,
                "fecha_entrega": _fecha_entrega(pedido.id),
            }
        )
    return {
        "items": items,
        "total": total or 0,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def detalle_propio(pedido_id: int, usuario_id: int) -> dict:
    return _detalle(pedido_de_usuario(pedido_id, usuario_id), solo_cliente=True)


def _detalle(pedido, solo_cliente=True) -> dict:
    venta = pedido.venta
    consulta_eventos = select(PedidoEvento).where(PedidoEvento.pedido_id == pedido.id)
    if solo_cliente:
        consulta_eventos = consulta_eventos.where(PedidoEvento.visible_cliente.is_(True))
    eventos = db.session.execute(
        consulta_eventos.order_by(PedidoEvento.fecha, PedidoEvento.id)
    ).scalars().all()
    envio = _envio(pedido.id)
    lineas = _lineas(pedido.id)
    respuesta = {
        "id": pedido.id,
        "folio": venta.folio,
        "fecha": venta.fecha,
        "estado": pedido.estado,
        "estado_desde": pedido.estado_desde,
        "fecha_promesa": pedido.fecha_promesa,
        "fecha_estimada": pedido.fecha_promesa,
        "fecha_entrega": _fecha_entrega(pedido.id),
        "total_articulos": sum(linea["cantidad"] for linea in lineas),
        "prioridad": pedido.prioridad,
        "estado_pago": venta.estado_pago,
        "subtotal": venta.subtotal,
        "descuento_monto": venta.descuento_monto,
        "costo_envio": venta.costo_envio,
        "total": venta.total,
        "direccion": _direccion_envio(venta.id),
        "articulos": lineas,
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
    if solo_cliente:
        return respuesta

    respuesta["venta_id"] = venta.id
    respuesta["cliente"] = {
        "id": venta.usuario.id,
        "nombre": venta.usuario.nombre,
        "apellidos": venta.usuario.apellidos,
        "correo": venta.usuario.correo,
    }
    respuesta["canal"] = venta.canal
    respuesta["semaforo"] = _semaforo(pedido)
    respuesta["ordenes"] = [
        {
            "orden_id": vinculo.orden_linea.orden_id,
            "folio": vinculo.orden_linea.orden.folio,
            "estado": vinculo.orden_linea.orden.estado,
            "cantidad": vinculo.cantidad,
        }
        for vinculo in db.session.execute(
            select(ProduccionPedido)
            .join(PedidoLinea, PedidoLinea.id == ProduccionPedido.pedido_linea_id)
            .where(PedidoLinea.pedido_id == pedido.id)
        ).scalars().all()
    ]
    preparacion = db.session.execute(
        select(Preparacion).where(Preparacion.pedido_id == pedido.id)
    ).scalars().first()
    respuesta["preparacion"] = (
        {"id": preparacion.id, "estado": preparacion.estado} if preparacion else None
    )
    respuesta["entrega"] = (
        {
            "id": envio[0].id,
            "folio": envio[0].folio,
            "estado": envio[0].estado,
            "intento": envio[0].intento,
        }
        if envio
        else None
    )
    return respuesta


def detalle_admin(pedido_id: int) -> dict:
    pedido = db.session.get(Pedido, pedido_id)
    if pedido is None:
        raise ApiError("PEDIDO_NO_ENCONTRADO", "Pedido no encontrado", 404)
    return _detalle(pedido, solo_cliente=False)


def listar_admin(filtros=None, pagina: int = 1, por_pagina: int = 20) -> dict:
    filtros = filtros or {}
    consulta = (
        select(Pedido, Venta, Usuario)
        .join(Venta, Venta.id == Pedido.venta_id)
        .join(Usuario, Usuario.id == Venta.usuario_id)
    )
    estado = filtros.get("estado")
    if estado:
        estados = GRUPOS_ESTADO.get(estado)
        if estados is None and estado not in ESTADOS_PEDIDO:
            raise ApiError("FILTRO_INVALIDO", "Estado de pedido no válido", 400)
        if estados:
            consulta = consulta.where(Pedido.estado.in_(estados))
        else:
            consulta = consulta.where(Pedido.estado == estado)
    if filtros.get("prioridad"):
        consulta = consulta.where(Pedido.prioridad == filtros["prioridad"])
    if filtros.get("desde"):
        consulta = consulta.where(Pedido.creado_en >= filtros["desde"])
    if filtros.get("hasta"):
        consulta = consulta.where(Pedido.creado_en < filtros["hasta"])
    if filtros.get("q"):
        patron = f"%{filtros['q']}%"
        consulta = consulta.where(
            db.or_(
                Venta.folio.like(patron),
                Usuario.nombre.like(patron),
                Usuario.apellidos.like(patron),
                Usuario.correo.like(patron),
            )
        )
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.session.execute(
        consulta.order_by(Pedido.creado_en.desc(), Pedido.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    ids = [pedido.id for pedido, _, _ in filas]
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
            "cliente": {
                "id": usuario.id,
                "nombre": usuario.nombre,
                "apellidos": usuario.apellidos,
                "correo": usuario.correo,
            },
            "estado": pedido.estado,
            "estado_desde": pedido.estado_desde,
            "prioridad": pedido.prioridad,
            "semaforo": _semaforo(pedido),
            "articulos": sum(linea["cantidad"] for linea in _lineas(pedido.id)),
            "total": venta.total,
            "guia": guias.get(pedido.id),
        }
        for pedido, venta, usuario in filas
    ]
    return {
        "items": items,
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def pendientes_produccion(filtros=None, pagina=1, por_pagina=20) -> dict:
    """Expone la demanda pendiente desde el servicio propietario de producción."""
    from app.services import produccion_service

    return produccion_service.pendientes_lineas(filtros, pagina, por_pagina)


def actualizar_admin(pedido_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    pedido = db.session.get(Pedido, pedido_id)
    if pedido is None:
        raise ApiError("PEDIDO_NO_ENCONTRADO", "Pedido no encontrado", 404)
    if pedido.estado == "CANCELADO":
        raise ApiError("PEDIDO_CANCELADO", "El pedido está cancelado", 409)
    cambios = {}
    if "prioridad" in datos:
        if datos["prioridad"] not in ("NORMAL", "ALTA"):
            raise ApiError("PRIORIDAD_INVALIDA", "Prioridad no válida", 422)
        cambios["prioridad"] = datos["prioridad"]
        pedido.prioridad = datos["prioridad"]
    if datos.get("nota"):
        agregar_evento(
            pedido,
            pedido.estado,
            datos["nota"],
            visible_cliente=False,
            usuario_id=usuario_id,
        )
        cambios["nota"] = datos["nota"]
    if not cambios:
        raise ApiError("VALIDACION", "Se requiere prioridad o nota", 400)
    registrar_bitacora(
        usuario_id, "PEDIDO_ACTUALIZADO", "pedido", pedido.id, cambios, ip
    )
    db.session.commit()
    return detalle_admin(pedido.id)


def activar_pago(pedido, usuario_id: int, aprobado: bool = True) -> None:
    """TRANSICIÓN RECIBIDO → CONFIRMADO/EN_PRODUCCION tras validar el pago."""
    if pedido.estado != "RECIBIDO":
        raise ApiError(
            "ESTADO_NO_VALIDO",
            "El pago solo puede validarse en un pedido recibido",
            409,
        )
    if not aprobado:
        agregar_evento(
            pedido,
            "RECIBIDO",
            "Pago rechazado por el Administrador",
            visible_cliente=False,
            usuario_id=usuario_id,
        )
        return
    hay_pendiente = any(
        int(linea["cant_pendiente"]) > 0 for linea in _lineas(pedido.id)
    )
    pedido.estado = "EN_PRODUCCION" if hay_pendiente else "CONFIRMADO"
    pedido.estado_desde = _ahora()
    agregar_evento(
        pedido,
        pedido.estado,
        "Pago aprobado por el Administrador",
        usuario_id=usuario_id,
    )
    if not hay_pendiente:
        crear_preparacion(pedido)


def _semaforo(pedido) -> str | None:
    regla = UMBRALES.get(pedido.estado)
    if regla is None:
        return None
    clave, unidad = regla
    limite = configuracion_service.valor_entero(clave, 24 if unidad == "horas" else 7)
    transcurrido = (_ahora() - pedido.estado_desde).total_seconds()
    limite_segundos = limite * 3600 if unidad == "horas" else limite * 86400
    if transcurrido > limite_segundos:
        return "ROJO"
    if transcurrido >= limite_segundos * Decimal("0.75"):
        return "AMBAR"
    return "VERDE"


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


def cancelar(pedido_id: int, usuario_id: int, motivo: str, ip=None) -> dict:
    pedido = pedido_de_usuario(pedido_id, usuario_id)
    return _cancelar(pedido, usuario_id, motivo, es_admin=False, ip=ip)


def cancelar_admin(pedido_id: int, usuario_id: int, motivo: str, ip=None) -> dict:
    pedido = db.session.get(Pedido, pedido_id)
    if pedido is None:
        raise ApiError("PEDIDO_NO_ENCONTRADO", "Pedido no encontrado", 404)
    return _cancelar(pedido, usuario_id, motivo, es_admin=True, ip=ip)


def _cancelar(pedido, usuario_id: int, motivo: str, es_admin: bool, ip=None) -> dict:
    permitidos = CANCELABLES_ADMIN if es_admin else CANCELABLES
    if pedido.estado not in permitidos:
        raise ApiError(
            "ESTADO_NO_CANCELABLE",
            "El pedido ya no puede ser cancelado",
            422,
        )
    venta = pedido.venta
    if venta.estado == "CANCELADA":
        raise ApiError("VENTA_YA_CANCELADA", "La venta ya está cancelada", 409)
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
    total = Decimal(str(venta.total))
    reembolsado = Decimal(
        str(
            db.session.scalar(
                select(func.coalesce(func.sum(Pago.monto), 0)).where(
                    Pago.venta_id == venta.id,
                    Pago.tipo == "REEMBOLSO",
                    Pago.estado == "APROBADO",
                )
            )
            or 0
        )
    )
    restante = max(Decimal("0"), total - reembolsado)
    if cobro is not None and restante > 0:
        db.session.add(
            Pago(
                venta_id=venta.id,
                tipo="REEMBOLSO",
                metodo=cobro.metodo,
                estado="APROBADO",
                medio_pago_id=cobro.medio_pago_id,
                monto=restante,
                referencia=f"RE-{secrets.token_hex(5).upper()}",
                ultimos4=cobro.ultimos4,
                titular=cobro.titular,
                registrado_por=usuario_id,
            )
        )
        if cobro.metodo == "CUENTA" and cobro.medio_pago_id:
            medio = db.session.get(MedioPago, cobro.medio_pago_id)
            if medio is not None:
                medio.saldo_simulado = Decimal(str(medio.saldo_simulado or 0)) + restante
        reembolsado += restante
    if reembolsado > 0:
        venta.estado_pago = (
            "REEMBOLSADA" if reembolsado >= total else "REEMBOLSADA_PARCIAL"
        )

    venta.estado = "CANCELADA"
    venta.cancelada_en = _ahora()
    venta.motivo_cancelacion = motivo
    pedido.estado = "CANCELADO"
    pedido.estado_desde = _ahora()
    agregar_evento(
        pedido,
        "CANCELADO",
        (
            "El Administrador canceló el pedido; se liberaron reservas y se aplicó el reembolso"
            if es_admin
            else "El cliente canceló el pedido; se liberaron reservas y se aplicó el reembolso"
        ),
        usuario_id=usuario_id,
    )
    registrar_bitacora(
        usuario_id,
        "PEDIDO_CANCELADO",
        "pedido",
        pedido.id,
        {"motivo": motivo, "folio": venta.folio},
        ip,
    )
    db.session.commit()
    return detalle_admin(pedido.id) if es_admin else detalle_propio(pedido.id, usuario_id)
