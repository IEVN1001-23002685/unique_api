"""Pruebas de integración de productos, recetas e inventario de PT (M10-M12)."""

import io
import re
import secrets

import pytest
from PIL import Image
from sqlalchemy import select

from app.extensions import db
from app.models import (
    CategoriaMaterial,
    CategoriaProducto,
    Color,
    Material,
    MovimientoProducto,
    ProductoImagen,
    Receta,
    Talla,
)


def _png():
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 255, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def producto_base(app, client, headers_admin, limpieza_fase3):
    with app.app_context():
        categoria_id = db.session.scalar(
            select(CategoriaProducto.id).where(CategoriaProducto.prefijo_sku == "GO")
        )
    sufijo = secrets.token_hex(3).upper()
    respuesta = client.post(
        "/api/v1/productos",
        json={
            "categoria_id": categoria_id,
            "nombre": f"Gorro prueba {sufijo}",
            "descripcion": "Gorro para pruebas automatizadas",
            "composicion_textil": "100% algodón",
            "guia_medidas": "Única",
            "precio_venta": "450.00",
            "tallas": ["UN"],
            "colores": ["GR"],
        },
        headers=headers_admin,
    )
    assert respuesta.status_code == 201, respuesta.get_json()
    producto = respuesta.get_json()
    ids = [item["id"] for item in producto["variantes"]]

    limpieza_fase3(
        "DELETE FROM movimiento_producto WHERE variante_id IN :ids",
        {"ids": ids},
    )
    limpieza_fase3(
        "DELETE FROM alerta WHERE entidad_tipo = 'variante_producto' AND entidad_id IN :ids",
        {"ids": ids},
    )
    limpieza_fase3("DELETE FROM stock_variante WHERE variante_id IN :ids", {"ids": ids})
    limpieza_fase3("DELETE FROM variante_producto WHERE id IN :ids", {"ids": ids})
    limpieza_fase3(
        "DELETE FROM receta_linea WHERE receta_id IN "
        "(SELECT id FROM receta WHERE producto_id = :id)",
        {"id": producto["id"]},
    )
    limpieza_fase3(
        "DELETE FROM receta_bordado WHERE receta_id IN "
        "(SELECT id FROM receta WHERE producto_id = :id)",
        {"id": producto["id"]},
    )
    limpieza_fase3(
        "DELETE FROM receta WHERE origen_receta_id IS NOT NULL AND producto_id = :id",
        {"id": producto["id"]},
    )
    limpieza_fase3("DELETE FROM receta WHERE producto_id = :id", {"id": producto["id"]})
    limpieza_fase3("DELETE FROM producto_imagen WHERE producto_id = :id", {"id": producto["id"]})
    limpieza_fase3("DELETE FROM producto WHERE id = :id", {"id": producto["id"]})
    return producto


@pytest.fixture
def receta_producto(app, client, headers_admin, producto_base):
    with app.app_context():
        talla_id = db.session.scalar(select(Talla.id).where(Talla.codigo == "UN"))
        color_id = db.session.scalar(select(Color.id).where(Color.codigo == "GR"))
        materiales = {
            fila.codigo: fila.id
            for fila in db.session.execute(
                select(Material).where(
                    Material.codigo.in_(
                        ("TEL-FEL", "HIL-COS", "ETQ-MAR", "ETQ-COM-GO")
                    )
                )
            ).scalars()
        }
        db.session.add(
            ProductoImagen(
                producto_id=producto_base["id"],
                color_id=color_id,
                url="/uploads/prueba.png",
                orden=0,
            )
        )
        db.session.commit()

    with app.app_context():
        borrador = db.session.scalar(
            select(Receta).where(
                Receta.producto_id == producto_base["id"],
                Receta.talla_id == talla_id,
                Receta.estado == "BORRADOR",
            )
        )
        assert borrador is not None
        receta = {
            "id": borrador.id,
            "producto_id": borrador.producto_id,
            "version": borrador.version,
        }

    for codigo in ("TEL-FEL", "HIL-COS", "ETQ-MAR", "ETQ-COM-GO"):
        linea = client.post(
            f"/api/v1/recetas/{receta['id']}/lineas",
            json={"material_id": materiales[codigo], "cantidad_neta": "1.0000"},
            headers=headers_admin,
        )
        assert linea.status_code == 201, (codigo, linea.get_json())
    return receta


