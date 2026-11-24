"""Casos de uso administrativos de usuarios y roles."""

from sqlalchemy import func, select

from app.extensions import db
from app.models import Rol, TokenRefresco, Usuario
from app.security.password import generar_hash
from app.services.auth_service import _rol_por_codigo
from app.services.bitacora_service import registrar_bitacora
from app.utils.errores import ApiError


def listar_usuarios(pagina: int, por_pagina: int):
    total = db.session.scalar(select(func.count()).select_from(Usuario)) or 0
    filas = db.session.execute(
        select(Usuario).order_by(Usuario.id).offset((pagina - 1) * por_pagina).limit(por_pagina)
    ).scalars()
    return {"items": list(filas), "total": total, "pagina": pagina, "por_pagina": por_pagina}


def obtener_usuario(usuario_id: int) -> Usuario:
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        raise ApiError("USUARIO_NO_ENCONTRADO", "Usuario no encontrado", 404)
    return usuario


def _validar_correo(correo: str, excluir_id=None):
    consulta = select(Usuario).where(Usuario.correo == correo.strip().lower())
    if excluir_id is not None:
        consulta = consulta.where(Usuario.id != excluir_id)
    if db.session.execute(consulta).scalar_one_or_none():
        raise ApiError("CORREO_REGISTRADO", "El correo ya está registrado", 409)


def crear_usuario(datos: dict, ip=None, actor_id=None) -> Usuario:
    correo = datos["correo"].strip().lower()
    _validar_correo(correo)
    usuario = Usuario(
        rol_id=_rol_por_codigo(datos["rol"]).id,
        nombre=datos["nombre"].strip(),
        apellidos=datos["apellidos"].strip(),
        correo=correo,
        telefono=datos["telefono"],
        password_hash=generar_hash(datos["password"]),
        estado_cuenta="ACTIVA",
        intentos_fallidos=0,
        acepta_promociones=datos.get("acepta_promociones", False),
    )
    db.session.add(usuario)
    db.session.flush()
    registrar_bitacora(actor_id, "USUARIO_CREADO", "usuario", usuario.id, {"rol": datos["rol"]}, ip)
    db.session.commit()
    return usuario


def _es_ultimo_admin(usuario: Usuario, nuevo_rol=None, nuevo_estado=None) -> bool:
    rol_final = nuevo_rol or usuario.rol.codigo
    estado_final = nuevo_estado or usuario.estado_cuenta
    if not (usuario.rol.codigo == "ADMIN" and (rol_final != "ADMIN" or estado_final != "ACTIVA")):
        return False
    admin_id = db.session.execute(select(Rol.id).where(Rol.codigo == "ADMIN")).scalar_one()
    total = db.session.scalar(
        select(func.count()).select_from(Usuario).where(
            Usuario.rol_id == admin_id, Usuario.estado_cuenta == "ACTIVA"
        )
    )
    return (total or 0) <= 1


def actualizar_usuario(usuario_id: int, datos: dict, ip=None, actor_id=None) -> Usuario:
    usuario = obtener_usuario(usuario_id)
    cambios = {}
    if "correo" in datos:
        _validar_correo(datos["correo"], excluir_id=usuario.id)
        usuario.correo = datos["correo"].strip().lower()
        cambios["correo"] = usuario.correo
    for campo in ("nombre", "apellidos", "telefono", "acepta_promociones"):
        if campo in datos:
            setattr(usuario, campo, datos[campo])
            cambios[campo] = datos[campo]

    nuevo_rol = datos.get("rol")
    nuevo_estado = datos.get("estado_cuenta")
    if _es_ultimo_admin(usuario, nuevo_rol, nuevo_estado):
        raise ApiError("ULTIMO_ADMIN", "No se puede desactivar ni cambiar el rol del último Administrador", 422)

    if nuevo_rol:
        usuario.rol_id = _rol_por_codigo(nuevo_rol).id
        cambios["rol"] = nuevo_rol
    if nuevo_estado:
        usuario.estado_cuenta = nuevo_estado
        cambios["estado_cuenta"] = nuevo_estado
        if nuevo_estado != "ACTIVA":
            for token_row in db.session.execute(
                select(TokenRefresco).where(TokenRefresco.usuario_id == usuario.id)
            ).scalars():
                token_row.revocado = True

    registrar_bitacora(actor_id, "USUARIO_ACTUALIZADO", "usuario", usuario.id, cambios, ip)
    db.session.commit()
    return usuario


def desactivar_usuario(usuario_id: int, ip=None, actor_id=None) -> None:
    usuario = obtener_usuario(usuario_id)
    if _es_ultimo_admin(usuario, nuevo_estado="INACTIVA"):
        raise ApiError("ULTIMO_ADMIN", "No se puede desactivar al último Administrador", 422)
    usuario.estado_cuenta = "INACTIVA"
    for token_row in db.session.execute(
        select(TokenRefresco).where(TokenRefresco.usuario_id == usuario.id)
    ).scalars():
        token_row.revocado = True
    registrar_bitacora(actor_id, "USUARIO_DESACTIVADO", "usuario", usuario.id, ip=ip)
    db.session.commit()
