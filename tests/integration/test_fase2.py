"""Pruebas de integración de la Fase 2 (M02–M06) contra MySQL real."""

import secrets

from sqlalchemy import text

from app.extensions import db
from app.models import ProductoImagen
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


def _clave():
    return f"test-{secrets.token_hex(8)}"


def test_catalogo_publico_no_expone_existencias(app, client, tienda):
    producto = tienda["crear_producto"](existencia=1)
    respuesta = client.get("/api/v1/catalogo")
    assert respuesta.status_code == 200
    items = [item for item in respuesta.get_json() if item["id"] == producto["producto_id"]]
    assert len(items) == 1
    variante = items[0]["variantes"][0]
    assert variante["disponibilidad"] == "Pocas unidades"
    assert "existencia" not in variante and "reservado" not in variante

    detalle = client.get(f"/api/v1/catalogo/{producto['producto_id']}")
    assert detalle.status_code == 200
    texto = str(detalle.get_json()).lower()
    for dato in ("costo", "precio_compra", "margen", "existencia"):
        assert dato not in texto

    filtrado = client.get("/api/v1/catalogo?color=NG")
    assert all(
        item["id"] != producto["producto_id"] for item in filtrado.get_json()
    )


def test_cuenta_direcciones_medios_pago_y_cobertura(client, tienda):
    cobertura = client.get("/api/v1/envio/cobertura?cp=37000")
    assert cobertura.status_code == 200
    assert cobertura.get_json()["cobertura"] is True
    assert client.get("/api/v1/envio/cobertura?cp=abc").status_code == 400

    usuario = tienda["crear_cliente"]()
    headers = _headers(client, usuario)

    assert client.get("/api/v1/cuenta/direcciones").status_code == 401
    direccion = client.post(
        "/api/v1/cuenta/direcciones", headers=headers, json=DIRECCION
    )
    assert direccion.status_code == 201
    direccion_id = direccion.get_json()["id"]
    listado = client.get("/api/v1/cuenta/direcciones", headers=headers)
    assert [item["id"] for item in listado.get_json()] == [direccion_id]
    actualizada = client.patch(
        f"/api/v1/cuenta/direcciones/{direccion_id}",
        headers=headers,
        json={"alias": "Oficina", "predeterminada": True},
    )
    assert actualizada.get_json()["alias"] == "Oficina"
    assert client.delete(
        f"/api/v1/cuenta/direcciones/{direccion_id}", headers=headers
    ).status_code == 204
    assert client.get("/api/v1/cuenta/direcciones", headers=headers).get_json() == []

    medio = client.post(
        "/api/v1/cuenta/medios-pago",
        headers=headers,
        json={
            "tipo": "CUENTA",
            "alias": "Principal",
            "titular": "Cliente Prueba",
        },
    )
    assert medio.status_code == 201
    assert medio.get_json()["saldo_simulado"] == "5000.00"
    medio_id = medio.get_json()["id"]
    assert client.patch(
        f"/api/v1/cuenta/medios-pago/{medio_id}",
        headers=headers,
        json={"alias": "Simulada"},
    ).status_code == 200
    assert client.delete(
        f"/api/v1/cuenta/medios-pago/{medio_id}", headers=headers
    ).status_code == 204
    assert client.get("/api/v1/cuenta/medios-pago", headers=headers).get_json() == []


def test_carrito_valida_cantidad_y_fusiona(client, tienda):
    producto = tienda["crear_producto"](existencia=10)
    usuario = tienda["crear_cliente"]()
    headers = _headers(client, usuario)

    exceso = client.put(
        "/api/v1/carrito/lineas",
        headers=headers,
        json={"variante_id": producto["variante_id"], "cantidad": 11},
    )
    assert exceso.status_code == 422
    assert exceso.get_json()["codigo"] == "CANTIDAD_MAXIMA"

    agregada = client.put(
        "/api/v1/carrito/lineas",
        headers=headers,
        json={"variante_id": producto["variante_id"], "cantidad": 2},
    )
    assert agregada.status_code == 200
    assert agregada.get_json()["items"][0]["comprable"] is True
    fusion = client.post(
        "/api/v1/carrito/fusionar",
        headers=headers,
        json={"lineas": [{"variante_id": producto["variante_id"], "cantidad": 1}]},
    )
    assert fusion.status_code == 200
    assert fusion.get_json()["items"][0]["cantidad"] == 3

    borrada = client.delete(
        f"/api/v1/carrito/lineas/{producto['variante_id']}", headers=headers
    )
    assert borrada.status_code == 204
    assert client.get("/api/v1/carrito", headers=headers).get_json()["items"] == []