def test_crear_producto_genera_sku_y_no_lo_cambia_al_editar(client, headers_admin, producto_base):
    variante = producto_base["variantes"][0]
    assert re.fullmatch(r"GO\d*-UN-GR", variante["sku"])
    assert len(variante["sku"].split("-")) == 3
    assert producto_base["activo"] is False
    assert variante["existencia"] == 0
    assert variante["stock_minimo"] == 5
    assert variante["cantidad_reposicion"] == 20

    editado = client.patch(
        f"/api/v1/productos/{producto_base['id']}",
        json={"nombre": "Gorro renombrado"},
        headers=headers_admin,
    )
    assert editado.status_code == 200, editado.get_json()
    assert editado.get_json()["variantes"][0]["sku"] == variante["sku"]


def test_activar_producto_exige_receta_vigente(client, headers_admin, receta_producto):
    producto_id = receta_producto["producto_id"]
    respuesta = client.post(f"/api/v1/productos/{producto_id}/activar", headers=headers_admin)
    assert respuesta.status_code == 422
    assert respuesta.get_json()["codigo"] == "RECETA_NO_VIGENTE"

    activada = client.post(
        f"/api/v1/recetas/{receta_producto['id']}/activar", headers=headers_admin
    )
    assert activada.status_code == 200, activada.get_json()
    assert activada.get_json()["estado"] == "VIGENTE"

    producto = client.post(f"/api/v1/productos/{producto_id}/activar", headers=headers_admin)
    assert producto.status_code == 200, producto.get_json()
    assert producto.get_json()["activo"] is True
    assert all(item["activa"] for item in producto.get_json()["variantes"])


def test_post_receta_reutiliza_el_borrador_existente(app, client, headers_admin, receta_producto):
    with app.app_context():
        talla_id = db.session.scalar(
            select(Receta.talla_id).where(Receta.id == receta_producto["id"])
        )
    respuesta = client.post(
        "/api/v1/recetas",
        json={
            "producto_id": receta_producto["producto_id"],
            "talla_id": talla_id,
            "mano_obra": "12.00",
        },
        headers=headers_admin,
    )
    assert respuesta.status_code == 201, respuesta.get_json()
    assert respuesta.get_json()["id"] == receta_producto["id"]
    assert respuesta.get_json()["mano_obra"] == "12.00"


def test_reglas_de_reposicion_aceptan_patch_parcial(client, headers_admin, producto_base):
    variante_id = producto_base["variantes"][0]["id"]
    respuesta = client.patch(
        f"/api/v1/inventario/producto/{variante_id}/reglas",
        json={"stock_minimo": 7},
        headers=headers_admin,
    )
    assert respuesta.status_code == 200, respuesta.get_json()
    assert respuesta.get_json()["stock_minimo"] == 7
    assert respuesta.get_json()["cantidad_reposicion"] == 20


def test_receta_vigente_no_se_edita_y_copia_archiva_la_anterior(
    client, headers_admin, receta_producto
):
    activada = client.post(
        f"/api/v1/recetas/{receta_producto['id']}/activar", headers=headers_admin
    )
    assert activada.status_code == 200, activada.get_json()

    edicion = client.patch(
        f"/api/v1/recetas/{receta_producto['id']}",
        json={"mano_obra": "99.00"},
        headers=headers_admin,
    )
    assert edicion.status_code == 422
    assert edicion.get_json()["codigo"] == "RECETA_NO_EDITABLE"

    copia = client.post(
        f"/api/v1/recetas/{receta_producto['id']}/copiar", json={}, headers=headers_admin
    )
    assert copia.status_code == 201, copia.get_json()
    nueva = copia.get_json()
    assert nueva["estado"] == "BORRADOR"
    assert nueva["version"] > receta_producto["version"]

    activa_copia = client.post(
        f"/api/v1/recetas/{nueva['id']}/activar", headers=headers_admin
    )
    assert activa_copia.status_code == 200, activa_copia.get_json()
    anterior = client.get(f"/api/v1/recetas/{receta_producto['id']}", headers=headers_admin)
    assert anterior.get_json()["estado"] == "ARCHIVADA"


def test_operativo_recibe_recetas_sin_costos(client, headers_admin, headers_operativo, receta_producto):
    operativo = client.get("/api/v1/recetas", headers=headers_operativo)
    assert operativo.status_code == 200, operativo.get_json()
    fila = next(
        item
        for item in operativo.get_json()["items"]
        if item["id"] == receta_producto["id"]
    )
    campos_costeo = (
        "mano_obra",
        "costo_bordado",
        "costos_indirectos",
        "costo_materia_prima",
        "costo_estandar",
        "precio_sugerido",
        "margen_real",
    )
    assert all(campo not in fila for campo in campos_costeo)
    assert "costo_linea" not in fila["lineas"][0]

    admin = client.get(f"/api/v1/recetas/{receta_producto['id']}", headers=headers_admin)
    assert admin.status_code == 200
    assert "costo_estandar" in admin.get_json()


