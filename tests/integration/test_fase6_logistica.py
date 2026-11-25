"""Pruebas de integración de la Fase 6 (M18–M22) contra MySQL real."""

import secrets
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.extensions import db
from app.models import (
    Carrito,
    Color,
    Configuracion,
    LoteMaterial,
    Pedido,
    TokenRefresco,
)
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


@pytest.fixture
def logistica(app, client, tienda, headers_admin, headers_operativo):
    pedidos = set()
    entregas = []
    repartidores = []
    tarifas = []
    lotes = []

    with app.app_context():
        for codigo in ("EMP-BOL", "EMP-PAP", "EMP-TAR", "EMP-ETE"):
            filas = db.session.execute(
                text(
                    "SELECT im.id FROM inventario_material im "
                    "JOIN material ma ON ma.id = im.material_id WHERE ma.codigo = :codigo"
                ),
                {"codigo": codigo},
            ).scalars().all()
            for inventario_id in filas:
                lote = LoteMaterial(
                    inventario_material_id=inventario_id,
                    folio=f"LT-F6-{secrets.token_hex(6).upper()}",
                    fecha_entrada=date.today(),
                    cantidad_base_recibida=10000,
                    cantidad_base_disponible=10000,
                    costo_unitario_base=1,
                    costo_total=10000,
                    estado="DISPONIBLE",
                )
                db.session.add(lote)
                db.session.flush()
                lotes.append(lote.id)
        db.session.commit()

    def crear_pedido():
        producto = tienda["crear_producto"](existencia=5)
        usuario = tienda["crear_cliente"]()
        headers = iniciar_sesion(client, usuario["correo"], usuario["password"])
        assert client.put(
            "/api/v1/carrito/lineas",
            headers=headers,
            json={"variante_id": producto["variante_id"], "cantidad": 1},
        ).status_code == 200
        respuesta = client.post(
            "/api/v1/checkout/pagar",
            headers={**headers, "Idempotency-Key": f"f6-{secrets.token_hex(8)}"},
            json=_pago(),
        )
        assert respuesta.status_code == 201, respuesta.get_json()
        datos = respuesta.get_json()
        pedidos.add(datos["pedido"]["id"])
        with app.app_context():
            preparacion_id = db.session.execute(
                text("SELECT id FROM preparacion WHERE pedido_id = :id"),
                {"id": datos["pedido"]["id"]},
            ).scalar()
        return {
            "usuario": usuario,
            "headers": headers,
            "producto": producto,
            "venta_id": datos["venta"]["id"],
            "pedido_id": datos["pedido"]["id"],
            "preparacion_id": preparacion_id,
        }

    def preparar(pedido):
        respuesta = client.post(
            f"/api/v1/preparacion/{pedido['pedido_id']}/tomar",
            headers=headers_operativo,
        )
        if respuesta.status_code != 200:
            assert respuesta.get_json()["codigo"] in (
                "PREPARACION_NO_DISPONIBLE",
                "PEDIDO_NO_PREPARABLE",
            )
        with app.app_context():
            filas = db.session.execute(
                text(
                    "SELECT pl.id, vl.sku, pl.cantidad_requerida "
                    "FROM preparacion_linea pl "
                    "JOIN pedido_linea pd ON pd.id = pl.pedido_linea_id "
                    "JOIN venta_linea vl ON vl.id = pd.venta_linea_id "
                    "WHERE pl.preparacion_id = :id ORDER BY pl.id"
                ),
                {"id": pedido["preparacion_id"]},
            ).all()
        lineas = [
            {"id": fila[0], "sku": fila[1], "cantidad_requerida": fila[2]}
            for fila in filas
        ]
        respuesta = client.patch(
            f"/api/v1/preparacion/{pedido['preparacion_id']}/lineas",
            headers=headers_operativo,
            json={
                "lineas": [
                    {
                        "preparacion_linea_id": linea["id"],
                        "cantidad_surtida": linea["cantidad_requerida"],
                        "sku": linea["sku"],
                        "sku_verificado": True,
                        "diseno_verificado": True,
                        "etiquetas_verificadas": True,
                    }
                    for linea in lineas
                ]
            },
        )
        assert respuesta.status_code == 200, respuesta.get_json()
        respuesta = client.post(
            f"/api/v1/preparacion/{pedido['preparacion_id']}/empacar",
            headers=headers_operativo,
        )
        assert respuesta.status_code == 200, respuesta.get_json()
        return respuesta.get_json()

    def crear_repartidor():
        respuesta = client.post(
            "/api/v1/repartidores",
            headers=headers_admin,
            json={
                "nombre": f"Repartidor {secrets.token_hex(3)}",
                "telefono": "1234567890",
                "vehiculo": "Motocicleta",
            },
        )
        assert respuesta.status_code == 201, respuesta.get_json()
        repartidores.append(respuesta.get_json()["id"])
        return respuesta.get_json()

    def asignar(pedido, repartidor):
        respuesta = client.post(
            "/api/v1/entregas",
            headers=headers_operativo,
            json={
                "pedido_id": pedido["pedido_id"],
                "repartidor_id": repartidor["id"],
                "fecha_programada": date.today().isoformat(),
            },
        )
        assert respuesta.status_code == 201, respuesta.get_json()
        entregas.append(respuesta.get_json()["id"])
        return respuesta.get_json()

    def crear_tarifa(cp_inicio, cp_fin, nombre=None):
        respuesta = client.post(
            "/api/v1/catalogos/tarifa-envio",
            headers=headers_admin,
            json={
                "nombre": nombre or f"Tarifa {secrets.token_hex(3)}",
                "cp_inicio": cp_inicio,
                "cp_fin": cp_fin,
                "costo": "150.00",
                "dias_estimados": 2,
            },
        )
        if respuesta.status_code == 201:
            tarifas.append(respuesta.get_json()["id"])
        return respuesta

    yield {
        "crear_pedido": crear_pedido,
        "preparar": preparar,
        "crear_repartidor": crear_repartidor,
        "asignar": asignar,
        "crear_tarifa": crear_tarifa,
        "pedidos": pedidos,
    }

    with app.app_context():
        ids_entregas = entregas or [-1]
        ids_pedidos = list(pedidos) or [-1]
        db.session.execute(
            text("DELETE FROM entrega WHERE id IN :ids").bindparams(
                db.bindparam("ids", ids_entregas, expanding=True)
            )
        )
        db.session.execute(
            text(
                "DELETE FROM alerta WHERE entidad_tipo = 'pedido' AND entidad_id IN :ids"
            ).bindparams(db.bindparam("ids", ids_pedidos, expanding=True))
        )
        if repartidores:
            db.session.execute(
                text("DELETE FROM repartidor WHERE id IN :ids").bindparams(
                    db.bindparam("ids", repartidores, expanding=True)
                )
            )
        if tarifas:
            db.session.execute(
                text("DELETE FROM bitacora WHERE entidad = 'tarifa-envio' AND entidad_id IN :ids")
                .bindparams(db.bindparam("ids", tarifas, expanding=True))
            )
            db.session.execute(
                text("DELETE FROM tarifa_envio WHERE id IN :ids").bindparams(
                    db.bindparam("ids", tarifas, expanding=True)
                )
            )
        if lotes:
            db.session.execute(
                text("DELETE FROM movimiento_material WHERE lote_id IN :ids").bindparams(
                    db.bindparam("ids", lotes, expanding=True)
                )
            )
            db.session.execute(
                text("DELETE FROM lote_material WHERE id IN :ids").bindparams(
                    db.bindparam("ids", lotes, expanding=True)
                )
            )
        db.session.commit()


