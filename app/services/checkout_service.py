"""Checkout atómico, idempotente y con pago simulado (M05, flujo 9.5)."""

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select

from app.extensions import db
from app.models import (
    Descuento,
    Pago,
    Pedido,
    PedidoLinea,
    Preparacion,
    PreparacionLinea,
    VarianteProducto,
    Venta,
    VentaDireccion,
    VentaLinea,
)
from app.services import (
    alertas_service,
    carrito_service,
    configuracion_service,
    descuento_service,
    direccion_service,
    envio_service,
    idempotencia_service,
    medio_pago_service,
    pago_service,
    pedido_service,
    receta_service,
    stock_service,
)
from app.utils.errores import ApiError
from app.utils.folios import generar_folio

ALCANCE_IDEMPOTENCIA = "checkout:pagar"
CAMPOS_DIRECCION = (
    "destinatario",
    "telefono",
    "calle",
    "numero_ext",
    "numero_int",
    "colonia",
    "municipio",
    "estado",
    "codigo_postal",
    "referencia",
)


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _dos_decimales(valor) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _direccion(usuario_id: int, datos: dict):
    if datos.get("direccion_id"):
        return direccion_service.obtener(usuario_id, datos["direccion_id"])
    if datos.get("direccion"):
        return datos["direccion"]
    if datos.get("codigo_postal"):
        return {"codigo_postal": datos["codigo_postal"]}
    raise ApiError(
        "DIRECCION_REQUERIDA", "Se requiere una dirección de envío", 422
    )


def _codigo_postal(direccion) -> str:
    if isinstance(direccion, dict):
        return direccion["codigo_postal"]
    return direccion.codigo_postal


def _datos_direccion(direccion) -> dict:
    if isinstance(direccion, dict):
        return {campo: direccion.get(campo) for campo in CAMPOS_DIRECCION}
    return {campo: getattr(direccion, campo) for campo in CAMPOS_DIRECCION}


def _subtotal(lineas: list) -> Decimal:
    total = sum(
        (_dos_decimales(linea["precio_unitario"]) * linea["cantidad"] for linea in lineas),
        Decimal("0"),
    )
    return _dos_decimales(total)


def _resumen(usuario_id: int, lineas: list, datos: dict) -> dict:
    subtotal = _subtotal(lineas)
    articulos = sum(linea["cantidad"] for linea in lineas)
    direccion = _direccion(usuario_id, datos)
    tarifa, costo_envio = envio_service.calcular_envio(_codigo_postal(direccion))
    descuento = descuento_service.mejor(
        usuario_id, subtotal, articulos, datos.get("descuento_codigo")
    )
    descuento_monto = descuento["monto"] if descuento else Decimal("0")
    total = _dos_decimales(subtotal - descuento_monto + costo_envio)
    iva_pct = configuracion_service.valor_decimal("iva_pct", Decimal("16"))
    iva_importe = _dos_decimales(total * iva_pct / (Decimal("100") + iva_pct))
    dias = configuracion_service.valor_entero("dias_produccion_estandar", 5) + int(
        tarifa.dias_estimados
    )
    fecha_promesa = (datetime.now(timezone.utc) + timedelta(days=dias)).date()
    return {
        "subtotal": subtotal,
        "descuento_monto": _dos_decimales(descuento_monto),
        "costo_envio": costo_envio,
        "iva_importe": iva_importe,
        "total": total,
        "monto_articulos": articulos,
        "descuento": descuento,
        "tarifa": envio_service.detalle_tarifa(tarifa),
        "fecha_promesa": fecha_promesa,
        "lineas": [
            {
                "variante_id": linea["variante_id"],
                "sku": linea["sku"],
                "nombre_producto": linea["nombre_producto"],
                "talla": linea["talla"],
                "color": linea["color"],
                "cantidad": linea["cantidad"],
                "precio_unitario": f"{_dos_decimales(linea['precio_unitario']):.2f}",
                "subtotal": f"{_dos_decimales(linea['subtotal']):.2f}",
                "disponibilidad": linea["disponibilidad"],
            }
            for linea in lineas
        ],
    }


def _serializar_resumen(resumen: dict) -> dict:
    resultado = dict(resumen)
    resultado["subtotal"] = f"{resumen['subtotal']:.2f}"
    resultado["descuento_monto"] = f"{resumen['descuento_monto']:.2f}"
    resultado["costo_envio"] = f"{resumen['costo_envio']:.2f}"
    resultado["iva_importe"] = f"{resumen['iva_importe']:.2f}"
    resultado["total"] = f"{resumen['total']:.2f}"
    resultado["fecha_promesa"] = resumen["fecha_promesa"].isoformat()
    if resumen["descuento"]:
        resultado["descuento"] = {
            clave: valor
            for clave, valor in resumen["descuento"].items()
            if clave != "monto"
        }
    return resultado


