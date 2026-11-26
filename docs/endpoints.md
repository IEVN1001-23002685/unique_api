# Contrato HTTP

Prefijo global: `/api/v1`. Estado: Fases 0 a 6 implementadas y verificadas. La Fase 5
cubre ventas (M08), pedidos administrativos (M09) y cambios/devoluciones (M07), con
reembolsos simulados, venta de reemplazo a `$0.00`, dictamen de devoluciones y
cancelación administrativa hasta `LISTO_ENVIO`. La Fase 6 cubre preparación (M18),
entregas (M19), dashboard (M20), alertas (M21), catálogos administrativos y tareas
programadas.

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
| `POST` | `/auth/registro` | P | `nombre`, `apellidos`, `correo`, `telefono`, `password`, `acepta_promociones` | `201`, `{ access_token, usuario }` + cookie de refresco; crea `CLIENTE` |
| `POST` | `/auth/login` | P | `correo`, `password` | `200`, `{ access_token, usuario }` + cookie de refresco |
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
| `GET` | `/mis-pedidos/{id}` | C | — | Detalle propio con artículos (`venta_linea_id`, `variante_id` y `producto_id` para solicitudes M07), eventos visibles, guía y repartidor (`200`) |
| `POST` | `/mis-pedidos/{id}/cancelar` | C | `motivo` | Pedido cancelado (`200`) |
| `GET` | `/mis-pedidos/{id}/comprobante` | C | — | Comprobante histórico (`200`) |

La cancelación del cliente es válida en `RECIBIDO`, `CONFIRMADO` o `EN_PRODUCCION`: libera
reservas con `LIBERA_RESERVA`, ajusta la orden de producción abierta, elimina la preparación
y registra un reembolso simulado. El `CHECK` de `pedido_linea` exige que
`cant_reservada + cant_pendiente = cantidad`; por eso al cancelar se deja `cantidad = 0` junto
con ambas cantidades en cero. El histórico de la venta conserva la cantidad original.
Cualquier pedido ajeno responde `404`, nunca `403`, para no revelar existencia de recursos de
otros clientes.

## M10 — Productos, variantes, imágenes y activación

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/productos` | A | `q`, `categoria`, `color`, `talla`, `activo`, `pagina`, `por_pagina` | Lista paginada (`200`) |
| `POST` | `/productos` | A | `categoria_id`, `nombre`, `descripcion`, `composicion_textil`, `guia_medidas`, `precio_venta`, `tallas`, `colores`, `stock_minimo`, `cantidad_reposicion`, `permite_bajo_pedido` | Producto con variantes y recetas borrador (`201`) |
| `GET` | `/productos/{id}` | A | — | Detalle con variantes, imágenes y recetas (`200`) |
| `PATCH` | `/productos/{id}` | A | Campos editables; `tallas`/`colores` opcionales | Producto actualizado (`200`) |
| `DELETE` | `/productos/{id}` | A | — | `204`; borrado lógico o físico solo sin historial |
| `POST` | `/productos/{id}/imagenes` | A | `multipart/form-data`: `archivo`, `color`, `orden` | Imagen guardada (`201`) |
| `PATCH` | `/variantes/{id}` | A | `activa` | Variante (`200`) |
| `POST` | `/productos/{id}/activar` | A | — | Producto activo (`200`) |

El SKU se genera en servidor con tres segmentos (`categoria-talla-color`) y no se modifica al
renombrar el producto. `POST /productos` crea una receta `BORRADOR` por cada talla solicitada.
`activar` exige al menos una imagen y una receta `VIGENTE` **por cada talla del producto**, no
por todas las tallas de la categoría. Las imágenes admiten JPG, PNG y WebP de hasta 2 MB; se
verifica el contenido real con Pillow, el MIME declarado debe coincidir y el archivo se guarda
fuera del código con nombre aleatorio. Un error posterior al guardado elimina el archivo.

Errores: `400 ARCHIVO_GRANDE`, `401`, `403`, `404 CATEGORIA_NO_DISPONIBLE`,
`409 PRODUCTO_YA_ACTIVO`, `409 SKU_DUPLICADO`, `422 IMAGEN_REQUERIDA`,
`422 IMAGEN_NO_VALIDA`, `422 RECETA_NO_VIGENTE`, `422 PRODUCTO_CON_HISTORIAL`.

## M11 — Recetas, costeo y diseños

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/recetas` | A, O | `producto_id`, `talla_id`, `estado`, `q`, `pagina`, `por_pagina` | Lista paginada (`200`) |
| `POST` | `/recetas` | A | `producto_id`, `talla_id`, `mano_obra`, `costo_bordado`, `costos_indirectos`, `nota` | Receta borrador (`201`) |
| `GET` | `/recetas/{id}` | A, O | — | Receta (`200`) |
| `PATCH` | `/recetas/{id}` | A | Campos económicos y `nota` | Receta (`200`) |
| `POST` | `/recetas/{id}/lineas` | A | `material_id` o `diseno_id`, `cantidad_neta`, `factor_consumo`, `merma_pct`, `aplicaciones`, `ubicacion` | Línea (`201`) |
| `POST` | `/recetas/previsualizar` | A | Producto, talla y líneas propuestas | Costeo prospectivo (`200`) |
| `POST` | `/recetas/{id}/copiar` | A | `producto_id`, `talla_id`, `nota` | Nuevo borrador (`201`) |
| `POST` | `/recetas/{id}/activar` | A | — | Receta `VIGENTE`; la anterior pasa a `ARCHIVADA` (`200`) |
| `GET` | `/recetas/costeo` | A | Filtros de producto/talla/estado | Costeo paginado (`200`) |
| `GET` | `/disenos` | A | `activo`, `estado`, `pagina`, `por_pagina` | Lista paginada (`200`) |
| `POST` | `/disenos` | A | Datos del diseño | Diseño (`201`) |
| `GET` | `/disenos/{id}` | A | — | Diseño (`200`) |
| `PATCH` | `/disenos/{id}` | A | Campos editables | Diseño (`200`) |
| `DELETE` | `/disenos/{id}` | A | — | Borrado lógico (`204`) |

