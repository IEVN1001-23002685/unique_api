"""Alinea la galería de los productos reales con el paquete JSON exportado.

``importar_datos_reales`` solo crea las imágenes que faltan: no corrige el color ni el
orden de las filas ya publicadas. Este script hace un *upsert* por URL y es idempotente,
así que permite corregir una base ya sembrada sin borrar ni duplicar registros.

Se ejecuta dentro del servicio API, donde están el código, la BD y el volumen de
imágenes. Sin ``--aplicar`` solo genera el informe y revierte cualquier cambio.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from flask import current_app

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import Color, Producto, ProductoImagen, Usuario
from app.services.bitacora_service import registrar_bitacora

logger = logging.getLogger(__name__)


class SincronizacionError(Exception):
    """Datos incompletos o inválidos: no se aplica nada."""


def validar_usuario(usuario_id) -> None:
    if usuario_id is not None and db.session.get(Usuario, usuario_id) is None:
        raise SincronizacionError("El usuario indicado para la bitácora no existe")


def _catalogo_color(codigo) -> int | None:
    texto = str(codigo or "").strip().upper()
    if not texto:
        return None
    color = db.session.scalar(select(Color).where(Color.codigo == texto))
    if color is None:
        raise SincronizacionError(f"No existe en el catálogo de destino: Color {texto}")
    return color.id


def preparar_sincronizacion(
    datos: dict, *, verificar_archivos=True, skus=None
) -> dict:
    """Prepara los cambios en la sesión sin confirmarlos ni registrar bitácora."""
    if datos.get("version") != 1:
        raise SincronizacionError("Versión de archivo no soportada")
    productos_origen = datos.get("productos") or []
    if not productos_origen:
        raise SincronizacionError("El archivo no contiene productos reales")

    filtros = {str(sku).strip().upper() for sku in (skus or [])}
    if filtros:
        productos_origen = [
            item
            for item in productos_origen
            if str(item.get("codigo_sku") or "").strip().upper() in filtros
        ]
        if not productos_origen:
            raise SincronizacionError("Ningún SKU del archivo coincide con el filtro")

    carpeta_uploads = Path(
        current_app.config.get("UPLOAD_FOLDER") or "/var/lib/unique/uploads"
    )
    informe = {"creadas": [], "actualizadas": [], "sin_cambios": 0}

    for origen in productos_origen:
        sku = str(origen.get("codigo_sku") or "").strip().upper()
        producto = db.session.scalar(select(Producto).where(Producto.codigo_sku == sku))
        if producto is None:
            raise SincronizacionError(f"No existe el producto en la BD de destino: {sku}")

        imagenes = origen.get("imagenes") or []
        if not imagenes:
            raise SincronizacionError(f"{sku} no tiene imágenes en el archivo")
        for item in imagenes:
            url = str(item.get("url") or "").strip()
            if not url.startswith("/uploads/"):
                raise SincronizacionError(f"URL de imagen no válida: {url!r}")
            archivo = url.rsplit("/", 1)[-1]
            color_id = _catalogo_color(item.get("color"))
            try:
                orden = int(item.get("orden") or 0)
            except (TypeError, ValueError) as error:
                raise SincronizacionError(f"Orden no válido para {url}") from error

            imagen = db.session.scalar(
                select(ProductoImagen).where(ProductoImagen.url == url)
            )
            if imagen is None:
                if verificar_archivos and not (carpeta_uploads / archivo).is_file():
                    raise SincronizacionError(
                        f"Falta el archivo real de la imagen en el volumen: {archivo}"
                    )
                db.session.add(
                    ProductoImagen(
                        producto_id=producto.id,
                        url=url,
                        color_id=color_id,
                        orden=orden,
                    )
                )
                informe["creadas"].append({"sku": sku, "url": url, "orden": orden})
                continue

            cambios = []
            if imagen.producto_id != producto.id:
                imagen.producto_id = producto.id
                cambios.append("producto_id")
            if imagen.color_id != color_id:
                imagen.color_id = color_id
                cambios.append("color_id")
            if imagen.orden != orden:
                imagen.orden = orden
                cambios.append("orden")
            if cambios:
                informe["actualizadas"].append(
                    {"sku": sku, "url": url, "cambios": cambios}
                )
            else:
                informe["sin_cambios"] += 1

    return informe


def sincronizar(
    datos: dict,
    *,
    aplicar=False,
    verificar_archivos=True,
    usuario_id=None,
    skus=None,
) -> dict:
    validar_usuario(usuario_id)
    try:
        informe = preparar_sincronizacion(
            datos, verificar_archivos=verificar_archivos, skus=skus
        )
        if aplicar:
            registrar_bitacora(
                usuario_id,
                "SINCRONIZACION_IMAGENES_REALES",
                "producto",
                None,
                {
                    "creadas": len(informe["creadas"]),
                    "actualizadas": len(informe["actualizadas"]),
                    "sin_cambios": informe["sin_cambios"],
                },
            )
            db.session.commit()
            informe["aplicado"] = True
            logger.info(
                "Galería sincronizada: %s creadas, %s actualizadas",
                len(informe["creadas"]),
                len(informe["actualizadas"]),
            )
        else:
            db.session.rollback()
            logger.info("Informe generado; no se escribió nada")
    except Exception:
        db.session.rollback()
        raise

    return informe


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("archivo", nargs="?", default="datos_reales_railway.json")
    parser.add_argument(
        "--aplicar", action="store_true", help="Aplicar cambios; sin esto solo informa"
    )
    parser.add_argument(
        "--no-verificar-archivos",
        action="store_true",
        help="No exigir que las imágenes nuevas estén en el volumen de Railway",
    )
    parser.add_argument(
        "--sku",
        action="append",
        dest="skus",
        help="Sincronizar solo este SKU; se puede repetir",
    )
    parser.add_argument("--usuario-id", type=int, help="Usuario de la bitácora; opcional")
    argumentos = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ruta = Path(argumentos.archivo)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"ERROR: no se pudo leer {ruta}: {error}", file=sys.stderr)
        return 2

    aplicacion = create_app()
    with aplicacion.app_context():
        try:
            informe = sincronizar(
                datos,
                aplicar=argumentos.aplicar,
                verificar_archivos=not argumentos.no_verificar_archivos,
                usuario_id=argumentos.usuario_id,
                skus=argumentos.skus,
            )
        except SincronizacionError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2

    print(json.dumps(informe, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
