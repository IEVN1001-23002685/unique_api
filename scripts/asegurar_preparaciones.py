"""Crea hojas de preparación para pedidos CONFIRMADO que aún no tienen una.

Se ejecuta dentro del servicio API. Es idempotente: los pedidos con Preparacion
existente no se modifican y los pedidos en otros estados se ignoran.
"""

import logging
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.models import Pedido, Preparacion
from app.services import pedido_service

logger = logging.getLogger(__name__)


def asegurar_preparaciones() -> int:
    pedidos = db.session.execute(
        select(Pedido)
        .outerjoin(Preparacion, Preparacion.pedido_id == Pedido.id)
        .where(Pedido.estado == "CONFIRMADO", Preparacion.id.is_(None))
        .order_by(Pedido.id)
    ).scalars().all()
    try:
        for pedido in pedidos:
            pedido_service.crear_preparacion(pedido)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return len(pedidos)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    aplicacion = create_app()
    with aplicacion.app_context():
        creadas = asegurar_preparaciones()
    logger.info("Hojas de preparación creadas: %s", creadas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
