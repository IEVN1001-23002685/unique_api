import os
import secrets

import pytest
from sqlalchemy import create_engine, text

from app import create_app
from app.extensions import db
from app.models import Bitacora, RecuperacionContrasena, Rol, TokenRefresco, Usuario
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
