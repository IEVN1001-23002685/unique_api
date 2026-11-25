"""Solicitudes, inspección y resolución de cambios y devoluciones (M07)."""

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    Color,
    Devolucion,
    DevolucionEvidencia,
    DevolucionLinea,
    Pedido,
    Pago,
    Producto,
    Talla,
    VarianteProducto,
    Venta,
    VentaDireccion,
    VentaLinea,
)
from app.services import (
    alertas_service,
    configuracion_service,
    merma_service,
    stock_service,
    venta_service,
)
from app.services import checkout_service
from app.services.bitacora_service import registrar_bitacora
from app.utils.dinero import decimal_valor, dinero, redondear
from app.utils.errores import ApiError
from app.utils.folios import generar_folio
from app.utils.imagenes import guardar_imagen

TIPOS = ("DEVOLUCION", "CAMBIO")
MOTIVOS = ("DEFECTO", "AJUSTE", "DANO_ENVIO", "PRODUCTO_EQUIVOCADO", "ARREPENTIMIENTO")
CON_ENVIO = ("DEFECTO", "DANO_ENVIO", "PRODUCTO_EQUIVOCADO")
DICTAMENES = ("REINGRESO", "MERMA")
RESOLUCIONES = ("REEMBOLSO", "CAMBIO")


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fecha_texto(valor):
    return valor.isoformat() if valor else None


def _obtener(devolucion_id: int) -> Devolucion:
    devolucion = db.session.get(Devolucion, devolucion_id)
    if devolucion is None:
        raise ApiError("DEVOLUCION_NO_ENCONTRADA", "Devolución no encontrada", 404)
    return devolucion


def _sku_linea(venta_linea_id: int) -> str | None:
    venta_linea = db.session.get(VentaLinea, venta_linea_id)
    return venta_linea.sku if venta_linea else None


def serializar(devolucion: Devolucion, incluir_importes: bool = True) -> dict:
    lineas = db.session.execute(
        select(DevolucionLinea)
        .where(DevolucionLinea.devolucion_id == devolucion.id)
        .order_by(DevolucionLinea.id)
    ).scalars().all()
    evidencias = db.session.execute(
        select(DevolucionEvidencia)
        .where(DevolucionEvidencia.devolucion_id == devolucion.id)
        .order_by(DevolucionEvidencia.id)
    ).scalars().all()
    pedido_id = db.session.execute(
        select(Pedido.id).where(Pedido.venta_id == devolucion.venta_id)
    ).scalars().first()
    salida = {
        "id": devolucion.id,
        "folio": devolucion.folio,
        "venta_id": devolucion.venta_id,
        "venta_folio": devolucion.venta.folio if devolucion.venta else None,
        "pedido_id": pedido_id,
        "usuario_id": devolucion.usuario_id,
        "tipo": devolucion.tipo,
        "motivo": devolucion.motivo,
        "descripcion": devolucion.descripcion,
        "estado": devolucion.estado,
        "resolucion": devolucion.resolucion,
        "venta_reemplazo_id": devolucion.venta_reemplazo_id,
        "motivo_rechazo": devolucion.motivo_rechazo,
        "resuelta_por": devolucion.resuelta_por,
        "resuelta_en": _fecha_texto(devolucion.resuelta_en),
        "creado_en": _fecha_texto(devolucion.creado_en),
        "lineas": [
            {
                "id": linea.id,
                "venta_linea_id": linea.venta_linea_id,
                "sku": _sku_linea(linea.venta_linea_id),
                "cantidad": linea.cantidad,
                "variante_cambio_id": linea.variante_cambio_id,
                "dictamen": linea.dictamen,
            }
            for linea in lineas
        ],
        "evidencias": [evidencia.url for evidencia in evidencias],
    }
    if incluir_importes:
        salida["reembolso_monto"] = dinero(devolucion.reembolso_monto)
    return salida


