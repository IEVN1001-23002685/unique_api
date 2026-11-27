"""Regresiones mínimas de compatibilidad entre el frontend Angular y la API Flask."""

import pytest

from app.schemas.catalogo import VarianteDisponibilidadSchema
from app.schemas.pedido import (
    PedidoAdminFiltrosSchema,
    PendienteProduccionFiltrosSchema,
)
from app.schemas.ventas import (
    DescuentoFiltrosSchema,
    VentaFiltrosSchema,
    VentaPagoSchema,
)


@pytest.mark.parametrize(
    "ruta",
    [
        "/api/v1/ventas",
        "/api/v1/descuentos",
        "/api/v1/pedidos",
        "/api/v1/pedidos/pendientes-produccion",
    ],
)
def test_listados_aceptan_paginacion_del_frontend(client, headers_admin, ruta):
    respuesta = client.get(f"{ruta}?pagina=1&por_pagina=5", headers=headers_admin)
    assert respuesta.status_code == 200, respuesta.get_json()
    datos = respuesta.get_json()
    assert datos["pagina"] == 1
    assert datos["por_pagina"] == 5
    assert "items" in datos and "total" in datos


@pytest.mark.parametrize(
    "esquema",
    [
        VentaFiltrosSchema,
        DescuentoFiltrosSchema,
        PedidoAdminFiltrosSchema,
        PendienteProduccionFiltrosSchema,
    ],
)
def test_esquemas_de_filtro_ignoran_paginacion(esquema):
    assert esquema().load({"pagina": 1, "por_pagina": 5}) == {}


def test_catalogo_serializa_comprable():
    variante = {
        "id": 1,
        "sku": "PL-CH-NE-0001",
        "talla": "CH",
        "color": "NE",
        "disponibilidad": "DISPONIBLE",
        "bajo_pedido": False,
        "fecha_estimada": None,
        "comprable": True,
    }
    assert VarianteDisponibilidadSchema().dump(variante)["comprable"] is True


def test_cuerpo_de_pago_del_frontend_no_requiere_ultimos4():
    datos = VentaPagoSchema().load(
        {
            "accion": "APROBAR",
            "metodo_pago": "EFECTIVO",
            "titular": None,
            "motivo": None,
        }
    )
    assert datos["accion"] == "APROBAR"
    assert "ultimos4" not in datos
