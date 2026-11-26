import os
import secrets
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from app import create_app
from app.extensions import db
from app.models import (
    Bitacora,
    CategoriaProducto,
    Color,
    Producto,
    RecuperacionContrasena,
    Receta,
    Rol,
    StockVariante,
    Talla,
    TokenRefresco,
    Usuario,
    VarianteProducto,
)
from app.security.password import generar_hash


@pytest.fixture(scope="session")
def app():
    aplicacion = create_app()
    aplicacion.config.update(TESTING=True, DEBUG=False)
    return aplicacion


@pytest.fixture
def client(app):
    cliente = app.test_client()
    cliente.environ_base["REMOTE_ADDR"] = f"10.20.{secrets.randbelow(255)}.{secrets.randbelow(255)}"
    return cliente


@pytest.fixture(scope="session")
def mysql_disponible():
    url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("No hay URL de MySQL configurada")
    motor = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with motor.connect() as conexion:
            conexion.execute(text("SELECT 1"))
    except Exception as error:
        pytest.skip(f"MySQL no disponible: {type(error).__name__}")
    finally:
        motor.dispose()
    return True


@pytest.fixture
def crear_usuario(app):
    creados = []

    def _crear(codigo_rol="CLIENTE", password="ClaveSegura123!", correo=None):
        correo = correo or f"prueba-{secrets.token_hex(6)}@example.com"
        with app.app_context():
            rol = db.session.query(Rol).filter_by(codigo=codigo_rol).one()
            usuario = Usuario(
                rol_id=rol.id,
                nombre="Prueba",
                apellidos="Automatizada",
                correo=correo,
                telefono="1234567890",
                password_hash=generar_hash(password),
                estado_cuenta="ACTIVA",
                intentos_fallidos=0,
                acepta_promociones=False,
            )
            db.session.add(usuario)
            db.session.commit()
            creados.append(usuario.id)
            return {"id": usuario.id, "correo": correo, "password": password}

    yield _crear

    with app.app_context():
        for usuario_id in creados:
            db.session.query(TokenRefresco).filter_by(usuario_id=usuario_id).delete()
            db.session.query(RecuperacionContrasena).filter_by(usuario_id=usuario_id).delete()
            db.session.query(Bitacora).filter_by(usuario_id=usuario_id).delete()
            usuario = db.session.get(Usuario, usuario_id)
            if usuario is not None:
                db.session.delete(usuario)
        db.session.commit()


def iniciar_sesion(client, correo, password):
    respuesta = client.post(
        "/api/v1/auth/login", json={"correo": correo, "password": password}
    )
    assert respuesta.status_code == 200, respuesta.get_json()
    return {"Authorization": f"Bearer {respuesta.get_json()['access_token']}"}


@pytest.fixture
def headers_admin(client, crear_usuario):
    usuario = crear_usuario("ADMIN")
    return iniciar_sesion(client, usuario["correo"], usuario["password"])


@pytest.fixture
def headers_operativo(client, crear_usuario):
    usuario = crear_usuario("OPERATIVO")
    return iniciar_sesion(client, usuario["correo"], usuario["password"])


@pytest.fixture
def headers_cliente(client, crear_usuario):
    usuario = crear_usuario("CLIENTE")
    return iniciar_sesion(client, usuario["correo"], usuario["password"])


