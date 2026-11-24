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
- `v_merma_resumen`: merma por fecha, etapa, causa, producto y material con costo perdido.
- `v_pedidos_estancados`: pedidos que superan el umbral de su estado en `configuracion`.

## Migraciones

El entorno Alembic ya existe en `migrations/`. No se usa `db.create_all()` en producción.
Revisiones aplicadas:

1. `3baed16b1d4b` — `Fase 1 modelo de datos` (65 tablas, restricciones, índices y claves foráneas).
2. `7c1f9d2a4b60` — `Vistas de lectura del documento funcional`.

Elaboración: `docker compose exec api flask db migrate -m "descripcion"`;
aplicación: `docker compose exec api flask db upgrade`.