def test_carrito_publica_comprable_por_disponibilidad(client, tienda):
    disponible = tienda["crear_producto"](existencia=10)
    bajo_pedido = tienda["crear_producto"](existencia=0, permite_bajo_pedido=True)
    agotado = tienda["crear_producto"](existencia=0, permite_bajo_pedido=False)
    usuario = tienda["crear_cliente"]()
    headers = _headers(client, usuario)

    for producto in (disponible, bajo_pedido, agotado):
        respuesta = client.put(
            "/api/v1/carrito/lineas",
            headers=headers,
            json={"variante_id": producto["variante_id"], "cantidad": 1},
        )
        assert respuesta.status_code == 200, respuesta.get_json()

    carrito = client.get("/api/v1/carrito", headers=headers).get_json()
    lineas = {linea["variante_id"]: linea for linea in carrito["items"]}
    assert lineas[disponible["variante_id"]]["comprable"] is True
    assert lineas[bajo_pedido["variante_id"]]["comprable"] is True
    assert lineas[bajo_pedido["variante_id"]]["bajo_pedido"] is True
    assert lineas[agotado["variante_id"]]["comprable"] is False
    assert carrito["puede_pagar"] is False


def test_checkout_idempotente_y_conflicto(app, client, tienda):
    producto = tienda["crear_producto"](existencia=5)
    usuario = tienda["crear_cliente"]()
    headers = _headers(client, usuario)
    clave = _clave()

    client.put(
        "/api/v1/carrito/lineas",
        headers=headers,
        json={"variante_id": producto["variante_id"], "cantidad": 1},
    )
    cotizacion = client.post(
        "/api/v1/checkout/cotizar", headers=headers, json={"codigo_postal": "37000"}
    )
    assert cotizacion.status_code == 200, cotizacion.get_json()
    assert cotizacion.get_json()["iva_importe"] == "40.00"

    primera = client.post(
        "/api/v1/checkout/pagar", headers={**headers, "Idempotency-Key": clave}, json=_pago()
    )
    assert primera.status_code == 201, primera.get_json()
    assert primera.get_json()["resumen"]["iva_importe"] == "40.00"
    venta_id = primera.get_json()["venta"]["id"]
    segunda = client.post(
        "/api/v1/checkout/pagar", headers={**headers, "Idempotency-Key": clave}, json=_pago()
    )
    assert segunda.status_code == 201
    assert segunda.get_json()["venta"]["id"] == venta_id

    conflicto = client.post(
        "/api/v1/checkout/pagar",
        headers={**headers, "Idempotency-Key": clave},
        json=_pago(notas="Peticion distinta"),
    )
    assert conflicto.status_code == 409
    assert conflicto.get_json()["codigo"] == "IDEMPOTENCIA_CONFLICTO"

    with app.app_context():
        total_ventas = db.session.execute(
            text("SELECT COUNT(*) FROM venta WHERE usuario_id = :id"),
            {"id": usuario["id"]},
        ).scalar()
    assert total_ventas == 1