def listar(
    filtros=None,
    usuario_id: int | None = None,
    incluir_importes: bool = True,
    pagina: int = 1,
    por_pagina: int = 20,
) -> dict:
    filtros = filtros or {}
    consulta = select(Devolucion)
    if usuario_id is not None:
        consulta = consulta.where(Devolucion.usuario_id == usuario_id)
    if filtros.get("estado"):
        estados = filtros["estado"].split(",")
        consulta = consulta.where(Devolucion.estado.in_(estados))
    if filtros.get("tipo"):
        consulta = consulta.where(Devolucion.tipo == filtros["tipo"])
    if filtros.get("motivo"):
        consulta = consulta.where(Devolucion.motivo == filtros["motivo"])
    if filtros.get("desde"):
        consulta = consulta.where(Devolucion.creado_en >= filtros["desde"])
    if filtros.get("hasta"):
        consulta = consulta.where(Devolucion.creado_en < filtros["hasta"])
    if filtros.get("q"):
        patron = f"%{filtros['q']}%"
        consulta = consulta.where(
            db.or_(
                Devolucion.folio.like(patron),
                Devolucion.descripcion.like(patron),
            )
        )
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.session.execute(
        consulta.order_by(Devolucion.creado_en.desc(), Devolucion.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars().all()
    return {
        "items": [serializar(fila, incluir_importes) for fila in filas],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def detalle(devolucion_id: int, usuario_id: int | None = None, incluir_importes=True) -> dict:
    devolucion = _obtener(devolucion_id)
    if usuario_id is not None and devolucion.usuario_id != usuario_id:
        raise ApiError("DEVOLUCION_NO_ENCONTRADA", "Devolución no encontrada", 404)
    return serializar(devolucion, incluir_importes)


def _linea_vendida(venta_linea_id: int):
    linea = db.session.get(VentaLinea, venta_linea_id)
    if linea is None:
        raise ApiError("LINEA_NO_ENCONTRADA", "La línea de venta no existe", 404)
    return linea


def _devuelto(venta_linea_id: int) -> int:
    total = db.session.scalar(
        select(func.coalesce(func.sum(DevolucionLinea.cantidad), 0))
        .join(Devolucion, Devolucion.id == DevolucionLinea.devolucion_id)
        .where(
            DevolucionLinea.venta_linea_id == venta_linea_id,
            Devolucion.estado != "RECHAZADA",
        )
    )
    return int(total or 0)


def _variante_cambio(variante_id: int) -> VarianteProducto:
    fila = db.session.execute(
        select(VarianteProducto, Producto)
        .join(Producto, Producto.id == VarianteProducto.producto_id)
        .where(
            VarianteProducto.id == variante_id,
            VarianteProducto.activa.is_(True),
            Producto.activo.is_(True),
            Producto.eliminado_en.is_(None),
        )
    ).first()
    if fila is None:
        raise ApiError("VARIANTE_CAMBIO_NO_DISPONIBLE", "La variante de cambio no está disponible", 422)
    return fila[0]


def crear(datos: dict, archivos: list, usuario_id: int, ip=None) -> dict:
    if len(archivos) > 3:
        raise ApiError("EVIDENCIA_EXCEDIDA", "Se permiten hasta 3 imágenes", 400)
    pedido = db.session.get(Pedido, datos["pedido_id"])
    if pedido is None:
        raise ApiError("PEDIDO_NO_ENCONTRADO", "Pedido no encontrado", 404)
    venta = db.session.get(Venta, pedido.venta_id)
    if venta.usuario_id != usuario_id:
        raise ApiError("PEDIDO_NO_ENCONTRADO", "Pedido no encontrado", 404)
    if pedido.estado != "ENTREGADO":
        raise ApiError(
            "PEDIDO_NO_ENTREGADO",
            "Solo se pueden solicitar cambios o devoluciones de pedidos entregados",
            422,
        )
    dias = configuracion_service.valor_entero("dias_devolucion", 15)
    entregado = pedido.entregado_en or pedido.estado_desde or venta.fecha
    if entregado + timedelta(days=dias) < _ahora():
        raise ApiError("VENTANA_DEVOLUCION_CERRADA", "La ventana de devolución terminó", 422)

    tipo = datos["tipo"]
    if tipo not in TIPOS:
        raise ApiError("TIPO_INVALIDO", "Tipo de solicitud no válido", 422)
    if datos["motivo"] not in MOTIVOS:
        raise ApiError("MOTIVO_INVALIDO", "Motivo de devolución no válido", 422)
    if not datos.get("lineas"):
        raise ApiError("LINEAS_REQUERIDAS", "Se requiere al menos una línea", 422)

    acumuladas = {}
    for item in datos["lineas"]:
        venta_linea_id = item["venta_linea_id"]
        if venta_linea_id in acumuladas:
            raise ApiError("LINEA_DUPLICADA", "La línea de venta está repetida", 422)
        linea = _linea_vendida(venta_linea_id)
        if linea.venta_id != venta.id:
            raise ApiError("LINEA_AJENA", "La línea no pertenece al pedido", 422)
        cantidad = int(item["cantidad"])
        restante = int(linea.cantidad) - _devuelto(venta_linea_id)
        if cantidad <= 0 or cantidad > restante:
            raise ApiError(
                "CANTIDAD_DEVOLUCION_INVALIDA",
                "La cantidad excede las unidades disponibles para devolver",
                422,
            )
        variante_cambio_id = item.get("variante_cambio_id")
        if tipo == "CAMBIO" and not variante_cambio_id:
            raise ApiError(
                "VARIANTE_CAMBIO_REQUERIDA",
                "Cada línea de cambio requiere una variante de reemplazo",
                422,
            )
        if variante_cambio_id:
            _variante_cambio(variante_cambio_id)
        acumuladas[venta_linea_id] = {
            "venta_linea_id": venta_linea_id,
            "cantidad": cantidad,
            "variante_cambio_id": variante_cambio_id,
        }

    try:
        devolucion = Devolucion(
            folio=generar_folio("DEV"),
            venta_id=venta.id,
            usuario_id=usuario_id,
            tipo=tipo,
            motivo=datos["motivo"],
            descripcion=datos["descripcion"],
            estado="SOLICITADA",
        )
        db.session.add(devolucion)
        db.session.flush()
        for linea in acumuladas.values():
            db.session.add(DevolucionLinea(devolucion_id=devolucion.id, **linea))
        for archivo in archivos:
            _, url = guardar_imagen(archivo)
            db.session.add(DevolucionEvidencia(devolucion_id=devolucion.id, url=url))
        alertas_service.abrir(
            "DEVOLUCION_PENDIENTE",
            "PREVENTIVA",
            "Solicitud de devolución sin atender",
            f"La solicitud {devolucion.folio} está pendiente de aprobación.",
            "devolucion",
            devolucion.id,
            rol_destino="ADMIN",
            clave_unica=f"DEVOLUCION_PENDIENTE:{devolucion.id}",
            accion_sugerida="Aprobar o rechazar la solicitud",
        )
        registrar_bitacora(
            usuario_id,
            "DEVOLUCION_SOLICITADA",
            "devolucion",
            devolucion.id,
            {"folio": devolucion.folio, "tipo": tipo, "motivo": datos["motivo"]},
            ip,
        )
        db.session.commit()
        return detalle(devolucion.id, usuario_id)
    except Exception:
        db.session.rollback()
        raise


def _atender(devolucion_id: int, estado: str, datos: dict, usuario_id: int, ip: str, accion: str) -> dict:
    devolucion = _obtener(devolucion_id)
    if devolucion.estado != "SOLICITADA":
        raise ApiError("ESTADO_NO_VALIDO", "La solicitud ya fue atendida", 409)
    if estado == "RECHAZADA" and not datos.get("motivo"):
        raise ApiError("MOTIVO_REQUERIDO", "El rechazo requiere un motivo", 422)
    devolucion.estado = estado
    if estado == "RECHAZADA":
        devolucion.resolucion = "RECHAZO"
        devolucion.motivo_rechazo = datos["motivo"]
    alertas_service.cerrar(f"DEVOLUCION_PENDIENTE:{devolucion.id}")
    registrar_bitacora(
        usuario_id,
        f"DEVOLUCION_{accion}",
        "devolucion",
        devolucion.id,
        {"folio": devolucion.folio, "estado": estado},
        ip,
    )
    db.session.commit()
    return serializar(devolucion)


def aprobar(devolucion_id: int, usuario_id: int, ip=None) -> dict:
    return _atender(devolucion_id, "APROBADA", {}, usuario_id, ip, "APROBADA")


def rechazar(devolucion_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    return _atender(devolucion_id, "RECHAZADA", datos, usuario_id, ip, "RECHAZADA")


def recibir(devolucion_id: int, usuario_id: int, ip=None) -> dict:
    devolucion = _obtener(devolucion_id)
    if devolucion.estado != "APROBADA":
        raise ApiError("ESTADO_NO_VALIDO", "La solicitud no está aprobada", 409)
    devolucion.estado = "RECIBIDA"
    alertas_service.abrir(
        "DEVOLUCION_PENDIENTE",
        "PREVENTIVA",
        "Devolución recibida sin inspeccionar",
        f"La devolución {devolucion.folio} está pendiente de dictamen.",
        "devolucion",
        devolucion.id,
        rol_destino="AMBOS",
        clave_unica=f"DEVOLUCION_INSPECCION:{devolucion.id}",
        accion_sugerida="Dictaminar cada línea recibida",
    )
    registrar_bitacora(
        usuario_id,
        "DEVOLUCION_RECIBIDA",
        "devolucion",
        devolucion.id,
        {"folio": devolucion.folio},
        ip,
    )
    db.session.commit()
    return serializar(devolucion, incluir_importes=False)


def dictaminar(devolucion_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    devolucion = _obtener(devolucion_id)
    if devolucion.estado != "RECIBIDA":
        raise ApiError("ESTADO_NO_VALIDO", "La devolución no está recibida", 409)
    lineas = {
        linea.id: linea
        for linea in db.session.execute(
            select(DevolucionLinea).where(DevolucionLinea.devolucion_id == devolucion.id)
        ).scalars().all()
    }
    solicitadas = datos.get("lineas") or []
    if len(solicitadas) != len(lineas):
        raise ApiError(
            "DICTAMEN_INCOMPLETO", "Se requiere el dictamen de todas las líneas", 422
        )
    vistos = set()
    stocks = {}
    for item in solicitadas:
        linea_id = int(item["devolucion_linea_id"])
        if linea_id not in lineas or linea_id in vistos:
            raise ApiError("LINEA_DICTAMEN_INVALIDA", "Línea de devolución no válida", 422)
        vistos.add(linea_id)
        linea = lineas[linea_id]
        if linea.dictamen != "PENDIENTE":
            raise ApiError("DICTAMEN_DUPLICADO", "La línea ya fue dictaminada", 409)
        dictamen = item["dictamen"]
        if dictamen not in DICTAMENES:
            raise ApiError("DICTAMEN_INVALIDO", "Dictamen no válido", 422)
        venta_linea = db.session.get(VentaLinea, linea.venta_linea_id)
        if dictamen == "REINGRESO":
            if venta_linea.variante_id not in stocks:
                stocks.update(stock_service.bloquear([venta_linea.variante_id]))
            stock = stocks[venta_linea.variante_id]
            stock.existencia += int(linea.cantidad)
            stock_service.registrar_movimiento(
                stock,
                "REINGRESO",
                int(linea.cantidad),
                0,
                "DEVOLUCION",
                devolucion.id,
                usuario_id,
                f"Reingreso por {devolucion.folio}",
            )
        else:
            merma_service.registrar_merma(
                {
                    "origen": "PRODUCTO",
                    "variante_id": venta_linea.variante_id,
                    "cantidad": int(linea.cantidad),
                    "etapa": "DEVOLUCION",
                    "causa_id": item.get("causa_id"),
                    "causa_nombre": item.get("causa_nombre"),
                    "descripcion": item.get("descripcion") or datos.get("descripcion")
                    or f"Merma de devolución {devolucion.folio}",
                    "devolucion_linea_id": linea.id,
                    "folio_origen": devolucion.folio,
                },
                usuario_id,
                ip=ip,
                descontar=False,
                confirmar=False,
            )
        linea.dictamen = dictamen

    alertas_service.cerrar(f"DEVOLUCION_INSPECCION:{devolucion.id}")
    registrar_bitacora(
        usuario_id,
        "DEVOLUCION_DICTAMINADA",
        "devolucion",
        devolucion.id,
        {"folio": devolucion.folio, "lineas": len(solicitadas)},
        ip,
    )
    db.session.commit()
    return serializar(devolucion, incluir_importes=False)


def _importe_reembolso(devolucion: Devolucion) -> Decimal:
    lineas_db = {
        linea.id: linea
        for linea in db.session.execute(
            select(DevolucionLinea).where(DevolucionLinea.devolucion_id == devolucion.id)
        ).scalars().all()
    }
    importe = Decimal("0")
    for linea in lineas_db.values():
        venta_linea = db.session.get(VentaLinea, linea.venta_linea_id)
        subtotal = decimal_valor(venta_linea.subtotal) * int(linea.cantidad) / int(
            venta_linea.cantidad
        )
        importe += subtotal
    descuento_total = decimal_valor(devolucion.venta.descuento_monto)
    if descuento_total > 0:
        vendido = sum(
            decimal_valor(db.session.get(VentaLinea, linea.venta_linea_id).subtotal)
            for linea in lineas_db.values()
        )
        importe -= descuento_total * importe / vendido if vendido else Decimal("0")
    if devolucion.motivo in CON_ENVIO:
        importe += decimal_valor(devolucion.venta.costo_envio)
    return redondear(max(Decimal("0"), importe))


def _venta_reemplazo(devolucion: Devolucion, usuario_id: int, ip=None) -> Venta:
    original = devolucion.venta
    direccion = db.session.execute(
        select(VentaDireccion).where(
            VentaDireccion.venta_id == original.id,
            VentaDireccion.tipo == "ENVIO",
        )
    ).scalars().first()
    if direccion is None:
        raise ApiError("DIRECCION_VENTA_NO_ENCONTRADA", "La venta no tiene dirección de envío", 409)
    datos = {
        "direccion": checkout_service.datos_direccion(direccion),
        "requiere_factura": False,
        "notas": f"Venta de reemplazo de {devolucion.folio}",
    }
    devolucion_lineas = db.session.execute(
        select(DevolucionLinea)
        .where(DevolucionLinea.devolucion_id == devolucion.id)
        .order_by(DevolucionLinea.id)
    ).scalars().all()
    lineas = []
    for devolucion_linea in devolucion_lineas:
        venta_linea = db.session.get(VentaLinea, devolucion_linea.venta_linea_id)
        variante = db.session.get(
            VarianteProducto, devolucion_linea.variante_cambio_id
        )
        if variante is None:
            raise ApiError("VARIANTE_CAMBIO_REQUERIDA", "Falta la variante de reemplazo", 422)
        producto = db.session.get(Producto, variante.producto_id)
        talla = db.session.get(Talla, variante.talla_id)
        color = db.session.get(Color, variante.color_id)
        lineas.append(
            {
                "variante_id": variante.id,
                "sku": variante.sku,
                "nombre_producto": producto.nombre,
                "talla": talla.codigo,
                "color": color.codigo,
                "cantidad": int(devolucion_linea.cantidad),
                "precio_unitario": Decimal("0"),
                "subtotal": Decimal("0"),
                "disponibilidad": "Disponible",
            }
        )
    dias = configuracion_service.valor_entero("dias_produccion_estandar", 5)
    resumen = {
        "fecha_promesa": (_ahora() + timedelta(days=dias)).date(),
        "subtotal": Decimal("0"),
        "descuento": None,
        "descuento_monto": Decimal("0"),
        "tarifa": {"id": original.tarifa_envio_id},
        "costo_envio": Decimal("0"),
        "iva_importe": Decimal("0"),
        "total": Decimal("0"),
        "lineas": [],
    }
    referencia = f"CAM-{secrets.token_hex(5).upper()}"
    stocks = stock_service.bloquear([linea["variante_id"] for linea in lineas])
    venta = checkout_service.crear_venta_y_lineas(
        devolucion.usuario_id,
        datos,
        resumen,
        lineas,
        referencia,
        {"metodo": "TRANSFERENCIA"},
        canal="CAMBIO",
        estado_pago="PAGADA",
        creada_por=usuario_id,
        registrar_pago=False,
    )
    db.session.add(
        Pago(
            venta_id=venta.id,
            tipo="COBRO",
            metodo="TRANSFERENCIA",
            estado="APROBADO",
            monto=Decimal("0"),
            referencia=referencia,
            registrado_por=usuario_id,
        )
    )
    checkout_service.crear_pedido(
        devolucion.usuario_id, datos, resumen, lineas, venta, stocks
    )
    return venta


def resolver(devolucion_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    devolucion = _obtener(devolucion_id)
    if devolucion.estado != "RECIBIDA":
        raise ApiError("ESTADO_NO_VALIDO", "La devolución no está lista para resolver", 409)
    pendientes = db.session.scalar(
        select(func.count()).where(
            DevolucionLinea.devolucion_id == devolucion.id,
            DevolucionLinea.dictamen == "PENDIENTE",
        )
    )
    if pendientes:
        raise ApiError("DICTAMEN_PENDIENTE", "Todas las líneas deben estar dictaminadas", 422)
    resolucion = datos["resolucion"]
    if resolucion not in RESOLUCIONES:
        raise ApiError("RESOLUCION_INVALIDA", "Resolución no válida", 422)
    try:
        if resolucion == "REEMBOLSO":
            monto = _importe_reembolso(devolucion)
            reembolso = venta_service.reembolsar(
                devolucion.venta_id,
                {"monto": monto, "motivo": devolucion.descripcion},
                usuario_id,
                ip=ip,
                confirmar=False,
            )
            devolucion.reembolso_monto = reembolso.monto
        else:
            if devolucion.tipo != "CAMBIO":
                raise ApiError(
                    "CAMBIO_NO_SOLICITADO", "La solicitud no es de cambio", 422
                )
            venta = _venta_reemplazo(devolucion, usuario_id, ip)
            devolucion.venta_reemplazo_id = venta.id
            devolucion.reembolso_monto = Decimal("0")
        devolucion.resolucion = resolucion
        devolucion.estado = "RESUELTA"
        devolucion.resuelta_por = usuario_id
        devolucion.resuelta_en = _ahora()
        alertas_service.cerrar(f"DEVOLUCION_INSPECCION:{devolucion.id}")
        registrar_bitacora(
            usuario_id,
            "DEVOLUCION_RESUELTA",
            "devolucion",
            devolucion.id,
            {
                "folio": devolucion.folio,
                "resolucion": resolucion,
                "monto": dinero(devolucion.reembolso_monto),
            },
            ip,
        )
        db.session.commit()
        return serializar(devolucion)
    except Exception:
        db.session.rollback()
        raise
