"""Contrato único de respuestas de error de la API."""

from flask import Flask, current_app, jsonify
from werkzeug.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, codigo, mensaje, status_code=400, detalle=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.status_code = status_code
        self.detalle = detalle or []

    def respuesta(self):
        return jsonify({"codigo": self.codigo, "mensaje": self.mensaje, "detalle": self.detalle}), self.status_code


def registrar_manejadores_de_error(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _error_de_api(error):
        return error.respuesta()

    @app.errorhandler(413)
    def _archivo_demasiado_grande(_error):
        return ApiError("ARCHIVO_GRANDE", "El archivo enviado excede el tamaño permitido", 400).respuesta()

    @app.errorhandler(404)
    def _no_encontrado(_error):
        return ApiError("NO_ENCONTRADO", "Recurso no encontrado", 404).respuesta()

    @app.errorhandler(405)
    def _metodo_no_permitido(_error):
        return ApiError("METODO_NO_PERMITIDO", "Método no permitido", 405).respuesta()

    @app.errorhandler(429)
    def _demasiados_intentos(_error):
        return ApiError("DEMASIADOS_INTENTOS", "Demasiados intentos, intente más tarde", 429).respuesta()

    @app.errorhandler(HTTPException)
    def _http_generico(error):
        return ApiError("PETICION_INVALIDA", error.description or "Petición inválida", error.code or 400).respuesta()

    @app.errorhandler(Exception)
    def _error_interno(_error):
        current_app.logger.exception("Error no controlado en la API")
        return ApiError("ERROR_INTERNO", "Error interno del servidor", 500).respuesta()
