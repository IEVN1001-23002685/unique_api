# Modelo de datos

Fuente: sección 6 del documento integral. El modelo declara **64 tablas en 11 grupos**.
En la Fase 0 no se ha creado ninguna tabla: este archivo es el índice que guiará las
migraciones de la Fase 1.

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
entre las 64 tablas, por lo que se añadirá una tabla de infraestructura (por ejemplo
`idempotencia_operacion`) separada del modelo de negocio. Véase `decisiones-tecnicas.md`.

## Vistas

El documento define `v_disponibilidad_variante` y enumera `v_inventario_material`,
`v_ventas_sku`, `v_merma_resumen`, `v_capacidad_variante` y `v_pedidos_estancadas`, entre
otras. Todas se crearán en migraciones reproducibles durante la Fase 1.

## Migraciones

El entorno Alembic ya existe en `migrations/`. No se usa `db.create_all()` en producción.
Elaboración: `docker compose exec api flask db migrate -m "descripcion"`;
aplicación: `docker compose exec api flask db upgrade`.
