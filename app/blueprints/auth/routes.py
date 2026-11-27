"""Endpoints públicos y de sesión del módulo M01."""

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import set_refresh_cookies, unset_jwt_cookies

from app.extensions import limiter
from app.schemas import LoginSchema, RecuperarSchema, RegistroSchema, RestablecerSchema
from app.schemas.auth import UsuarioSchema
from app.security import autenticacion_requerida, usuario_actual
from app.services import auth_service
from app.utils.errores import ApiError
from app.utils.validacion import cuerpo

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def _clave_correo():
    datos = request.get_json(silent=True) or {}
    return str(datos.get("correo", "sin-correo")).strip().lower()


def _cookie_refresco():
    nombre = current_app.config.get("JWT_REFRESH_COOKIE_NAME", "refresh_token")
    return request.cookies.get(nombre)


def _valor_csrf():
    """Doble envío para las rutas que leen la cookie de refresco manualmente."""
    if not current_app.config.get("JWT_COOKIE_CSRF_PROTECT", True):
        return None
    nombre = current_app.config.get("JWT_REFRESH_CSRF_HEADER_NAME", "X-CSRF-TOKEN")
    valor = request.headers.get(nombre)
    if not valor:
        raise ApiError("CSRF_INVALIDO", "Falta la cabecera de protección CSRF", 401)
    return valor


@auth_bp.post("/registro")
@limiter.limit("5 per minute")
def registro():
    datos = cuerpo(RegistroSchema())
    usuario, access, refresh = auth_service.registrar_cliente(
        datos, ip=request.remote_addr
    )
    respuesta = jsonify({"access_token": access, "usuario": UsuarioSchema().dump(usuario)})
    set_refresh_cookies(respuesta, refresh)
    return respuesta, 201


@auth_bp.post("/login")
@limiter.limit("5 per minute")
@limiter.limit("5 per minute", key_func=_clave_correo)
def login():
    datos = cuerpo(LoginSchema())
    usuario, access, refresh = auth_service.autenticar(
        datos["correo"], datos["password"], ip=request.remote_addr
    )
    respuesta = jsonify({"access_token": access, "usuario": UsuarioSchema().dump(usuario)})
    set_refresh_cookies(respuesta, refresh)
    return respuesta


@auth_bp.post("/refrescar")
@limiter.limit("20 per minute")
def refrescar():
    token = _cookie_refresco()
    if not token:
        raise ApiError("SESION_INVALIDA", "No hay cookie de refresco", 401)
    usuario, access, refresh = auth_service.refrescar(
        token, ip=request.remote_addr, csrf_value=_valor_csrf()
    )
    respuesta = jsonify({"access_token": access, "usuario": UsuarioSchema().dump(usuario)})
    set_refresh_cookies(respuesta, refresh)
    return respuesta


@auth_bp.post("/logout")
@autenticacion_requerida
def logout():
    token = _cookie_refresco()
    if token:
        _valor_csrf()
    auth_service.cerrar_sesion(token, usuario_actual().id, ip=request.remote_addr)
    respuesta = jsonify({"mensaje": "Sesión cerrada"})
    unset_jwt_cookies(respuesta)
    return respuesta


@auth_bp.post("/recuperar")
@limiter.limit("5 per minute")
@limiter.limit("5 per minute", key_func=_clave_correo)
def recuperar():
    datos = cuerpo(RecuperarSchema())
    auth_service.solicitar_recuperacion(datos["correo"], ip=request.remote_addr)
    return jsonify(
        {"mensaje": "Si el correo está registrado, se generó una instrucción de recuperación"}
    )


@auth_bp.post("/restablecer")
@limiter.limit("10 per minute")
def restablecer():
    datos = cuerpo(RestablecerSchema())
    auth_service.restablecer_contrasena(
        datos["token"], datos["password"], ip=request.remote_addr
    )
    return jsonify({"mensaje": "Contraseña actualizada"})
