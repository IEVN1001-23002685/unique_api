"""Obtención del usuario autenticado y decoradores de autorización."""

from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt_identity, jwt_required, verify_jwt_in_request

from app.extensions import db
from app.models import Usuario
from app.utils.errores import ApiError


def usuario_actual() -> Usuario:
    usuario = getattr(g, "usuario_actual", None)
    if usuario is None:
        raise ApiError("NO_AUTENTICADO", "Se requiere una sesión válida", 401)
    return usuario


def cargar_usuario_actual() -> Usuario:
    verify_jwt_in_request()
    identidad = get_jwt_identity()
    try:
        usuario_id = int(identidad)
    except (TypeError, ValueError):
        raise ApiError("NO_AUTENTICADO", "Sesión inválida", 401)
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None or usuario.estado_cuenta != "ACTIVA":
        raise ApiError("NO_AUTENTICADO", "Sesión inválida", 401)
    g.usuario_actual = usuario
    return usuario


def autenticacion_requerida(funcion):
    """Exige un access token válido sin imponer un rol específico."""

    @wraps(funcion)
    @jwt_required()
    def envoltura(*args, **kwargs):
        cargar_usuario_actual()
        return funcion(*args, **kwargs)

    return envoltura


def tiene_rol(rol: str) -> bool:
    """Comprueba un rol con herencia de ADMIN sobre OPERATIVO."""
    codigo = usuario_actual().rol.codigo
    return codigo == rol or (codigo == "ADMIN" and rol == "OPERATIVO")


def roles_requeridos(*roles: str):
    def decorador(funcion):
        @wraps(funcion)
        @jwt_required()
        def envoltura(*args, **kwargs):
            cargar_usuario_actual()
            usuario = usuario_actual()
            permitidos = set(roles)
            if usuario.rol.codigo == "ADMIN" and "OPERATIVO" in permitidos:
                permitidos.add("ADMIN")
            if usuario.rol.codigo not in permitidos:
                raise ApiError("PERMISO_INSUFICIENTE", "No tiene permiso para esta operación", 403)
            return funcion(*args, **kwargs)

        return envoltura

    return decorador