def test_m18_cola_toma_verificacion_empaque_y_etiqueta(
    client, headers_operativo, headers_cliente, logistica
):
    pedido = logistica["crear_pedido"]()
    cola = client.get("/api/v1/preparacion/cola", headers=headers_operativo)
    assert cola.status_code == 200, cola.get_json()
    assert any(item["pedido_id"] == pedido["pedido_id"] for item in cola.get_json()["items"])

    rechazo = client.get("/api/v1/preparacion/cola", headers=headers_cliente)
    assert rechazo.status_code == 403

    tomada = client.post(
        f"/api/v1/preparacion/{pedido['pedido_id']}/tomar",
        headers=headers_operativo,
    )
    assert tomada.status_code == 200, tomada.get_json()
    assert tomada.get_json()["estado"] == "EN_PICKING"

    etiqueta = client.get(
        f"/api/v1/preparacion/{pedido['preparacion_id']}/etiqueta",
        headers=headers_operativo,
    )
    assert etiqueta.status_code == 200
    assert etiqueta.mimetype == "application/pdf"
    assert etiqueta.data.startswith(b"%PDF")

    resultado = logistica["preparar"](pedido)
    assert resultado["estado"] == "LISTA"


def test_m19_ciclo_completo_de_entrega_y_reportes(
    app, client, headers_admin, headers_operativo, headers_cliente, logistica
):
    pedido = logistica["crear_pedido"]()
    logistica["preparar"](pedido)
    repartidor = logistica["crear_repartidor"]()

    por_asignar = client.get("/api/v1/entregas/por-asignar", headers=headers_operativo)
    assert por_asignar.status_code == 200, por_asignar.get_json()
    assert any(item["pedido_id"] == pedido["pedido_id"] for item in por_asignar.get_json()["items"])

    entrega = logistica["asignar"](pedido, repartidor)
    assert entrega["folio"].startswith("EN-")
    assert entrega["estado"] == "PROGRAMADA"

    hoja = client.get(
        f"/api/v1/entregas/hoja-reparto?repartidor={repartidor['id']}&fecha={date.today().isoformat()}",
        headers=headers_operativo,
    )
    assert hoja.status_code == 200, hoja.get_json() if hoja.mimetype != "application/pdf" else None
    assert hoja.mimetype == "application/pdf"

    salida = client.post(
        f"/api/v1/entregas/{entrega['id']}/salida", headers=headers_operativo
    )
    assert salida.status_code == 200, salida.get_json()
    assert salida.get_json()["estado"] == "EN_RUTA"

    resultado = client.post(
        f"/api/v1/entregas/{entrega['id']}/resultado",
        headers=headers_operativo,
        json={"entregado": True, "receptor": "Receptor Prueba"},
    )
    assert resultado.status_code == 200, resultado.get_json()
    assert resultado.get_json()["estado"] == "ENTREGADA"

    repartidos = client.get(
        f"/api/v1/entregas/productos-repartidos?repartidor={repartidor['id']}",
        headers=headers_operativo,
    )
    assert repartidos.status_code == 200, repartidos.get_json()
    assert repartidos.get_json()["total"] >= 1

    with app.app_context():
        pedido_db = db.session.get(Pedido, pedido["pedido_id"])
        assert pedido_db.estado == "ENTREGADO"

    denegado = client.post(
        "/api/v1/entregas",
        headers=headers_cliente,
        json={
            "pedido_id": pedido["pedido_id"],
            "repartidor_id": repartidor["id"],
            "fecha_programada": date.today().isoformat(),
        },
    )
    assert denegado.status_code == 403