@pytest.fixture
def tienda(app, mysql_disponible):
    """Datos aislados de catálogo, clientes e idempotencia para Fase 2."""
    usuarios = []
    variantes = []
    productos = []
    claves_idempotencia = []

    def crear_producto(existencia=0, precio="100.00", permite_bajo_pedido=False):
        with app.app_context():
            categoria = db.session.query(CategoriaProducto).filter_by(
                prefijo_sku="PL"
            ).one()
            talla = db.session.query(Talla).filter_by(codigo="CH").one()
            color = db.session.query(Color).filter_by(codigo="GR").one()
            sufijo = secrets.token_hex(3).upper()
            producto = Producto(
                categoria_id=categoria.id,
                codigo_sku=sufijo[:4],
                nombre=f"Prueba {sufijo}",
                descripcion="Producto de prueba",
                composicion_textil="Algodón",
                guia_medidas="",
                precio_venta=precio,
                permite_bajo_pedido=permite_bajo_pedido,
                activo=True,
            )
            db.session.add(producto)
            db.session.flush()
            variante = VarianteProducto(
                producto_id=producto.id,
                talla_id=talla.id,
                color_id=color.id,
                sku=f"TST-{sufijo}",
                activa=True,
            )
            db.session.add(variante)
            db.session.flush()
            db.session.add(
                StockVariante(
                    variante_id=variante.id,
                    existencia=existencia,
                    reservado=0,
                    stock_minimo=1,
                    cantidad_reposicion=20,
                )
            )
            db.session.add(
                Receta(
                    producto_id=producto.id,
                    talla_id=talla.id,
                    version=1,
                    estado="VIGENTE",
                )
            )
            db.session.commit()
            productos.append(producto.id)
            variantes.append(variante.id)
            return {
                "producto_id": producto.id,
                "variante_id": variante.id,
                "sku": variante.sku,
            }

    def crear_cliente(rol="CLIENTE"):
        correo = f"tienda-{secrets.token_hex(6)}@example.com"
        password = "ClaveSegura123!"
        with app.app_context():
            rol_obj = db.session.query(Rol).filter_by(codigo=rol).one()
            usuario = Usuario(
                rol_id=rol_obj.id,
                nombre="Tienda",
                apellidos="Prueba",
                correo=correo,
                telefono="1234567890",
                password_hash=generar_hash(password),
                estado_cuenta="ACTIVA",
                intentos_fallidos=0,
                acepta_promociones=False,
            )
            db.session.add(usuario)
            db.session.commit()
            usuarios.append(usuario.id)
            return {"id": usuario.id, "correo": correo, "password": password}

    yield {"crear_producto": crear_producto, "crear_cliente": crear_cliente}

    with app.app_context():
        if not usuarios and not variantes:
            return
        if usuarios:
            db.session.execute(
                text(
                    "DELETE FROM carrito_linea WHERE carrito_id IN "
                    "(SELECT id FROM carrito WHERE usuario_id IN :ids)"
                ).bindparams(db.bindparam("ids", usuarios, expanding=True))
            )
        if variantes:
            db.session.execute(
                text("DELETE FROM carrito_linea WHERE variante_id IN :ids").bindparams(
                    db.bindparam("ids", variantes, expanding=True)
                )
            )
        ventas = [
            fila[0]
            for fila in db.session.execute(
                text("SELECT id FROM venta WHERE usuario_id IN :ids").bindparams(
                    db.bindparam("ids", usuarios, expanding=True)
                )
            ).all()
        ] if usuarios else []
        pedidos = []
        if ventas:
            pedidos = [
                fila[0]
                for fila in db.session.execute(
                    text("SELECT id FROM pedido WHERE venta_id IN :ids").bindparams(
                        db.bindparam("ids", ventas, expanding=True)
                    )
                ).all()
            ]
            pedido_lineas = [
                fila[0]
                for fila in db.session.execute(
                    text("SELECT id FROM pedido_linea WHERE pedido_id IN :ids").bindparams(
                        db.bindparam("ids", pedidos, expanding=True)
                    )
                ).all()
            ]
            preparaciones = [
                fila[0]
                for fila in db.session.execute(
                    text("SELECT id FROM preparacion WHERE pedido_id IN :ids").bindparams(
                        db.bindparam("ids", pedidos, expanding=True)
                    )
                ).all()
            ]
            ordenes = [
                fila[0]
                for fila in db.session.execute(
                    text(
                        "SELECT DISTINCT l.orden_id FROM produccion_pedido p "
                        "JOIN orden_produccion_linea l ON l.id = p.orden_linea_id "
                        "WHERE p.pedido_linea_id IN :ids"
                    ).bindparams(db.bindparam("ids", pedido_lineas, expanding=True))
                ).all()
            ] if pedido_lineas else []
            for tabla, columna, ids in (
                ("preparacion_linea", "preparacion_id", preparaciones),
                ("produccion_pedido", "pedido_linea_id", pedido_lineas),
                ("pedido_evento", "pedido_id", pedidos),
                ("pedido_linea", "pedido_id", pedidos),
                ("preparacion", "pedido_id", pedidos),
            ):
                if ids:
                    db.session.execute(
                        text(f"DELETE FROM {tabla} WHERE {columna} IN :ids").bindparams(
                            db.bindparam("ids", ids, expanding=True)
                        )
                    )
            if ordenes:
                lineas_orden = [
                    fila[0]
                    for fila in db.session.execute(
                        text(
                            "SELECT id FROM orden_produccion_linea WHERE orden_id IN :ids"
                        ).bindparams(db.bindparam("ids", ordenes, expanding=True))
                    ).all()
                ]
                if lineas_orden:
                    db.session.execute(
                        text(
                            "DELETE FROM orden_produccion_linea WHERE id IN :ids"
                        ).bindparams(db.bindparam("ids", lineas_orden, expanding=True))
                    )
                db.session.execute(
                    text("DELETE FROM orden_produccion WHERE id IN :ids").bindparams(
                        db.bindparam("ids", ordenes, expanding=True)
                    )
                )
            db.session.execute(text("DELETE FROM pedido WHERE id IN :ids").bindparams(
                db.bindparam("ids", pedidos, expanding=True)
            ))
            for tabla in ("pago", "venta_direccion", "venta_linea"):
                db.session.execute(
                    text(f"DELETE FROM {tabla} WHERE venta_id IN :ids").bindparams(
                        db.bindparam("ids", ventas, expanding=True)
                    )
                )
            db.session.execute(text("DELETE FROM venta WHERE id IN :ids").bindparams(
                db.bindparam("ids", ventas, expanding=True)
            ))

        if variantes:
            db.session.execute(text("SET @permite_borrar_movimiento=1"))
            db.session.execute(
                text("DELETE FROM movimiento_producto WHERE variante_id IN :ids").bindparams(
                    db.bindparam("ids", variantes, expanding=True)
                )
            )
            db.session.execute(text("SET @permite_borrar_movimiento=0"))
            db.session.execute(
                text(
                    "DELETE FROM alerta WHERE entidad_tipo = 'variante_producto' "
                    "AND entidad_id IN :ids"
                ).bindparams(db.bindparam("ids", variantes, expanding=True))
            )
            db.session.execute(
                text("DELETE FROM stock_variante WHERE variante_id IN :ids").bindparams(
                    db.bindparam("ids", variantes, expanding=True)
                )
            )
            db.session.execute(
                text("DELETE FROM variante_producto WHERE id IN :ids").bindparams(
                    db.bindparam("ids", variantes, expanding=True)
                )
            )
        if productos:
            recetas = [
                fila[0]
                for fila in db.session.execute(
                    text("SELECT id FROM receta WHERE producto_id IN :ids").bindparams(
                        db.bindparam("ids", productos, expanding=True)
                    )
                ).all()
            ]
            if recetas:
                for tabla in ("receta_linea", "receta_bordado"):
                    db.session.execute(
                        text(f"DELETE FROM {tabla} WHERE receta_id IN :ids").bindparams(
                            db.bindparam("ids", recetas, expanding=True)
                        )
                    )
                db.session.execute(
                    text("DELETE FROM receta WHERE id IN :ids").bindparams(
                        db.bindparam("ids", recetas, expanding=True)
                    )
                )
            db.session.execute(
                text("DELETE FROM producto WHERE id IN :ids").bindparams(
                    db.bindparam("ids", productos, expanding=True)
                )
            )
        db.session.execute(
            text(
                "DELETE FROM idempotencia_operacion WHERE clave LIKE 'test-%' "
                "OR clave IN :ids"
            ).bindparams(db.bindparam("ids", claves_idempotencia or [""], expanding=True))
        )
        if usuarios:
            for tabla in ("token_refresco", "recuperacion_contrasena", "bitacora"):
                db.session.execute(
                    text(f"DELETE FROM {tabla} WHERE usuario_id IN :ids").bindparams(
                        db.bindparam("ids", usuarios, expanding=True)
                    )
                )
            for tabla in ("carrito", "direccion", "medio_pago"):
                db.session.execute(
                    text(f"DELETE FROM {tabla} WHERE usuario_id IN :ids").bindparams(
                        db.bindparam("ids", usuarios, expanding=True)
                    )
                )
            db.session.execute(text("DELETE FROM usuario WHERE id IN :ids").bindparams(
                db.bindparam("ids", usuarios, expanding=True)
            ))
        db.session.commit()


