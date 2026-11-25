"""Pruebas de integración de la Fase 5 (M07–M09) contra MySQL real."""

import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.extensions import db
from app.models import Alerta, CausaMerma, Pedido, PedidoEvento, StockVariante, Venta
from tests.conftest import iniciar_sesion

DIRECCION = {
    "tipo": "ENVIO",
    "alias": "Casa",
    "destinatario": "Cliente Prueba",
    "telefono": "1234567890",
    "calle": "Calle Falsa",
    "numero_ext": "123",
    "colonia": "Centro",
    "municipio": "León",
    "estado": "Guanajuato",
    "codigo_postal": "37000",
}


def _headers(client, usuario):
    return iniciar_sesion(client, usuario["correo"], usuario["password"])


def _pago(**extra):
    datos = {
        "direccion": DIRECCION,
        "metodo_pago": "TARJETA",
        "numero_tarjeta": "4242424242424242",
        "titular": "Cliente Prueba",
        "vence_mes": 12,
        "vence_anio": 2030,
        "cvv": "123",
    }
    datos.update(extra)
    return datos


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def comercial(app, client, tienda):
    ventas = set()
    pedidos = set()

    def crear_venta(producto, usuario=None, entregado=True, cantidad=1):
        usuario = usuario or tienda["crear_cliente"]()
        headers = _headers(client, usuario)
        assert client.put(
            "/api/v1/carrito/lineas",
            headers=headers,
            json={"variante_id": producto["variante_id"], "cantidad": cantidad},
        ).status_code == 200
        respuesta = client.post(
            "/api/v1/checkout/pagar",
            headers={**headers, "Idempotency-Key": f"f5-{secrets.token_hex(8)}"},
            json=_pago(),
        )
        assert respuesta.status_code == 201, respuesta.get_json()
        venta_id = respuesta.get_json()["venta"]["id"]
        pedido_id = respuesta.get_json()["pedido"]["id"]
        ventas.add(venta_id)
        pedidos.add(pedido_id)
        if entregado:
            with app.app_context():
                pedido = db.session.get(Pedido, pedido_id)
                pedido.estado = "ENTREGADO"
                pedido.estado_desde = _ahora()
                pedido.entregado_en = _ahora()
                db.session.add(
                    PedidoEvento(
                        pedido_id=pedido_id,
                        estado="ENTREGADO",
                        descripcion="Entrega simulada para pruebas",
                        visible_cliente=True,
                    )
                )
                db.session.commit()
        return {
            "usuario": usuario,
            "headers": headers,
            "venta_id": venta_id,
            "pedido_id": pedido_id,
        }

    def linea_venta(venta_id):
        with app.app_context():
            fila = db.session.execute(
                text("SELECT id FROM venta_linea WHERE venta_id = :id ORDER BY id LIMIT 1"),
                {"id": venta_id},
            ).scalar()
            assert fila is not None
            return fila

    yield {"crear_venta": crear_venta, "linea_venta": linea_venta, "ventas": ventas}

    if not ventas:
        return
    with app.app_context():
        ids = list(ventas)
        filas_devolucion = db.session.execute(
            text(
                "SELECT id, venta_reemplazo_id FROM devolucion "
                "WHERE venta_id IN :ids OR venta_reemplazo_id IN :ids"
            ).bindparams(db.bindparam("ids", ids, expanding=True))
        ).all()
        devoluciones = [fila[0] for fila in filas_devolucion]
        reemplazos = {fila[1] for fila in filas_devolucion if fila[1]}
        lineas_devolucion = []
        if devoluciones:
            lineas_devolucion = [
                fila[0]
                for fila in db.session.execute(
                    text("SELECT id FROM devolucion_linea WHERE devolucion_id IN :ids")
                    .bindparams(db.bindparam("ids", devoluciones, expanding=True))
                ).all()
            ]
            db.session.execute(
                text("DELETE FROM merma WHERE devolucion_linea_id IN :ids").bindparams(
                    db.bindparam("ids", lineas_devolucion, expanding=True)
                )
            )
            db.session.execute(
                text("DELETE FROM devolucion_evidencia WHERE devolucion_id IN :ids")
                .bindparams(db.bindparam("ids", devoluciones, expanding=True))
            )
            db.session.execute(
                text("DELETE FROM devolucion_linea WHERE devolucion_id IN :ids")
                .bindparams(db.bindparam("ids", devoluciones, expanding=True))
            )
            db.session.execute(
                text("DELETE FROM alerta WHERE entidad_tipo = 'devolucion' "
                     "AND entidad_id IN :ids")
                .bindparams(db.bindparam("ids", devoluciones, expanding=True))
            )
            db.session.execute(
                text("DELETE FROM devolucion WHERE id IN :ids").bindparams(
                    db.bindparam("ids", devoluciones, expanding=True)
                )
            )

        db.session.commit()


