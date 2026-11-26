"""Endpoints de la cuenta del usuario autenticado (M02)."""

from flask import Blueprint, jsonify, request

from app.schemas import (
    CambiarContrasenaSchema,
    CoberturaSchema,
    CuentaActualizarSchema,
    DireccionActualizarSchema,
    DireccionCrearSchema,
    DireccionSchema,
    MedioPagoActualizarSchema,
    MedioPagoCrearSchema,
    MedioPagoSchema,
    UsuarioSchema,
)
from app.security import autenticacion_requerida, roles_requeridos, usuario_actual
from app.services import (
    cuenta_service,
    direccion_service,
    envio_service,
    medio_pago_service,
)
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


@cuenta_bp.patch("/cuenta/desactivar")
@autenticacion_requerida
def desactivar_cuenta():
    cuenta_service.desactivar_cuenta(ip=request.remote_addr)
    return jsonify({"mensaje": "Cuenta desactivada"})


@cuenta_bp.patch("/cuenta/contrasena")
@autenticacion_requerida
def cambiar_contrasena():
    datos = cuerpo(CambiarContrasenaSchema())
    cuenta_service.cambiar_contrasena(
        datos["contrasena_actual"], datos["contrasena_nueva"], ip=request.remote_addr
    )
    return jsonify({"mensaje": "Contraseña actualizada"})


@cuenta_bp.get("/cuenta/direcciones")
@roles_requeridos("CLIENTE")
def listar_direcciones():
    items = direccion_service.listar(usuario_actual().id)
    return jsonify(DireccionSchema(many=True).dump(items))


@cuenta_bp.post("/cuenta/direcciones")
@roles_requeridos("CLIENTE")
def crear_direccion():
    datos = cuerpo(DireccionCrearSchema())
    direccion = direccion_service.crear(usuario_actual().id, datos)
    return jsonify(DireccionSchema().dump(direccion)), 201


@cuenta_bp.patch("/cuenta/direcciones/<int:direccion_id>")
@roles_requeridos("CLIENTE")
def actualizar_direccion(direccion_id):
    datos = cuerpo(DireccionActualizarSchema(), parcial=True)
    direccion = direccion_service.actualizar(
        usuario_actual().id, direccion_id, datos
    )
    return jsonify(DireccionSchema().dump(direccion))


@cuenta_bp.delete("/cuenta/direcciones/<int:direccion_id>")
@roles_requeridos("CLIENTE")
def eliminar_direccion(direccion_id):
    direccion_service.desactivar(usuario_actual().id, direccion_id)
    return "", 204


@cuenta_bp.get("/cuenta/medios-pago")
@roles_requeridos("CLIENTE")
def listar_medios_pago():
    medios = medio_pago_service.listar(usuario_actual().id)
    return jsonify(MedioPagoSchema(many=True).dump(medios))


@cuenta_bp.post("/cuenta/medios-pago")
@roles_requeridos("CLIENTE")
def crear_medio_pago():
    datos = cuerpo(MedioPagoCrearSchema())
    medio = medio_pago_service.crear(usuario_actual().id, datos)
    return jsonify(MedioPagoSchema().dump(medio)), 201


@cuenta_bp.patch("/cuenta/medios-pago/<int:medio_id>")
@roles_requeridos("CLIENTE")
def actualizar_medio_pago(medio_id):
    datos = cuerpo(MedioPagoActualizarSchema())
    medio = medio_pago_service.actualizar(
        usuario_actual().id, medio_id, datos["alias"]
    )
    return jsonify(MedioPagoSchema().dump(medio))


@cuenta_bp.delete("/cuenta/medios-pago/<int:medio_id>")
@roles_requeridos("CLIENTE")
def eliminar_medio_pago(medio_id):
    medio_pago_service.desactivar(usuario_actual().id, medio_id)
    return "", 204


@cuenta_bp.get("/envio/cobertura")
def cobertura_envio():
    codigo_postal = request.args.get("cp", "")
    resultado = envio_service.cobertura(codigo_postal)
    return jsonify(CoberturaSchema().dump(resultado))
