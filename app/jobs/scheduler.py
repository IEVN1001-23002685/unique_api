"""Proceso único de tareas programadas con exclusión distribuida en MySQL."""

import logging
import os
from urllib.parse import unquote, urlparse

import pymysql
from apscheduler.schedulers.blocking import BlockingScheduler

from app import create_app
from app.jobs.tareas import TAREAS

logger = logging.getLogger("unique.scheduler")
NOMBRE_BLOQUEO = "unique_scheduler"


def _conectar_mysql():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL no está configurada")
    parsed = urlparse(url)
    return pymysql.connect(
        host=parsed.hostname or "mysql",
        port=parsed.port or 3306,
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=(parsed.path or "/unique").lstrip("/"),
        charset="utf8mb4",
        autocommit=True,
    )


def adquirir_bloqueo(conexion) -> bool:
    with conexion.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, 5)", (NOMBRE_BLOQUEO,))
        return cursor.fetchone()[0] == 1


def liberar_bloqueo(conexion) -> None:
    with conexion.cursor() as cursor:
        cursor.execute("SELECT RELEASE_LOCK(%s)", (NOMBRE_BLOQUEO,))


def ejecutar(nombre: str, app) -> None:
    try:
        with app.app_context():
            resultado = TAREAS[nombre]()
        logger.info("Tarea %s completada: %s", nombre, resultado)
    except Exception:
        logger.exception("La tarea %s falló", nombre)


def iniciar() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conexion = _conectar_mysql()
    if not adquirir_bloqueo(conexion):
        logger.info("Otro scheduler ya está activo; este proceso termina")
        conexion.close()
        return

    app = create_app()
    scheduler = BlockingScheduler(timezone=os.getenv("TZ", "America/Mexico_City"))
    scheduler.add_job(
        lambda: ejecutar("evaluar_estancamientos", app),
        "interval",
        minutes=15,
        id="evaluar_estancamientos",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        lambda: ejecutar("recalcular_semaforos", app),
        "interval",
        minutes=15,
        id="recalcular_semaforos",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        lambda: ejecutar("cerrar_alertas_resueltas", app),
        "interval",
        minutes=15,
        id="cerrar_alertas_resueltas",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        lambda: ejecutar("abandonar_carritos", app),
        "cron",
        hour=2,
        minute=0,
        id="abandonar_carritos",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        lambda: ejecutar("evaluar_proveedores", app),
        "cron",
        hour=2,
        minute=15,
        id="evaluar_proveedores",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        lambda: ejecutar("limpiar_tokens", app),
        "cron",
        hour=2,
        minute=30,
        id="limpiar_tokens",
        max_instances=1,
        coalesce=True,
    )
    try:
        logger.info("Scheduler UNIQUE iniciado con bloqueo %s", NOMBRE_BLOQUEO)
        scheduler.start()
    finally:
        scheduler.shutdown(wait=False)
        liberar_bloqueo(conexion)
        conexion.close()


if __name__ == "__main__":
    iniciar()
