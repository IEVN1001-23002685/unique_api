"""Regresiones del bloqueo distribuido del scheduler (Railway / múltiples réplicas)."""

import threading
from unittest.mock import MagicMock

from apscheduler.schedulers.base import SchedulerNotRunningError

from app.jobs.scheduler import MonitorBloqueo, ejecutar, latido, verificar_bloqueo


class CursorFalso:
    def __init__(self, conexion):
        self.conexion = conexion

    def __enter__(self):
        return self

    def __exit__(self, *argumentos):
        return False

    def execute(self, sql, parametros=None):
        self.conexion.consultas.append((sql, parametros))

    def fetchone(self):
        sql = self.conexion.consultas[-1][0]
        if "GET_LOCK" in sql:
            return (1,)
        if "IS_USED_LOCK" in sql:
            return (self.conexion.dueno,)
        return (1,)


class ConexionFalsa:
    def __init__(self, id_hilo=101, dueno=101, viva=True):
        self.id_hilo = id_hilo
        self.dueno = dueno
        self.viva = viva
        self.consultas = []
        self.pings = []
        self.cerrada = False

    def ping(self, reconnect=False):
        self.pings.append(reconnect)
        if not self.viva:
            raise RuntimeError("conexión cerrada")

    def cursor(self):
        return CursorFalso(self)

    def thread_id(self):
        return self.id_hilo

    def close(self):
        self.cerrada = True


def test_verificar_bloqueo_no_reconecta_silenciosamente():
    conexion = ConexionFalsa(viva=False)
    assert verificar_bloqueo(conexion) is False
    assert conexion.pings == [False]


def test_verificar_bloqueo_distingue_al_dueno_del_lock():
    assert verificar_bloqueo(ConexionFalsa(dueno=999)) is False
    assert verificar_bloqueo(ConexionFalsa(dueno=101)) is True


def test_jobs_concurrentes_con_lock_perdido_apagan_una_sola_vez():
    monitor = MonitorBloqueo(ConexionFalsa(dueno=999))
    scheduler = MagicMock()
    app = MagicMock()
    errores = []

    def correr():
        try:
            ejecutar("evaluar_estancamientos", app, monitor, scheduler)
        except Exception as error:  # pragma: no cover - la prueba debe fallar si ocurre
            errores.append(error)

    hilos = [threading.Thread(target=correr) for _ in range(3)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=5)

    assert errores == []
    assert monitor.apagando is True
    scheduler.shutdown.assert_called_once_with(wait=False)


def test_shutdown_duplicado_no_propaga_scheduler_not_running():
    monitor = MonitorBloqueo(ConexionFalsa(dueno=999))
    scheduler = MagicMock()
    scheduler.shutdown.side_effect = SchedulerNotRunningError()

    ejecutar("recalcular_semaforos", MagicMock(), monitor, scheduler)

    scheduler.shutdown.assert_called_once_with(wait=False)


def test_latido_mantiene_la_conexion_sin_apagar_el_scheduler():
    conexion = ConexionFalsa()
    monitor = MonitorBloqueo(conexion)
    scheduler = MagicMock()

    assert latido(monitor, scheduler) is True
    assert conexion.pings == [False]
    assert any("SELECT 1" in sql for sql, _ in conexion.consultas)
    scheduler.shutdown.assert_not_called()


def test_latido_fallido_apaga_una_sola_vez():
    monitor = MonitorBloqueo(ConexionFalsa(viva=False))
    scheduler = MagicMock()

    assert latido(monitor, scheduler) is False
    assert latido(monitor, scheduler) is False
    scheduler.shutdown.assert_called_once_with(wait=False)


def test_liberar_cierra_la_conexion_una_sola_vez():
    conexion = ConexionFalsa()
    monitor = MonitorBloqueo(conexion)

    monitor.liberar()

    assert conexion.cerrada is True
    assert any("RELEASE_LOCK" in sql for sql, _ in conexion.consultas)
