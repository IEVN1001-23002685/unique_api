# Contrato HTTP

Prefijo global: `/api/v1`. Estado: Fases 0, 1 y 2 implementadas y verificadas. La Fase 2
cubre cuenta, direcciones, medios de pago, cobertura de envío, catálogo, carrito, checkout
simulado y pedidos del cliente (M02–M06). Los módulos M07–M21 y el resto de M22 se
documentarán al implementarse.

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

## M02 — Cuenta y envío

| Método | Ruta | Rol | Cuerpo / parámetros | Respuesta |
|---|---|---|---|---|
| `GET` | `/cuenta` | autenticado | — | Perfil del usuario autenticado (`200`) |
| `PATCH` | `/cuenta` | autenticado | `nombre`, `apellidos`, `telefono`, `acepta_promociones` | Perfil actualizado (`200`) |
| `PATCH` | `/cuenta/contrasena` | autenticado | `contrasena_actual`, `contrasena_nueva` | `200`; revoca refresh tokens |
| `GET` | `/cuenta/direcciones` | C | — | Lista de direcciones activas propias (`200`) |
| `POST` | `/cuenta/direcciones` | C | `tipo`, `alias`, `destinatario`, `telefono`, `calle`, `numero_ext`, `colonia`, `municipio`, `estado`, `codigo_postal`, opcionales `numero_int`, `referencia`, `rfc`, `razon_social`, `predeterminada` | `201` |
| `PATCH` | `/cuenta/direcciones/{id}` | C | Campos parciales de dirección | `200` |
| `DELETE` | `/cuenta/direcciones/{id}` | C | — | `204`; borrado lógico (`activa=false`) |
| `GET` | `/cuenta/medios-pago` | C | — | Medios de pago activos propios (`200`) |
| `POST` | `/cuenta/medios-pago` | C | `tipo` (`TARJETA`/`CUENTA`), `alias`, `titular`; tarjeta: `numero_tarjeta`, `vence_mes`, `vence_anio`, `cvv`; cuenta: `saldo_inicial` opcional | `201`; solo se guardan `ultimos4`, marca y vigencia |
| `PATCH` | `/cuenta/medios-pago/{id}` | C | `alias` | `200` |
| `DELETE` | `/cuenta/medios-pago/{id}` | C | — | `204`; borrado lógico |
| `GET` | `/envio/cobertura?cp=` | P | `cp` de 5 dígitos | `200` con `cobertura`, `tarifa`, `costo` y `dias_estimados` |

Errores: `400 VALIDACION`, `400 CODIGO_POSTAL_INVALIDO`, `401 NO_AUTENTICADO`,
`403 PERMISO_INSUFICIENTE`, `404 DIRECCION_NO_ENCONTRADA`/`MEDIO_PAGO_NO_ENCONTRADO`,
`422 DATOS_FACTURACION_INCOMPLETOS`, `422 TARJETA_INVALIDA`/`TARJETA_VENCIDA`/`CVV_INVALIDO`.

Una sola dirección predeterminada por `tipo` por usuario. Las consultas siempre filtran por
el usuario autenticado; un `usuario_id` enviado por el navegador se ignora.

## M03 — Catálogo

| Método | Ruta | Rol | Parámetros | Respuesta |
|---|---|---|---|---|
| `GET` | `/catalogo` | P | `categoria`, `color`, `talla`, `q`, `disponibles` | Lista de productos activos con variantes (`200`) |
| `GET` | `/catalogo/{producto_id}` | P | — | Detalle con composición, guía, imágenes y variantes (`200`) |

Cada variante expone `disponibilidad` (`Disponible`, `Pocas unidades`, `Bajo pedido`,
`Agotado`), `bajo_pedido`, `fecha_estimada` y `comprable`. Nunca se exponen existencias
exactas ni reservas. El catálogo no incluye costos, precios de compra ni márgenes.

## M04 — Carrito

