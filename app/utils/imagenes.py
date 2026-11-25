"""Validación y almacenamiento de imágenes permitidas (JPG, PNG y WebP)."""

import io
import os
import secrets

from flask import current_app
from PIL import Image, UnidentifiedImageError

from app.utils.errores import ApiError

EXTENSIONES = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}
TAMANO_MAXIMO = 2 * 1024 * 1024


def guardar_imagen(archivo) -> tuple[str, str]:
    """Devuelve ``(nombre, url)`` tras validar contenido real, MIME y tamaño."""
    datos = archivo.read(TAMANO_MAXIMO + 1)
    if len(datos) > TAMANO_MAXIMO:
        raise ApiError("ARCHIVO_GRANDE", "La imagen no puede superar 2 MB", 400)
    if not datos:
        raise ApiError("ARCHIVO_VACIO", "El archivo de imagen está vacío", 400)

    mime = (archivo.mimetype or "").lower()
    try:
        with Image.open(io.BytesIO(datos)) as imagen:
            formato = imagen.format
            imagen.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise ApiError("IMAGEN_NO_VALIDA", "El archivo no es una imagen válida", 422)
    permitido = EXTENSIONES.get(formato)
    if permitido is None or mime != permitido[1]:
        raise ApiError("IMAGEN_NO_VALIDA", "Formato o MIME de imagen no permitido", 422)

    directorio = current_app.config.get("UPLOAD_FOLDER") or "/var/lib/unique/uploads"
    nombre = f"{secrets.token_hex(16)}.{permitido[0]}"
    try:
        os.makedirs(directorio, exist_ok=True)
        with open(os.path.join(directorio, nombre), "xb") as destino:
            destino.write(datos)
    except OSError:
        raise ApiError("ERROR_ALMACENAMIENTO", "No se pudo guardar la imagen", 500)
    return nombre, f"/uploads/{nombre}"


def ruta_archivo(nombre: str) -> str:
    directorio = current_app.config.get("UPLOAD_FOLDER") or "/var/lib/unique/uploads"
    return os.path.join(directorio, nombre)
