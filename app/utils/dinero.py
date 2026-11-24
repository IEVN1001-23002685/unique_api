"""Formatos decimales compartidos para respuestas HTTP."""

from decimal import Decimal, ROUND_HALF_UP


def decimal_valor(valor) -> Decimal:
    if valor is None:
        return Decimal("0")
    return Decimal(str(valor))


def redondear(valor, lugares="0.01") -> Decimal:
    return decimal_valor(valor).quantize(Decimal(lugares), rounding=ROUND_HALF_UP)


def dinero(valor) -> str:
    return f"{redondear(valor):.2f}"


def material(valor) -> str:
    return f"{redondear(valor, '0.0001'):.4f}".rstrip("0").rstrip(".")
