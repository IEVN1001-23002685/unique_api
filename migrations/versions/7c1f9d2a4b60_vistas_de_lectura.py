"""Vistas de lectura del documento funcional.

Revision ID: 7c1f9d2a4b60
Revises: 3baed16b1d4b
Create Date: 2026-11-24
"""

from alembic import op

revision = "7c1f9d2a4b60"
down_revision = "3baed16b1d4b"
branch_labels = None
depends_on = None


VISTAS = {
    "v_disponibilidad_variante": """
        SELECT v.id AS variante_id, v.sku, s.existencia, s.reservado,
               (s.existencia - s.reservado) AS disponible, s.stock_minimo,
               CASE WHEN s.existencia - s.reservado <= 0 THEN 'ROJO'
                    WHEN s.existencia - s.reservado <= s.stock_minimo THEN 'AMBAR'
                    ELSE 'VERDE' END AS semaforo
        FROM variante_producto v
        JOIN stock_variante s ON s.variante_id = v.id
    """,
    "v_inventario_material": """
        WITH consumo AS (
            SELECT l.inventario_material_id,
                   SUM(CASE WHEN m.tipo IN ('CONSUMO', 'MERMA') THEN m.cantidad_base ELSE 0 END) AS total_30d
            FROM movimiento_material m
            JOIN lote_material l ON l.id = m.lote_id
            WHERE m.fecha >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY l.inventario_material_id
        ),
        reservas AS (
            SELECT om.inventario_material_id,
                   SUM(om.cantidad_reservada - om.cantidad_consumida) AS reservado
            FROM orden_material om
            JOIN orden_produccion op ON op.id = om.orden_id
            WHERE op.estado IN ('PLANEADA', 'LISTA', 'EN_PROCESO', 'EN_REVISION')
            GROUP BY om.inventario_material_id
        ),
        compras AS (
            SELECT ocl.inventario_material_id,
                   SUM(ocl.cantidad_compra - ocl.cantidad_base_aceptada) AS en_compra
            FROM orden_compra_linea ocl
            JOIN orden_compra oc ON oc.id = ocl.orden_compra_id
            WHERE oc.estado IN ('EMITIDA', 'PARCIAL')
            GROUP BY ocl.inventario_material_id
        )
        SELECT im.id AS inventario_material_id, im.material_id, ma.codigo AS material_codigo,
               ma.nombre AS material_nombre, ma.unidad_base, co.codigo AS color_codigo,
               COALESCE((SELECT SUM(l.cantidad_base_disponible) FROM lote_material l
                         WHERE l.inventario_material_id = im.id), 0) AS fisico,
               COALESCE(r.reservado, 0) AS reservado,
               COALESCE(c.en_compra, 0) AS en_compra,
               COALESCE(cn.total_30d, 0) AS consumo_30d,
               im.consumo_diario_manual,
               CASE WHEN COALESCE(cn.total_30d, 0) > 0 THEN cn.total_30d / 30
                    ELSE COALESCE(im.consumo_diario_manual, 0) END AS consumo_diario,
               im.stock_minimo, im.stock_seguridad,
               COALESCE((SELECT SUM(l.cantidad_base_disponible) FROM lote_material l
                         WHERE l.inventario_material_id = im.id), 0)
                   - COALESCE(r.reservado, 0) AS disponible,
               COALESCE((SELECT SUM(l.cantidad_base_disponible) FROM lote_material l
                         WHERE l.inventario_material_id = im.id), 0)
                   - COALESCE(r.reservado, 0) + COALESCE(c.en_compra, 0) AS posicion
        FROM inventario_material im
        JOIN material ma ON ma.id = im.material_id
        JOIN color co ON co.id = im.color_id
        LEFT JOIN consumo cn ON cn.inventario_material_id = im.id
        LEFT JOIN reservas r ON r.inventario_material_id = im.id
        LEFT JOIN compras c ON c.inventario_material_id = im.id
    """,
    "v_capacidad_variante": """
        SELECT va.id AS variante_id, va.sku, re.id AS receta_id,
               MIN(FLOOR(vim.disponible / NULLIF(rl.cantidad_bruta, 0))) AS capacidad
        FROM variante_producto va
        JOIN receta re ON re.producto_id = va.producto_id AND re.talla_id = va.talla_id
                      AND re.estado = 'VIGENTE'
        JOIN receta_linea rl ON rl.receta_id = re.id
        JOIN material ma ON ma.id = rl.material_id
        JOIN color co ON co.codigo = CASE WHEN ma.por_color = 1 THEN
                         (SELECT codigo FROM color WHERE id = va.color_id) ELSE 'NA' END
        JOIN v_inventario_material vim ON vim.material_id = rl.material_id
                                      AND vim.color_codigo = co.codigo
        GROUP BY va.id, va.sku, re.id
    """,
    "v_ventas_sku": """
        SELECT DATE(ve.fecha) AS fecha, vl.sku, vl.nombre_producto,
               cp.nombre AS categoria, vl.talla, vl.color,
               SUM(vl.cantidad) AS unidades, SUM(vl.subtotal) AS ingresos
        FROM venta_linea vl
        JOIN venta ve ON ve.id = vl.venta_id
        JOIN variante_producto va ON va.id = vl.variante_id
        JOIN producto pr ON pr.id = va.producto_id
        JOIN categoria_producto cp ON cp.id = pr.categoria_id
        WHERE ve.estado = 'ACTIVA'
        GROUP BY DATE(ve.fecha), vl.sku, vl.nombre_producto, cp.nombre, vl.talla, vl.color
    """,
    "v_merma_resumen": """
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
    """,
    "v_pedidos_estancados": """
        SELECT pe.id AS pedido_id, pe.venta_id, pe.estado, pe.estado_desde,
               TIMESTAMPDIFF(HOUR, pe.estado_desde, NOW()) AS horas_en_estado,
               CASE pe.estado
                   WHEN 'RECIBIDO' THEN (SELECT CAST(valor AS UNSIGNED) FROM configuracion WHERE clave = 'horas_max_recibido')
                   WHEN 'CONFIRMADO' THEN (SELECT CAST(valor AS UNSIGNED) FROM configuracion WHERE clave = 'horas_max_confirmado')
                   WHEN 'EN_PRODUCCION' THEN (SELECT CAST(valor AS UNSIGNED) FROM configuracion WHERE clave = 'dias_max_en_produccion') * 24
                   WHEN 'EN_PREPARACION' THEN (SELECT CAST(valor AS UNSIGNED) FROM configuracion WHERE clave = 'horas_max_en_preparacion')
                   WHEN 'LISTO_ENVIO' THEN (SELECT CAST(valor AS UNSIGNED) FROM configuracion WHERE clave = 'horas_max_listo_envio')
                   WHEN 'EN_REPARTO' THEN (SELECT CAST(valor AS UNSIGNED) FROM configuracion WHERE clave = 'horas_max_en_reparto')
                   ELSE NULL END AS umbral_horas
        FROM pedido pe
        WHERE pe.estado NOT IN ('ENTREGADO', 'CANCELADO')
    """,
}


def upgrade():
    for nombre, consulta in VISTAS.items():
        op.execute(f"CREATE OR REPLACE VIEW {nombre} AS {consulta}")


def downgrade():
    for nombre in reversed(VISTAS):
        op.execute(f"DROP VIEW IF EXISTS {nombre}")
