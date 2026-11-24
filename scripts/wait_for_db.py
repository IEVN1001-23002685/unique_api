"""Espera acotada a que MySQL acepte conexiones antes de iniciar Gunicorn."""

import os
import sys
import time
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool


def esperar_base_de_datos() -> int:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        print("DATABASE_URL no está definida", file=sys.stderr)
        return 1

    destino = urlparse(url)
    ubicacion = f"{destino.hostname or '?'}:{destino.port or 3306}/{destino.path.lstrip('/') or '?'}"
    limite = time.monotonic() + int(os.getenv("DB_WAIT_TIMEOUT", "60"))
    motor = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 5})

    intento = 0
    while True:
        intento += 1
        try:
            with motor.connect() as conexion:
                conexion.execute(text("SELECT 1"))
            motor.dispose()
            print(f"MySQL disponible en {ubicacion} (intento {intento})", flush=True)
            return 0
        except Exception as error:
            motor.dispose()
            restante = limite - time.monotonic()
            if restante <= 0:
                print(f"MySQL no disponible en {ubicacion}: {type(error).__name__}", file=sys.stderr)
                return 1
            espera = min(2 ** min(intento - 1, 2), restante, 3.0)
            print(f"Esperando MySQL en {ubicacion} ({espera:.1f}s, intento {intento})", flush=True)
            time.sleep(espera)


if __name__ == "__main__":
    sys.exit(esperar_base_de_datos())