`POST /productos` ya crea el borrador de cada talla: si se repite `POST /recetas` para esa
misma talla, se reutiliza el borrador existente y se devuelve `201`. Una receta `VIGENTE` o
`ARCHIVADA` no se edita (`422 RECETA_NO_EDITABLE`); debe copiarse. `copiar` incrementa la
versión y `activar` archiva la vigente anterior en la misma transacción. La cantidad bruta
sigue `cantidad_neta * factor_consumo / (1 - merma_pct/100)`; `merma_pct` debe estar entre 0 y
100, y cantidad y factor deben ser positivos.

`ADMIN` recibe `mano_obra`, `costo_bordado`, `costos_indirectos`, `costo_materia_prima`,
`costo_estandar`, `precio_sugerido`, `margen_real` y `costo_linea`. `OPERATIVO` recibe las
mismas operaciones de lectura sin ninguno de esos campos. Las recetas semilla permanecen en
`BORRADOR`; la de Playera CH tiene una nota de patrón pendiente y no debe activarse sin revisión.

Errores: `409 RECETA_YA_VIGENTE`, `422 RECETA_SIN_TELA`, `422 RECETA_NO_ACTIVABLE`,
`422 RECETA_DUPLICADA`, `422 LINEA_RECETA_INVALIDA`, `422 DISENO_NO_DISPONIBLE`.

