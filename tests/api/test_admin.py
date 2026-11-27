import secrets

import pytest

from app.extensions import db
from app.models import (
    Bitacora,
    Configuracion,
    RecuperacionContrasena,
    Rol,
    TokenRefresco,
    Usuario,
)


def test_admin_lista_usuarios_paginado(client, headers_admin):
    respuesta = client.get("/api/v1/usuarios?pagina=1&por_pagina=5", headers=headers_admin)
    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert set(datos) == {"items", "total", "pagina", "por_pagina"}
    assert datos["pagina"] == 1 and datos["por_pagina"] == 5
    assert len(datos["items"]) <= 5
    assert "password_hash" not in datos["items"][0]


def test_operativo_no_puede_administrar_usuarios(client, headers_operativo):
    respuesta = client.get("/api/v1/usuarios", headers=headers_operativo)
    assert respuesta.status_code == 403
    assert respuesta.get_json()["codigo"] == "PERMISO_INSUFICIENTE"


def test_cliente_no_puede_administrar_usuarios(client, headers_cliente):
    respuesta = client.get("/api/v1/usuarios", headers=headers_cliente)
    assert respuesta.status_code == 403


@pytest.mark.parametrize("rol", ["CLIENTE", "OPERATIVO", "ADMIN"])
def test_admin_crea_cuenta_real_por_rol_y_login_devuelve_ese_rol(
    client, headers_admin, app, rol
):
    correo = f"alta-{rol.lower()}-{secrets.token_hex(5)}@example.com"
    password = "ClaveSegura123!"
    respuesta = client.post(
        "/api/v1/usuarios",
        headers=headers_admin,
        json={
            "nombre": "Nuevo",
            "apellidos": rol.title(),
            "correo": correo,
            "telefono": "1234567890",
            "password": password,
            "rol": rol,
        },
    )
    assert respuesta.status_code == 201, respuesta.get_json()
    creado = respuesta.get_json()
    assert creado["rol"] == rol
    assert creado["estado_cuenta"] == "ACTIVA"
    assert "password_hash" not in creado

    acceso = client.post("/api/v1/auth/login", json={"correo": correo, "password": password})
    assert acceso.status_code == 200, acceso.get_json()
    datos = acceso.get_json()
    assert datos["usuario"]["rol"] == rol
    assert datos["usuario"]["correo"] == correo
    assert "password_hash" not in datos["usuario"]
    assert datos["access_token"]

    with app.app_context():
        usuario = db.session.query(Usuario).filter_by(correo=correo).one()
        assert usuario.rol.codigo == rol
        assert usuario.password_hash != password
        registro = (
            db.session.query(Bitacora)
            .filter_by(accion="USUARIO_CREADO", entidad="usuario", entidad_id=usuario.id)
            .order_by(Bitacora.id.desc())
            .first()
        )
        assert registro is not None
        assert registro.usuario_id is not None

        # La cuenta es real: deja rastros en bitácora y tokens, que se limpian al terminar.
        db.session.query(TokenRefresco).filter_by(usuario_id=usuario.id).delete()
        db.session.query(RecuperacionContrasena).filter_by(usuario_id=usuario.id).delete()
        db.session.query(Bitacora).filter(
            (Bitacora.usuario_id == usuario.id)
            | ((Bitacora.entidad == "usuario") & (Bitacora.entidad_id == usuario.id))
        ).delete(synchronize_session=False)
        db.session.delete(usuario)
        db.session.commit()


def test_admin_no_puede_desactivar_al_ultimo_administrador(client, crear_usuario, app):
    admin = crear_usuario("ADMIN")
    acceso = client.post(
        "/api/v1/auth/login",
        json={"correo": admin["correo"], "password": admin["password"]},
    )
    token = acceso.get_json()["access_token"]

    with app.app_context():
        rol_id = db.session.query(Rol).filter_by(codigo="ADMIN").one().id
        otros = db.session.query(Usuario).filter(
            Usuario.rol_id == rol_id, Usuario.id != admin["id"]
        ).all()
        estados = [(u.id, u.estado_cuenta) for u in otros]
        for usuario in otros:
            usuario.estado_cuenta = "INACTIVA"
        db.session.commit()

    try:
        respuesta = client.delete(
            f"/api/v1/usuarios/{admin['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert respuesta.status_code == 422
        assert respuesta.get_json()["codigo"] == "ULTIMO_ADMIN"
    finally:
        with app.app_context():
            for usuario_id, estado in estados:
                db.session.get(Usuario, usuario_id).estado_cuenta = estado
            db.session.commit()


def test_clientes_solo_visibles_por_admin(client, headers_cliente, headers_admin):
    assert client.get("/api/v1/clientes", headers=headers_cliente).status_code == 403
    respuesta = client.get("/api/v1/clientes", headers=headers_admin)
    assert respuesta.status_code == 200
    assert "total" in respuesta.get_json()


def test_bitacora_registra_login(client, headers_admin):
    respuesta = client.get("/api/v1/bitacora?por_pagina=100", headers=headers_admin)
    assert respuesta.status_code == 200
    acciones = [item["accion"] for item in respuesta.get_json()["items"]]
    assert "LOGIN" in acciones


def test_configuracion_solo_admin_puede_modificar(client, headers_admin, headers_cliente, app):
    assert client.patch(
        "/api/v1/configuracion", headers=headers_cliente, json={"iva_pct": "16"}
    ).status_code == 403

    with app.app_context():
        original = db.session.get(Configuracion, "iva_pct").valor
    try:
        respuesta = client.patch(
            "/api/v1/configuracion", headers=headers_admin, json={"iva_pct": "16"}
        )
        assert respuesta.status_code == 200
        assert respuesta.get_json()["iva_pct"] == "16"
    finally:
        with app.app_context():
            db.session.get(Configuracion, "iva_pct").valor = original
            db.session.commit()
