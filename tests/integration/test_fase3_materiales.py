"""Pruebas de integración de proveedores e inventario de materia prima (M13, M15)."""

import secrets
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.extensions import db
from app.models import (
    CategoriaMaterial,
    LoteMaterial,
    MovimientoMaterial,
    Rol,
    Usuario,
)
from app.services import material_service
from app.utils.errores import ApiError


def _admin_id():
    return db.session.scalar(
        select(Usuario.id).join(Rol, Usuario.rol_id == Rol.id).where(Rol.codigo == "ADMIN")
    )


@pytest.fixture
def lotes_peps(app, datos_fase3, limpieza_fase3):
    inventario_id = datos_fase3["inventario_material_id"]
    with app.app_context():
        usuario = _admin_id()
        antiguo = material_service.registrar_entrada(
            inventario_id,
            "10.0000",
            "1.000000",
            date.today() - timedelta(days=10),
            None,
            None,
            usuario,
            "Lote antiguo",
        )
        reciente = material_service.registrar_entrada(
            inventario_id,
            "10.0000",
            "2.000000",
            date.today() - timedelta(days=1),
            None,
            None,
            usuario,
            "Lote reciente",
        )
        db.session.commit()
        ids = [antiguo.id, reciente.id]

    limpieza_fase3("DELETE FROM movimiento_material WHERE lote_id IN :ids", {"ids": ids})
    limpieza_fase3("DELETE FROM lote_material WHERE id IN :ids", {"ids": ids})
    return inventario_id, antiguo.id, reciente.id


def test_consumo_peps_agota_lote_antiguo_antes_del_reciente(app, lotes_peps):
    inventario_id, antiguo, reciente = lotes_peps
    with app.app_context():
        usuario = _admin_id()
        consumo = material_service.consumir_peps(
            inventario_id, "12.0000", "PRUEBA", 1, usuario, "Verificación PEPS"
        )
        assert [item["lote_id"] for item in consumo] == [antiguo, reciente]
        assert Decimal(consumo[0]["cantidad_base"]) == Decimal("10")
        assert Decimal(consumo[1]["cantidad_base"]) == Decimal("2")
        assert Decimal(consumo[0]["costo_unitario_base"]) == Decimal("1.000000")

        with pytest.raises(ApiError) as error:
            material_service.consumir_peps(
                inventario_id, "20.0000", "PRUEBA", 2, usuario, "Insuficiente"
            )
        assert error.value.codigo == "MATERIAL_INSUFICIENTE"
        lote_reciente = db.session.get(LoteMaterial, reciente)
        assert Decimal(str(lote_reciente.cantidad_base_disponible)) == Decimal("8.0000")
        movimientos = (
            db.session.query(MovimientoMaterial)
            .filter(MovimientoMaterial.lote_id.in_([antiguo, reciente]))
            .count()
        )
        assert movimientos == 4


def test_operativo_no_recibe_costos_de_materiales_lotes_y_kardex(
    client, headers_admin, headers_operativo, lotes_peps
):
    inventario_id, _, _ = lotes_peps
    consultas = (
        ("/api/v1/materiales", None, "costo_estandar_base"),
        ("/api/v1/inventario/material", "material_id", "costo_estandar_base"),
        (
            "/api/v1/inventario/material/lotes",
            "inventario_material_id",
            "costo_unitario_base",
        ),
        (
            "/api/v1/inventario/material/movimientos",
            "inventario_material_id",
            "costo_unitario_base",
        ),
    )
    for ruta, filtro, campo in consultas:
        sufijo = f"?{filtro}={inventario_id}" if filtro else ""
        operativo = client.get(ruta + sufijo, headers=headers_operativo)
        assert operativo.status_code == 200, (ruta, operativo.get_json())
        items = operativo.get_json()["items"]
        assert items, ruta
        assert all(campo not in item for item in items), ruta

        admin = client.get(ruta + sufijo, headers=headers_admin)
        assert admin.status_code == 200, ruta
        assert campo in admin.get_json()["items"][0], ruta