## M12 — Inventario de producto terminado

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/inventario/producto` | O | `categoria`, `sku`, `color`, `talla`, `semaforo`, `pagina`, `por_pagina` | Lista paginada con semáforo (`200`) |
| `GET` | `/inventario/producto/movimientos` | O | `sku`, `tipo`, `documento_tipo`, `desde`, `hasta`, `pagina`, `por_pagina` | Kardex paginado (`200`) |
| `POST` | `/inventario/producto/ajuste` | O | `variante_id`, `cantidad_contada`, `diferencia`, `motivo` | Ajuste y orden de reposición (`200`) |
| `PATCH` | `/inventario/producto/{variante_id}/reglas` | A | `stock_minimo` y/o `cantidad_reposicion` | Reglas (`200`) |

El ajuste bloquea la variante y el stock, exige `diferencia = contada - existencia` cuando se
envía, prohíbe dejar `cantidad_contada < reservado` y escribe un movimiento `AJUSTE`. Los
movimientos son de solo inserción: no existen rutas `PATCH`/`DELETE` para ellos y una corrección
se registra con un movimiento inverso y motivo. El ajuste a la baja por debajo del mínimo abre
la alerta `PT_STOCK_MINIMO` y crea o incrementa una orden de reposición. `PATCH` de reglas es
parcial; con cuerpo vacío responde `400`.

## M13 — Proveedores

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| `GET` | `/proveedores` | A | Lista paginada con `q`, `estatus`, `material_id`, `incluir_inactivos` |
| `POST` | `/proveedores` | A | Proveedor (`201`) |
| `GET` | `/proveedores/{id}` | A | Proveedor (`200`) |
| `PATCH` | `/proveedores/{id}` | A | Proveedor actualizado (`200`) |
| `DELETE` | `/proveedores/{id}` | A | `204`, desactivación lógica |
| `GET` | `/proveedores/{id}/materiales` | A | Lista paginada del catálogo surtido |
| `POST` | `/proveedores/{id}/materiales` | A | Relación material (`201`) |
| `PATCH` | `/proveedores/{id}/materiales/{material_id}` | A | Relación actualizada (`200`) |
| `DELETE` | `/proveedores/{id}/materiales/{material_id}` | A | `204` |
| `GET` | `/proveedores/evaluacion` | A | Evaluación derivada; **no modifica** el padrón |

El porcentaje de entregas a tiempo divide las entregas puntuales entre las órdenes recibidas.
Sin historial se reporta `100.00` para no penalizar al proveedor sin evidencia. Si se evalúa por
debajo del umbral, el estatus derivado es `EN_REVISION`. La persistencia del estatus y la alerta
`PROVEEDOR_EN_REVISION` quedan para la tarea programada `evaluar_proveedores` (Fase 6).

## M14 — Requisiciones, cotizaciones, órdenes y recepciones

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| `GET` | `/requisiciones` | A, O | Lista paginada |
| `POST` | `/requisiciones` | A, O | Requisición con folio `REQ-AAAA-NNNNNN` (`201`) |
| `GET` | `/requisiciones/{id}` | A, O | Requisición (`200`) |
| `PATCH` | `/requisiciones/{id}` | A, O | Requisición (`200`) |
| `DELETE` | `/requisiciones/{id}` | A, O | `204`, cancelación |
| `POST` | `/requisiciones/{id}/cotizaciones` | A | Cotización (`201`) |
| `GET` | `/cotizaciones` | A | Lista paginada; filtro `requisicion_id` |
| `POST` | `/cotizaciones/{id}/elegir` | A | Orden de compra borrador (`200`) |
| `GET` | `/ordenes-compra` | A | Lista paginada |
| `POST` | `/ordenes-compra` | A | Orden (`201`) |
| `GET` | `/ordenes-compra/{id}` | A | Orden (`200`) |
| `PATCH` | `/ordenes-compra/{id}` | A | Orden (`200`) |
| `DELETE` | `/ordenes-compra/{id}` | A | `204`, cancelación |
| `POST` | `/ordenes-compra/{id}/emitir` | A | Orden emitida (`200`) |
| `POST` | `/ordenes-compra/{id}/cancelar` | A | Orden cancelada (`200`) |
| `GET` | `/ordenes-compra/{id}/pdf` | A | `application/pdf` |
| `POST` | `/recepciones` | O | Recepción con lotes PEPS (`201`) |

`POST /recepciones` exige `Idempotency-Key` y usa el alcance `recepciones:registrar`. La misma
clave y cuerpo devuelven la respuesta original; la misma clave con otro cuerpo responde
`409 IDEMPOTENCIA_CONFLICTO`. Se valida `aceptada + rechazada = cantidad_medida` y
`aceptada <= pendiente`; el lote se crea solo con lo aceptado, la entrada se valora al costo real
y lo rechazado se registra como merma. La orden pasa a `PARCIAL` o `RECIBIDA` según el acumulado
y se cierra la alerta `OC_RETRASADA`. Una cotización exige que el proveedor surta cada material
en su catálogo activo; elegir una cotización vencida responde `409 COTIZACION_VENCIDA`. Desde
la Fase 4, la recepción también reevalúa las órdenes de producción abiertas y cerró la
dependencia pendiente con M16 que se registraba en Fase 3.

## M15 — Materiales e inventario de materia prima

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/materiales` | A, O | `categoria`, `codigo`, `q`, `por_color`, `incluir_inactivos`, paginación | Lista paginada |
| `POST` | `/materiales` | A | Material en unidad base | Material (`201`) |
| `GET` | `/materiales/{id}` | A, O | — | Material (`200`) |
| `PATCH` | `/materiales/{id}` | A | Campos editables | Material (`200`) |
| `DELETE` | `/materiales/{id}` | A | — | `204`, desactivación lógica |
| `GET` | `/inventario/material` | O | `categoria`, `material_id`, `color`, `semaforo`, paginación | Posiciones paginadas (`200`) |
| `GET` | `/inventario/material/lotes` | O | `inventario_material_id`, `estado`, paginación | Lotes paginados (`200`) |
| `GET` | `/inventario/material/movimientos` | O | `inventario_material_id`, `lote_id`, `tipo`, paginación | Kardex paginado (`200`) |
| `POST` | `/inventario/material/ajuste` | O | Ajuste por conteo, `mandar_a_merma` | Ajuste (`200`) |
| `PATCH` | `/inventario/material/{id}/politica` | A | Política de reposición | Inventario (`200`) |

`OPERATIVO` **nunca** recibe `costo_estandar_base`, `precio_compra`, `costo_unitario_base`,
`costo_total` ni márgenes en materiales, lotes, movimientos ni recetas. Los lotes se consumen
por PEPS (`fecha_entrada`, `id`) con `FOR UPDATE`. Si no hay suficiente existencia, la
transacción se revierte y responde `409 MATERIAL_INSUFICIENTE` con los faltantes. Un ajuste
negativo genera movimientos `AJUSTE`, no `CONSUMO`, para no inflar el consumo de los últimos
30 días.

Errores comunes de Fase 3: `401`, `403`, `404`, `409 ESTADO_INVALIDO`, `409 MATERIAL_INSUFICIENTE`,
`409 IDEMPOTENCIA_CONFLICTO`, `422 MATERIAL_NO_DISPONIBLE`, `422 PROVEEDOR_NO_SURTE_MATERIAL`.

