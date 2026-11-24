"""Creación segura de cuentas iniciales Administrador y Operativo.

Uso no interactivo (variables de entorno):
    ADMIN_EMAIL=... ADMIN_PASSWORD=... python -m scripts.create_admin admin
    OPERATIVO_EMAIL=... OPERATIVO_PASSWORD=... python -m scripts.create_admin operativo

Uso interactivo:
    python -m scripts.create_admin admin
    python -m scripts.create_admin operativo
"""

import getpass
import logging
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from argon2 import PasswordHasher

from app import create_app
from app.extensions import db
from app.models import Rol, Usuario

logger = logging.getLogger(__name__)

ROLES = {
    "admin": ("ADMIN", "ADMIN_EMAIL", "ADMIN_PASSWORD", "Administrador"),
    "operativo": ("OPERATIVO", "OPERATIVO_EMAIL", "OPERATIVO_PASSWORD", "Operativo"),
}


def crear_cuenta(tipo: str) -> None:
    codigo_rol, variable_correo, variable_clave, nombre = ROLES[tipo]
    correo = (os.getenv(variable_correo) or "").strip().lower()
    clave = os.getenv(variable_clave) or ""

    if not correo:
        correo = input("Correo: ").strip().lower()
    if not clave:
        clave = getpass.getpass("Contraseña: ")
        confirmacion = getpass.getpass("Confirme la contraseña: ")
        if clave != confirmacion:
            raise SystemExit("Las contraseñas no coinciden")
    if len(clave) < 12:
        raise SystemExit("La contraseña debe tener al menos 12 caracteres")

    app = create_app()
    with app.app_context():
        if db.session.query(Usuario).filter_by(correo=correo).first() is not None:
            logger.info("El correo ya existe; no se modifica la cuenta.")
            return
        rol = db.session.query(Rol).filter_by(codigo=codigo_rol).one()
        db.session.add(
            Usuario(
                rol_id=rol.id,
                nombre=nombre,
                apellidos="UNIQUE",
                correo=correo,
                telefono="",
                password_hash=PasswordHasher().hash(clave),
                estado_cuenta="ACTIVA",
                intentos_fallidos=0,
                acepta_promociones=False,
            )
        )
        db.session.commit()
        logger.info("Cuenta %s creada.", codigo_rol)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    tipo = sys.argv[1] if len(sys.argv) > 1 else "admin"
    if tipo not in ROLES:
        raise SystemExit(f"Tipo inválido: {tipo}. Use admin u operativo")
    crear_cuenta(tipo)


if __name__ == "__main__":
    main()
