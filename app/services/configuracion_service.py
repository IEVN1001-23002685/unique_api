"""Lectura y escritura de parámetros de configuración del sistema."""

from sqlalchemy import select

from app.extensions import db
from app.models import Bitacora, Configuracion
from app.utils.errores import ApiError


def listar_configuracion():
    filas = db.session.execute(select(Configuracion).order_by(Configuracion.clave)).scalars()
    return list(filas)


def obtener_configuracion(clave: str) -> Configuracion:
    fila = db.session.get(Configuracion, clave)
    if fila is None:
        raise ApiError("CONFIGURACION_NO_ENCONTRADA", "Parámetro no encontrado", 404)
    return fila


def actualizar_configuracion(clave: str, valor: str, usuario_id, ip=None, commit=True) -> Configuracion:
    fila = obtener_configuracion(clave)
    anterior = fila.valor
    fila.valor = valor
    db.session.add(
        Bitacora(
            usuario_id=usuario_id,
            accion="CONFIGURACION_ACTUALIZADA",
            entidad="configuracion",
            entidad_id=None,
            detalle={"clave": clave, "anterior": anterior, "nuevo": valor},
            ip=ip,
        )
    )
    if commit:
        db.session.commit()
    return fila
