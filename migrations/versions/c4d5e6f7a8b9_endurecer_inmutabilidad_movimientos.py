"""Restringe UPDATE/DELETE en tablas de movimientos.

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-11-26 00:00:00.000000
"""

from alembic import op


revision = "c4d5e6f7a8b9"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None

TABLAS = ("movimiento_producto", "movimiento_material")


def _trigger_sql(tabla: str, accion: str) -> str:
    nombre = f"trg_{tabla}_no_{accion.lower()}"
    return f"""
CREATE TRIGGER {nombre}
BEFORE {accion} ON {tabla}
FOR EACH ROW
BEGIN
    IF @permite_borrar_movimiento <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Los movimientos de inventario son inmutables';
    END IF;
END
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    for tabla in TABLAS:
        for accion in ("UPDATE", "DELETE"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{tabla}_no_{accion.lower()}")
            op.execute(_trigger_sql(tabla, accion))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    for tabla in TABLAS:
        for accion in ("UPDATE", "DELETE"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{tabla}_no_{accion.lower()}")