def test_m19_dos_entregas_fallidas_generan_alerta_critica_y_reingreso(
    app, client, headers_operativo, logistica
):
    pedido = logistica["crear_pedido"]()
    logistica["preparar"](pedido)
    repartidor = logistica["crear_repartidor"]()
    variante_id = pedido["producto"]["variante_id"]

    with app.app_context():
        stock_inicial = db.session.execute(
            text("SELECT existencia, reservado FROM stock_variante WHERE variante_id = :id"),
            {"id": variante_id},
        ).one()

    for intento in range(2):
        entrega = logistica["asignar"](pedido, repartidor)
        salida = client.post(
            f"/api/v1/entregas/{entrega['id']}/salida", headers=headers_operativo
        )
        assert salida.status_code == 200, salida.get_json()
        with app.app_context():
            durante = db.session.execute(
                text("SELECT existencia, reservado FROM stock_variante WHERE variante_id = :id"),
                {"id": variante_id},
            ).one()
            assert durante.existencia == stock_inicial.existencia - 1
            assert durante.reservado == stock_inicial.reservado - 1
        resultado = client.post(
            f"/api/v1/entregas/{entrega['id']}/resultado",
            headers=headers_operativo,
            json={"entregado": False, "motivo_fallo": "AUSENTE"},
        )
        assert resultado.status_code == 200, resultado.get_json()
        with app.app_context():
            despues = db.session.execute(
                text("SELECT existencia, reservado FROM stock_variante WHERE variante_id = :id"),
                {"id": variante_id},
            ).one()
            assert despues.existencia == stock_inicial.existencia
            assert despues.reservado == stock_inicial.reservado
            movimientos = db.session.execute(
                text(
                    "SELECT COUNT(*) FROM movimiento_producto WHERE tipo = 'REINGRESO' "
                    "AND documento_tipo = 'ENTREGA' AND documento_id = :id"
                ),
                {"id": entrega["id"]},
            ).scalar()
            assert movimientos == 1

    with app.app_context():
        alerta = db.session.execute(
            text("SELECT severidad, estado FROM alerta WHERE clave_unica = :clave"),
            {"clave": f"ENTREGA_FALLIDA:{pedido['pedido_id']}"},
        ).one()
        assert alerta.estado == "ABIERTA"
        assert alerta.severidad == "CRITICA"


