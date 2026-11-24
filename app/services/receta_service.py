"""Cálculo de costo estándar y selección de receta por variante."""

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import case, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Receta, RecetaLinea, VarianteProducto


def receta_para_variante(variante_id: int) -> Receta | None:
    variante = db.session.get(VarianteProducto, variante_id)
    if variante is None:
        return None
    return db.session.execute(
        select(Receta)
        .where(
            Receta.producto_id == variante.producto_id,
            Receta.talla_id == variante.talla_id,
            Receta.estado != "ARCHIVADA",
        )
        .order_by(
            case((Receta.estado == "VIGENTE", 0), else_=1),
            Receta.version.desc(),
        )
        .limit(1)
    ).scalars().first()


def calcular_costo(receta: Receta) -> Decimal:
    lineas = db.session.execute(
        select(RecetaLinea)
        .options(selectinload(RecetaLinea.material))
        .where(RecetaLinea.receta_id == receta.id)
    ).scalars().all()
    materiales = sum(
        (Decimal(str(linea.cantidad_bruta)) * Decimal(str(linea.material.costo_estandar_base)))
        for linea in lineas
    )
    total = (
        materiales
        + Decimal(str(receta.mano_obra or 0))
        + Decimal(str(receta.costo_bordado or 0))
        + Decimal(str(receta.costos_indirectos or 0))
    )
    return total.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def costo_estandar_unitario(variante_id: int) -> Decimal:
    receta = receta_para_variante(variante_id)
    if receta is None:
        return Decimal("0.000000")
    return calcular_costo(receta)