def test_pedidos_admin_lista_detalle_actualizacion_y_cancelacion(
    app, client, headers_admin, headers_operativo, headers_cliente, comercial, tienda
):
    producto = tienda["crear_producto"](existencia=5)
    venta = comercial["crear_venta"](producto, entregado=False)

    lista = client.get("/api/v1/pedidos?estado=CONFIRMADO", headers=headers_admin)
    assert lista.status_code == 200, lista.get_json()
    assert any(item["id"] == venta["pedido_id"] for item in lista.get_json()["items"])

    detalle = client.get(f"/api/v1/pedidos/{venta['pedido_id']}", headers=headers_operativo)
    assert detalle.status_code == 200
    assert detalle.get_json()["folio"] is not None

    actualizado = client.patch(
        f"/api/v1/pedidos/{venta['pedido_id']}",
        headers=headers_admin,
        json={"prioridad": "ALTA", "nota": "Priorizar por cliente frecuente"},
    )
    assert actualizado.status_code == 200, actualizado.get_json()
    assert actualizado.get_json()["prioridad"] == "ALTA"
    eventos = actualizado.get_json()["eventos"]
    assert any(evento["visible_cliente"] is False for evento in eventos)

    rechazo = client.patch(
        f"/api/v1/pedidos/{venta['pedido_id']}",
        headers=headers_cliente,
        json={"prioridad": "ALTA"},
    )
    assert rechazo.status_code == 403

    cancelado = client.post(
        f"/api/v1/pedidos/{venta['pedido_id']}/cancelar",
        headers=headers_admin,
        json={"motivo": "Cancelación administrativa de prueba"},
    )
    assert cancelado.status_code == 200, cancelado.get_json()
    with app.app_context():
        venta_db = db.session.get(Venta, venta["venta_id"])
        assert venta_db.estado == "CANCELADA"
        stock = db.session.execute(
            text("SELECT reservado FROM stock_variante WHERE variante_id = :id"),
            {"id": producto["variante_id"]},
        ).scalar()
        assert stock == 0


def test_pedidos_pendientes_produccion(app, client, headers_admin, tienda, comercial):
    producto = tienda["crear_producto"](existencia=0, permite_bajo_pedido=True)
    venta = comercial["crear_venta"](producto, entregado=False)

    respuesta = client.get("/api/v1/pedidos/pendientes-produccion", headers=headers_admin)
    assert respuesta.status_code == 200, respuesta.get_json()
    assert any(
        item["sku"] == "TST-" and item["demanda"] >= 1
        for item in respuesta.get_json()["items"]
    ) or respuesta.get_json()["total"] >= 1
    with app.app_context():
        pedido = db.session.get(Pedido, venta["pedido_id"])
        assert pedido.estado == "EN_PRODUCCION"


def test_venta_manual_pago_pendiente_validacion_y_cancelacion(
    app, client, headers_admin, tienda
):
    producto = tienda["crear_producto"](existencia=3)
    cliente = tienda["crear_cliente"]()
    manual = client.post(
        "/api/v1/ventas/manual",
        headers=headers_admin,
        json={
            "cliente_id": cliente["id"],
            "lineas": [{"sku": producto["sku"], "cantidad": 1}],
            "direccion": DIRECCION,
            "metodo_pago": "TRANSFERENCIA",
            "estado_pago": "PENDIENTE",
        },
    )
    assert manual.status_code == 201, manual.get_json()
    datos = manual.get_json()
    assert datos["estado_pago"] == "PENDIENTE"
    assert datos["pedido"]["estado"] == "RECIBIDO"
    venta_id = datos["id"]

    with app.app_context():
        assert (
            db.session.scalar(
                text(
                    "SELECT COUNT(*) FROM alerta WHERE clave_unica = :clave "
                    "AND estado = 'ABIERTA'"
                ),
                {"clave": f"PAGO_PENDIENTE:{venta_id}"},
            )
            == 1
        )

    pagada = client.post(
        f"/api/v1/ventas/{venta_id}/pago",
        headers=headers_admin,
        json={"accion": "APROBAR", "metodo_pago": "TRANSFERENCIA"},
    )
    assert pagada.status_code == 200, pagada.get_json()
    assert pagada.get_json()["estado_pago"] == "PAGADA"
    assert pagada.get_json()["pedido"]["estado"] in ("CONFIRMADO", "EN_PRODUCCION")

    cancelada = client.post(
        f"/api/v1/ventas/{venta_id}/cancelar",
        headers=headers_admin,
        json={"motivo": "Cliente canceló en mostrador"},
    )
    assert cancelada.status_code == 200, cancelada.get_json()
    assert cancelada.get_json()["estado"] == "CANCELADA"
    with app.app_context():
        assert (
            db.session.scalar(
                text(
                    "SELECT COUNT(*) FROM pago WHERE venta_id = :id "
                    "AND tipo = 'REEMBOLSO' AND estado = 'APROBADO'"
                ),
                {"id": venta_id},
            )
            == 1
        )
        assert (
            db.session.scalar(
                text("SELECT reservado FROM stock_variante WHERE variante_id = :id"),
                {"id": producto["variante_id"]},
            )
            == 0
        )


