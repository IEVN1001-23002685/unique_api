"""Publica productos borrador reales que ya existen en MySQL.

Esta script no crea productos, no inventa precios, no genera URLs de ejemplo y no
sustituye datos reales. Solo revisa las filas existentes en la base de datos de
Railway y publica las que ya tienen:

* precio real mayor que cero;
* al menos una imagen real registrada en ``producto_imagen``;
* variantes existentes;
* receta VIGENTE para cada talla implicada (o recetas BORRADOR reales indicadas
  explícitamente con ``--activar-receta`` y validadas antes de activarlas).

Ejecutar desde el shell del servicio API de Railway, que ya tiene el código y el
acceso privado a MySQL::

    python -m scripts.publicar_semilla
    python -m scripts.publicar_semilla --producto-id 818
    python -m scripts.publicar_semilla --activar-receta 12 --aplicar

Sin ``--aplicar`` el script solo genera un informe de candidatos y omisiones; no
escribe nada. Con ``--aplicar`` publica todos los candidatos en una sola
transacción y deja constancia en bitácora.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import (
    CategoriaMaterial,
    Material,
    Producto,
    ProductoImagen,
    Receta,
    RecetaLinea,
    Talla,
    Usuario,
    VarianteProducto,
)
from app.services.bitacora_service import registrar_bitacora

logger = logging.getLogger(__name__)

DOMINIOS_NO_REALES = ("localhost", "127.0.0.1", "::1", "example.com", "ejemplo.invalid")
SUFIJOS_NO_REALES = (".test", ".invalid", ".example", ".local", ".localhost")


class PublicacionError(Exception):
    """Validación fallida: no se escribió nada."""


def _url_real(valor: str) -> bool:
    url = str(valor or "").strip()
    if any(caracter in url for caracter in ('"', "\\", "\n", "\r", "<", ">")):
        return False
    analizada = urlparse(url)
    if analizada.scheme != "https" or not analizada.netloc:
        return False
    host = (analizada.hostname or "").lower()
    if host in DOMINIOS_NO_REALES or any(host.endswith(s) for s in SUFIJOS_NO_REALES):
        return False
    return True


def _precio_real(producto: Producto) -> Decimal:
    try:
        precio = Decimal(str(producto.precio_venta or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
    return precio if precio > 0 else Decimal("0")


def _validar_receta_borrador(receta: Receta, producto: Producto) -> None:
    """Aplica las mismas reglas que la API antes de marcar una receta VIGENTE."""
    filas = db.session.execute(
        select(RecetaLinea, Material, CategoriaMaterial)
        .join(Material, Material.id == RecetaLinea.material_id)
        .join(CategoriaMaterial, CategoriaMaterial.id == Material.categoria_material_id)
        .where(RecetaLinea.receta_id == receta.id)
    ).all()
    if not filas:
        raise PublicacionError(f"La receta {receta.id} no tiene líneas de material reales")

    codigos = {material.codigo for _, material, _ in filas}
    if not any(
        categoria.nombre.upper() == "TELA" or material.codigo == "HIL-EST"
        for _, material, categoria in filas
    ):
        raise PublicacionError(f"La receta {receta.id} requiere una línea de tela o HIL-EST")
    if "HIL-COS" not in codigos:
        raise PublicacionError(f"La receta {receta.id} requiere HIL-COS")
    if any(Decimal(str(linea.merma_pct or 0)) >= 100 for linea, _, _ in filas):
        raise PublicacionError(f"La receta {receta.id} tiene mermas inválidas")

    talla = db.session.get(Talla, receta.talla_id)
    if talla is None:
        raise PublicacionError(f"La receta {receta.id} tiene una talla inexistente")
    etiquetas = {"ETQ-MAR", f"ETQ-COM-{producto.categoria.prefijo_sku}"}
    if talla.codigo != "UN":
        etiquetas.add(f"ETQ-TAL-{talla.codigo}")
    faltantes = sorted(etiquetas - codigos)
    if faltantes:
        raise PublicacionError(
            f"A la receta {receta.id} le faltan etiquetas reales: {', '.join(faltantes)}"
        )


def _evaluar(producto: Producto, recetas_solicitadas: dict) -> tuple[dict | None, list[str]]:
    motivos = []
    precio = _precio_real(producto)
    if precio <= 0:
        motivos.append("precio real no definido (precio_venta = 0)")

    imagenes = db.session.execute(
        select(ProductoImagen)
        .where(ProductoImagen.producto_id == producto.id)
        .order_by(ProductoImagen.orden, ProductoImagen.id)
    ).scalars().all()
    urls_reales = [imagen.url for imagen in imagenes if _url_real(imagen.url)]
    if not urls_reales:
        motivos.append("sin imágenes reales registradas en producto_imagen")

    variantes = db.session.execute(
        select(VarianteProducto)
        .where(VarianteProducto.producto_id == producto.id)
        .order_by(VarianteProducto.id)
    ).scalars().all()
    if not variantes:
        motivos.append("sin variantes registradas")
        tallas = set()
    else:
        tallas = {variante.talla_id for variante in variantes}

    recetas = []
    for receta in recetas_solicitadas.get(producto.id, []):
        if receta.talla_id not in tallas:
            raise PublicacionError(
                f"la receta {receta.id} corresponde a otra talla del producto"
            )
        if receta.estado == "VIGENTE":
            continue
        if receta.estado != "BORRADOR":
            raise PublicacionError(f"la receta {receta.id} no está en BORRADOR")
        _validar_receta_borrador(receta, producto)
        recetas.append(receta)

    vigentes = set(
        db.session.execute(
            select(Receta.talla_id).where(
                Receta.producto_id == producto.id, Receta.estado == "VIGENTE"
            )
        ).scalars().all()
    )
    cubiertas = vigentes | {receta.talla_id for receta in recetas}
    faltan = tallas - cubiertas
    if faltan:
        codigos = db.session.execute(
            select(Talla.codigo).where(Talla.id.in_(sorted(faltan)))
        ).scalars().all()
        motivos.append("sin receta VIGENTE para tallas: " + ", ".join(sorted(codigos)))

    if motivos:
        return None, motivos

    return (
        {
            "producto_id": producto.id,
            "producto": producto.nombre,
            "sku": producto.codigo_sku,
            "precio_real": str(precio),
            "variantes": [variante.sku for variante in variantes],
            "imagenes": urls_reales,
            "recetas_a_activar": [receta.id for receta in recetas],
        },
        [],
    )


def publicar_borradores(
    *, producto_id=None, activar_recetas=None, usuario_id=None, aplicar=False
) -> dict:
    """Inspecciona borradores reales y, con ``aplicar=True``, los publica."""
    consulta = select(Producto).where(
        Producto.activo.is_(False), Producto.eliminado_en.is_(None)
    )
    if producto_id is not None:
        consulta = consulta.where(Producto.id == producto_id)
    productos = db.session.execute(consulta.order_by(Producto.id)).scalars().all()
    if not productos:
        raise PublicacionError("No hay productos borrador reales para revisar")

    if usuario_id is not None and db.session.get(Usuario, usuario_id) is None:
        raise PublicacionError("El usuario indicado para la bitácora no existe")

    ids_productos = {producto.id for producto in productos}
    recetas_solicitadas = {}
    for receta_id in activar_recetas or []:
        receta = db.session.get(Receta, int(receta_id))
        if receta is None or receta.producto_id not in ids_productos:
            raise PublicacionError(
                f"La receta {receta_id} no pertenece a un producto borrador seleccionado"
            )
        recetas_solicitadas.setdefault(receta.producto_id, []).append(receta)

    candidatos = []
    omitidos = []
    for producto in productos:
        candidato, motivos = _evaluar(producto, recetas_solicitadas)
        if candidato:
            candidatos.append(candidato)
        else:
            omitidos.append(
                {"producto_id": producto.id, "producto": producto.nombre, "motivos": motivos}
            )

    informe = {
        "candidatos": candidatos,
        "omitidos": omitidos,
        "aplicado": False,
    }

    if not aplicar or not candidatos:
        return informe

    try:
        for candidato in candidatos:
            producto = db.session.get(Producto, candidato["producto_id"])
            producto.activo = True
            variantes = db.session.execute(
                select(VarianteProducto).where(
                    VarianteProducto.producto_id == producto.id
                )
            ).scalars().all()
            for variante in variantes:
                variante.activa = True

            for receta_id in candidato["recetas_a_activar"]:
                receta = db.session.get(Receta, receta_id)
                anteriores = db.session.execute(
                    select(Receta)
                    .where(
                        Receta.producto_id == producto.id,
                        Receta.talla_id == receta.talla_id,
                        Receta.estado == "VIGENTE",
                    )
                    .with_for_update()
                ).scalars().all()
                for anterior in anteriores:
                    anterior.estado = "ARCHIVADA"
                receta.estado = "VIGENTE"
                receta.activada_en = datetime.now(timezone.utc).replace(tzinfo=None)

            registrar_bitacora(
                usuario_id,
                "PUBLICACION_SEMILLA",
                "producto",
                producto.id,
                {
                    "precio_real": candidato["precio_real"],
                    "variantes": [variante.id for variante in variantes],
                    "imagenes": candidato["imagenes"],
                    "recetas_activadas": candidato["recetas_a_activar"],
                },
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    informe["aplicado"] = True
    logger.info("Publicados %s productos borrador reales", len(candidatos))
    return informe


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--producto-id", type=int, help="Revisar solo este producto borrador")
    parser.add_argument(
        "--activar-receta",
        action="append",
        type=int,
        default=[],
        help="ID de receta BORRADOR real, ya revisada (repetible)",
    )
    parser.add_argument("--usuario-id", type=int, help="Usuario de la bitácora; opcional")
    parser.add_argument(
        "--aplicar", action="store_true", help="Publicar los candidatos; sin esto solo informa"
    )
    argumentos = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    aplicacion = create_app()
    with aplicacion.app_context():
        try:
            informe = publicar_borradores(
                producto_id=argumentos.producto_id,
                activar_recetas=argumentos.activar_receta,
                usuario_id=argumentos.usuario_id,
                aplicar=argumentos.aplicar,
            )
        except PublicacionError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2

    print(json.dumps(informe, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
