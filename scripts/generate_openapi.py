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
