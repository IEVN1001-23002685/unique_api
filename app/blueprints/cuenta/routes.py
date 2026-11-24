"""Endpoints de la cuenta del usuario autenticado (M02)."""

from flask import Blueprint, jsonify, request

from app.schemas import CambiarContrasenaSchema, CuentaActualizarSchema, UsuarioSchema
from app.security import autenticacion_requerida
from app.services import cuenta_service
from app.utils.validacion import cuerpo

cuenta_bp = Blueprint("cuenta", __name__, url_prefix="/api/v1")


@cuenta_bp.get("/cuenta")
@autenticacion_requerida
def obtener_cuenta():
    return jsonify(UsuarioSchema().dump(cuenta_service.perfil()))


@cuenta_bp.patch("/cuenta")
@autenticacion_requerida
def actualizar_cuenta():
    datos = cuerpo(CuentaActualizarSchema(), parcial=True)
    usuario = cuenta_service.actualizar_perfil(datos, ip=request.remote_addr)
    return jsonify(UsuarioSchema().dump(usuario))


@cuenta_bp.patch("/cuenta/contrasena")
@autenticacion_requerida
def cambiar_contrasena():
    datos = cuerpo(CambiarContrasenaSchema())
    cuenta_service.cambiar_contrasena(
        datos["contrasena_actual"], datos["contrasena_nueva"], ip=request.remote_addr
    )
    return jsonify({"mensaje": "Contraseña actualizada"})
