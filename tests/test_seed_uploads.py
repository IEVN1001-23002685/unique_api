"""Las imágenes reales publicadas deben viajar en la imagen de la API."""

import json
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parents[1]


def test_seed_uploads_cubre_todas_las_imagenes_del_paquete_real():
    datos = json.loads((BASE / "datos_reales_railway.json").read_text(encoding="utf-8"))
    urls = {
        str(imagen["url"])
        for producto in datos["productos"]
        for imagen in producto.get("imagenes") or []
    }
    assert urls

    for url in urls:
        archivo = BASE / "seed_uploads" / url.rsplit("/", 1)[-1]
        assert archivo.is_file(), f"Falta la imagen real {archivo.name}"
        with Image.open(archivo) as imagen:
            assert imagen.format == "PNG"
