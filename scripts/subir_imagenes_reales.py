"""Sube a Railway las imágenes reales exportadas desde la BD local.

Se ejecuta en tu máquina (o en un contenedor con el volumen local montado). Usa la API
pública de administración, no escribe en la BD directamente. Necesita:

* ``API_BASE_URL``: por ejemplo ``https://<dominio-api>/api/v1``;
* ``ADMIN_EMAIL`` y ``ADMIN_PASSWORD`` de una cuenta ADMIN ya creada en Railway.

El script genera ``datos_reales_railway.json``, una copia del archivo exportado en la
que cada imagen queda con la URL real devuelta por la API de Railway. Ese nuevo archivo
es el que debe importarse desde el shell del servicio API.
"""

import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class SubidaError(Exception):
    """Fallo de autenticación, consulta o subida."""


def _base() -> str:
    valor = os.getenv("API_BASE_URL", "").strip().rstrip("/")
    if not valor.startswith("https://"):
        raise SubidaError("API_BASE_URL debe ser HTTPS y terminar en /api/v1")
    return valor


def _peticion(method: str, ruta: str, datos=None, token=None, headers=None):
    url = f"{_base()}{ruta}"
    cuerpo = None
    cabeceras = dict(headers or {})
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    if datos is not None:
        cuerpo = json.dumps(datos).encode("utf-8")
        cabeceras["Content-Type"] = "application/json"
    peticion = Request(url, data=cuerpo, method=method, headers=cabeceras)
    try:
        with urlopen(peticion, timeout=60) as respuesta:
            texto = respuesta.read().decode("utf-8")
            return json.loads(texto) if texto else {}
    except HTTPError as error:
        detalle = error.read().decode("utf-8", "replace")
        raise SubidaError(f"{method} {ruta} → HTTP {error.code}: {detalle}") from error
    except (URLError, TimeoutError, ValueError) as error:
        raise SubidaError(f"{method} {ruta} falló: {error}") from error


def _login() -> str:
    correo = os.getenv("ADMIN_EMAIL", "").strip()
    clave = os.getenv("ADMIN_PASSWORD", "")
    if not correo or not clave:
        raise SubidaError("Defina ADMIN_EMAIL y ADMIN_PASSWORD en el entorno")
    respuesta = _peticion(
        "POST", "/auth/login", {"correo": correo, "password": clave}
    )
    token = respuesta.get("access_token")
    if not token:
        raise SubidaError("La API no devolvió access_token")
    usuario = respuesta.get("usuario") or {}
    if str(usuario.get("rol") or "").upper() not in ("ADMIN", "ADMINISTRADOR"):
        roles = usuario.get("roles") or []
        if not any(str(rol).upper() in ("ADMIN", "ADMINISTRADOR") for rol in roles):
            raise SubidaError("La cuenta indicada no tiene rol ADMIN")
    return token


def _id_producto(token: str, sku: str) -> int:
    respuesta = _peticion(
        "GET", f"/productos?{urlencode({'q': sku, 'por_pagina': 100})}", token=token
    )
    items = respuesta.get("items", respuesta)
    for producto in items:
        if str(producto.get("codigo_sku") or "").upper() == sku:
            return int(producto["id"])
    raise SubidaError(f"No existe en Railway el producto con SKU {sku}")


def _subir(token: str, producto_id: int, ruta: Path, color, orden) -> tuple[str, str]:
    limite = uuid.uuid4().hex
    separador = f"----unique{limite}"
    partes = []

    def campo(nombre, valor):
        partes.append(
            f"--{separador}\r\n"
            f'Content-Disposition: form-data; name="{nombre}"\r\n\r\n'
            f"{valor}\r\n".encode("utf-8")
        )

    campo("orden", int(orden or 0))
    if color:
        campo("color", str(color).upper())

    datos = ruta.read_bytes()
    partes.append(
        (
            f"--{separador}\r\n"
            'Content-Disposition: form-data; name="archivo"; '
            f'filename="{ruta.name}"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode("utf-8")
    )
    partes.append(datos)
    partes.append(f"\r\n--{separador}--\r\n".encode("utf-8"))
    cuerpo = b"".join(partes)

    peticion = Request(
        f"{_base()}/productos/{producto_id}/imagenes",
        data=cuerpo,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={separador}",
        },
    )
    try:
        with urlopen(peticion, timeout=120) as respuesta_http:
            respuesta = json.loads(respuesta_http.read().decode("utf-8"))
    except HTTPError as error:
        detalle = error.read().decode("utf-8", "replace")
        raise SubidaError(
            f"POST /productos/{producto_id}/imagenes → HTTP {error.code}: {detalle}"
        ) from error
    except (URLError, TimeoutError, ValueError) as error:
        raise SubidaError(f"Falló la subida de {ruta.name}: {error}") from error

    url = str(respuesta.get("url") or "")
    if not url.startswith("/uploads/"):
        raise SubidaError(f"La API devolvió una URL inesperada: {url!r}")
    return url, url.rsplit("/", 1)[-1]


def subir(datos: dict, carpeta_uploads: Path) -> dict:
    token = _login()
    resultado = json.loads(json.dumps(datos))
    resumen = []

    for producto in resultado.get("productos") or []:
        sku = str(producto.get("codigo_sku") or "").upper()
        producto_id = _id_producto(token, sku)
        for imagen in producto.get("imagenes") or []:
            archivo = str(imagen.get("archivo") or "")
            ruta = carpeta_uploads / archivo
            if not ruta.is_file():
                raise SubidaError(f"No existe la imagen real local: {ruta}")
            url, nombre = _subir(
                token,
                producto_id,
                ruta,
                imagen.get("color"),
                imagen.get("orden"),
            )
            imagen["url"] = url
            imagen["archivo"] = nombre
            resumen.append({"sku": sku, "archivo_local": archivo, "url_railway": url})

    return {"datos": resultado, "resumen": resumen}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("archivo", nargs="?", default="datos_reales.json")
    parser.add_argument("--uploads", default="/var/lib/unique/uploads")
    parser.add_argument("--salida", default="datos_reales_railway.json")
    argumentos = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        datos = json.loads(Path(argumentos.archivo).read_text(encoding="utf-8"))
        resultado = subir(datos, Path(argumentos.uploads))
    except (OSError, json.JSONDecodeError, SubidaError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    salida = Path(argumentos.salida)
    salida.write_text(
        json.dumps(resultado["datos"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("Subidas %s imágenes reales", len(resultado["resumen"]))
    for item in resultado["resumen"]:
        logger.info("%s: %s → %s", item["sku"], item["archivo_local"], item["url_railway"])
    logger.info("Archivo listo para Railway: %s", salida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
