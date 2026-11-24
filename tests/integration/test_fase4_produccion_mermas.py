"""Pruebas de integración de producción y mermas (M16 y M17)."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
import secrets
from sqlalchemy import text

from app.extensions import db
from app.models import (
    CausaMerma,
    CategoriaMaterial,
    CategoriaProducto,
    Color,
    InventarioMaterial,
    LoteMaterial,
    Material,
    MovimientoMaterial,
    MovimientoProducto,
    Merma,
    OrdenProduccion,
    Pedido,
    PedidoLinea,
    Producto,
    Receta,
    RecetaLinea,
    StockVariante,
    Talla,
    Usuario,
    VarianteProducto,
    Venta,
    VentaLinea,
)


@pytest.fixture
def datos_fase4(app, datos_fase3, limpieza_fase3, mysql_disponible):
    sufijo = secrets.token_hex(4).upper()
    lotes = []
    producto_id = None
    variante_id = None
    receta_id = None
    ordenes = []
    pedidos = []
    requisiciones = []

    with app.app_context():
        usuario = db.session.query(Usuario).join(Usuario.rol).filter_by(codigo="ADMIN").first()
        assert usuario is not None, "Se requiere el administrador sembrado"
        usuario_id = usuario.id
        categoria = db.session.query(CategoriaProducto).filter_by(prefijo_sku="PL").one()
        talla = db.session.query(Talla).filter_by(codigo="CH").one()
        color = db.session.query(Color).filter_by(codigo="BL").one()
        categoria_material = db.session.query(CategoriaMaterial).filter_by(nombre="Tela").one()
        material = Material(
            categoria_material_id=categoria_material.id,
            codigo=f"TS{sufijo}",
            nombre=f"Tela de prueba {sufijo}",
            unidad_base="M2",
            unidad_compra="m2",
            factor_compra_base=Decimal("1.0000"),
            costo_estandar_base=Decimal("10.000000"),
            merma_estandar_pct=Decimal("0.00"),
            por_color=True,
            activo=True,
        )
        db.session.add(material)
        db.session.flush()
        inventario = InventarioMaterial(
            material_id=material.id,
            color_id=color.id,
            stock_minimo=Decimal("0.0000"),
            stock_seguridad=Decimal("0.0000"),
            activo=True,
        )
        db.session.add(inventario)
        db.session.flush()
        inventario_id = inventario.id
        material_codigo = material.codigo
        material_id = material.id
        proveedor_id = datos_fase3["crear_proveedor"]()

        producto = Producto(
            categoria_id=categoria.id,
            codigo_sku=sufijo[:4],
            nombre=f"Producción {sufijo}",
            descripcion="Producto de pruebas de producción",
            composicion_textil="Felpa",
            guia_medidas="",
            precio_venta="100.00",
            permite_bajo_pedido=True,
            activo=True,
        )
        db.session.add(producto)
        db.session.flush()
        variante = VarianteProducto(
            producto_id=producto.id,
            talla_id=talla.id,
            color_id=color.id,
            sku=f"TST4-{sufijo[4:]}",
            activa=True,
        )
        db.session.add(variante)
        db.session.flush()
        db.session.add(
            StockVariante(
                variante_id=variante.id,
                existencia=0,
                reservado=0,
                stock_minimo=1,
                cantidad_reposicion=20,
            )
        )
        receta = Receta(
            producto_id=producto.id,
            talla_id=talla.id,
            version=1,
            estado="VIGENTE",
            creada_por=usuario_id,
            activada_en=datetime.utcnow(),
        )
        db.session.add(receta)
        db.session.flush()
        db.session.add(
            RecetaLinea(
                receta_id=receta.id,
                material_id=material.id,
                cantidad_neta=Decimal("1.0000"),
                factor_consumo=Decimal("1.000"),
                merma_pct=Decimal("0.00"),
                cantidad_bruta=Decimal("1.0000"),
            )
        )
        db.session.flush()

        from app.services import material_service

        for dias in (10, 2):
            lote = material_service.registrar_entrada(
                inventario_id,
                Decimal("5.0000"),
                Decimal("10.000000"),
                date.today() - timedelta(days=dias),
                proveedor_id,
                None,
                usuario_id,
                f"Lote de prueba Fase 4 {sufijo}",
            )
            lotes.append(lote.id)

        db.session.commit()
        producto_id = producto.id
        variante_id = variante.id
        receta_id = receta.id
        sku = variante.sku

    parametros = {
        "vid": variante_id,
        "iid": inventario_id,
        "material": material_id,
        "lotes": lotes,
        "producto": producto_id,
        "receta": receta_id,
        "usuario": usuario_id,
    }

    limpieza_fase3("DELETE FROM idempotencia_operacion WHERE clave LIKE 'test-prod-%'")
    limpieza_fase3(
        "DELETE FROM bitacora WHERE entidad = 'merma' AND entidad_id IN "
        "(SELECT id FROM merma WHERE variante_id = :vid OR inventario_material_id = :iid "
        "OR lote_id IN :lotes)",
        parametros,
    )
    limpieza_fase3(
        "DELETE FROM alerta WHERE entidad_tipo = 'merma' AND entidad_id IN "
        "(SELECT id FROM merma WHERE variante_id = :vid OR inventario_material_id = :iid "
        "OR lote_id IN :lotes)",
        parametros,
    )
    limpieza_fase3(
        "DELETE FROM merma WHERE reversa_de_id IN ("
        "SELECT id FROM (SELECT id FROM merma WHERE variante_id = :vid "
        "OR inventario_material_id = :iid OR lote_id IN :lotes) AS descartadas)",
        parametros,
    )
    limpieza_fase3(
        "DELETE FROM merma WHERE variante_id = :vid OR inventario_material_id = :iid "
        "OR lote_id IN :lotes",
        parametros,
    )
    limpieza_fase3("DELETE FROM movimiento_producto WHERE variante_id = :vid", parametros)
    limpieza_fase3("DELETE FROM movimiento_material WHERE lote_id IN :lotes", parametros)
    limpieza_fase3("DELETE FROM lote_material WHERE id IN :lotes", parametros)
    limpieza_fase3.al_final(
        "DELETE FROM receta_linea WHERE receta_id = :receta", parametros
    )
    limpieza_fase3.al_final("DELETE FROM receta WHERE id = :receta", parametros)
    limpieza_fase3.al_final("DELETE FROM stock_variante WHERE variante_id = :vid", parametros)
    limpieza_fase3.al_final("DELETE FROM variante_producto WHERE id = :vid", parametros)
    limpieza_fase3.al_final("DELETE FROM producto WHERE id = :producto", parametros)
    limpieza_fase3.al_final("DELETE FROM inventario_material WHERE id = :iid", parametros)
    limpieza_fase3.al_final("DELETE FROM material WHERE id = :material", parametros)

    def registrar_orden(orden_id):
        ordenes.append(orden_id)
        parametros_orden = {"id": orden_id}
        limpieza_fase3(
            "DELETE FROM orden_material WHERE orden_id = :id", parametros_orden
        )
        limpieza_fase3(
            "DELETE FROM revision_calidad WHERE orden_linea_id IN "
            "(SELECT id FROM orden_produccion_linea WHERE orden_id = :id)",
            parametros_orden,
        )
        limpieza_fase3(
            "DELETE FROM produccion_pedido WHERE orden_linea_id IN "
            "(SELECT id FROM orden_produccion_linea WHERE orden_id = :id)",
            parametros_orden,
        )
        limpieza_fase3(
            "DELETE FROM alerta WHERE entidad_tipo = 'orden_produccion' AND entidad_id = :id",
            parametros_orden,
        )
        limpieza_fase3(
            "DELETE FROM bitacora WHERE entidad = 'orden_produccion' AND entidad_id = :id",
            parametros_orden,
        )
        limpieza_fase3(
            "DELETE FROM orden_produccion_linea WHERE orden_id = :id", parametros_orden
        )
        limpieza_fase3("DELETE FROM orden_produccion WHERE id = :id", parametros_orden)

    def registrar_requisicion(requisicion_id):
        requisiciones.append(requisicion_id)
        parametros_req = {"id": requisicion_id}
        limpieza_fase3(
            "DELETE FROM requisicion_linea WHERE requisicion_id = :id", parametros_req
        )
        limpieza_fase3(
            "DELETE FROM bitacora WHERE entidad = 'requisicion' AND entidad_id = :id",
            parametros_req,
        )
        limpieza_fase3("DELETE FROM requisicion WHERE id = :id", parametros_req)

    def registrar_pedido(pedido_id):
        pedidos.append(pedido_id)
        with app.app_context():
            pedido = db.session.get(Pedido, pedido_id)
            venta_id = pedido.venta_id
        parametros_pedido = {"id": pedido_id}
        limpieza_fase3(
            "DELETE FROM produccion_pedido WHERE pedido_linea_id IN "
            "(SELECT id FROM pedido_linea WHERE pedido_id = :id)",
            parametros_pedido,
        )
        limpieza_fase3("DELETE FROM pedido_evento WHERE pedido_id = :id", parametros_pedido)
        limpieza_fase3("DELETE FROM pedido_linea WHERE pedido_id = :id", parametros_pedido)
        limpieza_fase3("DELETE FROM pedido WHERE id = :id", parametros_pedido)
        limpieza_fase3("DELETE FROM pago WHERE venta_id = :id", {"id": venta_id})
        limpieza_fase3("DELETE FROM venta_direccion WHERE venta_id = :id", {"id": venta_id})
        limpieza_fase3("DELETE FROM venta_linea WHERE venta_id = :id", {"id": venta_id})
        limpieza_fase3("DELETE FROM venta WHERE id = :id", {"id": venta_id})

    def crear_pedido(cantidad, dias_antiguedad=0):
        sufijo_pedido = secrets.token_hex(4).upper()
        with app.app_context():
            venta = Venta(
                folio=f"UNQ-TST-{sufijo_pedido}",
                usuario_id=usuario_id,
                canal="MANUAL",
                estado="ACTIVA",
                estado_pago="PAGADA",
                subtotal=Decimal("100.00"),
                total=Decimal("100.00"),
                iva_incluido=True,
            )
            db.session.add(venta)
            db.session.flush()
            venta_linea = VentaLinea(
                venta_id=venta.id,
                variante_id=variante_id,
                sku=sku,
                nombre_producto="Producción de prueba",
                talla="CH",
                color="BL",
                cantidad=cantidad,
                precio_unitario=Decimal("100.00"),
                subtotal=Decimal("100.00") * cantidad,
                costo_estandar_unitario=Decimal("10.000000"),
            )
            db.session.add(venta_linea)
            db.session.flush()
            pedido = Pedido(
                venta_id=venta.id,
                estado="EN_PRODUCCION",
                estado_desde=datetime.utcnow() - timedelta(days=dias_antiguedad),
                prioridad="NORMAL",
            )
            db.session.add(pedido)
            db.session.flush()
            db.session.add(
                PedidoLinea(
                    pedido_id=pedido.id,
                    venta_linea_id=venta_linea.id,
                    cantidad=cantidad,
                    cant_reservada=0,
                    cant_pendiente=cantidad,
                    cant_preparada=0,
                )
            )
            db.session.commit()
            pedido_id = pedido.id
        registrar_pedido(pedido_id)
        return pedido_id

    return {
        "variante_id": variante_id,
        "sku": sku,
        "inventario_id": inventario_id,
        "material_codigo": material_codigo,
        "lotes": lotes,
        "registrar_orden": registrar_orden,
        "registrar_requisicion": registrar_requisicion,
        "crear_pedido": crear_pedido,
        "app": app,
    }


def _consultar(datos_fase4, entidad, entidad_id):
    with datos_fase4["app"].app_context():
        return db.session.get(entidad, entidad_id)


def _cantidades_lotes(datos_fase4):
    with datos_fase4["app"].app_context():
        return [
            Decimal(fila[0])
            for fila in db.session.execute(
                text(
                    "SELECT cantidad_base_disponible FROM lote_material "
                    "WHERE id IN :ids ORDER BY fecha_entrada, id"
                ).bindparams(
                    db.bindparam("ids", datos_fase4["lotes"], expanding=True)
                )
            ).all()
        ]


def test_flujo_produccion_peps_idempotencia_dictamen_y_fifo(
    client, headers_operativo, datos_fase4
):
    pedido_antiguo = datos_fase4["crear_pedido"](2, dias_antiguedad=5)
    pedido_reciente = datos_fase4["crear_pedido"](1, dias_antiguedad=1)

    creada = client.post(
        "/api/v1/produccion/ordenes",
        json={"lineas": [{"variante_id": datos_fase4["variante_id"], "cantidad": 3}]},
        headers=headers_operativo,
    )
    assert creada.status_code == 201, creada.get_json()
    orden = creada.get_json()
    datos_fase4["registrar_orden"](orden["id"])
    assert orden["folio"].startswith("OP-")
    assert orden["estado"] == "PLANEADA"
    assert len(orden["materiales"]) == 1

    reserva = client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/reservar",
        headers=headers_operativo,
    )
    assert reserva.status_code == 200, reserva.get_json()
    assert reserva.get_json()["orden"]["estado"] == "LISTA"

    clave = f"test-prod-iniciar-{secrets.token_hex(6)}"
    iniciada = client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/iniciar",
        json={},
        headers={**headers_operativo, "Idempotency-Key": clave},
    )
    assert iniciada.status_code == 200, iniciada.get_json()
    assert iniciada.get_json()["orden"]["estado"] == "EN_PROCESO"
    assert [Decimal(item["cantidad"]) for item in iniciada.get_json()["consumo"]] == [
        Decimal("3")
    ]
    assert _cantidades_lotes(datos_fase4) == [Decimal("2.0000"), Decimal("5.0000")]

    repetida = client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/iniciar",
        json={},
        headers={**headers_operativo, "Idempotency-Key": clave},
    )
    assert repetida.status_code == 200
    assert repetida.get_json() == iniciada.get_json()
    assert _cantidades_lotes(datos_fase4) == [Decimal("2.0000"), Decimal("5.0000")]

    distinta = client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/iniciar",
        json={"notas": "otra petición"},
        headers={**headers_operativo, "Idempotency-Key": clave},
    )
    assert distinta.status_code == 409
    assert distinta.get_json()["codigo"] == "IDEMPOTENCIA_CONFLICTO"

    revision = client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/revision",
        json={"notas": "Revisión completa"},
        headers=headers_operativo,
    )
    assert revision.status_code == 200, revision.get_json()
    assert revision.get_json()["estado"] == "EN_REVISION"

    linea_id = revision.get_json()["lineas"][0]["id"]
    dictamen = client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/dictamen",
        json={
            "lineas": [
                {
                    "orden_linea_id": linea_id,
                    "cantidad_revisada": 3,
                    "cantidad_aprobada": 2,
                    "cantidad_reproceso": 0,
                    "cantidad_merma": 1,
                    "medidas_ok": True,
                    "costuras_ok": True,
                    "bordado_ok": True,
                    "etiquetas_ok": True,
                    "etapa_merma": "ACABADOS",
                    "observaciones": "Una unidad defectuosa",
                }
            ]
        },
        headers=headers_operativo,
    )
    assert dictamen.status_code == 200, dictamen.get_json()
    resultado = dictamen.get_json()
    assert resultado["estado"] == "CERRADA"
    assert resultado["total_aprobado"] == 2
    assert resultado["total_merma"] == 1

    with datos_fase4["app"].app_context():
        stock = db.session.execute(
            text("SELECT existencia, reservado FROM stock_variante WHERE variante_id = :id"),
            {"id": datos_fase4["variante_id"]},
        ).one()
        assert (stock[0], stock[1]) == (2, 2)
        lineas_pedido = db.session.execute(
            text(
                "SELECT pedido_id, cant_reservada, cant_pendiente FROM pedido_linea "
                "WHERE pedido_id IN :ids ORDER BY pedido_id"
            ).bindparams(
                db.bindparam("ids", [pedido_antiguo, pedido_reciente], expanding=True)
            )
        ).all()
        assert [(fila[1], fila[2]) for fila in lineas_pedido] == [(2, 0), (0, 1)]
        movimientos = db.session.execute(
            text(
                "SELECT tipo, delta_reservado FROM movimiento_producto "
                "WHERE variante_id = :id ORDER BY id"
            ),
            {"id": datos_fase4["variante_id"]},
        ).all()
        tipos = [fila[0] for fila in movimientos]
        assert "PRODUCCION" in tipos
        assert sum(fila[1] for fila in movimientos if fila[0] == "RESERVA") == 2
        mermas = db.session.execute(
            text(
                "SELECT origen, etapa, cantidad FROM merma WHERE variante_id = :id"
            ),
            {"id": datos_fase4["variante_id"]},
        ).all()
        assert len(mermas) == 1
        assert (mermas[0][0], mermas[0][1], Decimal(mermas[0][2])) == (
            "PRODUCTO",
            "ACABADOS",
            Decimal("1.0000"),
        )


def test_inicio_con_material_insuficiente_no_descuenta_lotes(
    client, headers_operativo, datos_fase4
):
    creada = client.post(
        "/api/v1/produccion/ordenes",
        json={"lineas": [{"variante_id": datos_fase4["variante_id"], "cantidad": 3}]},
        headers=headers_operativo,
    )
    assert creada.status_code == 201, creada.get_json()
    orden = creada.get_json()
    datos_fase4["registrar_orden"](orden["id"])

    assert client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/reservar", headers=headers_operativo
    ).status_code == 200

    with datos_fase4["app"].app_context():
        db.session.execute(
            text(
                "UPDATE lote_material SET cantidad_base_disponible = 0 "
                "WHERE id IN :ids"
            ).bindparams(db.bindparam("ids", datos_fase4["lotes"], expanding=True))
        )
        db.session.commit()
    antes = _cantidades_lotes(datos_fase4)

    respuesta = client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/iniciar",
        json={},
        headers={
            **headers_operativo,
            "Idempotency-Key": f"test-prod-falta-{secrets.token_hex(6)}",
        },
    )
    assert respuesta.status_code == 409, respuesta.get_json()
    assert respuesta.get_json()["codigo"] == "MATERIAL_INSUFICIENTE"
    assert respuesta.get_json()["detalle"]
    assert _cantidades_lotes(datos_fase4) == antes
    with datos_fase4["app"].app_context():
        assert db.session.get(OrdenProduccion, orden["id"]).estado == "LISTA"


def test_solicitud_de_compra_y_semáforo(client, headers_operativo, datos_fase4):
    creada = client.post(
        "/api/v1/produccion/ordenes",
        json={
            "lineas": [{"variante_id": datos_fase4["variante_id"], "cantidad": 100}],
            "fecha_requerida": (date.today() + timedelta(days=10)).isoformat(),
        },
        headers=headers_operativo,
    )
    assert creada.status_code == 201, creada.get_json()
    orden = creada.get_json()

    reserva = client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/reservar", headers=headers_operativo
    )
    assert reserva.status_code == 200
    assert reserva.get_json()["orden"]["estado"] == "PLANEADA"

    solicitada = client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/solicitar-compra",
        headers=headers_operativo,
    )
    assert solicitada.status_code == 200, solicitada.get_json()
    requisicion = solicitada.get_json()["requisicion"]
    datos_fase4["registrar_requisicion"](requisicion["id"])
    datos_fase4["registrar_orden"](orden["id"])

    detalle = client.get(
        f"/api/v1/produccion/ordenes/{orden['id']}", headers=headers_operativo
    )
    assert detalle.status_code == 200
    assert detalle.get_json()["semaforo"] == "AMBAR"

    duplicada = client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/solicitar-compra",
        headers=headers_operativo,
    )
    assert duplicada.status_code == 200
    assert duplicada.get_json()["duplicada"] is True


def test_merma_material_reverso_e_indicadores(
    client, headers_admin, headers_operativo, headers_cliente, datos_fase4, datos_fase3
):
    with datos_fase4["app"].app_context():
        causa = db.session.query(CausaMerma).filter_by(nombre="Otro").first()
        assert causa is not None
        causa_id = causa.id

    antes = _cantidades_lotes(datos_fase4)[0]
    creada = client.post(
        "/api/v1/mermas",
        json={
            "origen": "MATERIAL",
            "inventario_material_id": datos_fase4["inventario_id"],
            "lote_id": datos_fase4["lotes"][0],
            "etapa": "ALMACEN",
            "causa_id": causa_id,
            "cantidad": "1.0000",
            "descripcion": "Daño en almacén",
        },
        headers=headers_operativo,
    )
    assert creada.status_code == 201, creada.get_json()
    merma_id = creada.get_json()["id"]
    assert "costo_perdido" not in creada.get_json()
    assert _cantidades_lotes(datos_fase4)[0] == antes - Decimal("1.0000")

    vista_admin = client.get(f"/api/v1/mermas/{merma_id}", headers=headers_admin)
    assert vista_admin.status_code == 200
    assert "costo_perdido" in vista_admin.get_json()

    reverso = client.post(
        f"/api/v1/mermas/{merma_id}/reversar",
        json={"motivo": "Corrección de conteo"},
        headers=headers_admin,
    )
    assert reverso.status_code == 200, reverso.get_json()
    assert reverso.get_json()["merma"]["reversa_de_id"] is None
    assert reverso.get_json()["reverso"]["reversa_de_id"] == merma_id
    assert _cantidades_lotes(datos_fase4)[0] == antes

    duplicado = client.post(
        f"/api/v1/mermas/{merma_id}/reversar",
        json={"motivo": "Segundo reverso"},
        headers=headers_admin,
    )
    assert duplicado.status_code == 409
    assert duplicado.get_json()["codigo"] == "MERMA_YA_REVERSADA"

    with datos_fase4["app"].app_context():
        tipos = [
            fila[0]
            for fila in db.session.execute(
                text(
                    "SELECT tipo FROM movimiento_material WHERE lote_id = :id ORDER BY id"
                ),
                {"id": datos_fase4["lotes"][0]},
            ).all()
        ]
        assert tipos.count("MERMA") == 1
        assert tipos.count("REVERSA") == 1
        total_vista = db.session.execute(
            text(
                "SELECT COALESCE(SUM(cantidad), 0) FROM v_merma_resumen "
                "WHERE material = :material AND etapa = 'ALMACEN'"
            ),
            {"material": datos_fase4["material_codigo"]},
        ).scalar()
        assert Decimal(total_vista) == Decimal("0.0000")

    indicadores = client.get("/api/v1/mermas/indicadores", headers=headers_admin)
    assert indicadores.status_code == 200, indicadores.get_json()
    assert indicadores.get_json()["meta_pct"] == "5"
    assert isinstance(indicadores.get_json()["detalle"], list)

    assert client.get("/api/v1/mermas", headers=headers_cliente).status_code == 403
    assert client.get("/api/v1/mermas/indicadores", headers=headers_operativo).status_code == 403


def test_roles_transiciones_y_validaciones(client, headers_admin, headers_cliente, datos_fase4):
    assert client.get("/api/v1/produccion/ordenes", headers=headers_cliente).status_code == 403
    assert client.get("/api/v1/produccion/ordenes").status_code == 401

    sin_clave = client.post(
        f"/api/v1/produccion/ordenes/999999/iniciar", json={}, headers=headers_admin
    )
    assert sin_clave.status_code == 400
    assert sin_clave.get_json()["codigo"] == "IDEMPOTENCIA_REQUERIDA"

    creada = client.post(
        "/api/v1/produccion/ordenes",
        json={
            "lineas": [{"variante_id": datos_fase4["variante_id"], "cantidad": 1}],
            "fecha_requerida": (date.today() - timedelta(days=1)).isoformat(),
        },
        headers=headers_admin,
    )
    assert creada.status_code == 201, creada.get_json()
    orden = creada.get_json()
    datos_fase4["registrar_orden"](orden["id"])
    assert orden["semaforo"] == "ROJO"

    assert client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/reservar", headers=headers_admin
    ).status_code == 200
    assert client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/iniciar",
        json={},
        headers={
            **headers_admin,
            "Idempotency-Key": f"test-prod-rojo-{secrets.token_hex(6)}",
        },
    ).status_code == 200
    assert client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/revision",
        json={},
        headers=headers_admin,
    ).status_code == 200

    sin_cuadrar = client.post(
        f"/api/v1/produccion/ordenes/{orden['id']}/dictamen",
        json={
            "lineas": [
                {
                    "orden_linea_id": orden["lineas"][0]["id"],
                    "cantidad_revisada": 1,
                    "cantidad_aprobada": 1,
                    "cantidad_reproceso": 1,
                    "cantidad_merma": 0,
                    "medidas_ok": True,
                    "costuras_ok": True,
                    "bordado_ok": True,
                    "etiquetas_ok": True,
                }
            ]
        },
        headers=headers_admin,
    )
    assert sin_cuadrar.status_code == 422
    assert sin_cuadrar.get_json()["codigo"] == "CANTIDADES_NO_CONCUADRAN"

    cancelable = client.post(
        "/api/v1/produccion/ordenes",
        json={"lineas": [{"variante_id": datos_fase4["variante_id"], "cantidad": 1}]},
        headers=headers_admin,
    )
    assert cancelable.status_code == 201, cancelable.get_json()
    orden_cancelar = cancelable.get_json()
    datos_fase4["registrar_orden"](orden_cancelar["id"])

    cancelada = client.post(
        f"/api/v1/produccion/ordenes/{orden_cancelar['id']}/cancelar",
        json={"motivo": "Pedido cancelado por el cliente"},
        headers=headers_admin,
    )
    assert cancelada.status_code == 200, cancelada.get_json()
    assert cancelada.get_json()["estado"] == "CANCELADA"

    segunda = client.post(
        f"/api/v1/produccion/ordenes/{orden_cancelar['id']}/cancelar",
        json={"motivo": "Segunda cancelación"},
        headers=headers_admin,
    )
    assert segunda.status_code == 409
    assert segunda.get_json()["codigo"] == "ESTADO_INVALIDO"

    plan = client.get("/api/v1/produccion/plan-sugerido", headers=headers_admin)
    assert plan.status_code == 200
    assert set(plan.get_json()) == {"items", "total", "pagina", "por_pagina"}
