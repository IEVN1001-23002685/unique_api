"""Regresiones del ajuste idempotente de la galería de productos reales."""

import secrets
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import Bitacora, CategoriaProducto, Color, Producto, ProductoImagen
from scripts.sincronizar_imagenes_reales import sincronizar


@pytest.fixture
def galeria_para_ajustar(app, mysql_disponible):
    with app.app_context():
        categoria = db.session.scalar(select(CategoriaProducto).limit(1))
        assert categoria is not None
        sku = secrets.token_hex(2).upper()
        producto = Producto(
            categoria_id=categoria.id,
            codigo_sku=sku,
            nombre=f"Galería {sku}",
            descripcion="Producto de prueba de sincronización",
            composicion_textil="Algodón",
            guia_medidas="Única",
            precio_venta=Decimal("100.00"),
            permite_bajo_pedido=False,
            activo=True,
        )
        db.session.add(producto)
        db.session.flush()
        color_ng = db.session.scalar(select(Color).where(Color.codigo == "NG"))
        color_gr = db.session.scalar(select(Color).where(Color.codigo == "GR"))
        assert color_ng is not None and color_gr is not None
        negra = ProductoImagen(
            producto_id=producto.id,
            url=f"/uploads/{sku}-ng.png",
            color_id=color_ng.id,
            orden=0,
        )
        gris = ProductoImagen(
            producto_id=producto.id,
            url=f"/uploads/{sku}-gr.png",
            color_id=color_gr.id,
            orden=1,
        )
        db.session.add_all([negra, gris])
        db.session.commit()
        datos = {
            "sku": sku,
            "producto_id": producto.id,
            "urls": {"BL": negra.url.replace("-ng", "-bl"), "NG": negra.url, "GR": gris.url},
        }

    yield datos

    with app.app_context():
        db.session.query(Bitacora).filter_by(
            entidad="producto",
            accion="SINCRONIZACION_IMAGENES_REALES",
        ).delete()
        db.session.query(ProductoImagen).filter_by(producto_id=datos["producto_id"]).delete()
        db.session.query(Producto).filter_by(id=datos["producto_id"]).delete()
        db.session.commit()


def _datos(datos_fixture):
    urls = datos_fixture["urls"]
    return {
        "version": 1,
        "productos": [
            {
                "codigo_sku": datos_fixture["sku"],
                "imagenes": [
                    {"url": urls["BL"], "color": "BL", "orden": 0},
                    {"url": urls["NG"], "color": "NG", "orden": 1},
                    {"url": urls["GR"], "color": "GR", "orden": 2},
                ],
            }
        ],
    }


def _galeria(app, producto_id):
    with app.app_context():
        filas = db.session.scalars(
            select(ProductoImagen)
            .where(ProductoImagen.producto_id == producto_id)
            .order_by(ProductoImagen.orden)
        ).all()
        return [
            (fila.url, fila.orden, fila.color.codigo if fila.color else None)
            for fila in filas
        ]


def test_sincronizar_reordena_y_es_idempotente(app, galeria_para_ajustar):
    datos = _datos(galeria_para_ajustar)
    urls = galeria_para_ajustar["urls"]

    with app.app_context():
        informe = sincronizar(datos, aplicar=True, verificar_archivos=False)

    assert informe["aplicado"] is True
    assert len(informe["creadas"]) == 1
    assert len(informe["actualizadas"]) == 2
    assert [cambio["cambios"] for cambio in informe["actualizadas"]] == [
        ["orden"],
        ["orden"],
    ]

    esperado = [(urls["BL"], 0, "BL"), (urls["NG"], 1, "NG"), (urls["GR"], 2, "GR")]
    assert _galeria(app, galeria_para_ajustar["producto_id"]) == esperado

    with app.app_context():
        repetido = sincronizar(datos, aplicar=True, verificar_archivos=False)

    assert repetido["creadas"] == []
    assert repetido["actualizadas"] == []
    assert repetido["sin_cambios"] == 3
    assert _galeria(app, galeria_para_ajustar["producto_id"]) == esperado


def test_sincronizar_sin_aplicar_no_escribe(app, galeria_para_ajustar):
    antes = _galeria(app, galeria_para_ajustar["producto_id"])
    with app.app_context():
        informe = sincronizar(
            _datos(galeria_para_ajustar), aplicar=False, verificar_archivos=False
        )
    assert informe["aplicado"] is False
    assert _galeria(app, galeria_para_ajustar["producto_id"]) == antes