def test_m20_dashboard_segun_rol_y_exportacion_csv(
    client, headers_admin, headers_operativo, headers_cliente
):
    for ruta in ("resumen", "ventas", "produccion", "abastecimiento", "logistica"):
        respuesta = client.get(f"/api/v1/dashboard/{ruta}", headers=headers_admin)
        assert respuesta.status_code == 200, (ruta, respuesta.get_json())
    exportacion = client.get("/api/v1/dashboard/exportar", headers=headers_admin)
    assert exportacion.status_code == 200
    assert exportacion.mimetype.startswith("text/csv")
    assert "seccion,indicador,valor" in exportacion.get_data(as_text=True)

    for ruta in ("produccion", "abastecimiento", "logistica"):
        respuesta = client.get(f"/api/v1/dashboard/{ruta}", headers=headers_operativo)
        assert respuesta.status_code == 200
        texto = str(respuesta.get_json()).lower()
        assert "ingresos" not in texto
        assert "costo" not in texto
        assert "utilidad" not in texto

    for ruta in ("resumen", "ventas", "exportar"):
        assert client.get(f"/api/v1/dashboard/{ruta}", headers=headers_operativo).status_code == 403
        assert client.get(f"/api/v1/dashboard/{ruta}", headers=headers_cliente).status_code == 403


def test_m21_alertas_deduplicacion_reglas_y_accion(
    app, client, headers_admin, headers_operativo, logistica
):
    pedido = logistica["crear_pedido"]()
    clave = f"PEDIDO_ESTANCADO:{pedido['pedido_id']}"
    with app.app_context():
        from app.services import alertas_service

        primera = alertas_service.abrir(
            "PEDIDO_ESTANCADO",
            "PREVENTIVA",
            "Pedido estancado",
            "Prueba de deduplicación",
            "pedido",
            pedido["pedido_id"],
            rol_destino="AMBOS",
            clave_unica=clave,
        )
        segunda = alertas_service.abrir(
            "PEDIDO_ESTANCADO",
            "PREVENTIVA",
            "Pedido estancado",
            "Prueba de deduplicación",
            "pedido",
            pedido["pedido_id"],
            rol_destino="AMBOS",
            clave_unica=clave,
        )
        db.session.commit()
        alerta_id = primera.id
        assert segunda.id == alerta_id

    lista = client.get("/api/v1/alertas", headers=headers_operativo)
    assert lista.status_code == 200, lista.get_json()
    assert any(item["clave_unica"] == clave for item in lista.get_json()["items"])

    reglas = client.get("/api/v1/alertas/reglas", headers=headers_admin)
    assert reglas.status_code == 200
    assert any(item["clave"] == "merma_meta_pct" for item in reglas.get_json())
    assert client.get("/api/v1/alertas/reglas", headers=headers_operativo).status_code == 403

    with app.app_context():
        valor_original = db.session.get(Configuracion, "merma_meta_pct").valor
    actualizadas = client.patch(
        "/api/v1/alertas/reglas",
        headers=headers_admin,
        json={"reglas": [{"clave": "merma_meta_pct", "valor": "6"}]},
    )
    assert actualizadas.status_code == 200, actualizadas.get_json()
    with app.app_context():
        db.session.get(Configuracion, "merma_meta_pct").valor = valor_original
        db.session.commit()

    accion = client.post(
        f"/api/v1/alertas/{alerta_id}/accion",
        headers=headers_operativo,
        json={"accion": "ATENDER"},
    )
    assert accion.status_code == 200, accion.get_json()
    assert accion.get_json()["alerta"]["estado"] == "ATENDIDA"
    repetida = client.post(
        f"/api/v1/alertas/{alerta_id}/accion",
        headers=headers_operativo,
        json={"accion": "ATENDER"},
    )
    assert repetida.status_code == 409

    with app.app_context():
        from app.services import alertas_service

        assert alertas_service.cerrar(clave) is False
        db.session.execute(text("DELETE FROM alerta WHERE id = :id"), {"id": alerta_id})
        db.session.commit()


