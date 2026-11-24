"""Persistencia y comprobación de claves idempotentes."""

import hashlib
import json

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import IdempotenciaOperacion
from app.utils.errores import ApiError


def hash_peticion(payload: dict) -> str:
    canonico = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def iniciar(clave: str, alcance: str, peticion: dict):
    """Devuelve ``(registro, respuesta_previa)``.

    La respuesta previa existe solo cuando la misma clave y el mismo cuerpo ya fueron
    completados. Cualquier otro estado se considera conflicto.
    """
    if not clave or len(clave) > 255:
        raise ApiError("IDEMPOTENCIA_INVALIDA", "Idempotency-Key inválida", 400)
    huella = hash_peticion(peticion)
    registro = db.session.get(IdempotenciaOperacion, clave, with_for_update=True)

    if registro is None:
        registro = IdempotenciaOperacion(
            clave=clave,
            alcance=alcance,
            hash_peticion=huella,
            estado="PENDIENTE",
        )
        try:
            with db.session.begin_nested():
                db.session.add(registro)
        except IntegrityError:
            registro = db.session.get(
                IdempotenciaOperacion, clave, with_for_update=True
            )
        else:
            db.session.flush()
            return registro, None

    if registro.alcance != alcance or registro.hash_peticion != huella:
        raise ApiError(
            "IDEMPOTENCIA_CONFLICTO",
            "La clave idempotente ya fue usada con otra petición",
            409,
        )
    if registro.estado == "COMPLETADA":
        return registro, registro.respuesta
    if registro.estado == "ERROR":
        error = registro.respuesta or {}
        raise ApiError(
            error.get("codigo", "ERROR_OPERACION"),
            error.get("mensaje", "La operación fue rechazada"),
            error.get("status_code", 409),
        )
    raise ApiError(
        "IDEMPOTENCIA_EN_CURSO",
        "La operación con esta clave está en proceso",
        409,
    )


def completar(registro: IdempotenciaOperacion, respuesta: dict) -> None:
    registro.estado = "COMPLETADA"
    registro.respuesta = respuesta
    db.session.flush()


def registrar_error(clave: str, alcance: str, peticion: dict, respuesta: dict) -> None:
    """Guarda una respuesta de error sin participar en la transacción fallida."""
    huella = hash_peticion(peticion)
    registro = IdempotenciaOperacion(
        clave=clave,
        alcance=alcance,
        hash_peticion=huella,
        estado="ERROR",
        respuesta={
            "codigo": respuesta.get("codigo", "ERROR_OPERACION"),
            "mensaje": respuesta.get("mensaje", "La operación fue rechazada"),
            "detalle": respuesta.get("detalle", []),
            "status_code": respuesta.get("status_code", 409),
        },
    )
    db.session.merge(registro)
    db.session.commit()