## M16 — Producción

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/produccion/ordenes` | A, O | `estado`, `semaforo`, `origen`, `q`, `desde`, `hasta`, paginación | Lista paginada de órdenes (`200`) |
| `POST` | `/produccion/ordenes` | A, O | `lineas: [{variante_id, cantidad}]`, `fecha_requerida`, `notas` | Orden con folio `OP-AAAA-NNNN` y explosión de materiales (`201`) |
| `GET` | `/produccion/ordenes/{id}` | A, O | — | Detalle con líneas, materiales y semáforo (`200`) |
| `GET` | `/produccion/pendientes-produccion` | A, O | `semaforo`, paginación | Órdenes abiertas con unidades pendientes (`200`) |
| `GET` | `/produccion/plan-sugerido` | A, O | `q` (SKU), paginación | Cantidad sugerida por variante (`200`) |
| `POST` | `/produccion/ordenes/{id}/reservar` | A, O | — | Reserva disponible por material; orden `PLANEADA` o `LISTA` (`200`) |
| `POST` | `/produccion/ordenes/{id}/solicitar-compra` | A, O | — | Requisición con folio `REQ-AAAA-NNNNNN` o la existente (`200`) |
| `POST` | `/produccion/ordenes/{id}/iniciar` | A, O | `notas` opcional; cabecera `Idempotency-Key` obligatoria | Orden `EN_PROCESO` con consumo PEPS (`200`) |
| `POST` | `/produccion/ordenes/{id}/revision` | A, O | `notas` opcional | Orden `EN_REVISION` (`200`) |
| `POST` | `/produccion/ordenes/{id}/dictamen` | A, O | `lineas: [{orden_linea_id, cantidad_revisada, cantidad_aprobada, cantidad_reproceso, cantidad_merma, medidas_ok, costuras_ok, bordado_ok, etiquetas_ok, observaciones, causa_merma_id, etapa_merma}]` | Orden actualizada y asignaciones FIFO (`200`) |
| `POST` | `/produccion/ordenes/{id}/cancelar` | A, O | `motivo` | Orden `CANCELADA` (`200`) |

Ciclo de estados: `PLANEADA → LISTA → EN_PROCESO → EN_REVISION → CERRADA`. `CANCELADA`
solo desde `PLANEADA` o `LISTA`. `reservar` calcula lo libre restando reservas de otras
órdenes abiertas, actualiza el semáforo y mantiene `PLANEADA` si falta algo. `solicitar-compra`
es idempotente por orden: devuelve `duplicada=true` si ya hay requisición vigente y nunca
duplica faltantes. El semáforo es `VERDE` sin faltantes, `ROJO` si la fecha requerida ya pasó,
hay OC vencida o la compra no cubre la falta, y `AMBAR` en los demás casos con faltantes.

`POST /iniciar` usa el alcance `produccion:iniciar`. Bloquea orden y materiales/lotes en orden
determinista, exige estado `LISTA`, consume por PEPS (`fecha_entrada`, `id`) y escribe movimientos
`CONSUMO` con costo real por lote. Si un material no alcanza, revierte todo y responde
`409 MATERIAL_INSUFICIENTE` con el detalle de requerido, disponible y faltante. La misma clave
con el mismo cuerpo devuelve la respuesta original; con otro cuerpo responde
`409 IDEMPOTENCIA_CONFLICTO`. Sin cabecera responde `400 IDEMPOTENCIA_REQUERIDA`.

El dictamen exige `aprobadas + reproceso + merma = cantidad_revisada` (`422
CANTIDADES_NO_CONCUADRAN`), no exceder lo planeado (`409 EXCEDE_PLANIFICADO`) y el checklist
completo para aprobar (`422 CHECKLIST_INCOMPLETO`). Las aprobadas incrementan existencia con
movimiento `PRODUCCION`; las mermas se delegan a M17 con `descontar=false` porque la unidad ya
salió del lote de producción. Las unidades nuevas se asignan a pedidos `CONFIRMADO` o
`EN_PRODUCCION` por antigüedad (FIFO) con movimiento `RESERVA`, y el pedido pasa a `CONFIRMADO`
cuando se agota su pendiente. La orden queda `CERRADA`, `EN_PROCESO` si hay reproceso o
`EN_REVISION` si aún faltan unidades por dictaminar.

Errores: `400 IDEMPOTENCIA_REQUERIDA`, `401`, `403`, `404 ORDEN_NO_ENCONTRADA`/
`LINEA_NO_ENCONTRADA`, `409 ESTADO_INVALIDO`/`MATERIAL_INSUFICIENTE`/`EXCEDE_PLANIFICADO`/
`IDEMPOTENCIA_CONFLICTO`, `422 RECETA_NO_VIGENTE`/`ORDEN_SIN_MATERIALES`/`SIN_FALTANTES`/
`SIN_RESERVA`/`LINEAS_REQUERIDAS`/`LINEA_DUPLICADA`/`CANTIDADES_NO_CONCUADRAN`/
`CHECKLIST_INCOMPLETO`/`INVENTARIO_MATERIAL_NO_DISPONIBLE`.

`OPERATIVO` recibe las mismas operaciones que `ADMIN`; los datos económicos de materiales siguen
ocultos para `OPERATIVO` según M15.

## M17 — Mermas

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/mermas` | A, O | `origen`, `etapa`, `causa_id`, `variante_id`, `inventario_material_id`, `orden_produccion_id`, `desde`, `hasta`, paginación | Lista paginada (`200`) |
| `POST` | `/mermas` | A, O | `origen`, `etapa`, `causa_id`, `cantidad`, `inventario_material_id`/`lote_id` o `variante_id`, `orden_produccion_id`, `descripcion`, `evidencia_url` | Merma (`201`) |
| `GET` | `/mermas/{id}` | A, O | — | Merma (`200`) |
| `POST` | `/mermas/{id}/reversar` | A | `motivo`, `evidencia_url` opcional | Original y reverso (`200`) |
| `GET` | `/mermas/indicadores` | A | `desde`, `hasta`, `etapa`, `causa` | Resumen desde `v_merma_resumen` y totales (`200`) |

