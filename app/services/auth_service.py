"""Casos de uso de autenticación, recuperación y sesión."""

from datetime import datetime, timedelta, timezone

from flask_jwt_extended import create_access_token, create_refresh_token, decode_token
from sqlalchemy import select

from app.extensions import db
from app.models import (
    Configuracion,
    RecuperacionContrasena,
    Rol,
    TokenRefresco,
    Usuario,
)
from app.security.password import generar_hash, verificar_password
from app.security.tokens import generar_token_opaco, hash_token
from app.services.bitacora_service import registrar_bitacora
from app.utils.errores import ApiError


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _config_entero(clave: str, predeterminado: int) -> int:
    fila = db.session.execute(
        select(Configuracion).where(Configuracion.clave == clave)
    ).scalar_one_or_none()
    if fila is None:
        return predeterminado
    try:
        return int(float(fila.valor))
    except (TypeError, ValueError):
        return predeterminado


def _rol_por_codigo(codigo: str) -> Rol:
    rol = db.session.execute(select(Rol).where(Rol.codigo == codigo)).scalar_one_or_none()
    if rol is None:
        raise ApiError("CATALOGO_INCOMPLETO", "El catálogo de roles no está cargado", 500)
    return rol


def _tokens(usuario: Usuario):
    access = create_access_token(identity=str(usuario.id))
    refresh = create_refresh_token(identity=str(usuario.id))
    db.session.add(
        TokenRefresco(
            usuario_id=usuario.id,
            token_hash=hash_token(refresh),
            expira_en=_ahora() + timedelta(days=7),
            revocado=False,
        )
    )
    db.session.commit()
    return access, refresh


def registrar_cliente(datos: dict, ip=None):
    correo = datos["correo"].strip().lower()
    if db.session.execute(select(Usuario).where(Usuario.correo == correo)).scalar_one_or_none():
        raise ApiError("CORREO_REGISTRADO", "El correo ya está registrado", 409)

    usuario = Usuario(
        rol_id=_rol_por_codigo("CLIENTE").id,
        nombre=datos["nombre"].strip(),
        apellidos=datos["apellidos"].strip(),
        correo=correo,
        telefono=datos["telefono"],
        password_hash=generar_hash(datos["password"]),
        estado_cuenta="ACTIVA",
        intentos_fallidos=0,
        acepta_privacidad=datos["acepta_privacidad"],
        acepta_promociones=datos.get("acepta_promociones", False),
    )
    db.session.add(usuario)
    db.session.flush()
    registrar_bitacora(usuario.id, "REGISTRO", "usuario", usuario.id, ip=ip)
    access, refresh = _tokens(usuario)
    return usuario, access, refresh


def autenticar(correo: str, password: str, ip=None):
    correo = correo.strip().lower()
    usuario = db.session.execute(select(Usuario).where(Usuario.correo == correo)).scalar_one_or_none()
    mensaje_generico = "Credenciales inválidas"

    if usuario is None:
        raise ApiError("CREDENCIALES_INVALIDAS", mensaje_generico, 401)

    ahora = _ahora()
    if usuario.estado_cuenta != "ACTIVA":
        raise ApiError("CUENTA_NO_ACTIVA", "La cuenta no está activa", 403)
    if usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora:
        raise ApiError("CUENTA_BLOQUEADA", "La cuenta está bloqueada temporalmente", 429)

    max_intentos = _config_entero("intentos_login_max", 5)
    minutos_bloqueo = _config_entero("bloqueo_login_min", 15)

    if not verificar_password(usuario.password_hash or "", password):
        usuario.intentos_fallidos = (usuario.intentos_fallidos or 0) + 1
        if usuario.intentos_fallidos >= max_intentos:
            usuario.bloqueado_hasta = ahora + timedelta(minutes=minutos_bloqueo)
            usuario.intentos_fallidos = 0
        db.session.commit()
        raise ApiError("CREDENCIALES_INVALIDAS", mensaje_generico, 401)

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_acceso = ahora
    db.session.flush()
    registrar_bitacora(usuario.id, "LOGIN", "usuario", usuario.id, ip=ip)
    access, refresh = _tokens(usuario)
    return usuario, access, refresh