def cotizar(usuario_id: int, datos: dict) -> dict:
    lineas, _ = carrito_service.lineas_para_checkout(usuario_id)
    return _serializar_resumen(_resumen(usuario_id, lineas, datos))


def validar_descuento(usuario_id: int, datos: dict) -> dict:
    lineas, _ = carrito_service.lineas_para_checkout(usuario_id)
    subtotal = _subtotal(lineas)
    articulos = sum(linea["cantidad"] for linea in lineas)
    descuento = descuento_service.aplicable(
        usuario_id, subtotal, articulos, datos["codigo"]
    )
    return {
        "codigo": descuento["codigo"],
        "nombre": descuento["nombre"],
        "tipo": descuento["tipo"],
        "valor": descuento["valor"],
        "ahorro": descuento["monto_texto"],
    }


def _crear_venta_y_lineas(usuario_id, datos, resumen, lineas, referencia, resultado_pago):
    fecha_promesa = resumen["fecha_promesa"]
    venta = Venta(
        folio=generar_folio("UNQ"),
        usuario_id=usuario_id,
        canal="TIENDA",
        fecha=_ahora(),
        estado="ACTIVA",
        estado_pago="PAGADA",
        subtotal=resumen["subtotal"],
        descuento_id=resumen["descuento"]["descuento_id"] if resumen["descuento"] else None,
        descuento_monto=resumen["descuento_monto"],
        tarifa_envio_id=resumen["tarifa"]["id"],
        costo_envio=resumen["costo_envio"],
        total=resumen["total"],
        iva_incluido=True,
        requiere_factura=bool(datos.get("requiere_factura")),
        fecha_promesa=fecha_promesa,
        creada_por=usuario_id,
        notas=datos.get("notas"),
    )
    db.session.add(venta)
    db.session.flush()

    for linea in lineas:
        variante_id = linea["variante_id"]
        db.session.add(
            VentaLinea(
                venta_id=venta.id,
                variante_id=variante_id,
                sku=linea["sku"],
                nombre_producto=linea["nombre_producto"],
                talla=linea["talla"],
                color=linea["color"],
                cantidad=linea["cantidad"],
                precio_unitario=_dos_decimales(linea["precio_unitario"]),
                subtotal=_dos_decimales(linea["subtotal"]),
                costo_estandar_unitario=receta_service.costo_estandar_unitario(variante_id),
            )
        )
    db.session.flush()

    direccion = _direccion(usuario_id, datos)
    datos_envio = _datos_direccion(direccion)
    db.session.add(VentaDireccion(venta_id=venta.id, tipo="ENVIO", **datos_envio))

    if datos.get("requiere_factura"):
        rfc = datos.get("rfc")
        razon_social = datos.get("razon_social")
        if not rfc or not razon_social or not 12 <= len(rfc) <= 13:
            raise ApiError(
                "DATOS_FACTURACION_INCOMPLETOS",
                "Se requieren RFC de 12 o 13 caracteres y razón social",
                422,
            )
        datos_facturacion = dict(datos_envio)
        datos_facturacion["codigo_postal"] = datos.get("cp_fiscal") or datos_envio[
            "codigo_postal"
        ]
        datos_facturacion["rfc"] = rfc
        datos_facturacion["razon_social"] = razon_social
    else:
        datos_facturacion = dict(datos_envio)
        datos_facturacion["rfc"] = None
        datos_facturacion["razon_social"] = None
    db.session.add(
        VentaDireccion(venta_id=venta.id, tipo="FACTURACION", **datos_facturacion)
    )

    db.session.add(
        Pago(
            venta_id=venta.id,
            tipo="COBRO",
            metodo=resultado_pago["metodo"],
            estado="APROBADO",
            medio_pago_id=resultado_pago["medio_pago_id"],
            monto=resumen["total"],
            referencia=referencia,
            ultimos4=resultado_pago["ultimos4"],
            titular=resultado_pago["titular"],
            registrado_por=usuario_id,
        )
    )
    db.session.flush()
    return venta


