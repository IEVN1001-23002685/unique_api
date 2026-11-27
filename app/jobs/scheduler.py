"""Proceso único de tareas programadas con exclusión distribuida en MySQL."""

import logging
import os
import time
from urllib.parse import unquote, urlparse

import pymysql
from apscheduler.schedulers.blocking import BlockingScheduler

from app import create_app
from app.jobs.tareas import TAREAS

logger = logging.getLogger("unique.scheduler")
NOMBRE_BLOQUEO = "unique_scheduler"
REINTENTO_SEGUNDOS = 30


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


def verificar_bloqueo(conexion) -> bool:
    """Comprueba antes de cada tarea que esta conexión sigue siendo la dueña del lock."""
    try:
        conexion.ping(reconnect=True)
        with conexion.cursor() as cursor:
            cursor.execute("SELECT IS_USED_LOCK(%s)", (NOMBRE_BLOQUEO,))
            return cursor.fetchone()[0] == conexion.thread_id()
    except Exception:
        return False


def liberar_bloqueo(conexion) -> None:
    with conexion.cursor() as cursor:
        cursor.execute("SELECT RELEASE_LOCK(%s)", (NOMBRE_BLOQUEO,))


def ejecutar(nombre: str, app, conexion, scheduler) -> None:
    if not verificar_bloqueo(conexion):
        logger.error("Bloqueo %s perdido; deteniendo este scheduler", NOMBRE_BLOQUEO)
        scheduler.shutdown(wait=False)
        return
    try:
        with app.app_context():
            resultado = TAREAS[nombre]()
        logger.info("Tarea %s completada: %s", nombre, resultado)
    except Exception:
        logger.exception("La tarea %s falló", nombre)


def iniciar() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    while True:
        conexion = None
        try:
            conexion = _conectar_mysql()
            if not adquirir_bloqueo(conexion):
                logger.info("Otro scheduler ya está activo; se reintentará en %ss", REINTENTO_SEGUNDOS)
                continue

            app = create_app()
            scheduler = BlockingScheduler(timezone=os.getenv("TZ", "America/Mexico_City"))
            tareas = [
                ("evaluar_estancamientos", "interval", {"minutes": 15}),
                ("recalcular_semaforos", "interval", {"minutes": 15}),
                ("cerrar_alertas_resueltas", "interval", {"minutes": 15}),
                ("abandonar_carritos", "cron", {"hour": 2, "minute": 0}),
                ("evaluar_proveedores", "cron", {"hour": 2, "minute": 15}),
                ("limpiar_tokens", "cron", {"hour": 2, "minute": 30}),
            ]
            for nombre, disparador, opciones in tareas:
                scheduler.add_job(
                    lambda nombre=nombre: ejecutar(nombre, app, conexion, scheduler),
                    disparador,
                    id=nombre,
                    max_instances=1,
                    coalesce=True,
                    **opciones,
                )
            try:
                logger.info("Scheduler UNIQUE iniciado con bloqueo %s", NOMBRE_BLOQUEO)
                scheduler.start()
            finally:
                scheduler.shutdown(wait=False)
        except Exception:
            logger.exception("El scheduler no pudo iniciarse; se reintentará")
        finally:
            if conexion is not None:
                try:
                    liberar_bloqueo(conexion)
                except Exception:
                    logger.debug("No fue posible liberar el bloqueo", exc_info=True)
                conexion.close()
        time.sleep(REINTENTO_SEGUNDOS)


if __name__ == "__main__":
    iniciar()
