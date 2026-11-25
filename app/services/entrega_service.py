"""Casos de uso de entregas y repartidores (M19)."""

from datetime import date, datetime, timezone

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    Entrega,
    Pedido,
    PedidoLinea,
    Repartidor,
    Venta,
    VentaDireccion,
    VentaLinea,
)
from app.services import alertas_service, configuracion_service, pedido_service, stock_service
from app.services.bitacora_service import registrar_bitacora
from app.utils.errores import ApiError
from app.utils.folios import generar_folio


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _direccion(venta_id: int) -> dict | None:
    direccion = db.session.execute(
        select(VentaDireccion).where(
            VentaDireccion.venta_id == venta_id, VentaDireccion.tipo == "ENVIO"
        )
    ).scalars().first()
    if direccion is None:
        return None
    partes = [
        direccion.calle,
        direccion.numero_ext,
        direccion.numero_int,
        direccion.colonia,
        direccion.municipio,
        direccion.estado,
        direccion.codigo_postal,
    ]
    return {
        "destinatario": direccion.destinatario,
        "telefono": direccion.telefono,
        "direccion": ", ".join(str(parte) for parte in partes if parte),
        "codigo_postal": direccion.codigo_postal,
    }


def serializar(entrega: Entrega) -> dict:
    direccion = _direccion(entrega.pedido.venta_id)
    return {
        "id": entrega.id,
        "folio": entrega.folio,
        "pedido_id": entrega.pedido_id,
        "venta_folio": entrega.pedido.venta.folio,
        "estado": entrega.estado,
        "intento": entrega.intento,
        "fecha_programada": entrega.fecha_programada.isoformat(),
        "salida_en": entrega.salida_en.isoformat() if entrega.salida_en else None,
        "resultado_en": entrega.resultado_en.isoformat() if entrega.resultado_en else None,
        "receptor": entrega.receptor,
        "motivo_fallo": entrega.motivo_fallo,
        "notas": entrega.notas,
        "repartidor_id": entrega.repartidor_id,
        "repartidor": entrega.repartidor.nombre,
        "destinatario": direccion["destinatario"] if direccion else None,
        "direccion": direccion["direccion"] if direccion else None,
        "codigo_postal": direccion["codigo_postal"] if direccion else None,
        "telefono": direccion["telefono"] if direccion else None,
    }


