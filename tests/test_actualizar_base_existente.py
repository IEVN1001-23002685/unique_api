"""Regresiones de la actualización idempotente de una base ya sembrada."""

import secrets
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import (
    Bitacora,
    CategoriaProducto,
    Color,
    Configuracion,
    Producto,
    ProductoImagen,
)
from scripts.actualizar_base_existente import actualizar
from scripts.seed import CONFIGURACION


@pytest.fixture
def base_para_actualizar(app, mysql_disponible):
    with app.app_context():
        categoria = db.session.scalar(select(CategoriaProducto).limit(1))
        assert categoria is not None
        sku = secrets.token_hex(2).upper()
        producto = Producto(
            categoria_id=categoria.id,
            codigo_sku=sku,
            nombre=f"Actualización {sku}",
            descripcion="Producto de prueba de actualización",
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

        clave_config = f"prueba_{sku.lower()}"
        valor_config = "valor-inicial"
        configuracion = Configuracion(
            clave=clave_config, valor=valor_config, descripcion="Clave de prueba"
        )
        db.session.add(configuracion)
        db.session.commit()
        datos = {
            "sku": sku,
            "producto_id": producto.id,
            "clave_config": clave_config,
            "valor_config": valor_config,
            "urls": {
                "BL": negra.url.replace("-ng", "-bl"),
                "NG": negra.url,
                "GR": gris.url,
            },
        }

    yield datos

    with app.app_context():
        db.session.query(Bitacora).filter_by(
            accion="ACTUALIZACION_BASE_EXISTENTE",
            entidad="configuracion",
        ).delete()
        db.session.query(Configuracion).filter_by(clave=datos["clave_config"]).delete()
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


def _valor_configuracion(app, clave):
    with app.app_context():
        fila = db.session.get(Configuracion, clave)
        return fila.valor if fila is not None else None


def _galeria(app, producto_id):
    with app.app_context():
        filas = db.session.scalars(
            select(ProductoImagen)
            .where(ProductoImagen.producto_id == producto_id)
            .order_by(ProductoImagen.orden)
        ).all()
        return [(fila.url, fila.orden) for fila in filas]


def test_actualizar_es_idempotente_y_no_sobrescribe_configuracion(
    app, base_para_actualizar
):
    datos = _datos(base_para_actualizar)
    urls = base_para_actualizar["urls"]

    with app.app_context():
        informe = actualizar(datos, aplicar=True, verificar_archivos=False)

    assert informe["aplicado"] is True
    assert informe["configuracion"]["creadas"] == 0
    assert informe["configuracion"]["totales"] >= 1
    assert informe["imagenes"]["creadas"] == [
        {"sku": base_para_actualizar["sku"], "url": urls["BL"], "orden": 0}
    ]
    assert _valor_configuracion(app, base_para_actualizar["clave_config"]) == (
        base_para_actualizar["valor_config"]
    )

    esperado = [(urls["BL"], 0), (urls["NG"], 1), (urls["GR"], 2)]
    assert _galeria(app, base_para_actualizar["producto_id"]) == esperado

    with app.app_context():
        repetido = actualizar(datos, aplicar=True, verificar_archivos=False)

    assert repetido["configuracion"]["creadas"] == 0
    assert repetido["imagenes"]["creadas"] == []
    assert repetido["imagenes"]["actualizadas"] == []
    assert _galeria(app, base_para_actualizar["producto_id"]) == esperado


def test_actualizar_sin_aplicar_no_escribe(app, base_para_actualizar):
    antes = _galeria(app, base_para_actualizar["producto_id"])

    with app.app_context():
        informe = actualizar(
            _datos(base_para_actualizar), aplicar=False, verificar_archivos=False
        )

    assert informe["aplicado"] is False
    assert _galeria(app, base_para_actualizar["producto_id"]) == antes


def test_actualizar_crea_configuracion_faltante(app, base_para_actualizar):
    clave, valor, descripcion, es_propuesta = CONFIGURACION[0]
    texto = (
        f"PROPUESTA: pendiente de confirmar - {descripcion}" if es_propuesta else descripcion
    )

    with app.app_context():
        original = db.session.get(Configuracion, clave)
        original_existia = original is not None
        original_valor = original.valor if original is not None else valor
        original_descripcion = original.descripcion if original is not None else texto
        db.session.query(Configuracion).filter_by(clave=clave).delete()
        db.session.commit()

    try:
        with app.app_context():
            informe = actualizar(
                _datos(base_para_actualizar), aplicar=True, verificar_archivos=False
            )

        assert informe["configuracion"]["creadas"] == 1
        with app.app_context():
            fila = db.session.get(Configuracion, clave)
            assert fila is not None
            assert fila.valor == valor
            assert fila.descripcion == texto
    finally:
        with app.app_context():
            db.session.query(Configuracion).filter_by(clave=clave).delete()
            if original_existia:
                db.session.add(
                    Configuracion(
                        clave=clave,
                        valor=original_valor,
                        descripcion=original_descripcion,
                    )
                )
            db.session.commit()
