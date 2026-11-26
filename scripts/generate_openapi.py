"""Genera docs/openapi.json desde las rutas Flask registradas.

El contrato funcional detallado sigue en docs/endpoints.md; este archivo
expone la especificación OpenAPI 3.0 para clientes y herramientas.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from wsgi import app


ROLES = {
    "auth.registro": "Público",
    "auth.login": "Público",
    "auth.refrescar": "Público (cookie de refresco)",
    "auth.logout": "Autenticado",
    "auth.recuperar": "Público",
    "auth.restablecer": "Público",
    "cuenta.cobertura_envio": "Público",
    "catalogo.listar_catalogo": "Público",
    "catalogo.detalle_producto": "Público",
}

# Contratos corregidos durante la auditoría de integración. Se aplican además del
# esqueleto generado desde las rutas para que `docs/openapi.json` no pierda los
# campos reales cuando se regenera.
DETALLES = {
    ("/api/v1/auth/registro", "post"): {
        "request": {"$ref": "#/components/schemas/RegistroEntrada"},
        "responses": {"201": {"$ref": "#/components/responses/SesionCreada"}},
    },
    ("/api/v1/auth/login", "post"): {
        "responses": {"200": {"$ref": "#/components/responses/Sesion"}},
    },
    ("/api/v1/auth/refrescar", "post"): {
        "responses": {"200": {"$ref": "#/components/responses/Sesion"}},
    },
    ("/api/v1/cuenta", "patch"): {
        "request": {"$ref": "#/components/schemas/CuentaActualizar"},
    },
    ("/api/v1/cuenta/contrasena", "patch"): {
        "request": {"$ref": "#/components/schemas/ContrasenaCambiar"},
        "responses": {"200": {"$ref": "#/components/responses/Mensaje"}},
    },
    ("/api/v1/cuenta/desactivar", "patch"): {
        "responses": {"200": {"$ref": "#/components/responses/Mensaje"}},
    },
    ("/api/v1/mis-pedidos", "get"): {
        "responses": {"200": {"$ref": "#/components/responses/PedidosLista"}},
    },
    ("/api/v1/mis-pedidos/{pedido_id}", "get"): {
        "responses": {"200": {"$ref": "#/components/responses/PedidoDetalle"}},
    },
    ("/api/v1/mis-pedidos/{pedido_id}/comprobante", "get"): {
        "responses": {"200": {"$ref": "#/components/responses/Comprobante"}},
    },
}

TAG_MAP = {
    "health": "Salud",
    "auth": "M01 Auth",
    "cuenta": "M02 Cuenta",
    "catalogo": "M03 Catálogo",
    "carrito": "M04 Carrito",
    "checkout": "M05 Checkout",
    "mis_pedidos": "M06 Mis pedidos",
    "devoluciones": "M07 Devoluciones",
    "ventas": "M08 Ventas",
    "pedidos": "M09 Pedidos",
    "productos": "M10 Productos",
    "recetas": "M11 Recetas",
    "inventario_pt": "M12 Inventario PT",
    "proveedores": "M13 Proveedores",
    "compras": "M14 Compras",
    "inventario_mp": "M15 Inventario MP",
    "produccion": "M16 Producción",
    "mermas": "M17 Mermas",
    "preparacion": "M18 Preparación",
    "entregas": "M19 Entregas",
    "dashboard": "M20 Dashboard",
    "alertas": "M21 Alertas",
    "admin": "M22 Admin",
}


def _tag(endpoint: str) -> str:
    return TAG_MAP.get(endpoint.split(".", 1)[0], endpoint.split(".", 1)[0])


def _operation_id(endpoint: str, method: str) -> str:
    base = endpoint.replace(".", "_")
    return f"{method.lower()}_{base}"


def _path_params(rule: str):
    params = []
    for converter, _args, name in re.findall(r"<(?:(\w+):)?(?:[^>]*\b)?(\w+)>|<(\w+)>", rule):
        # regex above is imperfect; fallback
        pass
    for m in re.finditer(r"<(?:(?P<conv>\w+):)?(?P<name>\w+)>", rule):
        conv = m.group("conv") or "string"
        name = m.group("name")
        schema = {"type": "integer"} if conv == "int" else {"type": "string"}
        params.append({
            "name": name,
            "in": "path",
            "required": True,
            "schema": schema,
        })
    return params


def _openapi_path(rule: str) -> str:
    return re.sub(r"<(?:(?:\w+):)?(\w+)>", r"{\1}", rule)


def _default_responses(method: str):
    responses = {
        "400": {"$ref": "#/components/responses/BadRequest"},
        "401": {"$ref": "#/components/responses/Unauthorized"},
        "403": {"$ref": "#/components/responses/Forbidden"},
        "404": {"$ref": "#/components/responses/NotFound"},
        "409": {"$ref": "#/components/responses/Conflict"},
        "422": {"$ref": "#/components/responses/Unprocessable"},
        "429": {"$ref": "#/components/responses/TooManyRequests"},
        "500": {"$ref": "#/components/responses/InternalError"},
    }
    if method == "POST":
        responses["201"] = {"description": "Recurso creado"}
        responses["200"] = {"description": "Operación correcta"}
    elif method == "DELETE":
        responses["204"] = {"description": "Sin contenido"}
    else:
        responses["200"] = {"description": "Operación correcta"}
    return responses


def build_spec():
    paths = {}
    tags = [{"name": v, "description": f"Endpoints del módulo {v}."} for v in dict.fromkeys(TAG_MAP.values())]
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/v1"):
            continue
        openapi_path = _openapi_path(rule.rule)
        methods = sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})
        path_item = paths.setdefault(openapi_path, {})
        for method in methods:
            endpoint = rule.endpoint
            op = {
                "tags": [_tag(endpoint)],
                "operationId": _operation_id(endpoint, method),
                "summary": endpoint.replace(".", " ").replace("_", " ").title(),
                "description": f"Contrato detallado en docs/endpoints.md. Rol/seguridad: {ROLES.get(endpoint, 'ver docs/endpoints.md')}.",
                "responses": _default_responses(method),
            }
            params = _path_params(rule.rule)
            if params:
                op["parameters"] = params
            if method in {"POST", "PUT", "PATCH"}:
                op["requestBody"] = {
                    "required": False,
                    "content": {
                        "application/json": {"schema": {"type": "object", "additionalProperties": True}},
                        "multipart/form-data": {"schema": {"type": "object", "additionalProperties": True}},
                    },
                }
            if endpoint != "auth.login" and endpoint != "auth.registro" and endpoint != "auth.recuperar" and endpoint != "auth.restablecer" and endpoint != "auth.refrescar" and endpoint not in {"catalogo.listar_catalogo", "catalogo.detalle_producto", "cuenta.cobertura_envio", "health.liveness", "health.readiness"}:
                op["security"] = [{"bearerAuth": []}]
            else:
                op["security"] = []
            detalle = DETALLES.get((openapi_path, method.lower()))
            if detalle:
                if "request" in detalle:
                    op["requestBody"] = {
                        "required": method in {"POST", "PUT", "PATCH"},
                        "content": {"application/json": {"schema": detalle["request"]}},
                    }
                if "responses" in detalle:
                    op["responses"].update(detalle["responses"])
            path_item[method.lower()] = op

    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "UNIQUE API",
            "version": "1.0.0",
            "description": "Especificación OpenAPI generada desde las rutas Flask registradas. El contrato funcional detallado, reglas de negocio, ejemplos y campos se encuentran en docs/endpoints.md.",
        },
        "servers": [{"url": "/"}],
        "tags": tags,
        "paths": dict(sorted(paths.items())),
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {
                        "codigo": {"type": "string"},
                        "mensaje": {"type": "string"},
                        "detalle": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    },
                    "required": ["codigo", "mensaje", "detalle"],
                },
                "Paginado": {
                    "type": "object",
                    "properties": {
                        "items": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                        "total": {"type": "integer"},
                        "pagina": {"type": "integer"},
                        "por_pagina": {"type": "integer"},
                    },
                },
                "Mensaje": {
                    "type": "object",
                    "properties": {"mensaje": {"type": "string"}},
                },
                "Usuario": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "nombre": {"type": "string"},
                        "apellidos": {"type": "string"},
                        "correo": {"type": "string", "format": "email"},
                        "telefono": {"type": "string"},
                        "estado_cuenta": {"type": "string"},
                        "acepta_privacidad": {"type": "boolean"},
                        "acepta_promociones": {"type": "boolean"},
                        "rol": {"type": "string"},
                    },
                },
                "RegistroEntrada": {
                    "type": "object",
                    "required": ["nombre", "apellidos", "correo", "telefono", "password", "acepta_privacidad"],
                    "properties": {
                        "nombre": {"type": "string"},
                        "apellidos": {"type": "string"},
                        "correo": {"type": "string", "format": "email"},
                        "telefono": {"type": "string", "pattern": "^\\d{10}$"},
                        "password": {"type": "string", "minLength": 8},
                        "acepta_privacidad": {"type": "boolean", "enum": [True]},
                        "acepta_promociones": {"type": "boolean"},
                    },
                },
                "Sesion": {
                    "type": "object",
                    "properties": {
                        "access_token": {"type": "string"},
                        "usuario": {"$ref": "#/components/schemas/Usuario"},
                    },
                },
                "CuentaActualizar": {
                    "type": "object",
                    "properties": {
                        "nombre": {"type": "string"},
                        "apellidos": {"type": "string"},
                        "telefono": {"type": "string"},
                        "correo": {"type": "string", "format": "email"},
                        "contrasena_actual": {"type": "string", "description": "Obligatoria si se envía correo"},
                        "acepta_promociones": {"type": "boolean"},
                    },
                },
                "ContrasenaCambiar": {
                    "type": "object",
                    "required": ["contrasena_actual", "contrasena_nueva"],
                    "properties": {
                        "contrasena_actual": {"type": "string"},
                        "contrasena_nueva": {"type": "string", "minLength": 8},
                    },
                },
                "PedidoLinea": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "venta_linea_id": {"type": "integer"},
                        "variante_id": {"type": "integer"},
                        "producto_id": {"type": "integer"},
                        "sku": {"type": "string"},
                        "nombre_producto": {"type": "string"},
                        "cantidad": {"type": "integer"},
                        "precio_unitario": {"type": "string"},
                        "subtotal": {"type": "string"},
                        "imagen": {"type": "string", "nullable": True},
                    },
                },
                "PedidoLista": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "folio": {"type": "string"},
                        "fecha": {"type": "string", "format": "date-time"},
                        "estado": {"type": "string"},
                        "total": {"type": "string"},
                        "articulos": {"type": "integer"},
                        "guia": {"type": "string", "nullable": True},
                        "imagen": {"type": "string", "nullable": True},
                        "fecha_estimada": {"type": "string", "format": "date", "nullable": True},
                        "fecha_entrega": {"type": "string", "format": "date-time", "nullable": True},
                    },
                },
                "PedidoDetalle": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "folio": {"type": "string"},
                        "fecha": {"type": "string", "format": "date-time"},
                        "estado": {"type": "string"},
                        "fecha_promesa": {"type": "string", "format": "date", "nullable": True},
                        "fecha_estimada": {"type": "string", "format": "date", "nullable": True},
                        "fecha_entrega": {"type": "string", "format": "date-time", "nullable": True},
                        "total_articulos": {"type": "integer"},
                        "total": {"type": "string"},
                        "direccion": {"type": "object", "nullable": True},
                        "articulos": {"type": "array", "items": {"$ref": "#/components/schemas/PedidoLinea"}},
                        "eventos": {"type": "array", "items": {"type": "object"}},
                        "guia": {"type": "string", "nullable": True},
                        "repartidor": {"type": "object", "nullable": True},
                    },
                },
                "Comprobante": {
                    "type": "object",
                    "properties": {
                        "folio": {"type": "string"},
                        "fecha": {"type": "string", "format": "date-time"},
                        "estado_pago": {"type": "string"},
                        "cliente": {"type": "object"},
                        "direccion": {"type": "object", "nullable": True},
                        "lineas": {"type": "array", "items": {"$ref": "#/components/schemas/PedidoLinea"}},
                        "subtotal": {"type": "string"},
                        "descuento_monto": {"type": "string"},
                        "costo_envio": {"type": "string"},
                        "total": {"type": "string"},
                    },
                },
            },
            "responses": {
                "BadRequest": {"description": "Petición inválida", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                "Unauthorized": {"description": "No autenticado", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                "Forbidden": {"description": "Sin permiso", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                "NotFound": {"description": "No encontrado", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                "Conflict": {"description": "Conflicto", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                "Unprocessable": {"description": "Regla de negocio", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                "TooManyRequests": {"description": "Demasiados intentos", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                "InternalError": {"description": "Error interno", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}},
                "Mensaje": {"description": "Operación correcta", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Mensaje"}}}},
                "Sesion": {"description": "Sesión iniciada o refrescada", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Sesion"}}}},
                "SesionCreada": {"description": "Cuenta creada", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Sesion"}}}},
                "PedidosLista": {"description": "Lista paginada", "content": {"application/json": {"schema": {"type": "object", "properties": {"items": {"type": "array", "items": {"$ref": "#/components/schemas/PedidoLista"}}, "total": {"type": "integer"}, "pagina": {"type": "integer"}, "por_pagina": {"type": "integer"}}}}}},
                "PedidoDetalle": {"description": "Detalle del pedido", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/PedidoDetalle"}}}},
                "Comprobante": {"description": "Comprobante JSON (no PDF)", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Comprobante"}}}},
            },
        },
    }
    return spec


def main():
    spec = build_spec()
    out = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generado {out} con {len(spec['paths'])} paths")


if __name__ == "__main__":
    main()
