"""Registro de acciones sensibles en bitácora."""

from app.extensions import db
from app.models import Bitacora


def registrar_bitacora(usuario_id, accion, entidad, entidad_id=None, detalle=None, ip=None):
    db.session.add(
        Bitacora(
            usuario_id=usuario_id,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            detalle=detalle or {},
            ip=ip,
            fecha=db.func.current_timestamp(),
        )
    )
