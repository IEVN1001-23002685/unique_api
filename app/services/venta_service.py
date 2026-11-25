"""Registro completo de ventas, pagos, reembolsos y descuentos (M08).

La venta no se edita: solo cambian el pago y la cancelación. Las operaciones que
modifican venta, pedido, pago e inventario confirman o revierten todo juntos.
"""

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, or_, select

from app.extensions import db
from app.models import (
    Color,
    Descuento,
    MedioPago,
    Pago,
    Pedido,
    Producto,
    Rol,
    Talla,
    Usuario,
    VarianteProducto,
    Venta,
    VentaDireccion,
    VentaLinea,
)
from app.services import (
    alertas_service,
    checkout_service,
    configuracion_service,
    pago_service,
    pedido_service,
    stock_service,
)
from app.services.bitacora_service import registrar_bitacora
from app.utils.dinero import decimal_valor, dinero, redondear
from app.utils.errores import ApiError

METODOS_MANUALES = ("TARJETA", "CUENTA", "TRANSFERENCIA", "EFECTIVO")
ESTADOS_PAGO = ("PENDIENTE", "PAGADA", "REEMBOLSADA_PARCIAL", "REEMBOLSADA")


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fecha_texto(valor):
    return valor.isoformat() if valor else None


def _obtener(venta_id: int) -> Venta:
    venta = db.session.get(Venta, venta_id)
    if venta is None:
        raise ApiError("VENTA_NO_ENCONTRADA", "Venta no encontrada", 404)
    return venta


def _pedido(venta_id: int) -> Pedido | None:
    return db.session.execute(
        select(Pedido).where(Pedido.venta_id == venta_id)
    ).scalars().first()


def _iva_importe(venta: Venta) -> Decimal:
    total = decimal_valor(venta.total)
    iva_pct = configuracion_service.valor_decimal("iva_pct", Decimal("16"))
    return redondear(total * iva_pct / (Decimal("100") + iva_pct))


def serializar(venta: Venta) -> dict:
    venta_lineas = db.session.execute(
        select(VentaLinea).where(VentaLinea.venta_id == venta.id).order_by(VentaLinea.id)
    ).scalars().all()
    pagos = db.session.execute(
        select(Pago).where(Pago.venta_id == venta.id).order_by(Pago.fecha, Pago.id)
    ).scalars().all()
    direcciones = db.session.execute(
        select(VentaDireccion)
        .where(VentaDireccion.venta_id == venta.id)
        .order_by(VentaDireccion.id)
    ).scalars().all()
    pedido = _pedido(venta.id)
    total_costo = sum(
        decimal_valor(linea.costo_estandar_unitario) * int(linea.cantidad)
        for linea in venta_lineas
    )
    return {
        "id": venta.id,
        "folio": venta.folio,
        "fecha": _fecha_texto(venta.fecha),
        "cliente_id": venta.usuario_id,
        "cliente": {
            "id": venta.usuario.id,
            "nombre": venta.usuario.nombre,
            "apellidos": venta.usuario.apellidos,
            "correo": venta.usuario.correo,
        },
        "canal": venta.canal,
        "estado": venta.estado,
        "estado_pago": venta.estado_pago,
        "subtotal": dinero(venta.subtotal),
        "descuento_monto": dinero(venta.descuento_monto),
        "descuento_id": venta.descuento_id,
        "costo_envio": dinero(venta.costo_envio),
        "total": dinero(venta.total),
        "iva_importe": dinero(_iva_importe(venta)),
        "iva_incluido": bool(venta.iva_incluido),
        "requiere_factura": bool(venta.requiere_factura),
        "fecha_promesa": _fecha_texto(venta.fecha_promesa),
        "cancelada_en": _fecha_texto(venta.cancelada_en),
        "motivo_cancelacion": venta.motivo_cancelacion,
        "creada_por": venta.creada_por,
        "notas": venta.notas,
        "pedido": (
            {"id": pedido.id, "estado": pedido.estado, "prioridad": pedido.prioridad}
            if pedido
            else None
        ),
        "lineas": [
            {
                "id": linea.id,
                "variante_id": linea.variante_id,
                "sku": linea.sku,
                "nombre_producto": linea.nombre_producto,
                "talla": linea.talla,
                "color": linea.color,
                "cantidad": linea.cantidad,
                "precio_unitario": dinero(linea.precio_unitario),
                "subtotal": dinero(linea.subtotal),
                "costo_estandar_unitario": f"{decimal_valor(linea.costo_estandar_unitario):.6f}",
                "margen": dinero(decimal_valor(linea.subtotal) - decimal_valor(linea.costo_estandar_unitario) * int(linea.cantidad)),
            }
            for linea in venta_lineas
        ],
        "direcciones": [
            {
                "tipo": direccion.tipo,
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
                "rfc": direccion.rfc,
                "razon_social": direccion.razon_social,
            }
            for direccion in direcciones
        ],
        "pagos": [
            {
                "id": pago.id,
                "tipo": pago.tipo,
                "metodo": pago.metodo,
                "estado": pago.estado,
                "monto": dinero(pago.monto),
                "referencia": pago.referencia,
                "ultimos4": pago.ultimos4,
                "titular": pago.titular,
                "motivo_rechazo": pago.motivo_rechazo,
                "fecha": _fecha_texto(pago.fecha),
            }
            for pago in pagos
        ],
        "costo_estandar_total": dinero(total_costo),
        "margen_total": dinero(decimal_valor(venta.total) - total_costo),
    }


