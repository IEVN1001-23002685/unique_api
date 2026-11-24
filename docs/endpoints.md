# Contrato HTTP

Prefijo global: `/api/v1`. La Fase 0 implementa únicamente los endpoints de infraestructura.

## Endpoints implementados

### `GET /api/v1/health`

- Rol: público.
- Parámetros: ninguno.
- Respuesta `200`:

```json
{ "estado": "ok", "servicio": "api" }
```

No consulta MySQL. Se usa como liveness de Docker y de Gunicorn.

### `GET /api/v1/health/db`

- Rol: público.
- Parámetros: ninguno.
- Respuesta `200`:

```json
{ "estado": "ok", "base_datos": "disponible" }
```

- Error `503`:

```json
{ "codigo": "BASE_DATOS_NO_DISPONIBLE", "mensaje": "La base de datos no está disponible", "detalle": [] }
```

Ejecuta `SELECT 1`. No expone SQL, host, credenciales ni trazas.

## Contrato común

- Listas paginadas: `{ "items": [], "total": 0, "pagina": 1, "por_pagina": 20 }`.
- Error: `{ "codigo": "...", "mensaje": "...", "detalle": [] }`.
- Códigos: `200`, `201`, `204`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`
  y `503` para readiness.
- Dinero como cadena decimal con dos decimales; materiales hasta cuatro decimales.
- Fechas ISO 8601 con zona horaria `TZ`.

## Pendiente

Los blueprints M01–M22 se documentarán aquí a medida que se implementen. La tabla completa
de rutas requeridas está en la sección 11 del documento integral y en `AGENTS.md`.