M17 es el único dueño de la tabla `merma`: M14 (rechazo de recepción), M15 (ajuste negativo
con `mandar_a_merma`) y M16 (dictamen) delegan en `merma_service`. `cantidad` es decimal para
`MATERIAL` y entera para `PRODUCTO`. La causa debe estar activa y aplicar al origen indicado;
si no se envía `causa_id`, se usa la primera causa válida. La merma de material descuenta el
lote con movimiento `MERMA` y abre `MP_INSUFICIENTE`/`MERMA_ALTA` según corresponda.

El reverso crea una **nueva fila** con `reversa_de_id`, nunca edita la original: devuelve el
material con movimiento `REVERSA` o la prenda con movimiento `AJUSTE`, ambos con motivo y
bitácora. No se puede reversar un reverso (`422 REVERSO_INVALIDO`) ni reversar dos veces
(`409 MERMA_YA_REVERSADA`). `v_merma_resumen` netea los reversos con
`CASE WHEN reversa_de_id IS NULL THEN 1 ELSE -1 END`, de modo que los indicadores y el total
neto no cuentan dos veces el mismo evento. `OPERATIVO` no recibe `costo_perdido`.

Errores: `401`, `403`, `404 MERMA_NO_ENCONTRADA`, `409 MERMA_YA_REVERSADA`/
`LOTE_NO_DISPONIBLE`/`MATERIAL_INSUFICIENTE`, `422 ORIGEN_INVALIDO`/`ETAPA_INVALIDA`/
`CANTIDAD_INVALIDA`/`CAUSA_MERMA_NO_DISPONIBLE`/`VARIANTE_REQUERIDA`/`REVERSO_INVALIDO`.

## M07 — Cambios y devoluciones

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `POST` | `/devoluciones` | C | `pedido_id`, `tipo`, `motivo`, `descripcion`, `lineas[]`; opcional multipart `evidencias` (JPG/PNG/WebP, ≤2 MB) | Devolución `SOLICITADA` (`201`) |
| `GET` | `/devoluciones` | C, O, A | `estado`, `tipo`, `motivo`, `desde`, `hasta`, `q`, paginación | Lista paginada (`200`) |
| `PATCH` | `/devoluciones/{id}/aprobar` | A | — | Devolución `APROBADA` (`200`) |
| `PATCH` | `/devoluciones/{id}/rechazar` | A | `motivo` | Devolución `RECHAZADA` (`200`) |
| `POST` | `/devoluciones/{id}/recibir` | O, A | — | Devolución `RECIBIDA` (`200`) |
| `POST` | `/devoluciones/{id}/dictamen` | O, A | `lineas[]` con `devolucion_linea_id`, `dictamen` (`REINGRESO`/`MERMA`), `causa_id` opcional | Devolución dictaminada (`200`) |
| `POST` | `/devoluciones/{id}/resolver` | A | `resolucion` (`REEMBOLSO`/`CAMBIO`) | Devolución `RESUELTA` (`200`) |

`tipo` es `DEVOLUCION` o `CAMBIO`; `motivo` es `DEFECTO`, `AJUSTE`, `DANO_ENVIO`,
`PRODUCTO_EQUIVOCADO` o `ARREPENTIMIENTO`. Solo se aceptan pedidos `ENTREGADO` dentro de
`dias_devolucion` (configurable, propuesta 15 días) y hasta la cantidad vendida no devuelta.
Las solicitudes de cambio requieren `variante_cambio_id` por línea.

La recepción cambia el estado a `RECIBIDA` y abre una alerta de inspección. El dictamen
de `REINGRESO` incrementa `existencia` con movimiento `REINGRESO`; el de `MERMA` delega en
`merma_service` con `descontar=False`, sin modificar el histórico de movimientos. La
resolución por `REEMBOLSO` calcula el importe prorrateado de las líneas, descuenta la parte
proporcional del cupón y excluye el envío salvo `DEFECTO`, `DANO_ENVIO` o
`PRODUCTO_EQUIVOCADO`. La resolución por `CAMBIO` crea una venta `CAMBIO` con total
`$0.00`, su pago y su pedido, sin tarjeta ni CVV.

`OPERATIVO` no recibe `reembolso_monto` ni datos financieros. Errores: `401`, `403`,
`404 PEDIDO_NO_ENCONTRADO`/`DEVOLUCION_NO_ENCONTRADA`, `409 ESTADO_NO_VALIDO`/
`DICTAMEN_DUPLICADO`, `422 PEDIDO_NO_ENTREGADO`/`VENTANA_DEVOLUCION_CERRADA`/
`CANTIDAD_DEVOLUCION_INVALIDA`/`DICTAMEN_PENDIENTE`/`CAMBIO_NO_SOLICITADO`.

