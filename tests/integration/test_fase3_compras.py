"""Pruebas de integración de compras y recepciones (M14)."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import secrets

from app.extensions import db
from app.models import (
    Cotizacion,
    CotizacionLinea,
    LoteMaterial,
    Merma,
    OrdenCompra,
    OrdenCompraLinea,
    Recepcion,
    RecepcionLinea,
    Requisicion,
    RequisicionLinea,
    Usuario,
)


@pytest.fixture
def orden_para_recibir(app, datos_fase3, limpieza_fase3):
    with app.app_context():
        usuario = (
            db.session.query(Usuario)
            .join(Usuario.rol)
            .filter_by(codigo="ADMIN")
            .first()
        )
        assert usuario is not None, "Se requiere el administrador sembrado"
        proveedor_id = datos_fase3["crear_proveedor"]()
        inventario_id = datos_fase3["inventario_material_id"]
        sufijo = secrets.token_hex(4).upper()
        cantidad = Decimal("1.00")
        precio = Decimal("5000.00")

        requisicion = Requisicion(
            folio=f"REQ-TST-{sufijo}",
            origen="MANUAL",
            estado="COMPRA_EMITIDA",
            prioridad="NORMAL",
            solicitada_por=usuario.id,
            fecha=datetime.utcnow(),
        )
        db.session.add(requisicion)
        db.session.flush()
        req_linea = RequisicionLinea(
            requisicion_id=requisicion.id,
            inventario_material_id=inventario_id,
            cantidad_base_faltante=Decimal("64.8000"),
            cantidad_compra_sugerida=cantidad,
            cantidad_compra_atendida=cantidad,
        )
        db.session.add(req_linea)
        db.session.flush()

        cotizacion = Cotizacion(
            requisicion_id=requisicion.id,
            proveedor_id=proveedor_id,
            fecha=datetime.utcnow(),
            vigencia_hasta=date.today() + timedelta(days=15),
            plazo_dias=7,
            estado="ELEGIDA",
            total=cantidad * precio,
        )
        db.session.add(cotizacion)
        db.session.flush()
        cot_linea = CotizacionLinea(
            cotizacion_id=cotizacion.id,
            requisicion_linea_id=req_linea.id,
            cantidad_compra=cantidad,
            precio_unitario_compra=precio,
            subtotal=cantidad * precio,
        )
        db.session.add(cot_linea)

        orden = OrdenCompra(
            folio=f"OC-TST-{sufijo}",
            proveedor_id=proveedor_id,
            requisicion_id=requisicion.id,
            cotizacion_id=cotizacion.id,
            estado="EMITIDA",
            fecha_emision=datetime.utcnow(),
            fecha_prometida=date.today() + timedelta(days=7),
            total=cantidad * precio,
            condiciones_pago="Contado",
            creada_por=usuario.id,
        )
        db.session.add(orden)
        db.session.flush()
        orden_linea = OrdenCompraLinea(
            orden_compra_id=orden.id,
            inventario_material_id=inventario_id,
            cantidad_compra=cantidad,
            precio_unitario_compra=precio,
            subtotal=cantidad * precio,
            cantidad_base_aceptada=0,
        )
        db.session.add(orden_linea)
        db.session.commit()
        datos = {
            "orden_id": orden.id,
            "orden_linea_id": orden_linea.id,
            "inventario_id": inventario_id,
            "cotizacion_id": cotizacion.id,
            "cotizacion_linea_id": cot_linea.id,
            "requisicion_id": requisicion.id,
            "requisicion_linea_id": req_linea.id,
            "base_pedida": "64.8000",
        }

    limpieza_fase3(
        "DELETE FROM movimiento_material WHERE lote_id IN "
        "(SELECT id FROM lote_material WHERE recepcion_linea_id IN "
        "(SELECT id FROM recepcion_linea WHERE orden_compra_linea_id IN "
        "(SELECT id FROM orden_compra_linea WHERE orden_compra_id = :id)))",
        {"id": datos["orden_id"]},
    )
    limpieza_fase3(
        "DELETE FROM merma WHERE recepcion_linea_id IN "
        "(SELECT id FROM recepcion_linea WHERE orden_compra_linea_id IN "
        "(SELECT id FROM orden_compra_linea WHERE orden_compra_id = :id))",
        {"id": datos["orden_id"]},
    )
    limpieza_fase3(
        "DELETE FROM lote_material WHERE recepcion_linea_id IN "
        "(SELECT id FROM recepcion_linea WHERE orden_compra_linea_id IN "
        "(SELECT id FROM orden_compra_linea WHERE orden_compra_id = :id))",
        {"id": datos["orden_id"]},
    )
    limpieza_fase3(
        "DELETE FROM recepcion_linea WHERE orden_compra_linea_id IN "
        "(SELECT id FROM orden_compra_linea WHERE orden_compra_id = :id)",
        {"id": datos["orden_id"]},
    )
    limpieza_fase3("DELETE FROM recepcion WHERE orden_compra_id = :id", {"id": datos["orden_id"]})
    limpieza_fase3("DELETE FROM orden_compra_linea WHERE orden_compra_id = :id", {"id": datos["orden_id"]})
    limpieza_fase3("DELETE FROM orden_compra WHERE id = :id", {"id": datos["orden_id"]})
    limpieza_fase3(
        "DELETE FROM cotizacion_linea WHERE cotizacion_id IN "
        "(SELECT id FROM cotizacion WHERE requisicion_id = :id)",
        {"id": datos["requisicion_id"]},
    )
    limpieza_fase3("DELETE FROM cotizacion WHERE requisicion_id = :id", {"id": datos["requisicion_id"]})
    limpieza_fase3("DELETE FROM requisicion_linea WHERE requisicion_id = :id", {"id": datos["requisicion_id"]})
    limpieza_fase3("DELETE FROM requisicion WHERE id = :id", {"id": datos["requisicion_id"]})
    return datos


def _cuerpo_recepcion(datos, aceptada="60.0000", rechazada="4.8000"):
    return {
        "orden_compra_id": datos["orden_id"],
        "documento_proveedor": "FACT-001",
        "lineas": [
            {
                "orden_compra_linea_id": datos["orden_linea_id"],
                "cantidad_base_medida": "64.8000",
                "cantidad_base_aceptada": aceptada,
                "cantidad_base_rechazada": rechazada,
                "motivo_rechazo": "Defecto de tela",
            }
        ],
    }


def test_recepcion_idempotente_crea_lote_solo_aceptado_y_merma(
    app, client, headers_operativo, orden_para_recibir, limpieza_fase3
):
    clave = f"test-rec-{secrets.token_hex(6)}"
    respuesta = client.post(
        "/api/v1/recepciones",
        json=_cuerpo_recepcion(orden_para_recibir),
        headers={**headers_operativo, "Idempotency-Key": clave},
    )
    assert respuesta.status_code == 201, respuesta.get_json()
    primera = respuesta.get_json()
    assert primera["recepcion"]["folio"].startswith("REC-")
    assert primera["orden_compra"]["estado"] == "PARCIAL"

    repetida = client.post(
        "/api/v1/recepciones",
        json=_cuerpo_recepcion(orden_para_recibir),
        headers={**headers_operativo, "Idempotency-Key": clave},
    )
    assert repetida.status_code == 201
    assert repetida.get_json() == primera

    with app.app_context():
        recepciones = (
            db.session.query(Recepcion)
            .filter_by(orden_compra_id=orden_para_recibir["orden_id"])
            .all()
        )
        assert len(recepciones) == 1
        recepcion_id = recepciones[0].id
        lotes = (
            db.session.query(LoteMaterial)
            .join(RecepcionLinea, LoteMaterial.recepcion_linea_id == RecepcionLinea.id)
            .filter(RecepcionLinea.recepcion_id == recepcion_id)
            .all()
        )
        assert len(lotes) == 1
        assert Decimal(str(lotes[0].cantidad_base_recibida)) == Decimal("60.0000")
        assert Decimal(str(lotes[0].cantidad_base_disponible)) == Decimal("60.0000")
        mermas = (
            db.session.query(Merma)
            .join(RecepcionLinea, Merma.recepcion_linea_id == RecepcionLinea.id)
            .filter(RecepcionLinea.recepcion_id == recepcion_id)
            .all()
        )
        assert len(mermas) == 1
        assert Decimal(str(mermas[0].cantidad)) == Decimal("4.8000")
        assert mermas[0].etapa == "RECEPCION"

        limpieza_fase3(
            "DELETE FROM movimiento_material WHERE lote_id IN "
            "(SELECT id FROM lote_material WHERE recepcion_linea_id IN "
            "(SELECT id FROM recepcion_linea WHERE recepcion_id = :id))",
            {"id": recepcion_id},
        )
        limpieza_fase3("DELETE FROM merma WHERE recepcion_linea_id IN (SELECT id FROM recepcion_linea WHERE recepcion_id = :id)", {"id": recepcion_id})
        limpieza_fase3("DELETE FROM lote_material WHERE recepcion_linea_id IN (SELECT id FROM recepcion_linea WHERE recepcion_id = :id)", {"id": recepcion_id})
        limpieza_fase3("DELETE FROM recepcion_linea WHERE recepcion_id = :id", {"id": recepcion_id})
        limpieza_fase3("DELETE FROM recepcion WHERE id = :id", {"id": recepcion_id})
        limpieza_fase3("DELETE FROM idempotencia_operacion WHERE clave = :clave", {"clave": clave})


def test_recepcion_rechaza_misma_clave_con_peticion_distinta(
    client, headers_operativo, orden_para_recibir, limpieza_fase3
):
    clave = f"test-rec-{secrets.token_hex(6)}"
    primera = client.post(
        "/api/v1/recepciones",
        json=_cuerpo_recepcion(orden_para_recibir),
        headers={**headers_operativo, "Idempotency-Key": clave},
    )
    assert primera.status_code == 201
    distint = _cuerpo_recepcion(orden_para_recibir, aceptada="50.0000", rechazada="14.8000")
    segunda = client.post(
        "/api/v1/recepciones",
        json=distint,
        headers={**headers_operativo, "Idempotency-Key": clave},
    )
    assert segunda.status_code == 409
    assert segunda.get_json()["codigo"] == "IDEMPOTENCIA_CONFLICTO"
    limpieza_fase3("DELETE FROM idempotencia_operacion WHERE clave = :clave", {"clave": clave})


def test_recepcion_valida_conciliacion_y_roles(
    app, client, headers_operativo, headers_admin, headers_cliente, orden_para_recibir, limpieza_fase3
):
    claves = [f"test-rec-{secrets.token_hex(6)}" for _ in range(2)]
    sin_cuadrar = _cuerpo_recepcion(orden_para_recibir, aceptada="60.0000", rechazada="1.0000")
    respuesta = client.post(
        "/api/v1/recepciones",
        json=sin_cuadrar,
        headers={**headers_operativo, "Idempotency-Key": claves[0]},
    )
    assert respuesta.status_code == 422
    assert respuesta.get_json()["codigo"] == "CANTIDADES_NO_CONCUADRAN"

    cliente = client.post(
        "/api/v1/recepciones",
        json=_cuerpo_recepcion(orden_para_recibir),
        headers={**headers_cliente, "Idempotency-Key": f"test-rec-{secrets.token_hex(6)}"},
    )
    assert cliente.status_code == 403

    anonima = client.post(
        "/api/v1/recepciones", json=_cuerpo_recepcion(orden_para_recibir)
    )
    assert anonima.status_code == 401

    admin = client.post(
        "/api/v1/recepciones",
        json=_cuerpo_recepcion(orden_para_recibir),
        headers={**headers_admin, "Idempotency-Key": claves[1]},
    )
    assert admin.status_code == 201, admin.get_json()

    with app.app_context():
        recepcion_id = (
            db.session.query(Recepcion)
            .filter_by(orden_compra_id=orden_para_recibir["orden_id"])
            .first()
            .id
        )
        limpieza_fase3(
            "DELETE FROM movimiento_material WHERE lote_id IN "
            "(SELECT id FROM lote_material WHERE recepcion_linea_id IN "
            "(SELECT id FROM recepcion_linea WHERE recepcion_id = :id))",
            {"id": recepcion_id},
        )
        limpieza_fase3("DELETE FROM merma WHERE recepcion_linea_id IN (SELECT id FROM recepcion_linea WHERE recepcion_id = :id)", {"id": recepcion_id})
        limpieza_fase3("DELETE FROM lote_material WHERE recepcion_linea_id IN (SELECT id FROM recepcion_linea WHERE recepcion_id = :id)", {"id": recepcion_id})
        limpieza_fase3("DELETE FROM recepcion_linea WHERE recepcion_id = :id", {"id": recepcion_id})
        limpieza_fase3("DELETE FROM recepcion WHERE id = :id", {"id": recepcion_id})
    for clave in claves:
        limpieza_fase3("DELETE FROM idempotencia_operacion WHERE clave = :clave", {"clave": clave})


def test_flujo_requisicion_cotizacion_orden_y_pdf(
    client, headers_admin, headers_operativo, datos_fase3, limpieza_fase3
):
    proveedor_id = datos_fase3["crear_proveedor"]()
    inventario_id = datos_fase3["inventario_material_id"]

    req = client.post(
        "/api/v1/requisiciones",
        json={
            "origen": "MANUAL",
            "lineas": [
                {
                    "inventario_material_id": inventario_id,
                    "cantidad_base_faltante": "64.8000",
                }
            ],
        },
        headers=headers_operativo,
    )
    assert req.status_code == 201, req.get_json()
    requisicion = req.get_json()
    assert requisicion["folio"].startswith("REQ-")
    assert Decimal(requisicion["lineas"][0]["cantidad_compra_sugerida"]) > 0

    cot = client.post(
        f"/api/v1/requisiciones/{requisicion['id']}/cotizaciones",
        json={
            "proveedor_id": proveedor_id,
            "plazo_dias": 7,
            "lineas": [
                {
                    "requisicion_linea_id": requisicion["lineas"][0]["id"],
                    "cantidad_compra": "1.00",
                    "precio_unitario_compra": "5000.00",
                }
            ],
        },
        headers=headers_admin,
    )
    assert cot.status_code == 201, cot.get_json()
    cotizacion = cot.get_json()
    assert Decimal(cotizacion["total"]) == Decimal("5000.00")

    elegida = client.post(
        f"/api/v1/cotizaciones/{cotizacion['id']}/elegir", headers=headers_admin
    )
    assert elegida.status_code == 200, elegida.get_json()
    orden = elegida.get_json()
    assert orden["folio"].startswith("OC-")
    assert orden["estado"] == "BORRADOR"

    emitida = client.post(
        f"/api/v1/ordenes-compra/{orden['id']}/emitir", headers=headers_admin
    )
    assert emitida.status_code == 200
    assert emitida.get_json()["estado"] == "EMITIDA"

    pdf = client.get(f"/api/v1/ordenes-compra/{orden['id']}/pdf", headers=headers_admin)
    assert pdf.status_code == 200
    assert pdf.data.startswith(b"%PDF")
    assert pdf.mimetype == "application/pdf"

    limpieza_fase3("DELETE FROM orden_compra_linea WHERE orden_compra_id = :id", {"id": orden["id"]})
    limpieza_fase3("DELETE FROM orden_compra WHERE id = :id", {"id": orden["id"]})
    limpieza_fase3("DELETE FROM cotizacion_linea WHERE cotizacion_id = :id", {"id": cotizacion["id"]})
    limpieza_fase3("DELETE FROM cotizacion WHERE id = :id", {"id": cotizacion["id"]})
    limpieza_fase3("DELETE FROM requisicion_linea WHERE requisicion_id = :id", {"id": requisicion["id"]})
    limpieza_fase3("DELETE FROM requisicion WHERE id = :id", {"id": requisicion["id"]})