def test_pago_rechazado_no_deja_venta_pedido_ni_reserva(app, client, tienda):
    producto = tienda["crear_producto"](existencia=3)
    usuario = tienda["crear_cliente"]()
    headers = _headers(client, usuario)
    client.put(
        "/api/v1/carrito/lineas",
        headers=headers,
        json={"variante_id": producto["variante_id"], "cantidad": 1},
    )
    clave = _clave()
    respuesta = client.post(
        "/api/v1/checkout/pagar",
        headers={**headers, "Idempotency-Key": clave},
        json=_pago(numero_tarjeta="4242424242420000"),
    )
    assert respuesta.status_code in (400, 422), respuesta.get_json()

    with app.app_context():
        assert db.session.execute(
            text("SELECT COUNT(*) FROM venta WHERE usuario_id = :id"),
            {"id": usuario["id"]},
        ).scalar() == 0
        assert db.session.execute(
            text("SELECT COUNT(*) FROM pedido WHERE venta_id IN "
                 "(SELECT id FROM venta WHERE usuario_id = :id)"),
            {"id": usuario["id"]},
        ).scalar() == 0
        reservado = db.session.execute(
            text("SELECT reservado FROM stock_variante WHERE variante_id = :id"),
            {"id": producto["variante_id"]},
        ).scalar()
        assert reservado == 0
        carrito = db.session.execute(
            text(
                "SELECT COUNT(*) FROM carrito_linea WHERE variante_id = :id "
                "AND carrito_id IN (SELECT id FROM carrito WHERE usuario_id = :uid)"
            ),
            {"id": producto["variante_id"], "uid": usuario["id"]},
        ).scalar()
        assert carrito == 1


def test_ultima_unidad_dos_clientes(app, client, tienda):
    producto = tienda["crear_producto"](existencia=1, permite_bajo_pedido=True)
    primero = tienda["crear_cliente"]()
    segundo = tienda["crear_cliente"]()
    datos = _pago()

    for indice, usuario in enumerate((primero, segundo)):
        headers = _headers(client, usuario)
        client.put(
            "/api/v1/carrito/lineas",
            headers=headers,
            json={"variante_id": producto["variante_id"], "cantidad": 1},
        )
        respuesta = client.post(
            "/api/v1/checkout/pagar",
            headers={**headers, "Idempotency-Key": _clave()},
            json=dict(datos, notas=f"cliente-{indice}"),
        )
        assert respuesta.status_code == 201, respuesta.get_json()
        if indice == 0:
            assert respuesta.get_json()["pedido"]["estado"] == "CONFIRMADO"
        else:
            assert respuesta.get_json()["pedido"]["estado"] == "EN_PRODUCCION"

    with app.app_context():
        pendiente = db.session.execute(
            text(
                "SELECT SUM(cant_pendiente) FROM pedido_linea WHERE venta_linea_id IN "
                "(SELECT id FROM venta_linea WHERE variante_id = :id)"
            ),
            {"id": producto["variante_id"]},
        ).scalar()
        assert pendiente == 1
        orden = db.session.execute(
            text(
                "SELECT COUNT(*) FROM orden_produccion WHERE creada_por IN :ids"
            ).bindparams(db.bindparam("ids", [primero["id"], segundo["id"]], expanding=True))
        ).scalar()
        assert orden == 1


def test_cliente_no_consulta_pedidos_ajenos(client, tienda):
    producto = tienda["crear_producto"](existencia=2)
    dueno = tienda["crear_cliente"]()
    otro = tienda["crear_cliente"]()
    headers = _headers(client, dueno)
    client.put(
        "/api/v1/carrito/lineas",
        headers=headers,
        json={"variante_id": producto["variante_id"], "cantidad": 1},
    )
    pago = client.post(
        "/api/v1/checkout/pagar",
        headers={**headers, "Idempotency-Key": _clave()},
        json=_pago(),
    )
    pedido_id = pago.get_json()["pedido"]["id"]

    headers_otro = _headers(client, otro)
    for ruta in (
        f"/api/v1/mis-pedidos/{pedido_id}",
        f"/api/v1/mis-pedidos/{pedido_id}/comprobante",
    ):
        respuesta = client.get(ruta, headers=headers_otro)
        assert respuesta.status_code == 404
    cancelacion = client.post(
        f"/api/v1/mis-pedidos/{pedido_id}/cancelar",
        headers=headers_otro,
        json={"motivo": "Intento ajeno"},
    )
    assert cancelacion.status_code == 404


