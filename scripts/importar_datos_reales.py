"""Importa a Railway los productos reales exportados desde la BD local.

Se ejecuta dentro del shell del servicio API de Railway, donde ya existe el código y
el acceso privado a MySQL. El archivo ``datos_reales.json`` se genera con
``scripts.exportar_datos_reales`` y se copia al contenedor.

El script empareja por SKU, no copia IDs. Actualiza productos, variantes, stock,
imágenes y recetas; activa las recetas BORRADOR validadas y publica los productos.
No inventa datos: todo viene del archivo exportado. Sin ``--aplicar`` solo genera un
informe y revierte cualquier cambio en memoria.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import current_app

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import (
    CategoriaMaterial,
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
    Usuario,
    VarianteProducto,
)
from app.services.bitacora_service import registrar_bitacora

logger = logging.getLogger(__name__)


class ImportacionError(Exception):
    """Datos incompletos o inválidos: no se aplica nada."""


def _decimal(valor, campo) -> Decimal:
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ImportacionError(f"{campo} no es decimal válido: {valor!r}") from error


def _catalogo(modelo, codigo: str, campo="codigo"):
    fila = db.session.scalar(select(modelo).where(getattr(modelo, campo) == codigo))
    if fila is None:
        raise ImportacionError(f"No existe en el catálogo de destino: {modelo.__name__} {codigo}")
    return fila


def _validar_receta(receta: Receta) -> None:
    filas = db.session.execute(
        select(RecetaLinea, Material, CategoriaMaterial)
        .join(Material, Material.id == RecetaLinea.material_id)
        .join(CategoriaMaterial, CategoriaMaterial.id == Material.categoria_material_id)
        .where(RecetaLinea.receta_id == receta.id)
    ).all()
    if not filas:
        raise ImportacionError(f"La receta {receta.id} no tiene líneas de material")
    codigos = {material.codigo for _, material, _ in filas}
    if not any(
        categoria.nombre.upper() == "TELA" or material.codigo == "HIL-EST"
        for _, material, categoria in filas
    ):
        raise ImportacionError(f"La receta {receta.id} requiere tela o HIL-EST")
    if "HIL-COS" not in codigos:
        raise ImportacionError(f"La receta {receta.id} requiere HIL-COS")
    if any(Decimal(str(linea.merma_pct or 0)) >= 100 for linea, _, _ in filas):
        raise ImportacionError(f"La receta {receta.id} tiene mermas inválidas")

    producto = db.session.get(Producto, receta.producto_id)
    talla = db.session.get(Talla, receta.talla_id)
    etiquetas = {"ETQ-MAR", f"ETQ-COM-{producto.categoria.prefijo_sku}"}
    if talla.codigo != "UN":
        etiquetas.add(f"ETQ-TAL-{talla.codigo}")
    faltan = sorted(etiquetas - codigos)
    if faltan:
        raise ImportacionError(
            f"A la receta {receta.id} le faltan etiquetas: {', '.join(faltan)}"
        )


def importar(datos: dict, *, aplicar=False, verificar_archivos=True, usuario_id=None) -> dict:
    if datos.get("version") != 1:
        raise ImportacionError("Versión de archivo no soportada")
    productos_origen = datos.get("productos") or []
    if not productos_origen:
        raise ImportacionError("El archivo no contiene productos reales")

    if usuario_id is not None and db.session.get(Usuario, usuario_id) is None:
        raise ImportacionError("El usuario indicado para la bitácora no existe")

    carpeta_uploads = Path(
        current_app.config.get("UPLOAD_FOLDER") or "/var/lib/unique/uploads"
    )
    informe = {"aplicado": False, "productos": [], "errores": []}

    try:
        for origen in productos_origen:
            sku = str(origen.get("codigo_sku") or "").strip().upper()
            if not sku:
                raise ImportacionError("Producto sin codigo_sku")

            producto = db.session.scalar(
                select(Producto).where(Producto.codigo_sku == sku)
            )
            if producto is None:
                categoria = _catalogo(
                    CategoriaProducto,
                    str(origen.get("categoria_prefijo") or "").strip().upper(),
                    "prefijo_sku",
                )
                producto = Producto(codigo_sku=sku, categoria_id=categoria.id)
                db.session.add(producto)
                db.session.flush()

            precio = _decimal(origen.get("precio_venta"), f"precio de {sku}")
            if precio <= 0:
                raise ImportacionError(f"{sku} no tiene precio real mayor que cero")
            producto.nombre = str(origen["nombre"])
            producto.descripcion = str(origen.get("descripcion") or "")
            producto.composicion_textil = str(origen.get("composicion_textil") or "")
            producto.guia_medidas = str(origen.get("guia_medidas") or "")
            producto.precio_venta = precio
            producto.permite_bajo_pedido = bool(origen.get("permite_bajo_pedido"))
            producto.activo = True
            producto.eliminado_en = None

            variantes_detalle = []
            for item in origen.get("variantes") or []:
                variante_sku = str(item.get("sku") or "").strip().upper()
                talla = _catalogo(Talla, str(item.get("talla") or "").strip().upper())
                color = _catalogo(Color, str(item.get("color") or "").strip().upper())
                variante = db.session.scalar(
                    select(VarianteProducto).where(VarianteProducto.sku == variante_sku)
                )
                if variante is None:
                    variante = VarianteProducto(
                        sku=variante_sku,
                        producto_id=producto.id,
                        talla_id=talla.id,
                        color_id=color.id,
                    )
                    db.session.add(variante)
                    db.session.flush()
                elif variante.producto_id != producto.id:
                    raise ImportacionError(
                        f"La variante {variante_sku} pertenece a otro producto"
                    )
                variante.activa = bool(item.get("activa", True))

                stock = db.session.get(StockVariante, variante.id)
                if stock is None:
                    stock = StockVariante(variante_id=variante.id)
                    db.session.add(stock)
                datos_stock = item.get("stock") or {}
                for campo in (
                    "existencia",
                    "reservado",
                    "stock_minimo",
                    "cantidad_reposicion",
                ):
                    valor = datos_stock.get(campo, 0)
                    if not isinstance(valor, int) or valor < 0:
                        raise ImportacionError(
                            f"{variante_sku}.{campo} debe ser entero no negativo"
                        )
                    setattr(stock, campo, valor)
                if stock.reservado > stock.existencia:
                    raise ImportacionError(f"{variante_sku} tiene reservado > existencia")
                variantes_detalle.append(variante_sku)

            imagenes_detalle = []
            for item in origen.get("imagenes") or []:
                url = str(item.get("url") or "").strip()
                archivo = str(item.get("archivo") or "").strip()
                if not url.startswith("/uploads/") or not archivo:
                    raise ImportacionError(f"URL de imagen no válida: {url!r}")
                if verificar_archivos and not (carpeta_uploads / archivo).is_file():
                    raise ImportacionError(
                        f"Falta el archivo real de imagen en Railway: {archivo}. "
                        "Súbalo con scripts.subir_imagenes_reales antes de importar."
                    )
                imagen = db.session.scalar(
                    select(ProductoImagen).where(ProductoImagen.url == url)
                )
                if imagen is None:
                    color_id = None
                    if item.get("color"):
                        color_id = _catalogo(
                            Color, str(item["color"]).strip().upper()
                        ).id
                    imagen = ProductoImagen(
                        producto_id=producto.id,
                        url=url,
                        color_id=color_id,
                        orden=int(item.get("orden") or 0),
                    )
                    db.session.add(imagen)
                elif imagen.producto_id != producto.id:
                    raise ImportacionError(f"La imagen {url} ya pertenece a otro producto")
                imagenes_detalle.append(url)
            if not imagenes_detalle:
                raise ImportacionError(f"{sku} no tiene imágenes en el archivo")

            recetas_detalle = []
            for item in origen.get("recetas") or []:
                talla = _catalogo(Talla, str(item.get("talla") or "").strip().upper())
                version = int(item.get("version") or 1)
                receta = db.session.scalar(
                    select(Receta).where(
                        Receta.producto_id == producto.id,
                        Receta.talla_id == talla.id,
                        Receta.version == version,
                    )
                )
                if receta is None:
                    receta = Receta(
                        producto_id=producto.id,
                        talla_id=talla.id,
                        version=version,
                        estado="BORRADOR",
                    )
                    db.session.add(receta)
                    db.session.flush()
                elif receta.estado not in ("BORRADOR", "VIGENTE"):
                    raise ImportacionError(
                        f"La receta {receta.id} está {receta.estado}; no se puede importar"
                    )

                if receta.estado == "BORRADOR":
                    receta.mano_obra = _decimal(item.get("mano_obra", 0), "mano_obra")
                    receta.costo_bordado = _decimal(
                        item.get("costo_bordado", 0), "costo_bordado"
                    )
                    receta.costos_indirectos = _decimal(
                        item.get("costos_indirectos", 0), "costos_indirectos"
                    )
                    receta.nota = item.get("nota")

                    db.session.query(RecetaLinea).filter_by(receta_id=receta.id).delete()
                    db.session.query(RecetaBordado).filter_by(receta_id=receta.id).delete()
                    db.session.flush()
                    for linea in item.get("lineas") or []:
                        material = _catalogo(
                            Material, str(linea.get("material") or "").strip().upper()
                        )
                        db.session.add(
                            RecetaLinea(
                                receta_id=receta.id,
                                material_id=material.id,
                                cantidad_neta=_decimal(
                                    linea.get("cantidad_neta"), "cantidad_neta"
                                ),
                                factor_consumo=_decimal(
                                    linea.get("factor_consumo", 1), "factor_consumo"
                                ),
                                merma_pct=_decimal(linea.get("merma_pct", 0), "merma_pct"),
                                cantidad_bruta=_decimal(
                                    linea.get("cantidad_bruta"), "cantidad_bruta"
                                ),
                                nota=linea.get("nota"),
                            )
                        )
                    for bordado in item.get("bordados") or []:
                        diseno = _catalogo(
                            DisenoBordado,
                            str(bordado.get("diseno") or "").strip().upper(),
                        )
                        db.session.add(
                            RecetaBordado(
                                receta_id=receta.id,
                                diseno_id=diseno.id,
                                aplicaciones=int(bordado.get("aplicaciones") or 1),
                                ubicacion=bordado.get("ubicacion"),
                            )
                        )
                    db.session.flush()
                    _validar_receta(receta)
                    anteriores = db.session.execute(
                        select(Receta)
                        .where(
                            Receta.producto_id == producto.id,
                            Receta.talla_id == talla.id,
                            Receta.estado == "VIGENTE",
                        )
                        .with_for_update()
                    ).scalars().all()
                    for anterior in anteriores:
                        anterior.estado = "ARCHIVADA"
                    receta.estado = "VIGENTE"
                    receta.activada_en = datetime.now(timezone.utc).replace(tzinfo=None)
                recetas_detalle.append(
                    {"id": receta.id, "talla": talla.codigo, "estado": receta.estado}
                )

            registrar_bitacora(
                usuario_id,
                "IMPORTACION_DATOS_REALES",
                "producto",
                producto.id,
                {
                    "sku": sku,
                    "precio_real": str(precio),
                    "variantes": variantes_detalle,
                    "imagenes": imagenes_detalle,
                    "recetas": recetas_detalle,
                },
            )
            informe["productos"].append(
                {
                    "sku": sku,
                    "producto_id": producto.id,
                    "precio_real": str(precio),
                    "variantes": len(variantes_detalle),
                    "imagenes": len(imagenes_detalle),
                    "recetas": len(recetas_detalle),
                }
            )

        if aplicar:
            db.session.commit()
            informe["aplicado"] = True
            logger.info("Importados %s productos reales", len(informe["productos"]))
        else:
            db.session.rollback()
            logger.info("Informe generado; no se escribió nada")
    except Exception:
        db.session.rollback()
        raise

    return informe


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("archivo", nargs="?", default="datos_reales.json")
    parser.add_argument(
        "--aplicar", action="store_true", help="Aplicar cambios; sin esto solo informa"
    )
    parser.add_argument(
        "--no-verificar-archivos",
        action="store_true",
        help="No comprobar que las imágenes ya estén en el volumen de Railway",
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
            informe = importar(
                datos,
                aplicar=argumentos.aplicar,
                verificar_archivos=not argumentos.no_verificar_archivos,
                usuario_id=argumentos.usuario_id,
            )
        except ImportacionError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2

    print(json.dumps(informe, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
