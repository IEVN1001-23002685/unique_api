"""Cobertura y tarifas de envío por código postal (M05)."""

import re
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models import TarifaEnvio
from app.utils.errores import ApiError


def codigo_valido(codigo_postal: str) -> bool:
    return bool(codigo_postal and re.fullmatch(r"\d{5}", str(codigo_postal)))


def tarifa_por_cp(codigo_postal: str) -> TarifaEnvio | None:
    if not codigo_valido(codigo_postal):
        return None
    return db.session.execute(
        select(TarifaEnvio)
        .where(
            TarifaEnvio.activa.is_(True),
            TarifaEnvio.cp_inicio <= codigo_postal,
            TarifaEnvio.cp_fin >= codigo_postal,
        )
        .order_by(TarifaEnvio.cp_inicio.desc(), TarifaEnvio.id.desc())
    ).scalars().first()


def calcular_envio(codigo_postal: str) -> tuple[TarifaEnvio, Decimal]:
    tarifa = tarifa_por_cp(codigo_postal)
    if tarifa is None:
        raise ApiError(
            "SIN_COBERTURA",
            "No hay cobertura de envío para el código postal proporcionado",
            422,
        )
    return tarifa, Decimal(str(tarifa.costo)).quantize(Decimal("0.01"))


def detalle_tarifa(tarifa: TarifaEnvio) -> dict:
    return {
        "id": tarifa.id,
        "nombre": tarifa.nombre,
        "cp_inicio": tarifa.cp_inicio,
        "cp_fin": tarifa.cp_fin,
        "costo": f"{Decimal(str(tarifa.costo)):.2f}",
        "dias_estimados": tarifa.dias_estimados,
    }


def cobertura(codigo_postal: str) -> dict:
    if not codigo_valido(codigo_postal):
        raise ApiError("CODIGO_POSTAL_INVALIDO", "El código postal debe tener 5 dígitos", 400)
    tarifa = tarifa_por_cp(codigo_postal)
    if tarifa is None:
        return {
            "codigo_postal": codigo_postal,
            "cobertura": False,
            "tarifa": None,
            "costo": None,
            "dias_estimados": None,
        }
    return {
        "codigo_postal": codigo_postal,
        "cobertura": True,
        "tarifa": detalle_tarifa(tarifa),
        "costo": f"{Decimal(str(tarifa.costo)):.2f}",
        "dias_estimados": tarifa.dias_estimados,
    }


def rangos_solapados(cp_inicio: str, cp_fin: str, excluir_id=None) -> bool:
    if not codigo_valido(cp_inicio) or not codigo_valido(cp_fin) or cp_inicio > cp_fin:
        raise ApiError("RANGO_CP_INVALIDO", "El rango de códigos postales no es válido", 400)
    consulta = select(TarifaEnvio.id).where(
        TarifaEnvio.cp_inicio <= cp_fin, TarifaEnvio.cp_fin >= cp_inicio
    )
    if excluir_id is not None:
        consulta = consulta.where(TarifaEnvio.id != excluir_id)
    return db.session.execute(consulta.limit(1)).first() is not None


def hoy():
    return datetime.now(timezone.utc).date()
