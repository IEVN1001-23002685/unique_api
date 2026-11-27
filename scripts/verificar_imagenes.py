"""Verifica que las imágenes publicadas existan en disco y respondan por HTTP.

Se ejecuta dentro del servicio API de Railway. No escribe nada: solo contrasta
las filas de ``producto_imagen`` con el volumen de uploads y con la propia API.
Sirve para diagnosticar por qué el catálogo o el carrito muestran una imagen
en blanco cuando la respuesta JSON ya contiene la URL ``/uploads/...``.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from flask import current_app

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import Producto, ProductoImagen


def _origen_api(base: str) -> str:
    valor = (base or "").strip().rstrip("/")
    if not valor:
        puerto = os.getenv("PORT") or os.getenv("APP_PORT") or "8000"
        return f"http://127.0.0.1:{puerto}"
    return valor.replace("/api/v1", "").rstrip("/")


def verificar(api_base_url: str = "") -> dict:
    origen = _origen_api(api_base_url)
    directorio = Path(
        current_app.config.get("UPLOAD_FOLDER") or "/var/lib/unique/uploads"
    )
    filas = db.session.execute(
        select(Producto.codigo_sku, Producto.nombre, ProductoImagen.url)
        .join(Producto, Producto.id == ProductoImagen.producto_id)
        .where(Producto.activo.is_(True))
        .order_by(Producto.codigo_sku, ProductoImagen.orden)
    ).all()

    detalle = []
    for sku, nombre, url in filas:
        url = str(url)
        archivo = url.rsplit("/", 1)[-1] if url.startswith("/uploads/") else ""
        en_disco = bool(archivo) and (directorio / archivo).is_file()
        codigo_http = None
        if archivo:
            try:
                with urlopen(f"{origen}{url}", timeout=5) as respuesta:
                    codigo_http = respuesta.status
            except HTTPError as error:
                codigo_http = error.code
            except (URLError, TimeoutError, ValueError):
                codigo_http = "sin respuesta"
        detalle.append(
            {
                "sku": sku,
                "producto": nombre,
                "url": url,
                "archivo": archivo,
                "en_disco": en_disco,
                "http": codigo_http,
                "ok": en_disco and codigo_http == 200,
            }
        )

    return {
        "upload_folder": str(directorio),
        "origen_api": origen,
        "total": len(detalle),
        "correctas": sum(1 for item in detalle if item["ok"]),
        "imagenes": detalle,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--api-base-url",
        default=os.getenv("API_BASE_URL", ""),
        help="URL de la API (termina en /api/v1). Por defecto usa localhost.",
    )
    parser.add_argument(
        "--fallar-si-falta",
        action="store_true",
        help="Devuelve código 1 cuando alguna imagen no sirve correctamente.",
    )
    args = parser.parse_args(argv)

    app = create_app()
    with app.app_context():
        informe = verificar(args.api_base_url)

    print(json.dumps(informe, ensure_ascii=False, indent=2))
    if args.fallar_si_falta and informe["correctas"] != informe["total"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
