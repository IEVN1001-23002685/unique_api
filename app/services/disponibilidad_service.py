"""Cálculo de disponibilidad comercial sin exponer existencias exactas."""

from datetime import datetime, timedelta, timezone

from app.services import configuracion_service

ETIQUETAS = ("Disponible", "Pocas unidades", "Bajo pedido", "Agotado")


def estado(
    libre: int,
    stock_minimo: int,
    permite_bajo_pedido: bool,
    dias_estimados: int = 0,
):
    if libre > stock_minimo:
        return {
            "disponibilidad": "Disponible",
            "bajo_pedido": False,
            "fecha_estimada": None,
            "comprable": True,
        }
    if libre >= 1:
        return {
            "disponibilidad": "Pocas unidades",
            "bajo_pedido": False,
            "fecha_estimada": None,
            "comprable": True,
        }
    if permite_bajo_pedido:
        dias = configuracion_service.valor_entero("dias_produccion_estandar", 5) + int(
            dias_estimados or 0
        )
        return {
            "disponibilidad": "Bajo pedido",
            "bajo_pedido": True,
            "fecha_estimada": (datetime.now(timezone.utc) + timedelta(days=dias)).date(),
            "comprable": True,
        }
    return {
        "disponibilidad": "Agotado",
        "bajo_pedido": False,
        "fecha_estimada": None,
        "comprable": False,
    }
