# Contrato HTTP

Prefijo global: `/api/v1`. Estado: Fase 0 (infraestructura) y Fase 1 (modelo de datos,
semillas, autenticación y administración) implementadas. Los módulos M02–M22 restantes
se documentarán al implementarse.

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

## M01 — Autenticación

| Método | Ruta | Rol | Cuerpo | Respuesta |
|---|---|---|---|---|
| `POST` | `/auth/registro` | P | `nombre`, `apellidos`, `correo`, `telefono`, `password`, `acepta_promociones` | `201`, `access_token` + cookie de refresco; crea `CLIENTE` |
| `POST` | `/auth/login` | P | `correo`, `password` | `200`, `access_token` + cookie de refresco |
| `POST` | `/auth/refrescar` | P | Cookie `refresh_token_cookie` | `200`, nuevo `access_token` y rotación de cookie |
| `POST` | `/auth/logout` | autenticado | Cookie de refresco; cabecera Bearer | `200`, revoca el refresco |
| `POST` | `/auth/recuperar` | P | `correo` | `200`, mensaje genérico |
| `POST` | `/auth/restablecer` | P | `token`, `password` | `200` |

Errores habituales: `400 VALIDACION`, `401 CREDENCIALES_INVALIDAS`/`SESION_INVALIDA`,
`403 CUENTA_NO_ACTIVA`, `409 CORREO_REGISTRADO`, `429 DEMASIADOS_INTENTOS`.

- Rate limit de login: 5 intentos por minuto por IP y por correo.
- Access token: 15 minutos en `Authorization: Bearer`.
- Refresh token: 7 días en cookie `httpOnly`, `SameSite=Strict`, `Secure` en producción.
- La misma clave de refresco solo sirve una vez; al usarla se emite una nueva y la anterior queda revocada.

## M02 — Cuenta (parcial)

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| `GET` | `/cuenta` | autenticado | Perfil del usuario autenticado |
| `PATCH` | `/cuenta` | autenticado | `nombre`, `apellidos`, `telefono`, `acepta_promociones` |
| `PATCH` | `/cuenta/contrasena` | autenticado | `contrasena_actual`, `contrasena_nueva`; revoca refresh tokens |

## M22 — Administración (parcial)

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| `GET` | `/usuarios` | A | Lista paginada |
| `POST` | `/usuarios` | A | `201`, crea usuario con rol indicado |
| `GET` | `/usuarios/{id}` | A | Usuario |
| `PATCH` | `/usuarios/{id}` | A | Actualiza campos permitidos |
| `DELETE` | `/usuarios/{id}` | A | `204`, desactivación lógica |
| `GET` | `/clientes` | A | Lista paginada de `CLIENTE` |
| `GET` | `/clientes/{id}` | A | Cliente |
| `GET` | `/bitacora` | A | Lista paginada de acciones sensibles |
| `GET` | `/configuracion` | A | Parámetros del sistema |
| `PATCH` | `/configuracion` | A | Actualiza uno o varios parámetros |

`OPERATIVO` **no** puede administrar usuarios; `ADMIN` sí puede ejecutar acciones de
`OPERATIVO`. No se puede desactivar ni cambiar el rol al último `ADMIN` activo
(`422 ULTIMO_ADMIN`).

## Contrato común

- Listas paginadas: `{ "items": [], "total": 0, "pagina": 1, "por_pagina": 20 }`.
- Error: `{ "codigo": "...", "mensaje": "...", "detalle": [] }`.
- Códigos: `200`, `201`, `204`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`
  y `503` para readiness.
- Dinero como cadena decimal con dos decimales; materiales hasta cuatro decimales.
- Fechas ISO 8601 con zona horaria `TZ`.

## Pendiente

Los blueprints M03–M21 y el resto de M02/M22 se documentarán aquí a medida que se
implementen. La tabla completa de rutas requeridas está en la sección 11 del documento
integral y en `AGENTS.md`.
