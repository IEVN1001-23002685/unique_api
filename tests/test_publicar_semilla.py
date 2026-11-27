"""Regresiones de la publicación explícita de productos semilla."""

import secrets
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import (
    Bitacora,
    CategoriaProducto,
    Color,
    Producto,
    ProductoImagen,
    Receta,
    StockVariante,
    Talla,
    VarianteProducto,
)
from scripts.publicar_semilla import PublicacionError, publicar_borradores


@pytest.fixture
def producto_publicable(app, mysql_disponible):
    with app.app_context():
        categoria = db.session.scalar(select(CategoriaProducto).limit(1))
        talla = db.session.scalar(select(Talla).where(Talla.codigo == "CH"))
        color = db.session.scalar(select(Color).where(Color.codigo == "BL"))
        assert categoria is not None and talla is not None and color is not None

        sku = secrets.token_hex(2)
        producto = Producto(
            categoria_id=categoria.id,
            codigo_sku=sku,
            nombre=f"Prueba {sku}",
            descripcion="Producto de prueba",
            composicion_textil="Algodón",
            guia_medidas="CH",
            precio_venta=Decimal("0.00"),
            permite_bajo_pedido=True,
            activo=False,
        )
        db.session.add(producto)
        db.session.flush()

        variante = VarianteProducto(
            producto_id=producto.id,
            talla_id=talla.id,
            color_id=color.id,
            sku=f"{sku}-CH-BL",
            activa=False,
        )
        db.session.add(variante)
        db.session.flush()
        db.session.add(
            StockVariante(
                variante_id=variante.id,
                existencia=0,
                reservado=0,
                stock_minimo=5,
                cantidad_reposicion=20,
            )
        )
        url = f"https://servidor-real.invalid/{sku}.png"
        db.session.add(ProductoImagen(producto_id=producto.id, url=url, orden=0))
        receta = Receta(
            producto_id=producto.id,
            talla_id=talla.id,
            version=1,
            estado="VIGENTE",
            mano_obra=Decimal("0.00"),
            costo_bordado=Decimal("0.00"),
            costos_indirectos=Decimal("0.00"),
            activada_en=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.session.add(receta)
        db.session.commit()
        datos = {
            "producto_id": producto.id,
            "variante_id": variante.id,
            "receta_id": receta.id,
            "url": url,
        }

    yield datos

    with app.app_context():
        db.session.query(Bitacora).filter_by(
            entidad="producto", entidad_id=datos["producto_id"], accion="PUBLICACION_SEMILLA"
        ).delete()
        db.session.query(ProductoImagen).filter_by(producto_id=datos["producto_id"]).delete()
        db.session.query(StockVariante).filter_by(variante_id=datos["variante_id"]).delete()
        db.session.query(VarianteProducto).filter_by(id=datos["variante_id"]).delete()
        db.session.query(Receta).filter_by(id=datos["receta_id"]).delete()
        db.session.query(Producto).filter_by(id=datos["producto_id"]).delete()
        db.session.commit()


def test_informe_no_modifica_la_base(app, producto_publicable):
    with app.app_context():
        informe = publicar_borradores(producto_id=producto_publicable["producto_id"])
        producto = db.session.get(Producto, producto_publicable["producto_id"])
        variante = db.session.get(VarianteProducto, producto_publicable["variante_id"])

    assert informe["candidatos"] == []
    assert informe["aplicado"] is False
    assert any("precio" in motivo for motivo in informe["omitidos"][0]["motivos"])
    assert producto.activo is False
    assert variante.activa is False


def test_publica_solo_si_todos_los_datos_son_reales(app, producto_publicable):
    with app.app_context():
        producto = db.session.get(Producto, producto_publicable["producto_id"])
        producto.precio_venta = Decimal("249.50")
        imagen = db.session.scalar(
            select(ProductoImagen).where(
                ProductoImagen.producto_id == producto_publicable["producto_id"]
            )
        )
        imagen.url = "https://cdn.dominio-real.com/productos/real.png"
        db.session.commit()

        informe = publicar_borradores(
            producto_id=producto_publicable["producto_id"], aplicar=True
        )
        producto = db.session.get(Producto, producto_publicable["producto_id"])
        variante = db.session.get(VarianteProducto, producto_publicable["variante_id"])
        bitacora = db.session.scalar(
            select(Bitacora).where(
                Bitacora.entidad == "producto",
                Bitacora.entidad_id == producto_publicable["producto_id"],
                Bitacora.accion == "PUBLICACION_SEMILLA",
            )
        )

    assert informe["aplicado"] is True
    assert informe["candidatos"][0]["precio_real"] == "249.50"
    assert producto.activo is True
    assert variante.activa is True
    assert bitacora is not None
    assert bitacora.detalle["precio_real"] == "249.50"
    assert bitacora.usuario_id is None


def test_rechaza_url_no_real(app, producto_publicable):
    with app.app_context():
        producto = db.session.get(Producto, producto_publicable["producto_id"])
        producto.precio_venta = Decimal("150.00")
        db.session.commit()

        informe = publicar_borradores(producto_id=producto_publicable["producto_id"])
        motivos = " ".join(informe["omitidos"][0]["motivos"])

    assert "imágenes reales" in motivos


def test_rechaza_receta_borrador_sin_lineas_reales(app, producto_publicable):
    with app.app_context():
        producto = db.session.get(Producto, producto_publicable["producto_id"])
        producto.precio_venta = Decimal("150.00")
        receta = db.session.get(Receta, producto_publicable["receta_id"])
        receta.estado = "BORRADOR"
        imagen = db.session.scalar(
            select(ProductoImagen).where(
                ProductoImagen.producto_id == producto_publicable["producto_id"]
            )
        )
        imagen.url = "https://cdn.dominio-real.com/productos/real.png"
        db.session.commit()

        with pytest.raises(PublicacionError, match="no tiene líneas de material reales"):
            publicar_borradores(
                producto_id=producto_publicable["producto_id"],
                activar_recetas=[producto_publicable["receta_id"]],
            )
