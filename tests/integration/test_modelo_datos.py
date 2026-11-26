from sqlalchemy import text

from app.extensions import db
from app.models import (
    CausaMerma,
    CategoriaMaterial,
    CategoriaProducto,
    Color,
    Configuracion,
    Descuento,
    DisenoBordado,
    EmpaqueRegla,
    InventarioMaterial,
    Material,
    Producto,
    Receta,
    Rol,
    StockVariante,
    Talla,
    VarianteProducto,
)

VISTAS = (
    "v_disponibilidad_variante",
    "v_inventario_material",
    "v_capacidad_variante",
    "v_ventas_sku",
    "v_merma_resumen",
    "v_pedidos_estancados",
)


def test_todas_las_tablas_y_vistas_existen(app, mysql_disponible):
    with app.app_context():
        tablas = {
            fila[0]
            for fila in db.session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'"
                )
            )
        }
        assert len(db.metadata.tables) == 65
        assert len(tablas - {"alembic_version"}) == 65

        vistas = {
            fila[0]
            for fila in db.session.execute(
                text(
                    "SELECT table_name FROM information_schema.views "
                    "WHERE table_schema = DATABASE()"
                )
            )
        }
        assert set(VISTAS) <= vistas


def test_semillas_cargadas(app, mysql_disponible):
    with app.app_context():
        assert db.session.query(Rol).count() >= 3
        assert db.session.query(Color).count() >= 4
        assert db.session.query(Talla).count() >= 4
        assert db.session.query(CategoriaProducto).count() >= 5
        assert db.session.query(CategoriaMaterial).count() >= 6
        assert db.session.query(CausaMerma).count() >= 13
        assert db.session.query(DisenoBordado).count() >= 6
        assert db.session.query(Configuracion).count() >= 21
        assert db.session.query(Material).count() >= 26
        assert db.session.query(InventarioMaterial).count() >= 36
        codigos_producto = {fila[0] for fila in db.session.query(Producto.codigo_sku).all()}
        assert {"SD", "PL", "PN", "GO", "BO"} <= codigos_producto
        skus = {fila[0] for fila in db.session.query(VarianteProducto.sku).all()}
        assert {"GO-UN-NG", "PL-MD-GR"} <= skus
        assert db.session.query(StockVariante).count() >= 33
        assert db.session.query(Receta).count() >= 11
        assert db.session.query(Descuento).count() >= 1
        assert db.session.query(EmpaqueRegla).count() >= 4


def test_sku_y_restricciones_de_stock(app, mysql_disponible):
    with app.app_context():
        skus = {fila[0] for fila in db.session.query(VarianteProducto.sku).all()}
        assert "GO-UN-NG" in skus
        assert "PL-MD-GR" in skus
        assert len(skus) >= 33

        minimos = db.session.execute(
            text(
                "SELECT COUNT(*) FROM stock_variante "
                "WHERE existencia < 0 OR reservado < 0 OR reservado > existencia"
            )
        ).scalar()
        assert minimos == 0

        engine = db.session.execute(
            text(
                "SELECT engine FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = 'usuario'"
            )
        ).scalar()
        assert engine == "InnoDB"


def test_movimientos_son_inmutables(app, mysql_disponible):
    with app.app_context():
        uid = db.session.execute(text("SELECT id FROM usuario LIMIT 1")).scalar()
        vid = db.session.execute(text("SELECT variante_id FROM stock_variante LIMIT 1")).scalar()
        if not uid or not vid:
            return
        db.session.execute(
            text(
                "INSERT INTO movimiento_producto "
                "(variante_id,tipo,delta_existencia,delta_reservado,documento_tipo,documento_id,usuario_id,fecha,creado_en,actualizado_en) "
                "VALUES (:v,'AJUSTE',0,0,'TEST_INMUTABILIDAD',1,:u,NOW(),NOW(),NOW())"
            ),
            {"v": vid, "u": uid},
        )
        db.session.commit()
        mid = db.session.execute(
            text("SELECT id FROM movimiento_producto WHERE documento_tipo='TEST_INMUTABILIDAD' ORDER BY id DESC LIMIT 1")
        ).scalar()

        for sql in (
            "UPDATE movimiento_producto SET motivo='x' WHERE id=:id",
            "DELETE FROM movimiento_producto WHERE id=:id",
        ):
            try:
                db.session.execute(text(sql), {"id": mid})
                db.session.commit()
                assert False, f"Se permitió operación prohibida: {sql}"
            except Exception:
                db.session.rollback()

        db.session.execute(text("SET @permite_borrar_movimiento=1"))
        db.session.execute(text("DELETE FROM movimiento_producto WHERE id=:id"), {"id": mid})
        db.session.execute(text("SET @permite_borrar_movimiento=0"))
        db.session.commit()
