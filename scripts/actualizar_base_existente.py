"""Actualiza de forma idempotente una base ya desplegada y sembrada.

En una sola transacción:

* asegura las filas de ``configuracion`` del seed sin sobrescribir valores operativos;
* alinea la galería de los productos reales con el archivo exportado.

Se ejecuta dentro del servicio API. Sin ``--aplicar`` solo genera el informe.
"""

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.services.bitacora_service import registrar_bitacora
from scripts.seed import CONFIGURACION, sembrar_configuracion
from scripts.sincronizar_imagenes_reales import (
    SincronizacionError,
    preparar_sincronizacion,
    validar_usuario,
)

logger = logging.getLogger(__name__)


def actualizar(
    datos: dict,
    *,
    aplicar=False,
    verificar_archivos=True,
    usuario_id=None,
    skus=None,
) -> dict:
    validar_usuario(usuario_id)
    contadores = Counter()
    try:
        sembrar_configuracion(contadores)
        informe_imagenes = preparar_sincronizacion(
            datos, verificar_archivos=verificar_archivos, skus=skus
        )
        if aplicar:
            registrar_bitacora(
                usuario_id,
                "ACTUALIZACION_BASE_EXISTENTE",
                "configuracion",
                None,
                {
                    "configuracion_creadas": contadores["configuracion"],
                    "configuracion_totales": len(CONFIGURACION),
                    "imagenes_creadas": len(informe_imagenes["creadas"]),
                    "imagenes_actualizadas": len(informe_imagenes["actualizadas"]),
                },
            )
            db.session.commit()
            logger.info(
                "Base actualizada: %s claves de configuración creadas, %s imágenes creadas",
                contadores["configuracion"],
                len(informe_imagenes["creadas"]),
            )
        else:
            db.session.rollback()
            logger.info("Informe generado; no se escribió nada")
    except Exception:
        db.session.rollback()
        raise

    return {
        "aplicado": bool(aplicar),
        "configuracion": {
            "creadas": contadores["configuracion"],
            "totales": len(CONFIGURACION),
        },
        "imagenes": informe_imagenes,
    }


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
        help="Actualizar solo este SKU; se puede repetir",
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
            informe = actualizar(
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
