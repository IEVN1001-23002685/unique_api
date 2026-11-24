"""Casos de uso de direcciones de la cuenta (M02)."""

from sqlalchemy import select

from app.extensions import db
from app.models import Direccion
from app.services import envio_service
from app.utils.errores import ApiError

CAMPOS = (
    "tipo",
    "alias",
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
    "rfc",
    "razon_social",
    "predeterminada",
)


def _serializar(direccion: Direccion) -> dict:
    resultado = {campo: getattr(direccion, campo) for campo in CAMPOS}
    resultado["id"] = direccion.id
    resultado["activa"] = direccion.activa
    resultado["cobertura"] = envio_service.cobertura(direccion.codigo_postal)
    return resultado


def listar(usuario_id: int) -> list:
    filas = db.session.execute(
        select(Direccion)
        .where(Direccion.usuario_id == usuario_id, Direccion.activa.is_(True))
        .order_by(Direccion.predeterminada.desc(), Direccion.id)
    ).scalars().all()
    return [_serializar(fila) for fila in filas]


def obtener(usuario_id: int, direccion_id: int) -> Direccion:
    direccion = db.session.get(Direccion, direccion_id)
    if (
        direccion is None
        or direccion.usuario_id != usuario_id
        or not direccion.activa
    ):
        raise ApiError("DIRECCION_NO_ENCONTRADA", "Dirección no encontrada", 404)
    return direccion


def _quitar_predeterminada(usuario_id: int, tipo: str) -> None:
    filas = db.session.execute(
        select(Direccion).where(
            Direccion.usuario_id == usuario_id,
            Direccion.tipo == tipo,
            Direccion.predeterminada.is_(True),
        )
    ).scalars().all()
    for fila in filas:
        fila.predeterminada = False


def crear(usuario_id: int, datos: dict) -> dict:
    if datos["tipo"] == "FACTURACION" and (
        not datos.get("rfc") or not datos.get("razon_social")
    ):
        raise ApiError(
            "DATOS_FACTURACION_INCOMPLETOS",
            "Se requieren RFC y razón social para una dirección de facturación",
            422,
        )
    if datos.get("predeterminada"):
        _quitar_predeterminada(usuario_id, datos["tipo"])
    direccion = Direccion(usuario_id=usuario_id)
    for campo in CAMPOS:
        setattr(direccion, campo, datos.get(campo))
    db.session.add(direccion)
    db.session.commit()
    return _serializar(direccion)


def actualizar(usuario_id: int, direccion_id: int, datos: dict) -> dict:
    direccion = obtener(usuario_id, direccion_id)
    if datos.get("predeterminada"):
        _quitar_predeterminada(
            usuario_id, datos.get("tipo", direccion.tipo)
        )
    for campo, valor in datos.items():
        if campo in CAMPOS:
            setattr(direccion, campo, valor)
    if direccion.tipo == "FACTURACION" and (
        not direccion.rfc or not direccion.razon_social
    ):
        db.session.rollback()
        raise ApiError(
            "DATOS_FACTURACION_INCOMPLETOS",
            "Se requieren RFC y razón social para una dirección de facturación",
            422,
        )
    db.session.commit()
    return _serializar(direccion)


def desactivar(usuario_id: int, direccion_id: int) -> None:
    direccion = obtener(usuario_id, direccion_id)
    direccion.activa = False
    direccion.predeterminada = False
    db.session.commit()