def test_m22_catalogos_tarifas_bitacora_y_cliente(
    app, client, headers_admin, headers_operativo, tienda, logistica
):
    assert client.get("/api/v1/catalogos/color", headers=headers_operativo).status_code == 403
    colores = client.get("/api/v1/catalogos/color", headers=headers_admin)
    assert colores.status_code == 200
    assert any(item["codigo"] == "GR" for item in colores.get_json()["items"])

    primera = logistica["crear_tarifa"]("99100", "99199")
    assert primera.status_code == 201, primera.get_json()
    solapada = logistica["crear_tarifa"]("99150", "99200")
    assert solapada.status_code == 409
    assert solapada.get_json()["codigo"] == "RANGO_TARIFA_SOLAPADO"

    with app.app_context():
        color = db.session.query(Color).filter_by(codigo="GR").one()
        color_id = color.id
    inmutable = client.patch(
        f"/api/v1/catalogos/color/{color_id}",
        headers=headers_admin,
        json={"codigo": "ZZ"},
    )
    assert inmutable.status_code == 409
    assert inmutable.get_json()["codigo"] == "CODIGO_SKU_INMUTABLE"

    tienda["crear_producto"]()
    en_uso = client.delete(
        f"/api/v1/catalogos/color/{color_id}", headers=headers_admin
    )
    assert en_uso.status_code == 409

    bitacora = client.get(
        "/api/v1/bitacora?accion=CATALOGO_CREADO", headers=headers_admin
    )
    assert bitacora.status_code == 200
    assert bitacora.get_json()["total"] >= 1

    pedido = logistica["crear_pedido"]()
    detalle = client.get(
        f"/api/v1/clientes/{pedido['usuario']['id']}", headers=headers_admin
    )
    assert detalle.status_code == 200, detalle.get_json()
    assert "resumen" in detalle.get_json()
    assert any(item["id"] == pedido["pedido_id"] for item in detalle.get_json()["pedidos"])


def test_jobs_limpiar_tokens_y_abandonar_carritos(app, tienda, headers_admin):
    from app.jobs import tareas

    with app.app_context():
        usuario_id = db.session.execute(
            text("SELECT id FROM usuario WHERE rol_id = (SELECT id FROM rol WHERE codigo='CLIENTE') LIMIT 1")
        ).scalar()
        vencido = TokenRefresco(
            usuario_id=usuario_id,
            token_hash=secrets.token_hex(32),
            expira_en=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
            revocado=False,
        )
        db.session.add(vencido)
        carrito = Carrito(usuario_id=usuario_id, estado="ABIERTO")
        db.session.add(carrito)
        db.session.flush()
        carrito.actualizado_en = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=10)
        db.session.commit()
        token_id = vencido.id
        carrito_id = carrito.id

    with app.app_context():
        resultado_tokens = tareas.limpiar_tokens()
        resultado_carritos = tareas.abandonar_carritos()
        assert resultado_tokens["tokens_refresco"] >= 1
        assert db.session.get(TokenRefresco, token_id) is None
        assert db.session.get(Carrito, carrito_id).estado == "ABANDONADO"

    with app.app_context():
        db.session.execute(text("DELETE FROM carrito_linea WHERE carrito_id = :id"), {"id": carrito_id})
        db.session.execute(text("DELETE FROM carrito WHERE id = :id"), {"id": carrito_id})
        db.session.commit()
