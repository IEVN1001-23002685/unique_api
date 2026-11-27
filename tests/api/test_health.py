import pytest


def test_liveness_no_consulta_base_de_datos(client):
    respuesta = client.get("/api/v1/health")
    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"estado": "ok", "servicio": "api"}


@pytest.mark.integration
def test_readiness_con_mysql(client, mysql_disponible):
    respuesta = client.get("/api/v1/health/db")
    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"estado": "ok", "base_datos": "disponible"}


def test_ruta_inexistente_usa_contrato_de_error(client):
    respuesta = client.get("/api/v1/ruta-inexistente")
    assert respuesta.status_code == 404
    assert respuesta.get_json() == {
        "codigo": "NO_ENCONTRADO",
        "mensaje": "Recurso no encontrado",
        "detalle": [],
    }


def test_cabeceras_de_seguridad(client):
    respuesta = client.get("/api/v1/health")
    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
    assert respuesta.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in respuesta.headers["Content-Security-Policy"]


def test_csp_de_swagger_no_debilita_la_api(client):
    documentacion = client.get("/api/v1/docs")
    assert documentacion.status_code == 200
    csp_docs = documentacion.headers["Content-Security-Policy"]
    assert "https://unpkg.com" in csp_docs
    assert "/static/swagger-init.js" in documentacion.get_data(as_text=True)

    csp_api = client.get("/api/v1/health").headers["Content-Security-Policy"]
    assert "https://unpkg.com" not in csp_api
    assert client.get("/static/swagger-init.js").status_code == 200