def test_venta_manual_sku_inconsistente_y_descuentos_crud(
    client, headers_admin, headers_cliente, tienda
):
    producto = tienda["crear_producto"](existencia=2)
    cliente = tienda["crear_cliente"]()
    invalida = client.post(
        "/api/v1/ventas/manual",
        headers=headers_admin,
        json={
            "cliente_id": cliente["id"],
            "lineas": [{"sku": "NO-EXISTE", "cantidad": 1}],
            "direccion": DIRECCION,
            "metodo_pago": "EFECTIVO",
        },
    )
    assert invalida.status_code == 404
    assert invalida.get_json()["codigo"] == "SKU_NO_DISPONIBLE"

    codigo = f"PROMO{secrets.token_hex(3).upper()}"
    creado = client.post(
        "/api/v1/descuentos",
        headers=headers_admin,
        json={
            "codigo": codigo,
            "nombre": "Descuento de prueba",
            "tipo": "PORCENTAJE",
            "valor": "10.00",
            "aplicacion": "CUPON",
            "vigente_desde": "2026-01-01",
            "activo": True,
        },
    )
    assert creado.status_code == 201, creado.get_json()
    descuento_id = creado.get_json()["id"]
    actualizado = client.patch(
        f"/api/v1/descuentos/{descuento_id}",
        headers=headers_admin,
        json={"nombre": "Descuento editado"},
    )
    assert actualizado.status_code == 200
    assert actualizado.get_json()["nombre"] == "Descuento editado"

    assert client.get("/api/v1/descuentos", headers=headers_cliente).status_code == 403
    assert client.delete(
        f"/api/v1/descuentos/{descuento_id}", headers=headers_admin
    ).status_code == 204


def _solicitud_devolucion(pedido_id, venta_linea_id, tipo="DEVOLUCION", cambiar=None):
    lineas = [{"venta_linea_id": venta_linea_id, "cantidad": 1}]
    if cambiar:
        lineas[0]["variante_cambio_id"] = cambiar
    return {
        "pedido_id": pedido_id,
        "tipo": tipo,
        "motivo": "DEFECTO",
        "descripcion": "Prenda con defecto de confección",
        "lineas": lineas,
    }


