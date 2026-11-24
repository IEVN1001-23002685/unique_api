"""Validación del cuerpo HTTP con esquemas Marshmallow."""

from flask import request
from marshmallow import ValidationError

from app.utils.errores import ApiError


def cuerpo(schema, parcial=False):
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        raise ApiError("JSON_INVALIDO", "Se requiere un objeto JSON", 400)
    try:
        return schema.load(datos, partial=parcial)
    except ValidationError as error:
        raise ApiError("VALIDACION", "Datos inválidos", 400, _detalles(error.messages))


def _detalles(mensajes, ruta=""):
    detalles = []
    for campo, valor in mensajes.items():
        ubicacion = f"{ruta}.{campo}" if ruta else str(campo)
        if isinstance(valor, dict):
            detalles.extend(_detalles(valor, ubicacion))
        elif isinstance(valor, list):
            detalles.extend({"campo": ubicacion, "mensaje": str(item)} for item in valor)
        else:
            detalles.append({"campo": ubicacion, "mensaje": str(valor)})
    return detalles
