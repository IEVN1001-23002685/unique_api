"""Entrega pública de las imágenes validadas y guardadas por M10."""

from flask import Blueprint, current_app, send_from_directory

imagenes_bp = Blueprint("imagenes", __name__)


@imagenes_bp.get("/uploads/<string:nombre>")
def servir_imagen(nombre):
    """Sirve solo un nombre de archivo del directorio de uploads.

    ``<string>`` no admite separadores y ``send_from_directory`` comprueba que
    la ruta resuelta siga dentro del directorio configurado.
    """
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], nombre)
