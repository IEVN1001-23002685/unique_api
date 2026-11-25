"""Casos de uso de preparación, verificación y empaque (M18)."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import case, func, select

from app.extensions import db
from app.models import (
    EmpaqueRegla,
    InventarioMaterial,
    Material,
    Pedido,
    PedidoLinea,
    Preparacion,
    PreparacionLinea,
    Venta,
    VentaDireccion,
    VentaLinea,
    VarianteProducto,
)
from app.services import alertas_service, material_service, merma_service, pedido_service, stock_service
from app.services.bitacora_service import registrar_bitacora
from app.utils.dinero import material as material_texto
from app.utils.errores import ApiError


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _preparacion(preparacion_id: int, bloquear=False) -> Preparacion:
    consulta = select(Preparacion).where(Preparacion.id == preparacion_id)
    if bloquear:
        consulta = consulta.with_for_update()
    preparacion = db.session.execute(consulta).scalars().first()
    if preparacion is None:
        raise ApiError("PREPARACION_NO_ENCONTRADA", "Preparación no encontrada", 404)
    return preparacion


def _lineas(preparacion_id: int) -> list:
    filas = db.session.execute(
        select(PreparacionLinea, PedidoLinea, VentaLinea)
        .join(PedidoLinea, PedidoLinea.id == PreparacionLinea.pedido_linea_id)
        .join(VentaLinea, VentaLinea.id == PedidoLinea.venta_linea_id)
        .where(PreparacionLinea.preparacion_id == preparacion_id)
        .order_by(PreparacionLinea.id)
    ).all()
    return [
        {
            "linea": linea,
            "pedido_linea": pedido_linea,
            "venta_linea": venta_linea,
        }
        for linea, pedido_linea, venta_linea in filas
    ]


def serializar(preparacion: Preparacion) -> dict:
    pedido = preparacion.pedido
    venta = pedido.venta
    direccion = db.session.execute(
        select(VentaDireccion).where(
            VentaDireccion.venta_id == venta.id, VentaDireccion.tipo == "ENVIO"
        )
    ).scalars().first()
    return {
        "id": preparacion.id,
        "pedido_id": preparacion.pedido_id,
        "folio": venta.folio,
        "estado": preparacion.estado,
        "prioridad": pedido.prioridad,
        "fecha_promesa": (
            pedido.fecha_promesa.isoformat() if pedido.fecha_promesa else None
        ),
        "destinatario": direccion.destinatario if direccion else None,
        "codigo_postal": direccion.codigo_postal if direccion else None,
        "tomada_por": preparacion.tomada_por,
        "iniciada_en": preparacion.iniciada_en.isoformat() if preparacion.iniciada_en else None,
        "terminada_en": (
            preparacion.terminada_en.isoformat() if preparacion.terminada_en else None
        ),
        "notas": preparacion.notas,
        "lineas": [
            {
                "id": fila["linea"].id,
                "pedido_linea_id": fila["pedido_linea"].id,
                "sku": fila["venta_linea"].sku,
                "nombre_producto": fila["venta_linea"].nombre_producto,
                "talla": fila["venta_linea"].talla,
                "color": fila["venta_linea"].color,
                "cantidad_requerida": fila["linea"].cantidad_requerida,
                "cantidad_surtida": fila["linea"].cantidad_surtida,
                "sku_verificado": fila["linea"].sku_verificado,
                "diseno_verificado": fila["linea"].diseno_verificado,
                "etiquetas_verificadas": fila["linea"].etiquetas_verificadas,
                "incidencia": fila["linea"].incidencia,
            }
            for fila in _lineas(preparacion.id)
        ],
    }


def cola(filtros=None, pagina=1, por_pagina=20) -> dict:
    filtros = filtros or {}
    consulta = (
        select(Preparacion, Pedido, Venta)
        .join(Pedido, Pedido.id == Preparacion.pedido_id)
        .join(Venta, Venta.id == Pedido.venta_id)
        .where(Pedido.estado == "CONFIRMADO")
    )
    estado = filtros.get("estado")
    if estado:
        consulta = consulta.where(Preparacion.estado == estado)
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.session.execute(
        consulta.order_by(
            case((Pedido.prioridad == "ALTA", 0), else_=1),
            Pedido.fecha_promesa,
            Pedido.id,
        )
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    return {
        "items": [serializar(preparacion) for preparacion, _, _ in filas],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def tomar_pedido(pedido_id: int, usuario_id: int) -> dict:
    pedido = db.session.execute(
        select(Pedido).where(Pedido.id == pedido_id).with_for_update()
    ).scalars().first()
    if pedido is None:
        raise ApiError("PEDIDO_NO_ENCONTRADO", "Pedido no encontrado", 404)
    if pedido.estado != "CONFIRMADO":
        raise ApiError("PEDIDO_NO_PREPARABLE", "El pedido no está listo para prepararse", 409)
    preparacion = db.session.execute(
        select(Preparacion).where(Preparacion.pedido_id == pedido_id).with_for_update()
    ).scalars().first()
    if preparacion is None:
        preparacion = pedido_service.crear_preparacion(pedido)
    if preparacion.estado != "POR_SURTIR":
        raise ApiError("PREPARACION_NO_DISPONIBLE", "La preparación ya fue tomada", 409)
    preparacion.estado = "EN_PICKING"
    preparacion.tomada_por = usuario_id
    preparacion.iniciada_en = _ahora()
    pedido_service.cambiar_estado(
        pedido,
        "EN_PREPARACION",
        "Pedido tomado para preparación",
        usuario_id=usuario_id,
    )
    alertas_service.cerrar(f"PEDIDO_ESTANCADO:{pedido.id}")
    db.session.commit()
    return serializar(preparacion)


def actualizar_lineas(preparacion_id: int, datos: dict, usuario_id: int) -> dict:
    preparacion = _preparacion(preparacion_id, bloquear=True)
    if preparacion.estado not in ("EN_PICKING", "EN_VERIFICACION"):
        raise ApiError(
            "PREPARACION_NO_EDITABLE", "La preparación no permite capturar líneas", 409
        )
    filas = {fila["linea"].id: fila for fila in _lineas(preparacion.id)}
    for cambio in datos["lineas"]:
        fila = filas.get(cambio["preparacion_linea_id"])
        if fila is None:
            raise ApiError(
                "LINEA_NO_ENCONTRADA", "La línea no pertenece a la preparación", 404
            )
        if "sku" in cambio and cambio["sku"]:
            sku = str(cambio["sku"]).strip().upper()
            if sku != fila["venta_linea"].sku:
                raise ApiError(
                    "SKU_NO_PERMITIDO", "El SKU no corresponde a una línea del pedido", 422
                )
        linea = fila["linea"]
        if "cantidad_surtida" in cambio:
            if cambio["cantidad_surtida"] > linea.cantidad_requerida:
                raise ApiError(
                    "CANTIDAD_SURTIDA_INVALIDA",
                    "La cantidad surtida supera la cantidad requerida",
                    422,
                )
            linea.cantidad_surtida = cambio["cantidad_surtida"]
            fila["pedido_linea"].cant_preparada = cambio["cantidad_surtida"]
        for campo in ("sku_verificado", "diseno_verificado", "etiquetas_verificadas"):
            if campo in cambio:
                setattr(linea, campo, bool(cambio[campo]))
        if "sku" in cambio and cambio["sku"]:
            linea.sku_verificado = True

    todas = list(filas.values())
    if all(f["linea"].cantidad_surtida >= f["linea"].cantidad_requerida for f in todas):
        preparacion.estado = "EN_VERIFICACION"
    verificado = all(
        f["linea"].sku_verificado
        and f["linea"].diseno_verificado
        and f["linea"].etiquetas_verificadas
        for f in todas
    )
    if verificado and all(f["linea"].cantidad_surtida > 0 for f in todas):
        preparacion.estado = "EN_EMPAQUE"
    db.session.commit()
    return serializar(preparacion)


def registrar_incidencia(
    preparacion_id: int, datos: dict, usuario_id: int, ip=None
) -> dict:
    preparacion = _preparacion(preparacion_id, bloquear=True)
    if preparacion.estado not in ("EN_PICKING", "EN_VERIFICACION", "EN_EMPAQUE"):
        raise ApiError("PREPARACION_NO_EDITABLE", "La preparación no permite incidencias", 409)
    filas = {fila["linea"].id: fila for fila in _lineas(preparacion.id)}
    fila = filas.get(datos["preparacion_linea_id"])
    if fila is None:
        raise ApiError("LINEA_NO_ENCONTRADA", "La línea no pertenece a la preparación", 404)
    linea = fila["linea"]
    linea.incidencia = datos["descripcion"]
    linea.sku_verificado = False
    linea.diseno_verificado = False
    linea.etiquetas_verificadas = False
    preparacion.estado = "EN_PICKING"
    preparacion.notas = datos["descripcion"]

    if datos["tipo"] == "CALIDAD":
        cantidad = int(datos.get("cantidad") or 1)
        if cantidad > linea.cantidad_requerida:
            raise ApiError("CANTIDAD_INVALIDA", "La cantidad excede lo requerido", 422)
        variante_id = fila["venta_linea"].variante_id
        stocks = stock_service.bloquear([variante_id])
        stock = stocks[variante_id]
        stock_service.liberar(
            stock, cantidad, "INCIDENCIA", linea.id, usuario_id, "Unidad defectuosa"
        )
        merma = merma_service.registrar_merma(
            {
                "origen": "PRODUCTO",
                "variante_id": variante_id,
                "etapa": "ALMACEN",
                "causa_nombre": "Defecto de acabado",
                "cantidad": cantidad,
                "descripcion": datos["descripcion"],
            },
            usuario_id,
            ip=ip,
            descontar=True,
            confirmar=False,
        )
        pedido_linea = fila["pedido_linea"]
        pedido_linea.cant_reservada = max(0, pedido_linea.cant_reservada - cantidad)
        pedido_linea.cant_pendiente = min(
            pedido_linea.cantidad,
            pedido_linea.cant_pendiente + cantidad,
        )
        pedido_linea.cant_preparada = max(
            0, pedido_linea.cant_preparada - cantidad
        )
        linea.cantidad_surtida = max(0, linea.cantidad_surtida - cantidad)
        variante = db.session.get(VarianteProducto, variante_id)
        pedido_service.vincular_o_crear_orden(
            variante, cantidad, pedido_linea, usuario_id
        )
        pedido_service.cambiar_estado(
            preparacion.pedido,
            "EN_PRODUCCION",
            f"Incidencia de calidad: unidad {merma.id} enviada a merma",
            usuario_id=usuario_id,
        )
    db.session.commit()
    return serializar(preparacion)


def _inventario_empaque(codigo: str) -> InventarioMaterial:
    inventario = db.session.execute(
        select(InventarioMaterial)
        .join(Material, Material.id == InventarioMaterial.material_id)
        .where(Material.codigo == codigo)
    ).scalars().first()
    if inventario is None:
        raise ApiError(
            "MATERIAL_EMPAQUE_NO_ENCONTRADO",
            f"No existe inventario para el material de empaque {codigo}",
            422,
        )
    return inventario


def marcar_empaque(preparacion_id: int, usuario_id: int) -> dict:
    preparacion = _preparacion(preparacion_id, bloquear=True)
    if preparacion.estado not in ("EN_EMPAQUE", "EN_VERIFICACION"):
        raise ApiError("EMPAQUE_NO_PERMITIDO", "La preparación no está lista para empaque", 409)
    filas = _lineas(preparacion.id)
    incompletas = [
        fila
        for fila in filas
        if not (
            fila["linea"].sku_verificado
            and fila["linea"].diseno_verificado
            and fila["linea"].etiquetas_verificadas
            and fila["linea"].cantidad_surtida >= fila["linea"].cantidad_requerida
        )
    ]
    if incompletas:
        raise ApiError(
            "VERIFICACION_INCOMPLETA",
            "Todas las líneas deben estar verificadas antes de empacar",
            422,
            [
                {
                    "preparacion_linea_id": fila["linea"].id,
                    "sku": fila["venta_linea"].sku,
                }
                for fila in incompletas
            ],
        )
    unidades = sum(fila["linea"].cantidad_surtida for fila in filas)
    reglas = db.session.execute(
        select(EmpaqueRegla).where(EmpaqueRegla.activa.is_(True)).order_by(EmpaqueRegla.id)
    ).scalars().all()
    consumos = []
    for regla in reglas:
        cantidad = Decimal(regla.cantidad) * (
            unidades if regla.base == "POR_PRENDA" else 1
        )
        if cantidad <= 0:
            continue
        inventario = _inventario_empaque(regla.material.codigo)
        consumos.extend(
            material_service.consumir_peps(
                inventario.id,
                cantidad,
                "PREPARACION",
                preparacion.id,
                usuario_id,
                f"Empaque de {regla.base.lower()}",
            )
        )
    preparacion.estado = "LISTA"
    preparacion.terminada_en = _ahora()
    pedido_service.cambiar_estado(
        preparacion.pedido,
        "LISTO_ENVIO",
        "Preparación verificada y empacada",
        usuario_id=usuario_id,
    )
    registrar_bitacora(
        usuario_id,
        "PREPARACION_EMPACADA",
        "preparacion",
        preparacion.id,
        {"pedido_id": preparacion.pedido_id, "unidades": unidades},
    )
    alertas_service.cerrar(f"PEDIDO_ESTANCADO:{preparacion.pedido_id}")
    db.session.commit()
    respuesta = serializar(preparacion)
    respuesta["consumo_empaque"] = consumos
    return respuesta


def etiqueta(preparacion_id: int) -> dict:
    preparacion = _preparacion(preparacion_id)
    pedido = preparacion.pedido
    venta = pedido.venta
    direccion = db.session.execute(
        select(VentaDireccion).where(
            VentaDireccion.venta_id == venta.id, VentaDireccion.tipo == "ENVIO"
        )
    ).scalars().first()
    partes = []
    if direccion:
        partes = [
            direccion.calle,
            direccion.numero_ext,
            direccion.numero_int,
            direccion.colonia,
            direccion.municipio,
            direccion.estado,
            direccion.codigo_postal,
        ]
    direccion_texto = ", ".join(str(parte) for parte in partes if parte)
    return {
        "folio": venta.folio,
        "pedido_id": pedido.id,
        "destinatario": direccion.destinatario if direccion else None,
        "direccion": direccion_texto,
        "codigo_postal": direccion.codigo_postal if direccion else None,
        "telefono": direccion.telefono if direccion else None,
        "qr": f"UNIQUE:{venta.folio}",
    }