def test_ajuste_inventario_pt_registra_movimiento_inmutable(
    app, client, headers_admin, headers_operativo, producto_base
):
    variante_id = producto_base["variantes"][0]["id"]
    ajuste = client.post(
        "/api/v1/inventario/producto/ajuste",
        json={"variante_id": variante_id, "cantidad_contada": 12, "motivo": "Conteo inicial"},
        headers=headers_operativo,
    )
    assert ajuste.status_code == 200, ajuste.get_json()
    assert ajuste.get_json()["diferencia"] == 12

    with app.app_context():
        movimientos = (
            db.session.query(MovimientoProducto)
            .filter_by(variante_id=variante_id)
            .all()
        )
        assert len(movimientos) == 1
        assert movimientos[0].tipo == "AJUSTE"
        assert movimientos[0].delta_existencia == 12
        movimiento_id = movimientos[0].id

    respuesta = client.patch(
        f"/api/v1/inventario/producto/movimientos/{movimiento_id}",
        json={"motivo": "editado"},
        headers=headers_admin,
    )
    assert respuesta.status_code == 404


def test_imagenes_rechazan_contenido_falso_mime_y_tamano(
    client, headers_admin, producto_base
):
    url = f"/api/v1/productos/{producto_base['id']}/imagenes"
    falso = client.post(
        url,
        data={
            "color": "GR",
            "archivo": (io.BytesIO(b"no es una imagen"), "falso.png", "image/png"),
        },
        headers=headers_admin,
    )
    assert falso.status_code == 422
    assert falso.get_json()["codigo"] == "IMAGEN_NO_VALIDA"

    mime = client.post(
        url,
        data={"color": "GR", "archivo": (io.BytesIO(_png()), "real.png", "text/plain")},
        headers=headers_admin,
    )
    assert mime.status_code == 422

    grande = client.post(
        url,
        data={
            "color": "GR",
            "archivo": (
                io.BytesIO(b"x" * (2 * 1024 * 1024 + 1)),
                "grande.png",
                "image/png",
            ),
        },
        headers=headers_admin,
    )
    assert grande.status_code == 400
    assert grande.get_json()["codigo"] == "ARCHIVO_GRANDE"

    valida = client.post(
        url,
        data={"color": "GR", "archivo": (io.BytesIO(_png()), "valida.png", "image/png")},
        headers=headers_admin,
    )
    assert valida.status_code == 201, valida.get_json()
    nombre = valida.get_json()["url"].rsplit("/", 1)[-1]
    app = client.application
    with app.app_context():
        import os

        ruta = os.path.join(app.config["UPLOAD_FOLDER"], nombre)
        if os.path.exists(ruta):
            os.remove(ruta)


def test_imagen_subida_esta_disponible_publicamente(client, headers_admin, producto_base):
    url = f"/api/v1/productos/{producto_base['id']}/imagenes"
    subida = client.post(
        url,
        data={"color": "GR", "archivo": (io.BytesIO(_png()), "visible.png", "image/png")},
        headers=headers_admin,
    )
    assert subida.status_code == 201, subida.get_json()
    ruta_publica = subida.get_json()["url"]
    respuesta = client.get(ruta_publica)
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "image/png"
    assert respuesta.data == _png()
    assert client.get("/uploads/no-existe.png").status_code == 404
    assert client.get("/uploads/%2E%2E%2Fapp.py").status_code == 404

    import os

    with client.application.app_context():
        os.remove(
            os.path.join(
                client.application.config["UPLOAD_FOLDER"],
                ruta_publica.rsplit("/", 1)[-1],
            )
        )


def test_roles_de_productos_y_recetas(client, headers_admin, headers_operativo, headers_cliente):
    for ruta in ("/api/v1/productos", "/api/v1/recetas"):
        assert client.get(ruta).status_code == 401
        assert client.get(ruta, headers=headers_cliente).status_code == 403
        assert client.get(ruta, headers=headers_admin).status_code == 200
    assert client.get("/api/v1/productos", headers=headers_operativo).status_code == 403
    assert client.get("/api/v1/recetas", headers=headers_operativo).status_code == 200
    assert client.post("/api/v1/productos", json={}, headers=headers_operativo).status_code == 403