## M08 — Ventas, pagos y descuentos

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/ventas` | A | `desde`, `hasta`, `canal`, `estado`, `estado_pago`, `q`, paginación | Lista paginada (`200`) |
| `GET` | `/ventas/{id}` | A | — | Venta con líneas, direcciones, pagos y pedido (`200`) |
| `POST` | `/ventas/manual` | A | `cliente_id` o `cliente`, `lineas[]` con `sku`, `direccion`, `metodo_pago`, `estado_pago`, opcionalmente pago, RFC y descuento | Venta creada (`201`) |
| `POST` | `/ventas/{id}/pago` | A | `accion` (`APROBAR`/`RECHAZAR`), `metodo_pago`, datos de tarjeta o `medio_pago_id`, `motivo` | Venta actualizada (`200`) |
| `POST` | `/ventas/{id}/cancelar` | A | `motivo` | Venta cancelada, reservas liberadas y reembolso simulado (`200`) |
| `POST` | `/ventas/{id}/reembolso` | A | `monto` opcional, `motivo` | Venta con `estado_pago` actualizado (`200`) |
| `GET` | `/descuentos` | A | `activo`, `aplicacion`, `q`, paginación | Lista paginada (`200`) |
| `POST` | `/descuentos` | A | `codigo`, `nombre`, `tipo`, `valor`, `aplicacion`, vigencia, límites de uso | Descuento (`201`) |
| `PATCH` | `/descuentos/{id}` | A | Campos parciales del descuento | Descuento (`200`) |
| `DELETE` | `/descuentos/{id}` | A | — | `204`; borrado lógico si ya se usó, físico si no |

`metodo_pago` es `TARJETA`, `CUENTA`, `TRANSFERENCIA` o `EFECTIVO`. Con `estado_pago =
PENDIENTE` el pedido queda en `RECIBIDO` y se abre `PAGO_PENDIENTE`; al aprobarlo se activa
a `CONFIRMADO` o `EN_PRODUCCION` según la reserva. El reembolso se limita al saldo pendiente
de la venta y actualiza `estado_pago` a `REEMBOLSADA` o `REEMBOLSADA_PARCIAL`. No se guarda
el número completo de tarjeta ni el CVV.

Errores: `401`, `403`, `404 VENTA_NO_ENCONTRADA`/`SKU_NO_DISPONIBLE`/
`DESCUENTO_NO_ENCONTRADO`, `409 VENTA_CANCELADA`/`PAGO_YA_APROBADO`/`CODIGO_DUPLICADO`,
`422 PAGO_RECHAZADO`/`MONTO_REEMBOLSO_INVALIDO`/`VALOR_DESCUENTO_INVALIDO`.

## M09 — Pedidos administrativos

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/pedidos` | A, O | `estado`, `prioridad`, `desde`, `hasta`, `q`, paginación | Lista paginada (`200`) |
| `GET` | `/pedidos/pendientes-produccion` | A, O | `semaforo`, `sku`, paginación | Demanda pendiente por SKU (`200`) |
| `GET` | `/pedidos/{id}` | A, O | — | Detalle con cliente, canal, semáforo, órdenes, preparación y entrega (`200`) |
| `PATCH` | `/pedidos/{id}` | A | `prioridad`, `nota` | Pedido actualizado con evento interno (`200`) |
| `POST` | `/pedidos/{id}/cancelar` | A | `motivo` | Pedido cancelado (`200`) |

La lista de pendientes reutiliza `produccion_service.pendientes_lineas`; M09 no duplica la
lógica de M16 y mantiene `/produccion/pendientes-produccion` como ruta equivalente. La
cancelación administrativa admite estados hasta `LISTO_ENVIO`, libera reservas, ajusta
órdenes vinculadas, cancela la venta y genera el reembolso simulado correspondiente. El
detalle para `ADMIN` incluye costos; el de `OPERATIVO` omite costos, márgenes y precios de compra.

Errores: `401`, `403`, `404 PEDIDO_NO_ENCONTRADO`, `409 ESTADO_NO_CANCELABLE`,
`422 VALIDACION`.

