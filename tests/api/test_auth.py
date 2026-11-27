import secrets

import pytest

from app.extensions import db
from app.models import Configuracion, Usuario

def iniciar_sesion(client, correo, password):
    respuesta = client.post(
        "/api/v1/auth/login", json={"correo": correo, "password": password}
    )
    assert respuesta.status_code == 200, respuesta.get_json()
    return {"Authorization": f"Bearer {respuesta.get_json()['access_token']}"}


def cabecera_csrf(client):
    cookie = client.get_cookie("csrf_refresh_token")
    assert cookie is not None, "El login debe emitir la cookie de doble envío CSRF"
    return {"X-CSRF-TOKEN": cookie.value}


def test_registro_publico_crea_cliente(client, app):
    respuesta = client.post(
        "/api/v1/auth/registro",
        json={
            "nombre": "Nueva",
            "apellidos": "Cliente",
            "correo": f"registro-{secrets.token_hex(5)}@example.com",
            "telefono": "1234567890",
            "password": "ClaveSegura123!",
            "acepta_privacidad": True,
            "acepta_promociones": True,
        },
    )
    assert respuesta.status_code == 201
    datos = respuesta.get_json()
    assert datos["usuario"]["rol"] == "CLIENTE"
    assert datos["usuario"]["acepta_privacidad"] is True
    assert "access_token" in datos
    assert any("refresh_token" in cookie for cookie in respuesta.headers.getlist("Set-Cookie"))
    with app.app_context():
        usuario = db.session.get(Usuario, datos["usuario"]["id"])
        assert usuario.acepta_privacidad is True


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


@pytest.mark.parametrize("acepta_privacidad", [None, False])
def test_registro_exige_aceptacion_de_privacidad(client, acepta_privacidad):
    cuerpo = {
        "nombre": "Nueva",
        "apellidos": "Cliente",
        "correo": f"privacidad-{secrets.token_hex(5)}@example.com",
        "telefono": "1234567890",
        "password": "ClaveSegura123!",
    }
    if acepta_privacidad is not None:
        cuerpo["acepta_privacidad"] = acepta_privacidad
    respuesta = client.post("/api/v1/auth/registro", json=cuerpo)
    assert respuesta.status_code == 400
    assert respuesta.get_json()["codigo"] == "VALIDACION"
    assert any(
        detalle["campo"] == "acepta_privacidad"
        for detalle in respuesta.get_json()["detalle"]
    )


def test_login_y_cuenta_autenticada(client, crear_usuario):
    usuario = crear_usuario()
    headers = iniciar_sesion(client, usuario["correo"], usuario["password"])
    respuesta = client.get("/api/v1/cuenta", headers=headers)
    assert respuesta.status_code == 200
    assert respuesta.get_json()["correo"] == usuario["correo"]


def test_cambio_de_correo_requiere_contrasena(client, crear_usuario):
    usuario = crear_usuario()
    otro = crear_usuario()
    headers = iniciar_sesion(client, usuario["correo"], usuario["password"])
    nuevo = f"nuevo-{secrets.token_hex(5)}@example.com"

    sin_contrasena = client.patch(
        "/api/v1/cuenta", headers=headers, json={"correo": nuevo}
    )
    assert sin_contrasena.status_code == 400
    assert sin_contrasena.get_json()["codigo"] == "VALIDACION"

    incorrecta = client.patch(
        "/api/v1/cuenta",
        headers=headers,
        json={"correo": nuevo, "contrasena_actual": "no-es-la-clave"},
    )
    assert incorrecta.status_code == 401
    assert incorrecta.get_json()["codigo"] == "CONTRASENA_INVALIDA"

    duplicado = client.patch(
        "/api/v1/cuenta",
        headers=headers,
        json={"correo": otro["correo"], "contrasena_actual": usuario["password"]},
    )
    assert duplicado.status_code == 409
    assert duplicado.get_json()["codigo"] == "CORREO_REGISTRADO"

    correcta = client.patch(
        "/api/v1/cuenta",
        headers=headers,
        json={"correo": nuevo, "contrasena_actual": usuario["password"]},
    )
    assert correcta.status_code == 200, correcta.get_json()
    assert correcta.get_json()["correo"] == nuevo


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
    csrf = cabecera_csrf(client)

    primera = client.post("/api/v1/auth/refrescar", headers=csrf)
    assert primera.status_code == 200
    assert "access_token" in primera.get_json()

    cliente_sin_cookies = app.test_client()
    reintento = cliente_sin_cookies.post(
        "/api/v1/auth/refrescar",
        headers={**csrf, "Cookie": f"{nombre}={valor_original}"},
    )
    assert reintento.status_code == 401
    assert reintento.get_json()["codigo"] == "SESION_INVALIDA"


def test_refrescar_requiere_cabecera_csrf(client, crear_usuario):
    usuario = crear_usuario()
    iniciar_sesion(client, usuario["correo"], usuario["password"])

    respuesta = client.post("/api/v1/auth/refrescar")
    assert respuesta.status_code == 401
    assert respuesta.get_json()["codigo"] == "CSRF_INVALIDO"


def test_logout_revoca_refresh(client, crear_usuario):
    usuario = crear_usuario()
    headers = {**iniciar_sesion(client, usuario["correo"], usuario["password"]), **cabecera_csrf(client)}
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


def test_desactivar_cuenta_propia_revoca_sesion(client, crear_usuario, app):
    usuario = crear_usuario()
    headers = iniciar_sesion(client, usuario["correo"], usuario["password"])

    generica = client.patch("/api/v1/cuenta", headers=headers, json={"estado_cuenta": "ACTIVA"})
    assert generica.status_code == 400
    assert generica.get_json()["codigo"] == "VALIDACION"

    respuesta = client.patch("/api/v1/cuenta/desactivar", headers=headers)
    assert respuesta.status_code == 200, respuesta.get_json()
    assert respuesta.get_json()["mensaje"] == "Cuenta desactivada"

    sin_sesion = client.patch("/api/v1/cuenta", headers=headers, json={"nombre": "Otro"})
    assert sin_sesion.status_code == 401

    segunda = client.patch("/api/v1/cuenta/desactivar", headers=headers)
    assert segunda.status_code == 401

    refresco = client.post("/api/v1/auth/refrescar")
    assert refresco.status_code == 401
    with app.app_context():
        assert db.session.get(Usuario, usuario["id"]).estado_cuenta == "INACTIVA"


def test_cambio_de_contrasena_rechaza_post(client, crear_usuario):
    usuario = crear_usuario()
    headers = iniciar_sesion(client, usuario["correo"], usuario["password"])
    respuesta = client.post(
        "/api/v1/cuenta/contrasena",
        headers=headers,
        json={
            "contrasena_actual": usuario["password"],
            "contrasena_nueva": "OtraClaveSegura456!",
        },
    )
    assert respuesta.status_code == 405
    assert respuesta.get_json()["codigo"] == "METODO_NO_PERMITIDO"


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
