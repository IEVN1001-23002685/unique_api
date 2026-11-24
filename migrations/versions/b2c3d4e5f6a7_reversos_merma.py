"""Reversos de merma y vista de indicadores neta de reversos.

Revision ID: b2c3d4e5f6a7
Revises: 7c1f9d2a4b60
Create Date: 2026-11-24
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import INTEGER

revision = "b2c3d4e5f6a7"
down_revision = "7c1f9d2a4b60"
branch_labels = None
depends_on = None

VISTA_RESUMEN = """
    SELECT DATE(COALESCE(orig.fecha, me.fecha)) AS fecha,
           me.etapa, ca.nombre AS causa,
           pr.nombre AS producto, ma.codigo AS material,
           SUM(CASE WHEN me.reversa_de_id IS NULL THEN me.cantidad
                    ELSE -me.cantidad END) AS cantidad,
           SUM(CASE WHEN me.reversa_de_id IS NULL THEN me.costo_perdido
                    ELSE -me.costo_perdido END) AS costo_perdido,
           COUNT(*) AS registros,
           ROUND(100 * SUM(CASE WHEN me.reversa_de_id IS NULL THEN me.cantidad
                                ELSE -me.cantidad END) / NULLIF(
               SUM(SUM(CASE WHEN me.reversa_de_id IS NULL THEN me.cantidad
                            ELSE -me.cantidad END)) OVER (
                   PARTITION BY DATE(COALESCE(orig.fecha, me.fecha)), me.etapa), 0), 2
           ) AS porcentaje_etapa
    FROM merma me
    JOIN causa_merma ca ON ca.id = me.causa_id
    LEFT JOIN merma orig ON orig.id = me.reversa_de_id
    LEFT JOIN variante_producto vp ON vp.id = me.variante_id
    LEFT JOIN producto pr ON pr.id = vp.producto_id
    LEFT JOIN inventario_material im ON im.id = me.inventario_material_id
    LEFT JOIN material ma ON ma.id = im.material_id
    GROUP BY DATE(COALESCE(orig.fecha, me.fecha)), me.etapa, ca.nombre,
             pr.nombre, ma.codigo
"""

VISTA_ANTERIOR = """
    SELECT DATE(me.fecha) AS fecha, me.etapa, ca.nombre AS causa,
           pr.nombre AS producto, ma.codigo AS material,
           SUM(me.cantidad) AS cantidad, SUM(me.costo_perdido) AS costo_perdido,
           COUNT(*) AS registros,
           ROUND(100 * SUM(me.cantidad) / NULLIF(
               SUM(SUM(me.cantidad)) OVER (PARTITION BY DATE(me.fecha), me.etapa), 0), 2
           ) AS porcentaje_etapa
    FROM merma me
    JOIN causa_merma ca ON ca.id = me.causa_id
    LEFT JOIN variante_producto vp ON vp.id = me.variante_id
    LEFT JOIN producto pr ON pr.id = vp.producto_id
    LEFT JOIN inventario_material im ON im.id = me.inventario_material_id
    LEFT JOIN material ma ON ma.id = im.material_id
    GROUP BY DATE(me.fecha), me.etapa, ca.nombre, pr.nombre, ma.codigo
"""


def upgrade():
    op.add_column(
        "merma",
        sa.Column(
            "reversa_de_id",
            INTEGER(unsigned=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_merma_reversa_de", "merma", "merma", ["reversa_de_id"], ["id"]
    )
    op.create_unique_constraint("uq_merma_reversa", "merma", ["reversa_de_id"])
    op.execute("DROP VIEW IF EXISTS v_merma_resumen")
    op.execute(f"CREATE VIEW v_merma_resumen AS {VISTA_RESUMEN}")


def downgrade():
    op.execute("DROP VIEW IF EXISTS v_merma_resumen")
    op.execute(f"CREATE VIEW v_merma_resumen AS {VISTA_ANTERIOR}")
    op.drop_constraint("uq_merma_reversa", "merma", type_="unique")
    op.drop_constraint("fk_merma_reversa_de", "merma", type_="foreignkey")
    op.drop_column("merma", "reversa_de_id")
