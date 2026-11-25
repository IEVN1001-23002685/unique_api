# Modelo de datos

Fuente: sección 6 del documento integral. El modelo declara **64 tablas en 11 grupos**.
En la Fase 1 se crearon las 64 tablas funcionales más `idempotencia_operacion`, con un total
de 65 tablas base. La verificación en MySQL confirma el número, el motor InnoDB y las vistas.

| Grupo | Tablas | Cantidad |
|---|---|---:|
| 1. Seguridad y configuración | `rol`, `usuario`, `token_refresco`, `recuperacion_contrasena`, `bitacora`, `configuracion`, `secuencia_folio` | 7 |
| 2. Catálogos | `color`, `talla`, `categoria_producto`, `categoria_material`, `causa_merma`, `tarifa_envio` | 6 |
| 3. Cliente | `direccion`, `medio_pago` | 2 |
| 4. Producto | `diseno_bordado`, `diseno_bordado_hilo`, `producto`, `producto_imagen`, `variante_producto`, `stock_variante`, `movimiento_producto` | 7 |
| 5. Materia prima | `material`, `inventario_material`, `lote_material`, `movimiento_material` | 4 |
| 6. Proveedores y compras | `proveedor`, `proveedor_material`, `requisicion`, `requisicion_linea`, `cotizacion`, `cotizacion_linea`, `orden_compra`, `orden_compra_linea`, `recepcion`, `recepcion_linea` | 10 |
| 7. Recetas y producción | `receta`, `receta_linea`, `receta_bordado`, `orden_produccion`, `orden_produccion_linea`, `orden_material`, `produccion_pedido`, `revision_calidad` | 8 |
| 8. Merma | `merma` | 1 |
| 9. Ventas y pedidos | `carrito`, `carrito_linea`, `descuento`, `venta`, `venta_linea`, `venta_direccion`, `pago`, `pedido`, `pedido_linea`, `pedido_evento` | 10 |
| 10. Logística y devoluciones | `preparacion`, `preparacion_linea`, `empaque_regla`, `repartidor`, `entrega`, `devolucion`, `devolucion_linea`, `devolucion_evidencia` | 8 |
| 11. Control | `alerta` | 1 |

## Reglas de diseño

- InnoDB y `utf8mb4`; nombres `snake_case` en español, sin acentos.
- PK `INT UNSIGNED AUTO_INCREMENT`, salvo excepciones del documento (por ejemplo
  `configuracion.clave` y `secuencia_folio` compuesta).
- Prendas y piezas en `INT`; materiales en `DECIMAL`, nunca `FLOAT`.
- Dinero `DECIMAL(12,2)`; costo unitario base `DECIMAL(12,6)`.
- `existencia >= 0`, `reservado >= 0`, `reservado <= existencia`.
- Movimientos de inventario: solo inserción; las correcciones son movimientos inversos.
- Borrado lógico donde el documento exige historial.

## Tabla de infraestructura adicional

`AGENTS.md` exige almacenamiento persistente de `Idempotency-Key`. El documento no la incluye
entre las 64 tablas, por lo que se añadió `idempotencia_operacion` como tabla de infraestructura,
separada del modelo de negocio. Véase `decisiones-tecnicas.md`.

## Vistas

Creadas en la migración `7c1f9d2a4b60_vistas_de_lectura.py`:

- `v_disponibilidad_variante`: existencia, reservado, disponible y semáforo por variante.
- `v_inventario_material`: físico, reservado, en compra, disponible, posición, consumo diario
  de 30 días o manual y punto de reorden por material y color.
- `v_capacidad_variante`: número máximo de prendas alcanzables según la receta vigente.
- `v_ventas_sku`: unidades e ingresos por fecha, SKU, categoría, talla y color.
- `v_merma_resumen`: merma por fecha, etapa, causa, producto y material con costo perdido. La
  migración `b2c3d4e5f6a7` la ajustó para netear reversos con
  `CASE WHEN me.reversa_de_id IS NULL THEN 1 ELSE -1 END`.
- `v_pedidos_estancados`: pedidos que superan el umbral de su estado en `configuracion`.

## Uso de tablas en Fase 3

Fase 3 no añadió tablas: todas las operaciones M10–M15 usan los grupos 4, 5, 6 y parte del 7
definidos en Fase 1. Las relaciones que se apoyan en las reglas de negocio son:

- `producto` → `variante_producto` → `stock_variante` → `movimiento_producto`. El SKU vive en
  `variante_producto.sku` con `UNIQUE`; `stock_variante` mantiene `reservado <= existencia`.
- `producto` → `receta` → (`receta_linea`, `receta_bordado`). La versión es única por
  `producto_id`, `talla_id`, `version`; solo una receta por talla puede estar `VIGENTE`.
- `material` → `inventario_material` → (`lote_material`, `movimiento_material`). Los lotes se
  valoran con `costo_unitario_base` y se consumen PEPS por `fecha_entrada` e `id`.
- `proveedor` → `proveedor_material` → `requisicion` → `cotizacion` → `orden_compra` →
  `recepcion` → `recepcion_linea`. La recepción crea lotes y mermas por el material rechazado.
