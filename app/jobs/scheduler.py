"""Proceso único de tareas programadas con exclusión distribuida en MySQL."""

import logging
import os
import threading
import time
from urllib.parse import unquote, urlparse

import pymysql
from apscheduler.executors.pool import ThreadPoolExecutor as ExecutorThreadPool
from apscheduler.schedulers.base import SchedulerNotRunningError
from apscheduler.schedulers.blocking import BlockingScheduler

from app import create_app
from app.jobs.tareas import TAREAS

logger = logging.getLogger("unique.scheduler")
NOMBRE_BLOQUEO = "unique_scheduler"
REINTENTO_SEGUNDOS = 30
LATIDO_SEGUNDOS = 60


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
    """Comprueba que esta conexión siga siendo la dueña del lock.

    No se usa ``reconnect=True``: reconectar cambiaría el ``thread_id`` y liberaría
    el lock en MySQL, haciendo creer que otro proceso lo tiene.
    """
    try:
        conexion.ping(reconnect=False)
        with conexion.cursor() as cursor:
            cursor.execute("SELECT IS_USED_LOCK(%s)", (NOMBRE_BLOQUEO,))
            return cursor.fetchone()[0] == conexion.thread_id()
    except Exception:
        return False


def liberar_bloqueo(conexion) -> None:
    with conexion.cursor() as cursor:
        cursor.execute("SELECT RELEASE_LOCK(%s)", (NOMBRE_BLOQUEO,))


class MonitorBloqueo:
    """Acceso serializado a la conexión que posee el bloqueo de MySQL.

    PyMySQL no es seguro para uso concurrente: APScheduler ejecuta los jobs en hilos.
    Un único mutex protege el lock, el latido y el cierre, y un Event garantiza que
    solo un hilo apague el scheduler cuando se pierde el bloqueo.
    """

    def __init__(self, conexion):
        self.conexion = conexion
        self._mutex = threading.Lock()
        self._apagando = threading.Event()

    @property
    def apagando(self) -> bool:
        return self._apagando.is_set()

    def adquirir(self) -> bool:
        with self._mutex:
            return adquirir_bloqueo(self.conexion)

    def verificar(self) -> bool:
        with self._mutex:
            return verificar_bloqueo(self.conexion)

    def latido(self) -> bool:
        """Mantiene viva la conexión que sostiene el lock."""
        with self._mutex:
            try:
                self.conexion.ping(reconnect=False)
                with self.conexion.cursor() as cursor:
                    cursor.execute("SELECT 1")
                return True
            except Exception:
                return False

    def debe_apagar(self) -> bool:
        """Devuelve True solo al primer hilo que detecta la pérdida del lock."""
        with self._mutex:
            if self._apagando.is_set():
                return False
            self._apagando.set()
            return True

    def liberar(self) -> None:
        with self._mutex:
            try:
                liberar_bloqueo(self.conexion)
            except Exception:
                logger.debug("No fue posible liberar el bloqueo", exc_info=True)
            finally:
                try:
                    self.conexion.close()
                except Exception:
                    logger.debug("No fue posible cerrar la conexión del bloqueo", exc_info=True)


def _detener(scheduler) -> None:
    try:
        scheduler.shutdown(wait=False)
    except SchedulerNotRunningError:
        logger.debug("El scheduler ya estaba detenido")
    except Exception:
        logger.exception("No fue posible detener el scheduler")


def ejecutar(nombre: str, app, monitor: MonitorBloqueo, scheduler) -> None:
    if monitor.apagando:
        return
    if not monitor.verificar():
        if monitor.debe_apagar():
            logger.error("Bloqueo %s perdido; deteniendo este scheduler", NOMBRE_BLOQUEO)
            _detener(scheduler)
        return
    try:
        with app.app_context():
            resultado = TAREAS[nombre]()
        logger.info("Tarea %s completada: %s", nombre, resultado)
    except Exception:
        logger.exception("La tarea %s falló", nombre)


def latido(monitor: MonitorBloqueo, scheduler) -> bool:
    if monitor.latido():
        return True
    if monitor.debe_apagar():
        logger.error("Latido de MySQL fallido; deteniendo este scheduler")
        _detener(scheduler)
    return False


def iniciar() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    while True:
        monitor = None
        try:
            monitor = MonitorBloqueo(_conectar_mysql())
            if not monitor.adquirir():
                logger.info(
                    "Otro scheduler ya está activo; se reintentará en %ss",
                    REINTENTO_SEGUNDOS,
                )
                continue

            app = create_app()
            # Un solo hilo de ejecución: los jobs comparten la conexión del bloqueo.
            scheduler = BlockingScheduler(
                timezone=os.getenv("TZ", "America/Mexico_City"),
                executors={"default": ExecutorThreadPool(max_workers=1)},
            )
            scheduler.add_job(
                lambda: latido(monitor, scheduler),
                "interval",
                seconds=LATIDO_SEGUNDOS,
                id="latido_bloqueo",
                max_instances=1,
                coalesce=True,
            )
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
                    lambda nombre=nombre: ejecutar(nombre, app, monitor, scheduler),
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
                _detener(scheduler)
        except Exception:
            logger.exception("El scheduler no pudo iniciarse; se reintentará")
        finally:
            if monitor is not None:
                monitor.liberar()
            time.sleep(REINTENTO_SEGUNDOS)


if __name__ == "__main__":
    iniciar()
