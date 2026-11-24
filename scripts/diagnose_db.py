"""Diagnostico de conectividad con MySQL sin exponer credenciales."""

import os
import re
import sys

from sqlalchemy import create_engine, text


def ocultar_secretos(mensaje: str) -> str:
    for nombre in ("MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD", "SECRET_KEY", "JWT_SECRET_KEY"):
        secreto = os.getenv(nombre, "")
        if secreto:
            mensaje = mensaje.replace(secreto, "***")
    return re.sub(r"(?i)password=[^&\s]+", "password=***", mensaje)


def diagnosticar() -> int:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL no esta definida", file=sys.stderr)
        return 1

    url_oculta = re.sub(r"://([^:]+):[^@]*@", r"://\1:***@", url)
    print(f"URL: {url_oculta}")

    motor = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with motor.connect() as conexion:
            version = conexion.execute(text("SELECT VERSION()")).scalar()
        print(f"Conexion OK. MySQL {version}")
        return 0
    except Exception as error:
        print(f"{type(error).__name__}: {ocultar_secretos(str(error))}", file=sys.stderr)
        return 1
    finally:
        motor.dispose()


if __name__ == "__main__":
    sys.exit(diagnosticar())