def test_devolucion_reembolso_reingreso_y_permisos(
    app, client, headers_admin, headers_operativo, headers_cliente, comercial, tienda
):
    producto = tienda["crear_producto"](existencia=5)
    venta = comercial["crear_venta"](producto)
    linea_id = comercial["linea_venta"](venta["venta_id"])

    with app.app_context():
        antes = db.session.scalar(
            text("SELECT existencia FROM stock_variante WHERE variante_id = :id"),
            {"id": producto["variante_id"]},
        )

    solicitud = client.post(
        "/api/v1/devoluciones",
        headers=venta["headers"],
        json=_solicitud_devolucion(venta["pedido_id"], linea_id),
    )
    assert solicitud.status_code == 201, solicitud.get_json()
    devolucion_id = solicitud.get_json()["id"]
    assert solicitud.get_json()["estado"] == "SOLICITADA"

    listado_cliente = client.get("/api/v1/devoluciones", headers=venta["headers"])
    assert listado_cliente.status_code == 200
    assert [item["id"] for item in listado_cliente.get_json()["items"]] == [devolucion_id]

    listado_operativo = client.get("/api/v1/devoluciones", headers=headers_operativo)
    assert listado_operativo.status_code == 200
    item_operativo = next(
        item
        for item in listado_operativo.get_json()["items"]
        if item["id"] == devolucion_id
    )
    assert "reembolso_monto" not in item_operativo

    assert client.patch(
        f"/api/v1/devoluciones/{devolucion_id}/aprobar", headers=venta["headers"]
    ).status_code == 403

    aprobada = client.patch(
        f"/api/v1/devoluciones/{devolucion_id}/aprobar", headers=headers_admin
    )
    assert aprobada.status_code == 200
    assert aprobada.get_json()["estado"] == "APROBADA"

    recibida = client.post(
        f"/api/v1/devoluciones/{devolucion_id}/recibir", headers=headers_operativo
    )
    assert recibida.status_code == 200
    assert recibida.get_json()["estado"] == "RECIBIDA"

    with app.app_context():
        causa = db.session.query(CausaMerma).filter_by(nombre="Error de confección").first()
        assert causa is not None
        causa_id = causa.id

    dictamen = client.post(
        f"/api/v1/devoluciones/{devolucion_id}/dictamen",
        headers=headers_operativo,
        json={
            "lineas": [
                {
                    "devolucion_linea_id": solicitud.get_json()["lineas"][0]["id"],
                    "dictamen": "REINGRESO",
                }
            ]
        },
    )
    assert dictamen.status_code == 200, dictamen.get_json()

    resuelta = client.post(
        f"/api/v1/devoluciones/{devolucion_id}/resolver",
        headers=headers_admin,
        json={"resolucion": "REEMBOLSO"},
    )
    assert resuelta.status_code == 200, resuelta.get_json()
    assert resuelta.get_json()["estado"] == "RESUELTA"
    assert Decimal(resuelta.get_json()["reembolso_monto"]) > 0

    with app.app_context():
        despues = db.session.scalar(
            text("SELECT existencia FROM stock_variante WHERE variante_id = :id"),
            {"id": producto["variante_id"]},
        )
        assert despues == antes + 1
        assert (
            db.session.scalar(
                text(
                    "SELECT COUNT(*) FROM pago WHERE venta_id = :id "
                    "AND tipo = 'REEMBOLSO' AND estado = 'APROBADO'"
                ),
                {"id": venta["venta_id"]},
            )
            == 1
        )
        assert (
            db.session.scalar(
                text(
                    "SELECT COUNT(*) FROM movimiento_producto WHERE documento_tipo = "
                    "'DEVOLUCION' AND documento_id = :id AND tipo = 'REINGRESO'"
                ),
                {"id": devolucion_id},
            )
            == 1
        )


def test_devolucion_cambio_genera_venta_reemplazo(
    app, client, headers_admin, headers_operativo, headers_cliente, comercial, tienda
):
    original = tienda["crear_producto"](existencia=5)
    reemplazo = tienda["crear_producto"](existencia=5)
    venta = comercial["crear_venta"](original)
    linea_id = comercial["linea_venta"](venta["venta_id"])

    solicitud = client.post(
        "/api/v1/devoluciones",
        headers=venta["headers"],
        json=_solicitud_devolucion(
            venta["pedido_id"],
            linea_id,
            tipo="CAMBIO",
            cambiar=reemplazo["variante_id"],
        ),
    )
    assert solicitud.status_code == 201, solicitud.get_json()
    devolucion_id = solicitud.get_json()["id"]
    assert client.patch(
        f"/api/v1/devoluciones/{devolucion_id}/aprobar", headers=headers_admin
    ).status_code == 200
    assert client.post(
        f"/api/v1/devoluciones/{devolucion_id}/recibir", headers=headers_operativo
    ).status_code == 200
    dictamen = client.post(
        f"/api/v1/devoluciones/{devolucion_id}/dictamen",
        headers=headers_operativo,
        json={
            "lineas": [
                {
                    "devolucion_linea_id": solicitud.get_json()["lineas"][0]["id"],
                    "dictamen": "REINGRESO",
                }
            ]
        },
    )
    assert dictamen.status_code == 200, dictamen.get_json()
    resuelta = client.post(
        f"/api/v1/devoluciones/{devolucion_id}/resolver",
        headers=headers_admin,
        json={"resolucion": "CAMBIO"},
    )
    assert resuelta.status_code == 200, resuelta.get_json()
    reemplazo_id = resuelta.get_json()["venta_reemplazo_id"]
    assert reemplazo_id is not None

    detalle = client.get(f"/api/v1/ventas/{reemplazo_id}", headers=headers_admin)
    assert detalle.status_code == 200
    assert detalle.get_json()["canal"] == "CAMBIO"
    assert detalle.get_json()["total"] == "0.00"


@pytest.mark.parametrize(
    "metodo,ruta",
    [
        ("get", "/api/v1/ventas"),
        ("get", "/api/v1/pedidos"),
        ("get", "/api/v1/devoluciones"),
    ],
)
def test_endpoints_comerciales_requieren_sesion(client, metodo, ruta):
    assert getattr(client, metodo)(ruta).status_code == 401
