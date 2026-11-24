"""Casos de uso del perfil de la cuenta autenticada."""

from app.security import usuario_actual
from app.security.password import generar_hash, verificar_password
from app.services import usuario_service
from app.services.bitacora_service import registrar_bitacora
from app.extensions import db
from app.models import TokenRefresco
from app.utils.errores import ApiError
from sqlalchemy import select


def perfil():
    return usuario_actual()


def actualizar_perfil(datos: dict, ip=None):
    permitidos = ("nombre", "apellidos", "telefono", "acepta_promociones")
    cambios = {clave: valor for clave, valor in datos.items() if clave in permitidos}
    if not cambios:
        raise ApiError("VALIDACION", "Se requiere al menos un campo", 400)
    return usuario_service.actualizar_usuario(
        usuario_actual().id, cambios, ip=ip, actor_id=usuario_actual().id
    )


def cambiar_contrasena(contrasena_actual: str, contrasena_nueva: str, ip=None) -> None:
    usuario = usuario_actual()
    if not verificar_password(usuario.password_hash or "", contrasena_actual):
        raise ApiError("CONTRASENA_INVALIDA", "La contraseña actual no es correcta", 401)
    usuario.password_hash = generar_hash(contrasena_nueva)
    for token_row in db.session.execute(
        select(TokenRefresco).where(TokenRefresco.usuario_id == usuario.id)
    ).scalars():
        token_row.revocado = True
    registrar_bitacora(usuario.id, "CONTRASENA_CAMBIADA", "usuario", usuario.id, ip=ip)
    db.session.commit()
