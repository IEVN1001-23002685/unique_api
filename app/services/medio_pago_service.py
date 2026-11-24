"""Casos de uso de medios de pago simulados (M02)."""

import secrets
from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models import MedioPago
from app.services import configuracion_service, pago_service
from app.utils.errores import ApiError


def listar(usuario_id: int) -> list:
    return db.session.execute(
        select(MedioPago)
        .where(MedioPago.usuario_id == usuario_id, MedioPago.activo.is_(True))
        .order_by(MedioPago.id)
    ).scalars().all()


def obtener(usuario_id: int, medio_id: int) -> MedioPago:
    medio = db.session.get(MedioPago, medio_id)
    if (
        medio is None
        or medio.usuario_id != usuario_id
        or not medio.activo
    ):
        raise ApiError("MEDIO_PAGO_NO_ENCONTRADO", "Medio de pago no encontrado", 404)
    return medio


def crear(usuario_id: int, datos: dict) -> MedioPago:
    tipo = datos["tipo"]
    if tipo == "TARJETA":
        numero = datos.get("numero_tarjeta")
        if not numero:
            raise ApiError(
                "TARJETA_REQUERIDA", "Se requiere el número de tarjeta", 422
            )
        pago_service.validar_datos_tarjeta(
            numero, datos.get("vence_mes"), datos.get("vence_anio"), datos.get("cvv")
        )
        if numero[-4:] == "0000":
            raise ApiError("TARJETA_RECHAZADA", "La tarjeta no puede ser registrada", 422)
        ultimos4 = numero[-4:]
        marca = pago_service.marca_tarjeta(numero)
        saldo = None
    else:
        ultimos4 = secrets.token_hex(2).upper()
        marca = "CUENTA_SIMULADA"
        saldo = datos.get("saldo_inicial")
        if saldo is None:
            saldo = configuracion_service.valor_decimal(
                "saldo_inicial_cuenta_simulada", Decimal("5000")
            )
        saldo = Decimal(str(saldo)).quantize(Decimal("0.01"))
        if saldo < 0:
            raise ApiError("SALDO_INVALIDO", "El saldo inicial no puede ser negativo", 422)

    medio = MedioPago(
        usuario_id=usuario_id,
        tipo=tipo,
        alias=datos["alias"],
        titular=datos["titular"],
        ultimos4=ultimos4,
        marca=marca,
        vence_mes=datos.get("vence_mes") if tipo == "TARJETA" else None,
        vence_anio=datos.get("vence_anio") if tipo == "TARJETA" else None,
        saldo_simulado=saldo,
        activo=True,
    )
    db.session.add(medio)
    db.session.commit()
    return medio


def actualizar(usuario_id: int, medio_id: int, alias: str) -> MedioPago:
    medio = obtener(usuario_id, medio_id)
    medio.alias = alias
    db.session.commit()
    return medio


def desactivar(usuario_id: int, medio_id: int) -> None:
    medio = obtener(usuario_id, medio_id)
    medio.activo = False
    db.session.commit()