def resumen(venta: Venta) -> dict:
    pedido = _pedido(venta.id)
    return {
        "id": venta.id,
        "folio": venta.folio,
        "fecha": _fecha_texto(venta.fecha),
        "cliente": {
            "id": venta.usuario.id,
            "nombre": venta.usuario.nombre,
            "apellidos": venta.usuario.apellidos,
            "correo": venta.usuario.correo,
        },
        "canal": venta.canal,
        "estado": venta.estado,
        "estado_pago": venta.estado_pago,
        "total": dinero(venta.total),
        "pedido_estado": pedido.estado if pedido else None,
    }


def detalle(venta_id: int) -> dict:
    return serializar(_obtener(venta_id))


def listar(filtros=None, pagina: int = 1, por_pagina: int = 20) -> dict:
    filtros = filtros or {}
    consulta = select(Venta).join(Usuario, Usuario.id == Venta.usuario_id)
    if filtros.get("desde"):
        consulta = consulta.where(Venta.fecha >= filtros["desde"])
    if filtros.get("hasta"):
        consulta = consulta.where(Venta.fecha < filtros["hasta"])
    if filtros.get("canal"):
        consulta = consulta.where(Venta.canal == filtros["canal"])
    if filtros.get("estado_pago"):
        consulta = consulta.where(Venta.estado_pago == filtros["estado_pago"])
    if filtros.get("estado"):
        consulta = consulta.where(Venta.estado == filtros["estado"])
    if filtros.get("q"):
        patron = f"%{filtros['q']}%"
        consulta = consulta.where(
            or_(
                Venta.folio.like(patron),
                Usuario.nombre.like(patron),
                Usuario.apellidos.like(patron),
                Usuario.correo.like(patron),
            )
        )
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    ventas = db.session.execute(
        consulta.order_by(Venta.fecha.desc(), Venta.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars().all()
    return {
        "items": [resumen(venta) for venta in ventas],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def _linea_por_sku(sku: str, cantidad: int) -> dict:
    if cantidad <= 0:
        raise ApiError("CANTIDAD_INVALIDA", "La cantidad debe ser mayor a cero", 422)
    fila = db.session.execute(
        select(VarianteProducto, Producto, Talla, Color)
        .join(Producto, Producto.id == VarianteProducto.producto_id)
        .join(Talla, Talla.id == VarianteProducto.talla_id)
        .join(Color, Color.id == VarianteProducto.color_id)
        .where(
            VarianteProducto.sku == str(sku).strip().upper(),
            VarianteProducto.activa.is_(True),
            Producto.activo.is_(True),
            Producto.eliminado_en.is_(None),
        )
    ).first()
    if fila is None:
        raise ApiError("SKU_NO_DISPONIBLE", "La variante con ese SKU no está disponible", 404)
    variante, producto, talla, color = fila
    precio = decimal_valor(producto.precio_venta)
    if precio <= 0:
        raise ApiError("PRECIO_NO_DISPONIBLE", "El producto no tiene precio de venta", 422)
    return {
        "variante_id": variante.id,
        "sku": variante.sku,
        "nombre_producto": producto.nombre,
        "talla": talla.codigo,
        "color": color.codigo,
        "cantidad": int(cantidad),
        "precio_unitario": precio,
        "subtotal": redondear(precio * int(cantidad)),
        "disponibilidad": "Disponible",
    }


def _lineas_manuales(solicitadas: list) -> list:
    if not solicitadas:
        raise ApiError("LINEAS_REQUERIDAS", "Se requiere al menos una línea", 422)
    lineas = {}
    for item in solicitadas:
        sku = str(item["sku"]).strip().upper()
        base = lineas.get(sku)
        if base is None:
            base = _linea_por_sku(sku, item["cantidad"])
            lineas[sku] = base
        else:
            base["cantidad"] += int(item["cantidad"])
            base["subtotal"] = redondear(base["precio_unitario"] * base["cantidad"])
    return list(lineas.values())


def _cliente_manual(datos: dict):
    cliente_id = datos.get("cliente_id")
    if cliente_id:
        usuario = db.session.get(Usuario, cliente_id)
        if usuario is None:
            raise ApiError("CLIENTE_NO_ENCONTRADO", "Cliente no encontrado", 404)
        if usuario.rol.codigo != "CLIENTE":
            raise ApiError("CLIENTE_INVALIDO", "El usuario no es un cliente", 422)
        return usuario

    nuevo = datos.get("cliente")
    if not nuevo:
        raise ApiError(
            "CLIENTE_REQUERIDO", "Se requiere un cliente existente o uno nuevo", 422
        )
    correo = str(nuevo["correo"]).strip().lower()
    if db.session.execute(select(Usuario.id).where(Usuario.correo == correo)).first():
        raise ApiError("CORREO_REGISTRADO", "El correo ya está registrado", 409)
    rol = db.session.execute(select(Rol).where(Rol.codigo == "CLIENTE")).scalars().first()
    usuario = Usuario(
        rol_id=rol.id,
        nombre=nuevo["nombre"].strip(),
        apellidos=nuevo["apellidos"].strip(),
        correo=correo,
        telefono=nuevo["telefono"],
        password_hash=None,
        estado_cuenta="SIN_ACCESO",
        intentos_fallidos=0,
        acepta_promociones=False,
    )
    db.session.add(usuario)
    db.session.flush()
    return usuario


def _resultado_pago_manual(metodo: str, datos: dict, referencia: str, pagar: bool):
    medio = None
    if datos.get("medio_pago_id"):
        medio = db.session.execute(
            select(MedioPago).where(
                MedioPago.id == datos["medio_pago_id"],
                MedioPago.usuario_id == datos.get("_usuario_id"),
            )
        ).scalars().first()
    if not pagar:
        return {
            "aprobado": False,
            "metodo": metodo,
            "medio_pago_id": medio.id if medio else None,
            "ultimos4": medio.ultimos4 if medio else None,
            "titular": medio.titular if medio else datos.get("titular"),
            "referencia": referencia,
        }
    if metodo in ("TARJETA", "CUENTA"):
        resultado = pago_service.simular(
            datos["_total"],
            metodo,
            medio_pago=medio,
            numero_tarjeta=datos.get("numero_tarjeta"),
            titular=datos.get("titular"),
            vence_mes=datos.get("vence_mes"),
            vence_anio=datos.get("vence_anio"),
            cvv=datos.get("cvv"),
            referencia=referencia,
        )
        if not resultado["aprobado"]:
            raise ApiError(
                "PAGO_RECHAZADO",
                "El pago fue rechazado",
                422,
                [{"motivo": resultado["motivo"]}],
            )
        return resultado
    return {
        "aprobado": True,
        "metodo": metodo,
        "medio_pago_id": None,
        "ultimos4": None,
        "titular": datos.get("titular"),
        "referencia": referencia,
    }


def crear_manual(datos: dict, usuario_id: int, ip=None) -> dict:
    try:
        cliente = _cliente_manual(datos)
        datos["_usuario_id"] = cliente.id
        lineas = _lineas_manuales(datos["lineas"])
        resumen_datos = checkout_service.resumen_lineas(cliente.id, lineas, datos)
        datos["_total"] = resumen_datos["total"]
        metodo = datos["metodo_pago"]
        if metodo not in METODOS_MANUALES:
            raise ApiError("METODO_PAGO_INVALIDO", "Método de pago no válido", 422)
        pagar = datos.get("estado_pago", "PAGADA") == "PAGADA"
        referencia = f"MAN-{secrets.token_hex(5).upper()}"
        resultado = _resultado_pago_manual(metodo, datos, referencia, pagar)

        stocks = stock_service.bloquear([linea["variante_id"] for linea in lineas])
        venta = checkout_service.crear_venta_y_lineas(
            cliente.id,
            datos,
            resumen_datos,
            lineas,
            referencia,
            resultado,
            canal="MANUAL",
            estado_pago="PAGADA" if pagar else "PENDIENTE",
            creada_por=usuario_id,
            registrar_pago=False,
        )
        db.session.add(
            Pago(
                venta_id=venta.id,
                tipo="COBRO",
                metodo=metodo,
                estado="APROBADO" if pagar else "PENDIENTE",
                medio_pago_id=resultado.get("medio_pago_id"),
                monto=resumen_datos["total"],
                referencia=referencia,
                ultimos4=resultado.get("ultimos4"),
                titular=resultado.get("titular"),
                registrado_por=usuario_id,
            )
        )
        pedido, variantes = checkout_service.crear_pedido(
            cliente.id, datos, resumen_datos, lineas, venta, stocks, pago_aprobado=pagar
        )
        if not pagar:
            alertas_service.abrir(
                "PAGO_PENDIENTE",
                "PREVENTIVA",
                "Venta manual con pago pendiente",
                f"La venta {venta.folio} tiene un cobro pendiente de validar.",
                "venta",
                venta.id,
                rol_destino="ADMIN",
                clave_unica=f"PAGO_PENDIENTE:{venta.id}",
                accion_sugerida="Validar el pago de la venta",
            )
        if resumen_datos["descuento"]:
            descuento = db.session.get(
                Descuento, resumen_datos["descuento"]["descuento_id"]
            )
            descuento.usos_actuales += 1
        alertas_service.evaluar_variantes(variantes)
        registrar_bitacora(
            usuario_id,
            "VENTA_MANUAL_CREADA",
            "venta",
            venta.id,
            {"folio": venta.folio, "pedido_id": pedido.id, "pago": venta.estado_pago},
            ip,
        )
        db.session.commit()
        return detalle(venta.id)
    except Exception:
        db.session.rollback()
        raise


def validar_pago(venta_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    venta = _obtener(venta_id)
    if venta.estado == "CANCELADA":
        raise ApiError("VENTA_CANCELADA", "La venta está cancelada", 409)
    if venta.estado_pago == "PAGADA":
        raise ApiError("PAGO_YA_APROBADO", "La venta ya está pagada", 409)
    pedido = _pedido(venta.id)
    if pedido is None:
        raise ApiError("PEDIDO_NO_ENCONTRADO", "La venta no tiene pedido", 409)

    pendiente = db.session.execute(
        select(Pago).where(
            Pago.venta_id == venta.id,
            Pago.tipo == "COBRO",
            Pago.estado == "PENDIENTE",
        )
    ).scalars().first()
    accion = datos.get("accion", "APROBAR")
    if accion == "RECHAZAR":
        if pendiente is not None:
            pendiente.estado = "RECHAZADO"
            pendiente.motivo_rechazo = datos.get("motivo")
            pendiente.registrado_por = usuario_id
        pedido_service.activar_pago(pedido, usuario_id, aprobado=False)
        registrar_bitacora(
            usuario_id,
            "PAGO_RECHAZADO",
            "venta",
            venta.id,
            {"folio": venta.folio, "motivo": datos.get("motivo")},
            ip,
        )
        db.session.commit()
        return detalle(venta.id)

    metodo = datos.get("metodo_pago") or (pendiente.metodo if pendiente else "TRANSFERENCIA")
    if metodo not in METODOS_MANUALES:
        raise ApiError("METODO_PAGO_INVALIDO", "Método de pago no válido", 422)
    total = decimal_valor(venta.total)
    referencia = (pendiente.referencia if pendiente else None) or f"PG-{secrets.token_hex(5).upper()}"
    medio = None
    if datos.get("medio_pago_id"):
        medio = db.session.get(MedioPago, datos["medio_pago_id"])
        if medio is None or medio.usuario_id != venta.usuario_id:
            raise ApiError("MEDIO_PAGO_INVALIDO", "El medio de pago no es del cliente", 422)
    if metodo in ("TARJETA", "CUENTA"):
        resultado = pago_service.simular(
            total,
            metodo,
            medio_pago=medio,
            numero_tarjeta=datos.get("numero_tarjeta"),
            titular=datos.get("titular"),
            vence_mes=datos.get("vence_mes"),
            vence_anio=datos.get("vence_anio"),
            cvv=datos.get("cvv"),
            referencia=referencia,
        )
        if not resultado["aprobado"]:
            raise ApiError(
                "PAGO_RECHAZADO",
                "El pago fue rechazado",
                422,
                [{"motivo": resultado["motivo"]}],
            )
        ultimos4 = resultado.get("ultimos4")
        titular = resultado.get("titular")
        medio_pago_id = resultado.get("medio_pago_id")
    else:
        ultimos4 = None
        titular = datos.get("titular")
        medio_pago_id = None

    if pendiente is None:
        db.session.add(
            Pago(
                venta_id=venta.id,
                tipo="COBRO",
                metodo=metodo,
                estado="APROBADO",
                medio_pago_id=medio_pago_id,
                monto=total,
                referencia=referencia,
                ultimos4=ultimos4,
                titular=titular,
                registrado_por=usuario_id,
            )
        )
    else:
        pendiente.estado = "APROBADO"
        pendiente.metodo = metodo
        pendiente.monto = total
        pendiente.referencia = referencia
        pendiente.ultimos4 = ultimos4
        pendiente.titular = titular
        pendiente.medio_pago_id = medio_pago_id
        pendiente.registrado_por = usuario_id
    venta.estado_pago = "PAGADA"
    pedido_service.activar_pago(pedido, usuario_id, aprobado=True)
    alertas_service.cerrar(f"PAGO_PENDIENTE:{venta.id}")
    registrar_bitacora(
        usuario_id,
        "PAGO_APROBADO",
        "venta",
        venta.id,
        {"folio": venta.folio, "metodo": metodo},
        ip,
    )
    db.session.commit()
    return detalle(venta.id)


def reembolsar(
    venta_id: int, datos: dict, usuario_id: int, ip=None, confirmar: bool = True
) -> Pago:
    venta = _obtener(venta_id)
    cobro = db.session.execute(
        select(Pago).where(
            Pago.venta_id == venta.id,
            Pago.tipo == "COBRO",
            Pago.estado == "APROBADO",
        )
    ).scalars().first()
    if cobro is None:
        raise ApiError("COBRO_NO_ENCONTRADO", "La venta no tiene un cobro aprobado", 422)
    total = decimal_valor(venta.total)
    ya_reembolsado = decimal_valor(
        db.session.scalar(
            select(func.coalesce(func.sum(Pago.monto), 0)).where(
                Pago.venta_id == venta.id,
                Pago.tipo == "REEMBOLSO",
                Pago.estado == "APROBADO",
            )
        )
    )
    restante = max(Decimal("0"), total - ya_reembolsado)
    monto = redondear(datos["monto"]) if datos.get("monto") is not None else restante
    if monto <= 0 or monto > restante:
        raise ApiError(
            "MONTO_REEMBOLSO_INVALIDO",
            "El monto a reembolsar excede el saldo pendiente de la venta",
            422,
        )
    reembolso = Pago(
        venta_id=venta.id,
        tipo="REEMBOLSO",
        metodo=cobro.metodo,
        estado="APROBADO",
        medio_pago_id=cobro.medio_pago_id,
        monto=monto,
        referencia=f"RE-{secrets.token_hex(5).upper()}",
        ultimos4=cobro.ultimos4,
        titular=cobro.titular,
        registrado_por=usuario_id,
    )
    db.session.add(reembolso)
    if cobro.metodo == "CUENTA" and cobro.medio_pago_id:
        medio = db.session.get(MedioPago, cobro.medio_pago_id)
        if medio is not None:
            medio.saldo_simulado = decimal_valor(medio.saldo_simulado) + monto
    total_reembolsado = ya_reembolsado + monto
    venta.estado_pago = (
        "REEMBOLSADA" if total_reembolsado >= total else "REEMBOLSADA_PARCIAL"
    )
    registrar_bitacora(
        usuario_id,
        "REEMBOLSO_REGISTRADO",
        "venta",
        venta.id,
        {"folio": venta.folio, "monto": dinero(monto), "motivo": datos.get("motivo")},
        ip,
    )
    if confirmar:
        db.session.commit()
    return reembolso


def cancelar(venta_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    venta = _obtener(venta_id)
    if venta.estado == "CANCELADA":
        raise ApiError("VENTA_YA_CANCELADA", "La venta ya está cancelada", 409)
    motivo = datos["motivo"]
    pedido = _pedido(venta.id)
    if pedido is not None:
        pedido_service.cancelar_admin(pedido.id, usuario_id, motivo, ip=ip)
    else:
        venta.estado = "CANCELADA"
        venta.cancelada_en = _ahora()
        venta.motivo_cancelacion = motivo
        if venta.estado_pago == "PAGADA":
            reembolsar(
                venta.id,
                {"monto": venta.total, "motivo": motivo},
                usuario_id,
                ip=ip,
            )
        registrar_bitacora(
            usuario_id,
            "VENTA_CANCELADA",
            "venta",
            venta.id,
            {"folio": venta.folio, "motivo": motivo},
            ip,
        )
        db.session.commit()
    return detalle(venta.id)


def _descuento_json(descuento: Descuento) -> dict:
    return {
        "id": descuento.id,
        "codigo": descuento.codigo,
        "nombre": descuento.nombre,
        "tipo": descuento.tipo,
        "valor": dinero(descuento.valor),
        "aplicacion": descuento.aplicacion,
        "solo_primera_compra": bool(descuento.solo_primera_compra),
        "monto_minimo": (
            dinero(descuento.monto_minimo) if descuento.monto_minimo is not None else None
        ),
        "min_articulos": descuento.min_articulos,
        "vigente_desde": _fecha_texto(descuento.vigente_desde),
        "vigente_hasta": _fecha_texto(descuento.vigente_hasta),
        "usos_maximos": descuento.usos_maximos,
        "usos_por_cliente": descuento.usos_por_cliente,
        "usos_actuales": descuento.usos_actuales,
        "activo": bool(descuento.activo),
    }


def _validar_descuento(datos: dict, descuento_id=None) -> None:
    codigo = datos.get("codigo")
    if codigo:
        consulta = select(Descuento.id).where(Descuento.codigo == codigo)
        if descuento_id is not None:
            consulta = consulta.where(Descuento.id != descuento_id)
        if db.session.execute(consulta).first():
            raise ApiError("CODIGO_DUPLICADO", "El código de descuento ya existe", 409)
    tipo = datos.get("tipo")
    valor = decimal_valor(datos.get("valor"))
    if valor < 0 or (tipo == "PORCENTAJE" and valor > 100):
        raise ApiError("VALOR_DESCUENTO_INVALIDO", "El valor del descuento no es válido", 422)
    desde = datos.get("vigente_desde")
    hasta = datos.get("vigente_hasta")
    if desde and hasta and hasta < desde:
        raise ApiError("VIGENCIA_INVALIDA", "La vigencia termina antes de iniciar", 422)
    if datos.get("usos_maximos") is not None and int(datos["usos_maximos"]) < 0:
        raise ApiError("USOS_INVALIDOS", "Los usos máximos no pueden ser negativos", 422)
    if datos.get("usos_por_cliente") is not None and int(datos["usos_por_cliente"]) < 1:
        raise ApiError("USOS_INVALIDOS", "Los usos por cliente deben ser al menos uno", 422)


CAMPOS_DESCUENTO = (
    "codigo",
    "nombre",
    "tipo",
    "valor",
    "aplicacion",
    "solo_primera_compra",
    "monto_minimo",
    "min_articulos",
    "vigente_desde",
    "vigente_hasta",
    "usos_maximos",
    "usos_por_cliente",
    "activo",
)


def obtener_descuento(descuento_id: int) -> Descuento:
    descuento = db.session.get(Descuento, descuento_id)
    if descuento is None:
        raise ApiError("DESCUENTO_NO_ENCONTRADO", "Descuento no encontrado", 404)
    return descuento


def listar_descuentos(filtros=None, pagina=1, por_pagina=20) -> dict:
    filtros = filtros or {}
    consulta = select(Descuento)
    if "activo" in filtros and filtros["activo"] is not None:
        consulta = consulta.where(Descuento.activo == filtros["activo"])
    if filtros.get("aplicacion"):
        consulta = consulta.where(Descuento.aplicacion == filtros["aplicacion"])
    if filtros.get("q"):
        patron = f"%{filtros['q']}%"
        consulta = consulta.where(
            or_(Descuento.nombre.like(patron), Descuento.codigo.like(patron))
        )
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.session.execute(
        consulta.order_by(Descuento.id)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars().all()
    return {
        "items": [_descuento_json(fila) for fila in filas],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def crear_descuento(datos: dict, usuario_id: int, ip=None) -> dict:
    _validar_descuento(datos)
    descuento = Descuento(**{campo: datos[campo] for campo in CAMPOS_DESCUENTO if campo in datos})
    db.session.add(descuento)
    db.session.flush()
    registrar_bitacora(
        usuario_id,
        "DESCUENTO_CREADO",
        "descuento",
        descuento.id,
        {"codigo": descuento.codigo, "nombre": descuento.nombre},
        ip,
    )
    db.session.commit()
    return _descuento_json(descuento)


def actualizar_descuento(descuento_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    descuento = obtener_descuento(descuento_id)
    fusion = _descuento_json(descuento)
    fusion.update(datos)
    _validar_descuento(fusion, descuento_id)
    cambios = {}
    for campo in CAMPOS_DESCUENTO:
        if campo in datos:
            setattr(descuento, campo, datos[campo])
            cambios[campo] = datos[campo]
    if not cambios:
        raise ApiError("VALIDACION", "Se requiere al menos un campo", 400)
    registrar_bitacora(
        usuario_id, "DESCUENTO_ACTUALIZADO", "descuento", descuento.id, cambios, ip
    )
    db.session.commit()
    return _descuento_json(descuento)


def desactivar_descuento(descuento_id: int, usuario_id: int, ip=None) -> None:
    descuento = obtener_descuento(descuento_id)
    if descuento.usos_actuales > 0:
        descuento.activo = False
    else:
        db.session.delete(descuento)
    registrar_bitacora(
        usuario_id,
        "DESCUENTO_ELIMINADO",
        "descuento",
        descuento_id,
        {"codigo": descuento.codigo},
        ip,
    )
    db.session.commit()