def refrescar(token: str, ip=None, csrf_value=None):
    try:
        datos = decode_token(token, csrf_value=csrf_value)
    except Exception:
        raise ApiError("SESION_INVALIDA", "Token de refresco inválido", 401)
    if datos.get("type") != "refresh":
        raise ApiError("SESION_INVALIDA", "Token de refresco inválido", 401)

    hash_actual = hash_token(token)
    registro = db.session.execute(
        select(TokenRefresco).where(TokenRefresco.token_hash == hash_actual)
    ).scalar_one_or_none()
    if registro is None or registro.revocado or registro.expira_en <= _ahora():
        raise ApiError("SESION_INVALIDA", "Token de refresco inválido o expirado", 401)

    usuario = db.session.get(Usuario, int(datos["sub"]))
    if usuario is None or usuario.estado_cuenta != "ACTIVA":
        raise ApiError("SESION_INVALIDA", "Sesión inválida", 401)

    registro.revocado = True
    db.session.flush()
    access, refresh = _tokens(usuario)
    registrar_bitacora(usuario.id, "REFRESCO_TOKEN", "usuario", usuario.id, ip=ip)
    return usuario, access, refresh


def cerrar_sesion(token: str, usuario_id: int, ip=None):
    if token:
        registro = db.session.execute(
            select(TokenRefresco).where(TokenRefresco.token_hash == hash_token(token))
        ).scalar_one_or_none()
        if registro is not None and registro.usuario_id == usuario_id:
            registro.revocado = True
    registrar_bitacora(usuario_id, "LOGOUT", "usuario", usuario_id, ip=ip)
    db.session.commit()


def generar_token_recuperacion(usuario_id: int) -> str:
    token = generar_token_opaco()
    minutos = _config_entero("vigencia_recuperacion_min", 30)
    db.session.add(
        RecuperacionContrasena(
            usuario_id=usuario_id,
            token_hash=hash_token(token),
            expira_en=_ahora() + timedelta(minutes=minutos),
            usado=False,
        )
    )
    db.session.commit()
    return token


def solicitar_recuperacion(correo: str, ip=None) -> None:
    usuario = db.session.execute(
        select(Usuario).where(Usuario.correo == correo.strip().lower())
    ).scalar_one_or_none()
    if usuario is not None and usuario.estado_cuenta == "ACTIVA":
        generar_token_recuperacion(usuario.id)
    registrar_bitacora(
        usuario.id if usuario else None,
        "RECUPERACION_SOLICITADA",
        "usuario",
        usuario.id if usuario else None,
        ip=ip,
    )
    db.session.commit()


def restablecer_contrasena(token: str, password: str, ip=None) -> None:
    registro = db.session.execute(
        select(RecuperacionContrasena).where(
            RecuperacionContrasena.token_hash == hash_token(token)
        )
    ).scalar_one_or_none()
    if registro is None or registro.usado or registro.expira_en <= _ahora():
        raise ApiError("TOKEN_INVALIDO", "El enlace de recuperación no es válido", 400)

    usuario = db.session.get(Usuario, registro.usuario_id)
    if usuario is None:
        raise ApiError("TOKEN_INVALIDO", "El enlace de recuperación no es válido", 400)

    usuario.password_hash = generar_hash(password)
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    registro.usado = True
    for token_row in db.session.execute(
        select(TokenRefresco).where(TokenRefresco.usuario_id == usuario.id)
    ).scalars():
        token_row.revocado = True
    registrar_bitacora(usuario.id, "CONTRASENA_RESTABLECIDA", "usuario", usuario.id, ip=ip)
    db.session.commit()
