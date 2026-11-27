"""Exporta los productos reales de la BD local a un JSON portable.

Se ejecuta en tu máquina, dentro del contenedor que tiene la BD local y el volumen
``unique_uploads_data`` montado en ``/var/lib/unique/uploads``. No escribe en la BD;
solo genera ``datos_reales.json``.

Los SKU exportados son los productos reales existentes; por defecto SD, PL, PN, GO y BO.
El archivo incluye precios, descripciones, variantes, stock, imágenes y recetas con sus
líneas y bordados. Las imágenes se referencian por nombre de archivo; el script verifica
que el archivo real exista en el volumen local.
"""

import argparse
import json
import logging
import sys
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import (
    CategoriaProducto,
    Color,
    DisenoBordado,
    Material,
    Producto,
    ProductoImagen,
    Receta,
    RecetaBordado,
    RecetaLinea,
    StockVariante,
    Talla,
    VarianteProducto,
)

logger = logging.getLogger(__name__)

SKUS_REALES = ("SD", "PL", "PN", "GO", "BO")
PALABRAS_NO_REALES = ("prueba", "test", "demo", "ejemplo", "example")


class ExportacionError(Exception):
    """Datos incompletos: el archivo no se genera."""


def _valor(valor):
    if isinstance(valor, Decimal):
        return str(valor)
    return valor


def _nombre_archivo(url: str) -> str:
    nombre = str(url or "").strip().rstrip("/").split("/")[-1]
    if not nombre or any(c in nombre for c in ("\\", "..", "\n", "\r")):
        raise ExportacionError(f"URL de imagen no válida: {url!r}")
    return nombre


def exportar(skus, carpeta_uploads) -> dict:
    aplicacion = create_app()
    with aplicacion.app_context():
        productos = db.session.execute(
            select(Producto)
            .where(Producto.codigo_sku.in_(skus), Producto.eliminado_en.is_(None))
            .order_by(Producto.id)
        ).scalars().all()
        encontrados = {producto.codigo_sku for producto in productos}
        faltan = sorted(set(skus) - encontrados)
        if faltan:
            raise ExportacionError("Faltan productos reales: " + ", ".join(faltan))

        salida = {"version": 1, "productos": []}
        for producto in productos:
            nombre = (producto.nombre or "").lower()
            if any(palabra in nombre for palabra in PALABRAS_NO_REALES):
                raise ExportacionError(
                    f"El producto {producto.codigo_sku} parece de prueba: {producto.nombre}"
                )
            if producto.precio_venta is None or Decimal(str(producto.precio_venta)) <= 0:
                raise ExportacionError(
                    f"El producto {producto.codigo_sku} no tiene precio real"
                )

            variantes = []
            for variante in db.session.execute(
                select(VarianteProducto)
                .where(VarianteProducto.producto_id == producto.id)
                .order_by(VarianteProducto.id)
            ).scalars().all():
                stock = db.session.get(StockVariante, variante.id)
                if stock is None:
                    raise ExportacionError(
                        f"Falta stock real de la variante {variante.sku}"
                    )
                variantes.append(
                    {
                        "sku": variante.sku,
                        "talla": db.session.get(Talla, variante.talla_id).codigo,
                        "color": db.session.get(Color, variante.color_id).codigo,
                        "activa": bool(variante.activa),
                        "stock": {
                            "existencia": stock.existencia,
                            "reservado": stock.reservado,
                            "stock_minimo": stock.stock_minimo,
                            "cantidad_reposicion": stock.cantidad_reposicion,
                        },
                    }
                )

            imagenes = []
            for imagen in db.session.execute(
                select(ProductoImagen)
                .where(ProductoImagen.producto_id == producto.id)
                .order_by(ProductoImagen.orden, ProductoImagen.id)
            ).scalars().all():
                archivo = _nombre_archivo(imagen.url)
                ruta = Path(carpeta_uploads) / archivo
                if not ruta.is_file():
                    raise ExportacionError(f"No existe el archivo real de imagen: {ruta}")
                imagenes.append(
                    {
                        "url": imagen.url,
                        "archivo": archivo,
                        "color": db.session.get(Color, imagen.color_id).codigo
                        if imagen.color_id
                        else None,
                        "orden": imagen.orden,
                    }
                )
            if not imagenes:
                raise ExportacionError(
                    f"El producto {producto.codigo_sku} no tiene imágenes reales"
                )

            recetas = []
            for receta in db.session.execute(
                select(Receta)
                .where(
                    Receta.producto_id == producto.id,
                    Receta.estado == "VIGENTE",
                )
                .order_by(Receta.id)
            ).scalars().all():
                lineas = []
                for linea in db.session.execute(
                    select(RecetaLinea).where(RecetaLinea.receta_id == receta.id)
                ).scalars().all():
                    material = db.session.get(Material, linea.material_id)
                    lineas.append(
                        {
                            "material": material.codigo,
                            "cantidad_neta": _valor(linea.cantidad_neta),
                            "factor_consumo": _valor(linea.factor_consumo),
                            "merma_pct": _valor(linea.merma_pct),
                            "cantidad_bruta": _valor(linea.cantidad_bruta),
                            "nota": linea.nota,
                        }
                    )
                bordados = []
                for bordado in db.session.execute(
                    select(RecetaBordado).where(RecetaBordado.receta_id == receta.id)
                ).scalars().all():
                    diseno = db.session.get(DisenoBordado, bordado.diseno_id)
                    bordados.append(
                        {
                            "diseno": diseno.codigo,
                            "aplicaciones": bordado.aplicaciones,
                            "ubicacion": bordado.ubicacion,
                        }
                    )
                recetas.append(
                    {
                        "talla": db.session.get(Talla, receta.talla_id).codigo,
                        "version": receta.version,
                        "mano_obra": _valor(receta.mano_obra),
                        "costo_bordado": _valor(receta.costo_bordado),
                        "costos_indirectos": _valor(receta.costos_indirectos),
                        "nota": receta.nota,
                        "lineas": lineas,
                        "bordados": bordados,
                    }
                )
            if not recetas:
                raise ExportacionError(
                    f"El producto {producto.codigo_sku} no tiene recetas VIGENTE"
                )

            categoria = db.session.get(CategoriaProducto, producto.categoria_id)
            salida["productos"].append(
                {
                    "codigo_sku": producto.codigo_sku,
                    "categoria_prefijo": categoria.prefijo_sku,
                    "nombre": producto.nombre,
                    "descripcion": producto.descripcion,
                    "composicion_textil": producto.composicion_textil,
                    "guia_medidas": producto.guia_medidas,
                    "precio_venta": _valor(producto.precio_venta),
                    "permite_bajo_pedido": bool(producto.permite_bajo_pedido),
                    "variantes": variantes,
                    "imagenes": imagenes,
                    "recetas": recetas,
                }
            )
    return salida


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sku", action="append", default=[], help="SKU a exportar (repetible)")
    parser.add_argument(
        "--uploads",
        default="/var/lib/unique/uploads",
        help="Ruta local con los archivos reales de imagen",
    )
    parser.add_argument("salida", nargs="?", default="datos_reales.json")
    argumentos = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    skus = [sku.strip().upper() for sku in argumentos.sku] or list(SKUS_REALES)
    try:
        datos = exportar(skus, argumentos.uploads)
    except ExportacionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    ruta = Path(argumentos.salida)
    ruta.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    logger.info("Exportados %s productos a %s", len(datos["productos"]), ruta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
