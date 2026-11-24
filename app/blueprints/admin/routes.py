"""Endpoints administrativos de usuarios, clientes, bitácora y configuración (M22)."""

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select

from app.extensions import db
from app.models import Bitacora, Rol, Usuario
from app.schemas import (
    BitacoraSchema,
    ConfiguracionSchema,
    UsuarioActualizarSchema,
    UsuarioCrearSchema,
    UsuarioSchema,
)
from app.security import roles_requeridos, usuario_actual
from app.services import configuracion_service, usuario_service
from app.utils.errores import ApiError
from app.utils.paginacion import parametros_paginacion
from app.utils.validacion import cuerpo

admin_bp = Blueprint("admin", __name__, url_prefix="/api/v1")


@admin_bp.get("/usuarios")
@roles_requeridos("ADMIN")
def listar_usuarios():
    pagina, por_pagina = parametros_paginacion()
    resultado = usuario_service.listar_usuarios(pagina, por_pagina)
    resultado["items"] = UsuarioSchema(many=True).dump(resultado["items"])
    return jsonify(resultado)


@admin_bp.post("/usuarios")
@roles_requeridos("ADMIN")
def crear_usuario():
    datos = cuerpo(UsuarioCrearSchema())
    usuario = usuario_service.crear_usuario(
        datos, ip=request.remote_addr, actor_id=usuario_actual().id
    )
    return jsonify(UsuarioSchema().dump(usuario)), 201


@admin_bp.get("/usuarios/<int:usuario_id>")
@roles_requeridos("ADMIN")
def obtener_usuario(usuario_id):
    return jsonify(UsuarioSchema().dump(usuario_service.obtener_usuario(usuario_id)))


@admin_bp.patch("/usuarios/<int:usuario_id>")
@roles_requeridos("ADMIN")
def actualizar_usuario(usuario_id):
    datos = cuerpo(UsuarioActualizarSchema(), parcial=True)
    if not datos:
        raise ApiError("VALIDACION", "Se requiere al menos un campo", 400)
    usuario = usuario_service.actualizar_usuario(
        usuario_id, datos, ip=request.remote_addr, actor_id=usuario_actual().id
    )
    return jsonify(UsuarioSchema().dump(usuario))


@admin_bp.delete("/usuarios/<int:usuario_id>")
@roles_requeridos("ADMIN")
def desactivar_usuario(usuario_id):
    usuario_service.desactivar_usuario(
        usuario_id, ip=request.remote_addr, actor_id=usuario_actual().id
    )
    return "", 204


@admin_bp.get("/clientes")
@roles_requeridos("ADMIN")
def listar_clientes():
    pagina, por_pagina = parametros_paginacion()
    rol_id = db.session.execute(select(Rol.id).where(Rol.codigo == "CLIENTE")).scalar_one()
    total = db.session.scalar(
        select(func.count()).select_from(Usuario).where(Usuario.rol_id == rol_id)
    ) or 0
    filas = db.session.execute(
        select(Usuario)
        .where(Usuario.rol_id == rol_id)
        .order_by(Usuario.id)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars()
    return jsonify(
        {
            "items": UsuarioSchema(many=True).dump(filas),
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
        }
    )


@admin_bp.get("/clientes/<int:cliente_id>")
@roles_requeridos("ADMIN")
def obtener_cliente(cliente_id):
    usuario = usuario_service.obtener_usuario(cliente_id)
    if usuario.rol.codigo != "CLIENTE":
        raise ApiError("CLIENTE_NO_ENCONTRADO", "Cliente no encontrado", 404)
    return jsonify(UsuarioSchema().dump(usuario))


@admin_bp.get("/bitacora")
@roles_requeridos("ADMIN")
def listar_bitacora():
    pagina, por_pagina = parametros_paginacion()
    total = db.session.scalar(select(func.count()).select_from(Bitacora)) or 0
    filas = db.session.execute(
        select(Bitacora)
        .order_by(Bitacora.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars()
    return jsonify(
        {
            "items": BitacoraSchema(many=True).dump(filas),
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
        }
    )


@admin_bp.get("/configuracion")
@roles_requeridos("ADMIN")
def listar_configuracion():
    return jsonify(ConfiguracionSchema(many=True).dump(configuracion_service.listar_configuracion()))


@admin_bp.patch("/configuracion")
@roles_requeridos("ADMIN")
def actualizar_configuracion():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict) or not datos:
        raise ApiError("JSON_INVALIDO", "Se requiere un objeto con parámetros a actualizar", 400)
    valores = datos.get("valores", datos)
    if not isinstance(valores, dict) or not valores:
        raise ApiError("VALIDACION", "Se requiere al menos un par clave/valor", 400)

    resultado = {}
    for clave, valor in valores.items():
        if not isinstance(clave, str) or not isinstance(valor, (str, int, float)):
            raise ApiError("VALIDACION", "Cada parámetro debe tener un valor escalar", 400)
        fila = configuracion_service.actualizar_configuracion(
            clave, str(valor), usuario_actual().id, ip=request.remote_addr, commit=False
        )
        resultado[clave] = fila.valor
    db.session.commit()
    return jsonify(resultado)