## M18 — Preparación, verificación y empaque

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/preparacion/cola` | O | `estado` (`POR_SURTIR`, `EN_PICKING`, `EN_VERIFICACION`, `EN_EMPAQUE`, `LISTA`), paginación | Preparaciones de pedidos `CONFIRMADO` ordenadas por prioridad y fecha promesa (`200`) |
| `POST` | `/preparacion/{pedido_id}/tomar` | O | — | Preparación en `EN_PICKING`; crea la preparación si no existe (`200`) |
| `PATCH` | `/preparacion/{id}/lineas` | O | `lineas[]` con `preparacion_linea_id`, `cantidad_surtida`, `sku`, `sku_verificado`, `diseno_verificado`, `etiquetas_verificadas` | Preparación con validación de surtido (`200`) |
| `POST` | `/preparacion/{id}/incidencia` | O | `preparacion_linea_id`, `tipo` (`SKU`, `CANTIDAD`, `CALIDAD`), `descripcion`, `cantidad` opcional | Incidencia registrada (`201`) |
| `POST` | `/preparacion/{id}/empacar` | O | — | Preparación `LISTA`, pedido `LISTO_ENVIO` y empaque consumido por PEPS (`200`) |
| `GET` | `/preparacion/{id}/etiqueta` | O | — | Etiqueta en `application/pdf` con folio, destinatario, dirección, CP, teléfono y QR (`200`) |

El identificador de `/preparacion/{pedido_id}/tomar` es el **pedido**; los demás usan
el **id de preparación**. `marcar_empaque` consume las reglas sembradas `EMP-BOL` y
`EMP-PAP` por prenda y `EMP-TAR` y `EMP-ETE` por pedido, con consumo PEPS. Todas las
líneas requieren las tres verificaciones antes de empacar. Errores: `401`, `403`,
`404 PREPARACION_NO_ENCONTRADA`/`PEDIDO_NO_ENCONTRADO`, `409 PEDIDO_NO_PREPARABLE`/
`PREPARACION_NO_DISPONIBLE`/`PREPARACION_NO_EDITABLE`/`LINEA_NO_PERTENECE`/
`VERIFICACION_INCOMPLETA`/`MATERIAL_INSUFICIENTE`, `422 VALIDACION`.

## M19 — Entregas y repartidores

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/entregas/por-asignar` | O | `codigo_postal` opcional, paginación | Pedidos `LISTO_ENVIO` sin entrega vigente (`200`) |
| `POST` | `/entregas` | O | `pedido_id`, `repartidor_id`, `fecha_programada`, `notas` opcional | Entrega `PROGRAMADA` con folio `EN-AAAA-NNNNNN` (`201`) |
| `POST` | `/entregas/{id}/salida` | O | — | Entrega `EN_RUTA`; `SALIDA_ENVIO` descuenta existencia y reserva (`200`) |
| `POST` | `/entregas/{id}/resultado` | O | `entregado`, `receptor`, `motivo_fallo`, `notas` | Entrega `ENTREGADA` o `FALLIDA` con reingreso y Control de intentos (`200`) |
| `GET` | `/entregas/hoja-reparto?repartidor&fecha` | O | `repartidor`, `fecha`, paginación | Hoja de reparto en `application/pdf` (`200`) |
| `GET` | `/entregas/productos-repartidos` | O | `repartidor`, `desde`, `hasta`, paginación | Unidades entregadas por SKU (`200`) |
| `GET` | `/repartidores` | A | `activo`, paginación | Lista paginada (`200`) |
| `POST` | `/repartidores` | A | `nombre`, `telefono` (10 dígitos), `vehiculo` opcional | Repartidor creado (`201`) |
| `PATCH` | `/repartidores/{id}` | A | Campos parciales | Repartidor actualizado (`200`) |
| `DELETE` | `/repartidores/{id}` | A | — | `204`, borrado lógico |

Los fallos reingresan `+existencia` y `+reservado` (`REINGRESO`) porque la salida ya los
había descontado. Con `max_intentos_entrega = 2` (propuesta configurable), el segundo
fallo abre `ENTREGA_FALLIDA` con severidad `CRITICA`. Errores: `401`, `403`,
`404 PEDIDO_NO_ENCONTRADO`/`ENTREGA_NO_ENCONTRADA`/`REPARTIDOR_NO_ENCONTRADO`,
`409 ESTADO_NO_VALIDO`/`ENTREGA_DUPLICADA`/`REPARTIDOR_INACTIVO`, `422 VALIDACION`.

## M20 — Dashboard

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| `GET` | `/dashboard/resumen` | A | KPIs generales desde vistas agregadas (`200`) |
| `GET` | `/dashboard/ventas` | A | Ingresos, unidades y ticket por periodo (`200`) |
| `GET` | `/dashboard/produccion` | A, O | Órdenes, semáforos y aprobación; sin datos financieros para O (`200`) |
| `GET` | `/dashboard/abastecimiento` | A, O | Inventario de material, puntualidad y compras; sin costos para O (`200`) |
| `GET` | `/dashboard/logistica` | A, O | Preparación, entregas y fallos (`200`) |
| `GET` | `/dashboard/exportar` | A | CSV `text/csv; charset=utf-8` con `Content-Disposition: attachment` (`200`) |

Los filtros son `desde` y `hasta` según el recurso. Las consultas usan
`v_ventas_sku`, `v_merma_resumen`, `v_inventario_material`, `v_capacidad_variante` y
`v_pedidos_estancados`, con parámetros enlazados. El serializador de `OPERATIVO` omite
costo estándar, precio de compra, costo total, márgenes y utilidades. Errores: `401`,
`403`, `400 VALIDACION`.

## M21 — Alertas y reglas

| Método | Ruta | Rol | Parámetros / cuerpo | Respuesta |
|---|---|---|---|---|
| `GET` | `/alertas` | A, O | `estado` (`ABIERTA`, `ATENDIDA`, `RESUELTA_AUTO`), `tipo`, `severidad`, paginación | Alertas vigentes (`200`) |
| `GET` | `/alertas/resueltas` | A, O | Filtros anteriores, paginación | Alertas resueltas automáticamente (`200`) |
| `GET` | `/alertas/reglas` | A | — | Reglas configurables (`200`) |
| `PATCH` | `/alertas/reglas` | A | `reglas[]` con `clave` y `valor` numérico | Reglas actualizadas (`200`) |
| `POST` | `/alertas/{id}/accion` | A, O | `accion` (`ATENDER`, `GENERAR_PRODUCCION`, `GENERAR_REQUISICION`, `EVALUAR_PROVEEDOR`), `nota` opcional | Alerta y resultado de la acción (`200`) |