def test_roles_de_catalogos_y_politicas(client, headers_admin, headers_operativo, headers_cliente):
    assert client.get("/api/v1/materiales").status_code == 401
    assert client.get("/api/v1/materiales", headers=headers_cliente).status_code == 403
    assert client.get("/api/v1/materiales", headers=headers_operativo).status_code == 200
    assert client.post("/api/v1/materiales", json={}, headers=headers_operativo).status_code == 403
    assert (
        client.patch(
            "/api/v1/inventario/material/1/politica", json={}, headers=headers_operativo
        ).status_code
        == 403
    )
    assert client.get("/api/v1/proveedores", headers=headers_operativo).status_code == 403
    assert client.get("/api/v1/proveedores", headers=headers_admin).status_code == 200


def test_proveedores_crud_y_evaluacion(client, headers_admin, limpieza_fase3):
    sufijo = secrets.token_hex(4).upper()
    cuerpo = {
        "razon_social": f"Proveedor Prueba {sufijo}",
        "nombre_comercial": f"Taller {sufijo}",
        "contacto": "Contacto Prueba",
        "telefono": "1234567890",
        "correo": f"proveedor-{sufijo.lower()}@example.com",
        "direccion": "Calle de pruebas 123",
        "condiciones_pago": "Contado",
    }
    creado = client.post("/api/v1/proveedores", json=cuerpo, headers=headers_admin)
    assert creado.status_code == 201, creado.get_json()
    proveedor = creado.get_json()
    proveedor_id = proveedor["id"]
    limpieza_fase3.al_final("DELETE FROM proveedor WHERE id = :id", {"id": proveedor_id})

    editado = client.patch(
        f"/api/v1/proveedores/{proveedor_id}",
        json={"contacto": "Nuevo contacto"},
        headers=headers_admin,
    )
    assert editado.status_code == 200, editado.get_json()
    assert editado.get_json()["contacto"] == "Nuevo contacto"

    evaluacion = client.get("/api/v1/proveedores/evaluacion", headers=headers_admin)
    assert evaluacion.status_code == 200, evaluacion.get_json()
    assert "items" in evaluacion.get_json()

    borrado = client.delete(f"/api/v1/proveedores/{proveedor_id}", headers=headers_admin)
    assert borrado.status_code == 204


def test_materiales_crud_y_costos_solo_admin(app, client, headers_admin, headers_operativo, limpieza_fase3):
    with app.app_context():
        categoria_id = db.session.scalar(
            select(CategoriaMaterial.id).where(CategoriaMaterial.nombre == "Empaque")
        )
    sufijo = secrets.token_hex(3).upper()
    cuerpo = {
        "categoria_material_id": categoria_id,
        "codigo": f"TST-{sufijo}",
        "nombre": f"Material prueba {sufijo}",
        "unidad_base": "PZA",
        "unidad_compra": "pieza",
        "factor_compra_base": "1.0000",
        "costo_estandar_base": "3.000000",
        "merma_estandar_pct": "0.00",
    }
    creado = client.post("/api/v1/materiales", json=cuerpo, headers=headers_admin)
    assert creado.status_code == 201, creado.get_json()
    material_id = creado.get_json()["id"]
    assert "costo_estandar_base" in creado.get_json()

    limpieza_fase3("DELETE FROM inventario_material WHERE material_id = :id", {"id": material_id})
    limpieza_fase3("DELETE FROM material WHERE id = :id", {"id": material_id})

    operativo = client.get(f"/api/v1/materiales/{material_id}", headers=headers_operativo)
    assert operativo.status_code == 200
    assert "costo_estandar_base" not in operativo.get_json()

    borrado = client.delete(f"/api/v1/materiales/{material_id}", headers=headers_admin)
    assert borrado.status_code == 204