def _crear_pedido(usuario_id, datos, resumen, lineas, venta, stocks):
    pedido = Pedido(
        venta_id=venta.id,
        estado="RECIBIDO",
        estado_desde=_ahora(),
        fecha_promesa=resumen["fecha_promesa"],
    )
    db.session.add(pedido)
    db.session.flush()

    venta_lineas = db.session.execute(
        select(VentaLinea).where(VentaLinea.venta_id == venta.id).order_by(VentaLinea.id)
    ).scalars().all()
    parejas = []
    for venta_linea, linea in zip(venta_lineas, lineas):
        pedido_linea = PedidoLinea(
            pedido_id=pedido.id,
            venta_linea_id=venta_linea.id,
            cantidad=linea["cantidad"],
            cant_reservada=0,
            cant_pendiente=linea["cantidad"],
        )
        db.session.add(pedido_linea)
        db.session.flush()
        parejas.append((pedido_linea, linea))

    hay_pendiente = False
    variantes_tocadas = []
    for pedido_linea, linea in sorted(
        parejas, key=lambda pareja: pareja[1]["variante_id"]
    ):
        variante_id = linea["variante_id"]
        stocks[variante_id]
        reservada = stock_service.reservar(
            stocks[variante_id],
            linea["cantidad"],
            "PEDIDO",
            pedido.id,
            usuario_id,
        )
        pendiente = linea["cantidad"] - reservada
        pedido_linea.cant_reservada = reservada
        pedido_linea.cant_pendiente = pendiente
        if pendiente:
            hay_pendiente = True
            pedido_service.vincular_o_crear_orden(
                db.session.get(VarianteProducto, variante_id),
                pendiente,
                pedido_linea,
                usuario_id,
                resumen["fecha_promesa"],
            )
        variantes_tocadas.append(variante_id)

    pedido.estado = "EN_PRODUCCION" if hay_pendiente else "CONFIRMADO"
    pedido.estado_desde = _ahora()
    pedido_service.agregar_evento(
        pedido, "RECIBIDO", "Pedido recibido correctamente", usuario_id=usuario_id
    )
    pedido_service.agregar_evento(
        pedido,
        pedido.estado,
        (
            "Existencia reservada; el pedido pasa a preparación"
            if not hay_pendiente
            else "Existencia parcial; el faltante queda pendiente de producción"
        ),
        usuario_id=usuario_id,
    )

    if not hay_pendiente:
        preparacion = Preparacion(pedido_id=pedido.id, estado="POR_SURTIR")
        db.session.add(preparacion)
        db.session.flush()
        for pedido_linea, _ in parejas:
            db.session.add(
                PreparacionLinea(
                    preparacion_id=preparacion.id,
                    pedido_linea_id=pedido_linea.id,
                    cantidad_requerida=pedido_linea.cantidad,
                )
            )
    return pedido, variantes_tocadas


def _pagar_transaccion(usuario_id, datos, registro):
    lineas, carrito = carrito_service.lineas_para_checkout(usuario_id)
    stocks = stock_service.bloquear([linea["variante_id"] for linea in lineas])
    resumen = _resumen(usuario_id, lineas, datos)

    medio = None
    if datos.get("medio_pago_id"):
        medio = medio_pago_service.obtener(usuario_id, datos["medio_pago_id"])
    elif datos["metodo_pago"] == "CUENTA":
        raise ApiError(
            "MEDIO_PAGO_REQUERIDO", "Se requiere una cuenta simulada guardada", 422
        )

    referencia = f"SIM-{secrets.token_hex(5).upper()}"
    resultado_pago = pago_service.simular(
        resumen["total"],
        datos["metodo_pago"],
        medio_pago=medio,
        numero_tarjeta=datos.get("numero_tarjeta"),
        titular=datos.get("titular"),
        vence_mes=datos.get("vence_mes"),
        vence_anio=datos.get("vence_anio"),
        cvv=datos.get("cvv"),
        referencia=referencia,
    )
    if not resultado_pago["aprobado"]:
        raise ApiError(
            "PAGO_RECHAZADO",
            "El pago fue rechazado",
            422,
            [{"motivo": resultado_pago["motivo"]}],
        )

    venta = _crear_venta_y_lineas(
        usuario_id, datos, resumen, lineas, referencia, resultado_pago
    )
    pedido, variantes_tocadas = _crear_pedido(
        usuario_id, datos, resumen, lineas, venta, stocks
    )

    if resumen["descuento"]:
        descuento = db.session.get(Descuento, resumen["descuento"]["descuento_id"])
        descuento.usos_actuales += 1
    carrito_service.convertir(carrito)
    alertas_service.evaluar_variantes(variantes_tocadas)

    respuesta = {
        "venta": {
            "id": venta.id,
            "folio": venta.folio,
            "estado": venta.estado,
            "estado_pago": venta.estado_pago,
            "total": f"{resumen['total']:.2f}",
        },
        "pedido": {
            "id": pedido.id,
            "folio": venta.folio,
            "estado": pedido.estado,
        },
        "resumen": _serializar_resumen(resumen),
    }
    idempotencia_service.completar(registro, respuesta)
    db.session.commit()
    return respuesta


def pagar(usuario_id: int, datos: dict, clave: str) -> dict:
    if not clave:
        raise ApiError("IDEMPOTENCIA_REQUERIDA", "Se requiere Idempotency-Key", 400)
    peticion = {"usuario_id": usuario_id, **datos}
    registro, respuesta_previa = idempotencia_service.iniciar(
        clave, ALCANCE_IDEMPOTENCIA, peticion
    )
    if respuesta_previa is not None:
        return respuesta_previa
    try:
        return _pagar_transaccion(usuario_id, datos, registro)
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