Una alerta abierta con la misma `clave_unica` no se duplica; al cerrarse libera la
clave. `elevar` aumenta la severidad y `atender` registra la atención. Las once reglas
viven en `configuracion`, sin tabla adicional. Catálogo implementado: `PT_AGOTADO_DEMANDA`,
`PT_STOCK_MINIMO`, `MP_INSUFICIENTE`, `MP_REORDEN`, `ORDEN_ROJA`, `OC_RETRASADA`,
`PEDIDO_ESTANCADO`, `MERMA_ALTA`, `DIFERENCIA_CONTEO`, `ENTREGA_FALLIDA`,
`DEVOLUCION_PENDIENTE`, `PAGO_PENDIENTE`, `PROVEEDOR_EN_REVISION` y `DISENO_PENDIENTE`.
Errores: `401`, `403`, `404 ALERTA_NO_ENCONTRADA`/`REGLA_NO_ENCONTRADA`,
`409 ALERTA_YA_ATENDIDA`/`ACCION_NO_DISPONIBLE`, `422 VALIDACION`.

## M22 — Administración

| Método | Ruta | Rol | Respuesta |
|---|---|---|---|
| `GET` | `/usuarios` | A | Lista paginada |
| `POST` | `/usuarios` | A | `201`, crea usuario con rol indicado |
| `GET` | `/usuarios/{id}` | A | Usuario |
| `PATCH` | `/usuarios/{id}` | A | Actualiza campos permitidos |
| `DELETE` | `/usuarios/{id}` | A | `204`, desactivación lógica |
| `GET` | `/clientes` | A | Lista paginada de `CLIENTE` |
| `GET` | `/clientes/{id}` | A | Cliente con `resumen` y pedidos |
| `GET`, `POST` | `/catalogos/{recurso}` | A | Lista paginada / `201` |
| `GET`, `PATCH`, `DELETE` | `/catalogos/{recurso}/{id}` | A | Elemento / actualizado / `204` |
| `GET` | `/bitacora` | A | Lista paginada de acciones sensibles |
| `GET` | `/configuracion` | A | Parámetros del sistema |
| `PATCH` | `/configuracion` | A | Actualiza uno o varios parámetros |

Los recursos de catálogo son exactamente seis: `color`, `talla`, `categoria-producto`,
`categoria-material`, `causa-merma` y `tarifa-envio`. Los códigos usados en SKU
(`color.codigo`, `talla.codigo`, `categoria-producto.prefijo_sku`) son inmutables
después de crearlos (`409 CODIGO_SKU_INMUTABLE`). No se elimina un catálogo con
registros relacionados (`409 CATALOGO_EN_USO`). Las tarifas nuevas no se solapan
(`409 RANGO_TARIFA_SOLAPADO`). `OPERATIVO` **no** puede administrar usuarios ni
catálogos; `ADMIN` sí puede ejecutar acciones de `OPERATIVO`. No se puede desactivar
ni cambiar el rol al último `ADMIN` activo (`422 ULTIMO_ADMIN`).

## Tareas programadas

El scheduler es un proceso único dentro del contenedor `api`, iniciado por Supervisor
como `python -m app.jobs`. Usa `GET_LOCK('unique_scheduler', 5)` en MySQL para evitar
duplicados si se escalan workers.

| Tarea | Frecuencia | Servicio invocado |
|---|---|---|
| `evaluar_estancamientos` | Cada 15 min | Pedidos, órdenes y compras retrasadas → alertas |
| `recalcular_semaforos` | Cada 15 min | `produccion_service.recalcular_semaforos` |
| `cerrar_alertas_resueltas` | Cada 15 min | `alertas_service.cerrar` por clave |
| `abandonar_carritos` | Diaria | Carritos sin cambios en `dias_carrito_abandonado` |
| `evaluar_proveedores` | Diaria | `proveedor_service.evaluacion(persistir=True)` |
| `limpiar_tokens` | Diaria | Tokens de refresco vencidos o revocados |

## Contrato común

- Listas paginadas: `{ "items": [], "total": 0, "pagina": 1, "por_pagina": 20 }`.
- Error: `{ "codigo": "...", "mensaje": "...", "detalle": [] }`.
- Códigos: `200`, `201`, `204`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, `500`
  y `503` para readiness.
- Dinero como cadena decimal con dos decimales; materiales hasta cuatro decimales.
- Fechas ISO 8601 con zona horaria `TZ`.

## OpenAPI / Swagger

La especificación OpenAPI 3.0 se genera desde las rutas Flask registradas:

```bash
docker compose exec api sh -c 'cd /app && PYTHONPATH=/app python scripts/generate_openapi.py'
```

- `GET /api/v1/openapi.json` — especificación OpenAPI.
- `GET /api/v1/docs` — Swagger UI.

El detalle funcional, reglas de negocio y ejemplos siguen en este documento.

## Pendientes de negocio (no cerrados en Fase 7)

Registrados también en `docs/decisiones-tecnicas.md`:

- Cerrar órdenes de compra con faltante previa confirmación de `ADMIN`.
- Exigir dos cotizaciones cuando exista proveedor alterno.
- Restringir `UPDATE`/`DELETE` de tablas de movimientos con trigger o permisos de base de datos.
- Confirmar reglas propuestas: `dias_devolucion`, `max_intentos_entrega`,
  `dias_produccion_estandar`, `max_piezas_por_linea`, `saldo_inicial_cuenta_simulada`,
  tarifa «Local León» y stock mínimo/reposición de variantes.
- Definir `activa` para `color`, `talla` y `categoria-material` si el negocio requiere
  desactivación lógica de esos catálogos.