| Método | Ruta | Rol | Cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/carrito` | C | — | Carrito revalidado con disponibilidad por línea (`200`) |
| `PUT` | `/carrito/lineas` | C | `variante_id`, `cantidad` | Carrito actualizado (`200`) |
| `DELETE` | `/carrito/lineas/{variante_id}` | C | — | `204` |
| `POST` | `/carrito/fusionar` | C | `lineas: [{variante_id, cantidad}]` | Carrito fusionado (`200`) |

Existe un carrito `ABIERTO` por usuario. `cantidad` no puede superar
`max_piezas_por_linea` (configurable, propuesto 10). Las líneas se revalidan contra
variantes activas y existencia; una línea no comprable se marca `comprable=false`.

## M05 — Checkout

| Método | Ruta | Rol | Cuerpo | Respuesta |
|---|---|---|---|---|
| `POST` | `/checkout/cotizar` | C | `codigo_postal` o `direccion_id`, `descuento_codigo`, opcional facturación | Subtotal, descuento, envío, total, fecha promesa y líneas (`200`) |
| `POST` | `/checkout/descuento` | C | `codigo` | Descuento aplicable y ahorro (`200`) |
| `POST` | `/checkout/pagar` | C | `direccion_id` o `direccion`, `metodo_pago`, medio guardado o datos de tarjeta, opcional `descuento_codigo` y facturación | `201` con venta, pedido y resumen |

`/checkout/pagar` exige la cabecera `Idempotency-Key`. La misma clave con el mismo cuerpo
devuelve la respuesta original; con otro cuerpo responde `409 IDEMPOTENCIA_CONFLICTO`.
El total se recalcula en servidor como `subtotal - descuento + costo_envio`, con IVA
incluido en los precios. El pago simulado valida Luhn y vigencia; la terminación `0000`
rechaza. Nunca se guarda el número completo de tarjeta ni el CVV.

Flujo atómico: bloqueo de `stock_variante` por ID ascendente → validación de CP y descuento
→ pago → venta, líneas y direcciones históricas → pedido y líneas → reserva
`min(disponible, cantidad)` con movimiento `RESERVA` → orden de producción para el faltante
→ estado `CONFIRMADO` o `EN_PRODUCCION` → preparación `POR_SURTIR` si todo fue reservado →
eventos, conversión del carrito y alertas. Un pago rechazado revierte todo y conserva el carrito.
El resumen incluye `iva_importe` informativo, calculado como `total * iva_pct / (100 + iva_pct)`
con `iva_pct` de configuración; no modifica los importes contables.

Errores: `400 IDEMPOTENCIA_REQUERIDA`, `409 IDEMPOTENCIA_CONFLICTO`, `409 STOCK_NO_DISPONIBLE`,
`422 CARRITO_VACIO`, `422 CARRITO_NO_PAGABLE`, `422 SIN_COBERTURA`, `422 PAGO_RECHAZADO`,
`422 DESCUENTO_NO_APLICABLE`, `422 RECETA_NO_DISPONIBLE`.

## M06 — Mis pedidos

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/mis-pedidos` | C | `estado` (`TODOS`, `EN_PROCESO`, `ENVIADOS`, `ENTREGADOS`), `pagina`, `por_pagina` | Lista paginada propia (`200`) |
| `GET` | `/mis-pedidos/{id}` | C | — | Detalle propio con artículos, eventos visibles, guía y repartidor (`200`) |
| `POST` | `/mis-pedidos/{id}/cancelar` | C | `motivo` | Pedido cancelado (`200`) |
| `GET` | `/mis-pedidos/{id}/comprobante` | C | — | Comprobante histórico (`200`) |

La cancelación del cliente es válida en `RECIBIDO`, `CONFIRMADO` o `EN_PRODUCCION`: libera
reservas con `LIBERA_RESERVA`, ajusta la orden de producción abierta, elimina la preparación
y registra un reembolso simulado. El `CHECK` de `pedido_linea` exige que
`cant_reservada + cant_pendiente = cantidad`; por eso al cancelar se deja `cantidad = 0` junto
con ambas cantidades en cero. El histórico de la venta conserva la cantidad original.
Cualquier pedido ajeno responde `404`, nunca `403`, para no revelar existencia de recursos de
otros clientes.

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

Los blueprints M07–M21 y el resto de M22 se documentarán aquí a medida que se implementen.
La tabla completa de rutas requeridas está en la sección 11 del documento integral y en
`AGENTS.md`.
