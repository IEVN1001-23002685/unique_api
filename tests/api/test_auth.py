import secrets

from app.extensions import db
from app.models import Configuracion, Usuario

def iniciar_sesion(client, correo, password):
    respuesta = client.post(
        "/api/v1/auth/login", json={"correo": correo, "password": password}
    )
    assert respuesta.status_code == 200, respuesta.get_json()
    return {"Authorization": f"Bearer {respuesta.get_json()['access_token']}"}


def test_registro_publico_crea_cliente(client):
    respuesta = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre": "Nueva",
            "apellidos": "Cliente",
            "correo": f"registro-{secrets.token_hex(5)}@example.com",
            "telefono": "1234567890",
            "password": "ClaveSegura123!",
            "acepta_promociones": True,
        },
    )
    assert respuesta.status_code == 201
    datos = respuesta.get_json()
    assert datos["usuario"]["rol"] == "CLIENTE"
    assert "access_token" in datos
    assert any("refresh_token" in cookie for cookie in respuesta.headers.getlist("Set-Cookie"))


def test_registro_rechaza_datos_invalidos(client):
    respuesta = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre": "",
            "apellidos": "Cliente",
            "correo": "no-es-correo",
            "telefono": "123",
            "password": "corto",
        },
    )
    assert respuesta.status_code == 400
    datos = respuesta.get_json()
    assert datos["codigo"] == "VALIDACION"
    assert datos["detalle"]


def test_login_y_cuenta_autenticada(client, crear_usuario):
    usuario = crear_usuario()
    headers = iniciar_sesion(client, usuario["correo"], usuario["password"])
    respuesta = client.get("/api/v1/cuenta", headers=headers)
    assert respuesta.status_code == 200
    assert respuesta.get_json()["correo"] == usuario["correo"]


def test_sin_token_devuelve_401(client):
    respuesta = client.get("/api/v1/cuenta")
    assert respuesta.status_code == 401
    assert respuesta.get_json()["codigo"] == "NO_AUTENTICADO"


def test_login_credenciales_invalidas_no_revela_correo(client, crear_usuario):
    usuario = crear_usuario()
    respuesta = client.post(
        "/api/v1/auth/login",
        json={"correo": usuario["correo"], "password": "incorrecta"},
    )
    assert respuesta.status_code == 401
    assert respuesta.get_json()["mensaje"] == "Credenciales inválidas"


def test_refresh_tokens_se_rotan_y_se_revoca_el_anterior(client, crear_usuario, app):
    usuario = crear_usuario()
    respuesta = client.post(
        "/api/v1/auth/login",
        json={"correo": usuario["correo"], "password": usuario["password"]},
    )
    assert respuesta.status_code == 200
    cookie_original = next(
        valor.split(";", 1)[0]
        for valor in respuesta.headers.getlist("Set-Cookie")
        if valor.startswith("refresh_token")
    )
    nombre, valor_original = cookie_original.split("=", 1)

    primera = client.post("/api/v1/auth/refrescar")
    assert primera.status_code == 200
    assert "access_token" in primera.get_json()

    cliente_sin_cookies = app.test_client()
    reintento = cliente_sin_cookies.post(
        "/api/v1/auth/refrescar",
        headers={"Cookie": f"{nombre}={valor_original}"},
    )
    assert reintento.status_code == 401
    assert reintento.get_json()["codigo"] == "SESION_INVALIDA"


def test_logout_revoca_refresh(client, crear_usuario):
    usuario = crear_usuario()
    headers = iniciar_sesion(client, usuario["correo"], usuario["password"])
    respuesta = client.post("/api/v1/auth/logout", headers=headers)
    assert respuesta.status_code == 200
    posterior = client.post("/api/v1/auth/refrescar")
    assert posterior.status_code == 401


def test_usuario_desactivado_no_puede_entrar(client, crear_usuario, app):
    usuario = crear_usuario()
    with app.app_context():
        fila = db.session.get(Usuario, usuario["id"])
        fila.estado_cuenta = "INACTIVA"
        db.session.commit()
    respuesta = client.post(
        "/api/v1/auth/login",
        json={"correo": usuario["correo"], "password": usuario["password"]},
    )
    assert respuesta.status_code == 403
    assert respuesta.get_json()["codigo"] == "CUENTA_NO_ACTIVA"


def test_recuperacion_no_revela_si_existe_correo(client):
    respuesta = client.post("/api/v1/auth/recuperar", json={"correo": "nadie@example.com"})
    assert respuesta.status_code == 200
    assert "registrado" in respuesta.get_json()["mensaje"]


def test_cambio_de_contrasena_revoca_tokens(client, crear_usuario):
    usuario = crear_usuario()
    headers = iniciar_sesion(client, usuario["correo"], usuario["password"])
    respuesta = client.patch(
        "/api/v1/cuenta/contrasena",
        headers=headers,
        json={
            "contrasena_actual": usuario["password"],
            "contrasena_nueva": "OtraClaveSegura456!",
        },
    )
    assert respuesta.status_code == 200
    refresco = client.post("/api/v1/auth/refrescar")
    assert refresco.status_code == 401
    nuevo_login = client.post(
        "/api/v1/auth/login",
        json={"correo": usuario["correo"], "password": "OtraClaveSegura456!"},
    )
    assert nuevo_login.status_code == 200


def test_login_rate_limit_por_ip(client, crear_usuario):
    usuario = crear_usuario()
    ip = f"10.9.8.{secrets.randbelow(200) + 1}"
    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            json={"correo": usuario["correo"], "password": "incorrecta"},
            environ_base={"REMOTE_ADDR": ip},
        )
    respuesta = client.post(
        "/api/v1/auth/login",
        json={"correo": usuario["correo"], "password": "incorrecta"},
        environ_base={"REMOTE_ADDR": ip},
    )
    assert respuesta.status_code == 429
    assert respuesta.get_json()["codigo"] == "DEMASIADOS_INTENTOS"


def test_configuracion_sembrada(app, mysql_disponible):
    with app.app_context():
        claves = {
            fila.clave: fila.valor
            for fila in db.session.query(Configuracion).all()
        }
    assert claves["iva_pct"] == "16"
    assert claves["margen_objetivo_pct"] == "55"
    assert claves["max_piezas_por_linea"] == "10"
    assert claves["proveedor_minimo_a_tiempo_pct"] == "80"
