"""Pago simulado: validación de tarjeta, saldo y referencia."""

from datetime import date

from app.utils.errores import ApiError


def luhn_valido(numero: str) -> bool:
    if not numero or not numero.isdigit() or not 13 <= len(numero) <= 19:
        return False
    total = 0
    para_duplicar = False
    for caracter in reversed(numero):
        digito = int(caracter)
        if para_duplicar:
            digito *= 2
            if digito > 9:
                digito -= 9
        total += digito
        para_duplicar = not para_duplicar
    return total % 10 == 0


def vencimiento_valido(mes: int, anio: int, hoy=None) -> bool:
    hoy = hoy or date.today()
    if not 1 <= mes <= 12 or anio < hoy.year:
        return False
    return anio > hoy.year or mes >= hoy.month


def marca_tarjeta(numero: str) -> str:
    if numero.startswith("4"):
        return "VISA"
    if numero[:2] in {"51", "52", "53", "54", "55"}:
        return "MASTERCARD"
    return "OTRA"


def validar_datos_tarjeta(numero: str, mes: int, anio: int, cvv: str) -> None:
    if not luhn_valido(numero):
        raise ApiError("TARJETA_INVALIDA", "El número de tarjeta no es válido", 400)
    if not vencimiento_valido(mes, anio):
        raise ApiError("TARJETA_VENCIDA", "La tarjeta está vencida", 422)
    if not cvv or not cvv.isdigit() or not 3 <= len(cvv) <= 4:
        raise ApiError("CVV_INVALIDO", "El CVV no es válido", 400)


def simular(
    total,
    metodo: str,
    medio_pago=None,
    numero_tarjeta: str | None = None,
    titular: str | None = None,
    vence_mes: int | None = None,
    vence_anio: int | None = None,
    cvv: str | None = None,
    referencia: str = "",
):
    """Devuelve el resultado del cobro sin exponer datos sensibles."""
    if metodo not in {"TARJETA", "CUENTA"}:
        raise ApiError("METODO_PAGO_INVALIDO", "Método de pago no válido", 400)

    if metodo == "CUENTA":
        if medio_pago is None or medio_pago.tipo != "CUENTA" or not medio_pago.activo:
            raise ApiError("MEDIO_PAGO_INVALIDO", "La cuenta simulada no es válida", 422)
        if (medio_pago.saldo_simulado or 0) < total:
            return {
                "aprobado": False,
                "motivo": "SALDO_INSUFICIENTE",
                "metodo": metodo,
                "medio_pago_id": medio_pago.id,
                "ultimos4": None,
                "titular": medio_pago.titular,
            }
        medio_pago.saldo_simulado -= total
        return {
            "aprobado": True,
            "motivo": None,
            "metodo": metodo,
            "medio_pago_id": medio_pago.id,
            "ultimos4": medio_pago.ultimos4,
            "titular": medio_pago.titular,
            "referencia": referencia,
        }

    if medio_pago is not None:
        if medio_pago.tipo != "TARJETA" or not medio_pago.activo:
            raise ApiError("MEDIO_PAGO_INVALIDO", "La tarjeta guardada no es válida", 422)
        if not vencimiento_valido(medio_pago.vence_mes, medio_pago.vence_anio):
            return {
                "aprobado": False,
                "motivo": "TARJETA_VENCIDA",
                "metodo": metodo,
                "medio_pago_id": medio_pago.id,
                "ultimos4": medio_pago.ultimos4,
                "titular": medio_pago.titular,
            }
        ultimos4, titular = medio_pago.ultimos4, medio_pago.titular
        medio_pago_id = medio_pago.id
    else:
        if not numero_tarjeta:
            raise ApiError("TARJETA_REQUERIDA", "Se requiere el número de tarjeta", 422)
        ultimos4 = numero_tarjeta[-4:]
        if ultimos4 == "0000":
            return {
                "aprobado": False,
                "motivo": "PAGO_RECHAZADO",
                "metodo": metodo,
                "medio_pago_id": None,
                "ultimos4": ultimos4,
                "titular": titular,
            }
        validar_datos_tarjeta(numero_tarjeta, vence_mes, vence_anio, cvv)
        titular = titular
        medio_pago_id = None

    if ultimos4 == "0000":
        return {
            "aprobado": False,
            "motivo": "PAGO_RECHAZADO",
            "metodo": metodo,
            "medio_pago_id": medio_pago_id,
            "ultimos4": ultimos4,
            "titular": titular,
        }

    return {
        "aprobado": True,
        "motivo": None,
        "metodo": metodo,
        "medio_pago_id": medio_pago_id,
        "ultimos4": ultimos4,
        "titular": titular,
        "referencia": referencia,
    }