def por_asignar(filtros=None, pagina=1, por_pagina=20) -> dict:
    filtros = filtros or {}
    consulta = (
        select(Pedido, Venta)
        .join(Venta, Venta.id == Pedido.venta_id)
        .outerjoin(
            VentaDireccion,
            (VentaDireccion.venta_id == Venta.id) & (VentaDireccion.tipo == "ENVIO"),
        )
        .where(Pedido.estado == "LISTO_ENVIO")
    )
    if filtros.get("codigo_postal"):
        consulta = consulta.where(VentaDireccion.codigo_postal == filtros["codigo_postal"])
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.session.execute(
        consulta.order_by(VentaDireccion.codigo_postal, Pedido.id)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    return {
        "items": [
            {
                "pedido_id": pedido.id,
                "venta_folio": venta.folio,
                "prioridad": pedido.prioridad,
                "fecha_promesa": (
                    pedido.fecha_promesa.isoformat() if pedido.fecha_promesa else None
                ),
                "direccion": _direccion(venta.id),
            }
            for pedido, venta in filas
        ],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def asignar(datos: dict, usuario_id: int) -> dict:
    pedido = db.session.execute(
        select(Pedido).where(Pedido.id == datos["pedido_id"]).with_for_update()
    ).scalars().first()
    if pedido is None:
        raise ApiError("PEDIDO_NO_ENCONTRADO", "Pedido no encontrado", 404)
    if pedido.estado != "LISTO_ENVIO":
        raise ApiError("PEDIDO_NO_ASIGNABLE", "El pedido no está listo para asignar", 409)
    repartidor = db.session.get(Repartidor, datos["repartidor_id"])
    if repartidor is None or not repartidor.activo or repartidor.eliminado_en:
        raise ApiError("REPARTIDOR_NO_DISPONIBLE", "El repartidor no está disponible", 422)
    fecha = datos["fecha_programada"]
    if fecha < date.today():
        raise ApiError("FECHA_INVALIDA", "La fecha programada no puede ser pasada", 422)
    activa = db.session.execute(
        select(Entrega).where(
            Entrega.pedido_id == pedido.id,
            Entrega.estado.in_(("PROGRAMADA", "EN_RUTA")),
        )
    ).scalars().first()
    if activa is not None:
        raise ApiError("ENTREGA_ACTIVA", "El pedido ya tiene una entrega activa", 409)
    intento = (
        db.session.scalar(
            select(func.coalesce(func.max(Entrega.intento), 0)).where(
                Entrega.pedido_id == pedido.id
            )
        )
        or 0
    ) + 1
    entrega = Entrega(
        folio=generar_folio("EN"),
        pedido_id=pedido.id,
        repartidor_id=repartidor.id,
        intento=intento,
        estado="PROGRAMADA",
        fecha_programada=fecha,
        notas=datos.get("notas"),
    )
    db.session.add(entrega)
    db.session.flush()
    registrar_bitacora(
        usuario_id,
        "ENTREGA_ASIGNADA",
        "entrega",
        entrega.id,
        {"pedido_id": pedido.id, "repartidor_id": repartidor.id, "intento": intento},
    )
    db.session.commit()
    return serializar(entrega)


def _entrega(entrega_id: int, bloquear=False) -> Entrega:
    consulta = select(Entrega).where(Entrega.id == entrega_id)
    if bloquear:
        consulta = consulta.with_for_update()
    entrega = db.session.execute(consulta).scalars().first()
    if entrega is None:
        raise ApiError("ENTREGA_NO_ENCONTRADA", "Entrega no encontrada", 404)
    return entrega


def _lineas_pedido(pedido_id: int) -> list:
    return db.session.execute(
        select(PedidoLinea, VentaLinea)
        .join(VentaLinea, VentaLinea.id == PedidoLinea.venta_linea_id)
        .where(PedidoLinea.pedido_id == pedido_id)
        .order_by(PedidoLinea.id)
    ).all()


def confirmar_salida(entrega_id: int, usuario_id: int) -> dict:
    entrega = _entrega(entrega_id, bloquear=True)
    if entrega.estado != "PROGRAMADA":
        raise ApiError("ENTREGA_NO_PROGRAMADA", "La entrega no está programada", 409)
    pedido = entrega.pedido
    if pedido.estado != "LISTO_ENVIO":
        raise ApiError("PEDIDO_NO_LISTO", "El pedido no está listo para salir", 409)
    otra = db.session.execute(
        select(Entrega).where(
            Entrega.pedido_id == pedido.id,
            Entrega.estado == "EN_RUTA",
            Entrega.id != entrega.id,
        )
    ).scalars().first()
    if otra is not None:
        raise ApiError("ENTREGA_DUPLICADA", "El pedido ya tiene una entrega en ruta", 409)

    filas = _lineas_pedido(pedido.id)
    stocks = stock_service.bloquear([venta.variante_id for _, venta in filas])
    for pedido_linea, venta_linea in filas:
        cantidad = pedido_linea.cant_reservada
        if cantidad <= 0:
            raise ApiError("RESERVA_INSUFICIENTE", "El pedido no tiene existencia reservada", 409)
        stock = stocks[venta_linea.variante_id]
        if stock.existencia < cantidad:
            raise ApiError("STOCK_INSUFICIENTE", "No hay existencia para la salida", 409)
        stock.existencia -= cantidad
        stock.reservado -= cantidad
        stock_service.registrar_movimiento(
            stock,
            "SALIDA_ENVIO",
            -cantidad,
            -cantidad,
            "ENTREGA",
            entrega.id,
            usuario_id,
            f"Salida de {entrega.folio}",
        )
    entrega.estado = "EN_RUTA"
    entrega.salida_en = _ahora()
    pedido_service.cambiar_estado(
        pedido,
        "EN_REPARTO",
        f"Salida confirmada con guía {entrega.folio}",
        usuario_id=usuario_id,
    )
    alertas_service.cerrar(f"PEDIDO_ESTANCADO:{pedido.id}")
    db.session.commit()
    return serializar(entrega)


def registrar_resultado(entrega_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    entrega = _entrega(entrega_id, bloquear=True)
    if entrega.estado != "EN_RUTA":
        raise ApiError("ENTREGA_NO_EN_RUTA", "La entrega no está en ruta", 409)
    pedido = entrega.pedido
    entrega.resultado_en = _ahora()
    entrega.notas = datos.get("notas") or entrega.notas
    clave = f"ENTREGA_FALLIDA:{pedido.id}"

    if datos["entregado"]:
        if not datos.get("receptor"):
            raise ApiError("RECEPTOR_REQUERIDO", "Se requiere el nombre de quien recibe", 422)
        entrega.estado = "ENTREGADA"
        entrega.receptor = datos["receptor"]
        entrega.motivo_fallo = None
        pedido_service.cambiar_estado(
            pedido,
            "ENTREGADO",
            f"Entrega concretada con guía {entrega.folio}",
            usuario_id=usuario_id,
        )
        alertas_service.cerrar(clave)
        alertas_service.cerrar(f"PEDIDO_ESTANCADO:{pedido.id}")
        registrar_bitacora(
            usuario_id, "ENTREGA_EXITOSA", "entrega", entrega.id, {"folio": entrega.folio}, ip
        )
    else:
        if not datos.get("motivo_fallo"):
            raise ApiError("MOTIVO_FALLO_REQUERIDO", "Se requiere el motivo del fallo", 422)
        entrega.estado = "FALLIDA"
        entrega.motivo_fallo = datos["motivo_fallo"]
        filas = _lineas_pedido(pedido.id)
        stocks = stock_service.bloquear([venta.variante_id for _, venta in filas])
        for pedido_linea, venta_linea in filas:
            cantidad = pedido_linea.cant_reservada
            if cantidad <= 0:
                continue
            stock = stocks[venta_linea.variante_id]
            stock.existencia += cantidad
            stock.reservado += cantidad
            stock_service.registrar_movimiento(
                stock,
                "REINGRESO",
                cantidad,
                cantidad,
                "ENTREGA",
                entrega.id,
                usuario_id,
                f"Reingreso por entrega fallida {entrega.folio}",
            )
        pedido_service.cambiar_estado(
            pedido,
            "LISTO_ENVIO",
            f"Entrega fallida {entrega.folio}: {entrega.motivo_fallo}",
            usuario_id=usuario_id,
        )
        fallidos = db.session.scalar(
            select(func.count()).select_from(Entrega).where(
                Entrega.pedido_id == pedido.id, Entrega.estado == "FALLIDA"
            )
        ) or 0
        limite = configuracion_service.valor_entero("max_intentos_entrega", 2)
        severidad = "CRITICA" if fallidos >= limite else "PREVENTIVA"
        detalle = (
            f"El pedido {pedido.id} acumula {fallidos} intentos fallidos de {limite}."
        )
        alerta = alertas_service.abrir(
            "ENTREGA_FALLIDA",
            severidad,
            "Entrega fallida",
            detalle,
            "pedido",
            pedido.id,
            rol_destino="AMBOS",
            clave_unica=clave,
            accion_sugerida="Reprogramar o cancelar",
        )
        if alerta and alerta.severidad != severidad:
            alertas_service.elevar(clave, severidad, detalle)
        registrar_bitacora(
            usuario_id,
            "ENTREGA_FALLIDA",
            "entrega",
            entrega.id,
            {"folio": entrega.folio, "intento": entrega.intento, "motivo": entrega.motivo_fallo},
            ip,
        )
    db.session.commit()
    return serializar(entrega)


def hoja_reparto(repartidor_id: int, fecha: date, pagina=1, por_pagina=20) -> dict:
    consulta = (
        select(Entrega)
        .join(Repartidor, Repartidor.id == Entrega.repartidor_id)
        .where(Entrega.repartidor_id == repartidor_id, Entrega.fecha_programada == fecha)
    )
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    entregas = db.session.execute(
        consulta.order_by(Entrega.folio)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars().all()
    return {
        "items": [
            {
                **serializar(entrega),
                "lineas": [
                    {
                        "sku": venta.sku,
                        "nombre_producto": venta.nombre_producto,
                        "cantidad": pedido_linea.cantidad,
                    }
                    for pedido_linea, venta in _lineas_pedido(entrega.pedido_id)
                ],
            }
            for entrega in entregas
        ],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def productos_repartidos(filtros=None, pagina=1, por_pagina=20) -> dict:
    filtros = filtros or {}
    consulta = (
        select(
            VentaLinea.sku,
            VentaLinea.nombre_producto,
            func.sum(PedidoLinea.cantidad).label("unidades"),
            func.count(func.distinct(Entrega.pedido_id)).label("pedidos"),
        )
        .join(PedidoLinea, PedidoLinea.venta_linea_id == VentaLinea.id)
        .join(Entrega, Entrega.pedido_id == PedidoLinea.pedido_id)
        .where(Entrega.estado == "ENTREGADA")
    )
    if filtros.get("repartidor_id"):
        consulta = consulta.where(Entrega.repartidor_id == filtros["repartidor_id"])
    if filtros.get("desde"):
        consulta = consulta.where(Entrega.resultado_en >= filtros["desde"])
    if filtros.get("hasta"):
        consulta = consulta.where(Entrega.resultado_en < filtros["hasta"])
    consulta = consulta.group_by(VentaLinea.sku, VentaLinea.nombre_producto)
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.session.execute(
        consulta.order_by(VentaLinea.sku)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    return {
        "items": [
            {
                "sku": sku,
                "nombre_producto": nombre,
                "unidades": int(unidades),
                "pedidos": int(pedidos),
            }
            for sku, nombre, unidades, pedidos in filas
        ],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def listar_repartidores(filtros=None, pagina=1, por_pagina=20) -> dict:
    filtros = filtros or {}
    consulta = select(Repartidor).where(Repartidor.eliminado_en.is_(None))
    if filtros.get("activo") is not None:
        consulta = consulta.where(Repartidor.activo == filtros["activo"])
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.session.execute(
        consulta.order_by(Repartidor.id)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars().all()
    return {
        "items": [
            {
                "id": fila.id,
                "nombre": fila.nombre,
                "telefono": fila.telefono,
                "vehiculo": fila.vehiculo,
                "activo": fila.activo,
                "eliminado_en": (
                    fila.eliminado_en.isoformat() if fila.eliminado_en else None
                ),
            }
            for fila in filas
        ],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def crear_repartidor(datos: dict, usuario_id: int, ip=None) -> dict:
    repartidor = Repartidor(
        nombre=datos["nombre"],
        telefono=datos["telefono"],
        vehiculo=datos.get("vehiculo"),
        activo=True,
    )
    db.session.add(repartidor)
    db.session.flush()
    registrar_bitacora(
        usuario_id,
        "REPARTIDOR_CREADO",
        "repartidor",
        repartidor.id,
        {"nombre": repartidor.nombre},
        ip,
    )
    db.session.commit()
    return {
        "id": repartidor.id,
        "nombre": repartidor.nombre,
        "telefono": repartidor.telefono,
        "vehiculo": repartidor.vehiculo,
        "activo": repartidor.activo,
        "eliminado_en": None,
    }


def actualizar_repartidor(repartidor_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    repartidor = db.session.get(Repartidor, repartidor_id)
    if repartidor is None or repartidor.eliminado_en is not None:
        raise ApiError("REPARTIDOR_NO_ENCONTRADO", "Repartidor no encontrado", 404)
    for campo in ("nombre", "telefono", "vehiculo", "activo"):
        if campo in datos:
            setattr(repartidor, campo, datos[campo])
    registrar_bitacora(
        usuario_id,
        "REPARTIDOR_ACTUALIZADO",
        "repartidor",
        repartidor.id,
        {"campos": sorted(datos)},
        ip,
    )
    db.session.commit()
    return {
        "id": repartidor.id,
        "nombre": repartidor.nombre,
        "telefono": repartidor.telefono,
        "vehiculo": repartidor.vehiculo,
        "activo": repartidor.activo,
        "eliminado_en": (
            repartidor.eliminado_en.isoformat() if repartidor.eliminado_en else None
        ),
    }


def desactivar_repartidor(repartidor_id: int, usuario_id: int, ip=None) -> None:
    repartidor = db.session.get(Repartidor, repartidor_id)
    if repartidor is None or repartidor.eliminado_en is not None:
        raise ApiError("REPARTIDOR_NO_ENCONTRADO", "Repartidor no encontrado", 404)
    repartidor.activo = False
    repartidor.eliminado_en = _ahora()
    registrar_bitacora(
        usuario_id,
        "REPARTIDOR_DESACTIVADO",
        "repartidor",
        repartidor.id,
        {"nombre": repartidor.nombre},
        ip,
    )
    db.session.commit()
