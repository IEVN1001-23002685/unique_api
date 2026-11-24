import os

import pytest
from sqlalchemy import create_engine, text

from app import create_app


@pytest.fixture(scope="session")
def app():
    aplicacion = create_app()
    aplicacion.config.update(TESTING=True, DEBUG=False)
    return aplicacion


@pytest.fixture
def client(app):
    return app.test_client()


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