def test_listado_y_detalle_de_pedido_incluyen_fechas_imagen_y_conteo(app, client, tienda):
    producto = tienda["crear_producto"](existencia=2)
    with app.app_context():
        db.session.add(
            ProductoImagen(
                producto_id=producto["producto_id"],
                url="/uploads/prueba.png",
                orden=0,
            )
        )
        db.session.commit()

    usuario = tienda["crear_cliente"]()
    headers = _headers(client, usuario)
    client.put(
        "/api/v1/carrito/lineas",
        headers=headers,
        json={"variante_id": producto["variante_id"], "cantidad": 2},
    )
    pago = client.post(
        "/api/v1/checkout/pagar",
        headers={**headers, "Idempotency-Key": _clave()},
        json=_pago(),
    )
    assert pago.status_code == 201, pago.get_json()
    pedido_id = pago.get_json()["pedido"]["id"]

    listado = client.get("/api/v1/mis-pedidos", headers=headers)
    assert listado.status_code == 200
    item = listado.get_json()["items"][0]
    assert item["articulos"] == 2
    assert item["imagen"] == "/uploads/prueba.png"
    assert "fecha_estimada" in item
    assert "fecha_entrega" in item

    detalle = client.get(f"/api/v1/mis-pedidos/{pedido_id}", headers=headers)
    assert detalle.status_code == 200
    cuerpo = detalle.get_json()
    assert cuerpo["total_articulos"] == 2
    assert cuerpo["fecha_estimada"] == cuerpo["fecha_promesa"]
    assert "fecha_entrega" in cuerpo
    assert cuerpo["articulos"][0]["imagen"] == "/uploads/prueba.png"

    with app.app_context():
        db.session.execute(
            text("DELETE FROM producto_imagen WHERE producto_id = :id"),
            {"id": producto["producto_id"]},
        )
        db.session.commit()


def test_cancelacion_libera_reserva_y_reembolsa(app, client, tienda):
    producto = tienda["crear_producto"](existencia=2)
    usuario = tienda["crear_cliente"]()
    headers = _headers(client, usuario)
    client.put(
        "/api/v1/carrito/lineas",
        headers=headers,
        json={"variante_id": producto["variante_id"], "cantidad": 1},
    )
    pago = client.post(
        "/api/v1/checkout/pagar",
        headers={**headers, "Idempotency-Key": _clave()},
        json=_pago(),
    )
    pedido_id = pago.get_json()["pedido"]["id"]
    cancelacion = client.post(
        f"/api/v1/mis-pedidos/{pedido_id}/cancelar",
        headers=headers,
        json={"motivo": "Ya no deseo el producto"},
    )
    assert cancelacion.status_code == 200, cancelacion.get_json()
    assert cancelacion.get_json()["estado"] == "CANCELADO"

    with app.app_context():
        reservado = db.session.execute(
            text("SELECT reservado FROM stock_variante WHERE variante_id = :id"),
            {"id": producto["variante_id"]},
        ).scalar()
        assert reservado == 0
        tipo = db.session.execute(
            text(
                "SELECT tipo FROM pago WHERE venta_id IN "
                "(SELECT venta_id FROM pedido WHERE id = :id) ORDER BY id DESC LIMIT 1"
            ),
            {"id": pedido_id},
        ).scalar()
        assert tipo == "REEMBOLSO"


def test_roles_y_validacion_en_fase2(client, tienda):
    producto = tienda["crear_producto"](existencia=2)
    operativo = tienda["crear_cliente"]("OPERATIVO")
    headers = _headers(client, operativo)
    for metodo, ruta, cuerpo in (
        ("get", "/api/v1/carrito", None),
        ("put", "/api/v1/carrito/lineas", {"variante_id": producto["variante_id"], "cantidad": 1}),
        ("post", "/api/v1/checkout/cotizar", {"codigo_postal": "37000"}),
        ("get", "/api/v1/mis-pedidos", None),
        ("get", "/api/v1/cuenta/direcciones", None),
    ):
        metodo = getattr(client, metodo)
        kwargs = {"headers": headers}
        if cuerpo is not None:
            kwargs["json"] = cuerpo
        respuesta = metodo(ruta, **kwargs)
        assert respuesta.status_code == 403, (ruta, respuesta.get_json())

    sin_idempotencia = client.post(
        "/api/v1/checkout/pagar", headers=headers, json=_pago()
    )
    assert sin_idempotencia.status_code in (400, 403)

    cliente = tienda["crear_cliente"]()
    headers_cliente = _headers(client, cliente)
    sin_clave = client.post(
        "/api/v1/checkout/pagar", headers=headers_cliente, json=_pago()
    )
    assert sin_clave.status_code == 400
    assert sin_clave.get_json()["codigo"] == "IDEMPOTENCIA_REQUERIDA"
