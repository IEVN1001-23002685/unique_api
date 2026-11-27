"""Regresiones del importador de datos reales desde Railway."""

import secrets
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import Bitacora, CategoriaProducto, Producto, ProductoImagen
from scripts.importar_datos_reales import ImportacionError, importar


@pytest.fixture
def producto_con_imagen(app, mysql_disponible):
    with app.app_context():
        categoria = db.session.scalar(select(CategoriaProducto).limit(1))
        assert categoria is not None
        sku = secrets.token_hex(2)
        producto = Producto(
            categoria_id=categoria.id,
            codigo_sku=sku,
            nombre=f"Importación {sku}",
            descripcion="Producto de prueba de importación",
            composicion_textil="Algodón",
            guia_medidas="Única",
            precio_venta=Decimal("0.00"),
            permite_bajo_pedido=True,
            activo=False,
        )
        db.session.add(producto)
        db.session.flush()
        url = f"/uploads/{sku}.png"
        db.session.add(ProductoImagen(producto_id=producto.id, url=url, orden=0))
        db.session.commit()
        datos = {"sku": sku, "producto_id": producto.id, "url": url, "prefijo": categoria.prefijo_sku}

    yield datos

    with app.app_context():
        db.session.query(Bitacora).filter_by(
            entidad="producto",
            entidad_id=datos["producto_id"],
            accion="IMPORTACION_DATOS_REALES",
        ).delete()
        db.session.query(ProductoImagen).filter_by(producto_id=datos["producto_id"]).delete()
        db.session.query(Producto).filter_by(id=datos["producto_id"]).delete()
        db.session.commit()


def _datos(datos_fixture):
    return {
        "version": 1,
        "productos": [
            {
                "codigo_sku": datos_fixture["sku"],
                "categoria_prefijo": datos_fixture["prefijo"],
                "nombre": "Producto importado",
                "descripcion": "Descripción real",
                "composicion_textil": "Algodón",
                "guia_medidas": "Única",
                "precio_venta": "150.00",
                "permite_bajo_pedido": True,
                "variantes": [],
                "imagenes": [
                    {
                        "url": datos_fixture["url"],
                        "archivo": f"{datos_fixture['sku']}.png",
                        "color": None,
                        "orden": 0,
                    }
                ],
                "recetas": [],
            }
        ],
    }


def test_imagen_ya_subida_no_exige_archivo_en_disco(app, producto_con_imagen):
    with app.app_context():
        informe = importar(
            _datos(producto_con_imagen), aplicar=False, verificar_archivos=True
        )

    assert informe["aplicado"] is False
    assert informe["productos"][0]["sku"] == producto_con_imagen["sku"].upper()
    assert informe["productos"][0]["imagenes"] == 1


def test_imagen_nueva_sí_exige_archivo_en_disco(app, producto_con_imagen):
    datos = _datos(producto_con_imagen)
    datos["productos"][0]["imagenes"][0]["url"] = "/uploads/no-existe-en-bd.png"
    datos["productos"][0]["imagenes"][0]["archivo"] = "no-existe-en-bd.png"
    with app.app_context(), pytest.raises(ImportacionError, match="Falta el archivo real"):
        importar(datos, aplicar=False, verificar_archivos=True)