- `secuencia_folio` alimenta los folios `REQ`, `OC`, `REC` y `LT` dentro de la transacción que
  crea cada documento.

`movimiento_producto` y `movimiento_material` son de solo inserción en la aplicación: no hay
rutas de edición y las correcciones son movimientos inversos con motivo. La restricción a nivel
de base de datos (trigger o `GRANT`) queda registrada como pendiente en `decisiones-tecnicas.md`.

## Uso de tablas en Fase 4

Fase 4 tampoco añadió tablas funcionales; la migración `b2c3d4e5f6a7` solo agregó
`merma.reversa_de_id` (UNIQUE nullable, FK a `merma.id`) y actualizó `v_merma_resumen`.
Las relaciones nuevas que se apoyan en el modelo de Fase 1 son:

- `orden_produccion` → `orden_produccion_linea` → `revision_calidad`. El folio `OP` se genera
  con `secuencia_folio` dentro de la transacción de creación.
- `orden_produccion` → `orden_material` → `inventario_material` → `lote_material`. Las reservas
  se contabilizan en `orden_material.cantidad_reservada` y el consumo PEPS descuenta
  `lote_material.cantidad_base_disponible` con movimientos `CONSUMO`.
- `produccion_pedido` vincula una línea de orden con un `pedido_linea` cuando la demanda
  pendiente de un SKU se acumula en una orden abierta.
- El dictamen incrementa `stock_variante.existencia` con movimiento `PRODUCCION` y reserva
  unidades para pedidos antiguos con `RESERVA`, sin alterar el histórico de `venta_linea`.
- `merma.reversa_de_id` permite reversos sin borrar ni editar la merma original. Un reverso de
  material escribe `movimiento_material.tipo = REVERSA`; uno de producto escribe
  `movimiento_producto.tipo = AJUSTE`, ambos con documento_tipo `MERMA`.

La idempotencia de inicio de producción usa la misma tabla `idempotencia_operacion` con
alcance `produccion:iniciar`.

## Uso de tablas en Fase 5

Fase 5 no añadió tablas. Los módulos M07–M09 usan los grupos 8, 9 y 10:

- `venta` → `venta_linea` → `pedido_linea` conserva copias históricas de SKU, nombre,
  talla, color, precio y subtotal. Cancelar o devolver no altera esas copias.
- `pago` registra reembolsos simulados sin número de tarjeta ni CVV. Una venta de
  reemplazo por `CAMBIO` crea otra venta con total `$0.00` y su propio pedido.
- `devolucion` → `devolucion_linea` → `devolucion_evidencia` controla solicitud,
  recepción, dictamen y resolución; el dictamen `MERMA` delega en `merma_service`.
- `pedido_evento` registra cada transición de estado, incluida la cancelación
  administrativa hasta `LISTO_ENVIO`.

## Uso de tablas en Fase 6

Fase 6 tampoco añadió tablas funcionales; M18–M22 usan los grupos 1, 2, 9, 10 y 11:

- `pedido` → `preparacion` → `preparacion_linea` gestiona picking, verificación y
  empaque. `preparacion_linea` guarda `cantidad_surtida` y las tres verificaciones
  (`sku`, `diseno`, `etiquetas`).
- `empaque_regla` define consumo por prenda (`EMP-BOL`, `EMP-PAP`) y por pedido
  (`EMP-TAR`, `EMP-ETE`). El consumo usa `inventario_material` → `lote_material` por PEPS.
- `repartidor` → `entrega` con `UNIQUE(pedido_id, intento)`; `entrega` guarda folio
  `EN`, estado, intento, salida, resultado, receptor y motivo de fallo. La salida y el
  reingreso escriben `movimiento_producto` con `SALIDA_ENVIO` y `REINGRESO`.
- `alerta` centraliza las reglas de los once eventos; `clave_unica` evita duplicar
  alertas abiertas y se libera al cerrar. Las reglas numéricas viven en
  `configuracion`, sin una tabla adicional.
- `bitacora` registra altas, cambios y bajas de catálogos, tarifas, usuarios y reglas
  de alerta. El dashboard lee vistas del documento y consultas agregadas.

Las seis tareas programadas solo llaman a servicios de dominio; no escriben tablas
propias. El bloqueo `GET_LOCK('unique_scheduler', 5)` evita ejecuciones duplicadas
entre réplicas del contenedor `api`.

## Migraciones

El entorno Alembic ya existe en `migrations/`. No se usa `db.create_all()` en producción.
Revisiones aplicadas:

1. `3baed16b1d4b` — `Fase 1 modelo de datos` (65 tablas, restricciones, índices y claves foráneas).
2. `7c1f9d2a4b60` — `Vistas de lectura del documento funcional`.
3. `b2c3d4e5f6a7` — `Reversos de merma y vista neta` (columna `reversa_de_id` y ajuste de
   `v_merma_resumen`).

Elaboración: `docker compose exec api flask db migrate -m "descripcion"`;
aplicación: `docker compose exec api flask db upgrade`.