@pytest.fixture
def limpieza_fase3(app, mysql_disponible):
    """Limpia datos de Fase 3 en orden de registro: hijos antes que padres."""
    tareas = []
    finales = []

    def registrar(sql, parametros=None):
        tareas.append((sql, parametros or {}))

    def registrar_al_final(sql, parametros=None):
        finales.append((sql, parametros or {}))

    registrar.al_final = registrar_al_final
    yield registrar

    with app.app_context():
        for sql, parametros in (*tareas, *finales):
            db.session.execute(text(sql), parametros)
        db.session.commit()


@pytest.fixture
def datos_fase3(app, limpieza_fase3):
    """Datos base de catálogo y materiales para pruebas de M10-M15."""
    from app.models import (
        CausaMerma,
        CategoriaProducto,
        Color,
        InventarioMaterial,
        Material,
        Proveedor,
        ProveedorMaterial,
        Talla,
    )

    with app.app_context():
        categoria = db.session.query(CategoriaProducto).filter_by(prefijo_sku="PL").one()
        tallas = {
            fila.codigo: fila.id
            for fila in db.session.query(Talla).filter(Talla.codigo.in_(["CH", "MD", "GD"])).all()
        }
        colores = {
            fila.codigo: fila.id
            for fila in db.session.query(Color).filter(Color.codigo.in_(["BL", "NG", "GR"])).all()
        }
        material = db.session.query(Material).filter_by(codigo="TEL-FEL").one()
        inventario = db.session.query(InventarioMaterial).filter_by(
            material_id=material.id, color_id=colores["BL"]
        ).one()
        causa_rechazo = db.session.query(CausaMerma).filter_by(
            nombre="Rechazo en recepción"
        ).one()

    def crear_proveedor():
        sufijo = secrets.token_hex(4).upper()
        with app.app_context():
            proveedor = Proveedor(
                razon_social=f"Proveedor {sufijo}",
                nombre_comercial=f"Proveedor {sufijo}",
                rfc="AAA010101AAA",
                contacto="Contacto",
                telefono="1234567890",
                correo=f"proveedor-{sufijo.lower()}@example.com",
                direccion="Dirección de prueba",
                condiciones_pago="Contado",
            )
            db.session.add(proveedor)
            db.session.flush()
            proveedor_id = proveedor.id
            db.session.add(
                ProveedorMaterial(
                    proveedor_id=proveedor.id,
                    material_id=material.id,
                    precio_compra=Decimal("5000.00"),
                    minimo_compra=Decimal("1.00"),
                    plazo_dias=7,
                    es_principal=True,
                    activo=True,
                )
            )
            db.session.commit()
        limpieza_fase3("DELETE FROM proveedor_material WHERE proveedor_id = :id", {"id": proveedor_id})
        limpieza_fase3.al_final("DELETE FROM proveedor WHERE id = :id", {"id": proveedor_id})
        return proveedor_id

    return {
        "categoria_id": categoria.id,
        "tallas": tallas,
        "colores": colores,
        "material_id": material.id,
        "inventario_material_id": inventario.id,
        "causa_rechazo_id": causa_rechazo.id,
        "crear_proveedor": crear_proveedor,
        "limpiar": limpieza_fase3,
    }
