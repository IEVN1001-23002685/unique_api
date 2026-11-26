# Decisiones técnicas

Registro de decisiones que no están especificadas, que difieren del documento o que requieren
confirmación del equipo.

| Tema | Decisión | Estado |
|---|---|---|
| Versión de MySQL | El documento menciona MySQL 8.0, pero `AGENTS.md` exige la imagen exacta `mysql:8.4.3`. Prevalece `8.4.3`. | Definido |
| Etiqueta de phpMyAdmin | Se verificó en `docker compose ps` que el contenedor usa exactamente `phpmyadmin:5.2.3`. | Verificado |
| Conflictos de puertos en el host | Los puertos 8000, 3306 y 8080 están ocupados por contenedores de otro proyecto (`hospital_dr`, `mysql_db`, `phpmyadmin`). Se configuraron `API_HOST_PORT=8001`, `MYSQL_HOST_PORT=3307` y `PHPMYADMIN_PORT=8081` en `.env` y en `.env.example`. Los puertos internos y `DATABASE_URL` no cambian; `MYSQL_PORT` sigue siendo 3306. | Resuelto en este entorno |
| Configuración de Alembic | Flask-Migrate requiere `migrations/alembic.ini` además de `env.py` y `script.py.mako`. Se añadió con las secciones de logging y `script_location = %(here)s`. | Corregido |
| Autenticación de MySQL | PyMySQL necesita `cryptography` para `caching_sha2_password`, el plugin por defecto de MySQL 8.4. Se añadió `cryptography==43.0.3` a `requirements.txt`. | Corregido |
| Puerto y prefijo de la API | El frontend Angular apuntaba a `http://127.0.0.1:5000/api`; el contrato canónico es `/api/v1` en el puerto `8000`. No se duplican rutas en la API. El frontend ya usa `API_BASE_URL` (`http://localhost:8001/api/v1` en este entorno). | Corregido en el frontend |
| Tokens en el frontend | El access token se mantiene solo en memoria (`AuthStateService`) y el refresh token viaja en cookie `httpOnly`. El backend valida únicamente el JWT recibido en `Authorization: Bearer`. | Corregido en el frontend |
| Idempotencia | El documento exige persistencia de `Idempotency-Key` pero no lista una tabla para ella. Se creó la tabla de infraestructura `idempotencia_operacion` (clave, alcance, hash de petición, estado y respuesta), separada de las 64 tablas funcionales. | Implementado; confirmar nombre |
| Rate limit entre workers | `WEB_CONCURRENCY=1` por defecto, de modo que `memory://` aplica el límite en el único proceso Gunicorn. Si se aumentan los workers, configure `RATELIMIT_STORAGE_URI` con un almacén compartido (por ejemplo SQLAlchemy sobre MySQL, sin añadir un cuarto servicio); de lo contrario cada worker contaría por separado. | Resuelto para Fase 1; condición para escalar |
| CSRF de refresh cookie | Se desactivó `JWT_COOKIE_CSRF_PROTECT` por defecto porque el documento solo exige cookie `httpOnly`, `Secure` en HTTPS y `SameSite=Strict`, sin doble envío. La protección se apoya en `SameSite=Strict` y en la lista de orígenes CORS. Se puede reactivar con `JWT_COOKIE_CSRF_PROTECT=true` cuando el frontend envíe el encabezado CSRF. | Decidido; reversible por entorno |
| Código del readiness | `/api/v1/health/db` responde `503` cuando MySQL falla. El código no está listado en el contrato general, pero se justifica por ser un endpoint de infraestructura. | Definido |
| Valores propuestos del documento | `dias_devolucion`, `max_intentos_entrega`, `dias_produccion_estandar`, `max_piezas_por_linea`, `saldo_inicial_cuenta_simulada` y tarifa «Local León» se cargaron como configuración editable; la semilla los marca como propuestas pendientes de confirmar. El costo de $200.00 y 2 días de la tarifa son referencia, no dato definitivo. | Sembrado; pendiente de confirmar |
| Normalización de rutas ambiguas | Si una ruta del documento es ambigua por su representación en texto, se conserva la intención funcional y se registra aquí la URL normalizada. No se duplican rutas que colisionen. | Mecanismo definido |
| Enteros unsigned | SQLAlchemy 2.x no acepta `Integer(unsigned=True)`. Se definió `entero_unsigned()` en `app/models/base.py`, que usa `mysql.INTEGER(unsigned=True)` solo en MySQL y `Integer` en otros dialectos. No cambia los tipos definidos en el documento. | Corregido |
| Herencia de roles | «ADMIN hereda permisos del Operativo» se implementó en un solo sentido: `ADMIN` puede acceder a rutas `O`; `OPERATIVO` no puede acceder a rutas `A`. | Corregido |
| `receta.creada_por` | Se permite `NULL` porque las 11 recetas semilla no tienen autor humano. Las recetas creadas desde la API registrarán al administrador que las genera. | Decidido |
| Usuarios iniciales | No hay contraseñas fijas. `scripts/seed.py` crea ADMIN y OPERATIVO solo si existen `ADMIN_EMAIL`/`ADMIN_PASSWORD` y `OPERATIVO_EMAIL`/`OPERATIVO_PASSWORD`. También existe `python -m scripts.create_admin admin|operativo`, interactivo o con esas mismas variables. | Implementado |
| Vistas SQL | Se implementaron `v_disponibilidad_variante`, `v_inventario_material`, `v_capacidad_variante`, `v_ventas_sku`, `v_merma_resumen` y `v_pedidos_estancados` en una migración reproducible. El consumo diario usa movimientos de los últimos 30 días o el valor manual cuando no hay historial. | Implementado |
| Índices corregidos | Se ajustaron índices cuyas columnas no existían en el modelo (`fecha` en `devolucion`, `activa` en `material` y `producto`, `id` en `lote_material`) antes de generar la migración. | Corregido |
| Descuento de primera compra | El documento dice que «no se detecta solo» en el paso 5, pero la semilla lo define como `AUTOMATICO`. Decisión: el servidor lo aplica automáticamente al pagar si el cliente no tiene una venta `ACTIVA` previa; el botón «Aplicar» existe para mostrarlo antes del pago. El algoritmo de «primera compra» no está definido en el documento: se cuenta la primera venta `ACTIVA` del usuario. | Decidido; pendiente de confirmar |
| Código del descuento semilla | El documento no fija un `codigo` para «Primera compra». La semilla usa `PRIMERA_COMPRA` como identificador local; el descuento puede aplicarse sin que el cliente escriba el código. | Decidido; pendiente de confirmar |
| `iva_incluido` | El modelo de Fase 1 define `venta.iva_incluido` como `BOOLEAN`, coherente con «precios con IVA incluido». Se mantiene `true` y no se cambia el tipo sin autorización. La fórmula informativa de M08 se expone como `iva_importe = total * iva_pct / (100 + iva_pct)`, usando `iva_pct` de configuración; no altera los importes contables. | Implementado y verificado en cotización y pago; `iva_pct` pendiente de confirmar |
| Dos copias de `venta_direccion` | El flujo de pago pide dos copias (`ENVIO` y `FACTURACION`). Si `requiere_factura = false`, se guarda la dirección de envío en ambas copias y `rfc`/`razon_social` quedan `NULL`. | Decidido |
| Borrado de medios de pago | El documento muestra `🗑 eliminar`, pero la tabla tiene `activo`. Se aplica borrado lógico (`activo = false`), nunca físico. | Decidido |
| Filtros de catálogo | La pantalla menciona rango de precio y orden por precio/novedad, pero el endpoint canónico solo declara `categoria`, `color`, `talla`, `q` y `disponibles`. Se implementan solo los parámetros canónicos; los otros quedan pendientes de confirmación. | Decidido; pendiente de confirmar |
| `envio_gratis_desde` | Existe en configuración, pero el documento no describe la regla de cálculo. No se aplica envío gratis en Fase 2: el costo de la tarifa vigente siempre se cobra. | Decidido; pendiente de confirmar |
| Identificador de idempotencia | El resultado se guarda en `idempotencia_operacion` con `alcance = checkout:pagar`. La petición se identifica por hash del JSON canónico; la misma clave con otro cuerpo devuelve `409 IDEMPOTENCIA_CONFLICTO`. Un replay de una operación `COMPLETADA` devuelve la respuesta original; un replay `ERROR` devuelve el error original sin repetir efectos. Estos campos provienen de `AGENTS.md`, no del documento funcional. | Decidido según `AGENTS.md` |
| Cancelación de pedido | El `CHECK` de `pedido_linea` exige `cant_reservada + cant_pendiente = cantidad`. Al cancelar se ponen en cero las tres cantidades; la venta conserva la cantidad original en su histórico. | Implementado; efecto documentado |

## Fase 3 (M10–M15)

| Tema | Decisión | Estado |
|---|---|---|
| Formato de SKU | El documento ejemplifica `PL-MD-GR` y `GO-UN-NG`. El consecutivo por categoría se construye sobre el prefijo (`GO2-UN-GR`) para evitar duplicados cuando hay varias colecciones de la misma categoría. Sigue siendo de tres segmentos, se genera en servidor bloqueando la fila de categoría y no cambia al renombrar el producto. | Decidido; confirmar prefijo numérico con el equipo |
| Borradores de receta al crear producto | `POST /productos` crea una receta `BORRADOR` por talla. Un `POST /recetas` posterior para la misma talla reutiliza ese borrador y responde `201` en lugar de `409 BORRADOR_EXISTENTE`. Así se conserva el flujo M10→M11 sin recetas duplicadas. | Implementado |
| Activación de producto | La matriz de roles del documento (línea 473) permite lectura M10 a `OPERATIVO`, pero la sección 11 de `AGENTS.md` exige solo `ADMIN`. Prevalece `ADMIN` para `/productos` y se mantiene `OPERATIVO` para lectura de `/recetas`, donde el documento sí lo autoriza. | Decidido según `AGENTS.md`; pendiente de confirmar |
| Código de ajuste de inventario PT | La acción modifica existencias, por lo que responde `200` y no `201`, según el contrato general (sección 10). | Decidido |
| Listados en memoria | `/productos`, `/recetas`, `/disenos`, `/proveedores/{id}/materiales` y `/cotizaciones` se paginan en la capa HTTP con `{items,total,pagina,por_pagina}`. No se añadió `LIMIT/OFFSET` en servicio porque estos catálogos son pequeños; se revisará si crecen. | Implementado |
| Evaluación de proveedores | `GET /proveedores/evaluacion` es de solo lectura y devuelve el estatus derivado. La mutación de estatus y la alerta `PROVEEDOR_EN_REVISION` la ejecuta la tarea diaria `evaluar_proveedores` con `proveedor_service.evaluacion(persistir=True)`. El porcentaje divide entre órdenes **recibidas**, no entre órdenes con `fecha_prometida`; sin historial se reporta `100.00` para no penalizar sin evidencia. | Implementado en Fase 6 |
| Cotizaciones | El proveedor debe tener el material en su catálogo activo para cotizar. Elegir una cotización con `vigencia_hasta` vencida responde `409`. El mínimo de dos cotizaciones cuando hay alterno y el plazo de entrega por proveedor quedan pendientes: el documento no fija regla operativa completa. | Parcial; pendiente de confirmar |
| Recepción y reservas de producción | La recepción cierra `OC_RETRASADA`, crea lotes por lo aceptado y genera merma por el rechazo. Desde Fase 4 también reintenta reservas de órdenes `PLANEADA` y cierra `MP_REORDEN` mediante `produccion_service.reevaluar_ordenes_por_recepcion`. | Implementado en Fase 4 |
| Cierre de OC con faltante | El documento permite cerrar con faltante con confirmación de `ADMIN`, pero no define el estado final ni el efecto en la requisición. No se implementa una regla inventada. | Pendiente de confirmar |
| Inmutabilidad de movimientos | Las rutas solo insertan movimientos y las correcciones usan movimientos inversos. No hay `UPDATE`/`DELETE` expuestos, pero la restricción aún no existe en la base; se añadirá con trigger o `GRANT` en una migración. | Parcial |
| Tipo de movimiento en ajuste MP | `consumir_peps` acepta el tipo de movimiento. Los ajustes negativos escriben `AJUSTE` para no contaminar el consumo de 30 días que alimenta el punto de reorden. | Corregido |
| Dueño de la merma | M13/M15 registran mermas de recepción y ajuste con `CausaMerma`; desde Fase 4 M14, M15 y M16 delegan la creación en `merma_service` (M17), con `confirmar=False` cuando participan en una transacción ajena. | Implementado en Fase 4 |
| Alcance de idempotencia en recepciones | `recepciones:registrar`, separado de `checkout:pagar`. Un error persistido con la misma clave no sobrescribe una respuesta `COMPLETADA`. | Implementado |
| Imágenes | Se valida contenido real, MIME declarado y tamaño máximo de 2 MB antes de confirmar. Si falla la transacción después de escribir el archivo, se elimina el archivo huérfano. | Implementado |

## Fase 4 (M16–M17)

| Tema | Decisión | Estado |
|---|---|---|
| Semáforo de orden | El documento usa `ÁMBAR`; los códigos no llevan acentos, por lo que se serializa `AMBAR`. Los tres valores son `VERDE`, `AMBAR` y `ROJO`. | Normalizado; confirmar con el frontend |
| `GET /pedidos/pendientes-produccion` | `AGENTS.md` lo lista en M09, pero la información pertenece a las órdenes de M16. Fase 4 expuso `/produccion/pendientes-produccion`; en Fase 5 se añadió la ruta canónica de M09 y ambas delegan en `produccion_service.pendientes_lineas`. | Normalizado; implementado |
| Reverso de merma | No se edita ni borra la merma original: se inserta una nueva fila con `reversa_de_id` único. La migración `b2c3d4e5f6a7` ajustó `v_merma_resumen` para netear reversos (`+1`/`-1`), de modo que los indicadores no dupliquen el evento. | Implementado |
| Movimiento inverso | El reverso de material escribe `movimiento_material.tipo = REVERSA`; el de producto escribe `movimiento_producto.tipo = AJUSTE`, porque el dominio de movimientos de producto de Fase 1 no incluye `REVERSA`. Ambos llevan `documento_tipo = MERMA`, motivo y bitácora. | Implementado |
| Merma del dictamen | Las unidades mermadas en calidad se registran con `descontar=False`: el material ya se consumió por PEPS al iniciar y la merma es de producto terminado no aprobado. La fila de merma es de `PRODUCTO` y no vuelve a descontar stock. | Implementado |
| Inicio de producción | Exige orden `LISTA`. Solo se consumen materiales con reserva; el faltante queda pendiente y se atiende con `solicitar-compra` o una nueva recepción. Si falta PEPS para lo reservado, se revierte todo y se responde `MATERIAL_INSUFICIENTE`. | Implementado |
| Alcance de idempotencia | Inicio de producción usa `produccion:iniciar` en `idempotencia_operacion`, separado de `checkout:pagar` y `recepciones:registrar`. Un error persistido no sobrescribe una respuesta completada. | Implementado |
| Solicitud de compra | Si la orden ya tiene requisición `PENDIENTE`, `AUTORIZADA` o `COMPRA_EMITIDA`, se reutiliza y se responde `duplicada=true`. El documento no define el comportamiento ante solicitudes repetidas; se evita duplicar la demanda. | Decidido; pendiente de confirmar |
| Asignación de producido a pedidos | Las unidades aprobadas se reservan para pedidos `CONFIRMADO`/`EN_PRODUCCION` ordenados por `creado_en`, `id` y `pedido_linea.id`. El histórico de `venta_linea` no se modifica; solo cambian `cant_reservada`/`cant_pendiente` y el estado del pedido cuando se agota lo pendiente. | Implementado |
| Cierre de la orden | Se cierra cuando todas las líneas tienen `aprobadas + merma = planeada`; vuelve a `EN_PROCESO` si hay reproceso y permanece `EN_REVISION` si faltan unidades por dictaminar. El reproceso se registra pero no crea merma ni PT. | Implementado |
| Checklist de calidad | El documento enumera medidas, costuras, bordado y etiquetas. No se pueden aprobar unidades si alguno de los cuatro indicadores es `false`; el bloqueo responde `422 CHECKLIST_INCOMPLETO`. | Decidido |
| Causa de merma por defecto | Si el dictamen no envía `causa_merma_id`, se usa una causa activa válida para `PRODUCTO` (por defecto «Defecto de acabado»). No se inventa una causa nueva. | Decidido |

## Fase 5 (M07–M09)

| Tema | Decisión | Estado |
|---|---|---|
| Ventana de devolución | Solo se solicitan cambios/devoluciones de pedidos `ENTREGADO` dentro de `dias_devolucion` (configuración inicial propuesta: 15 días, pendiente de confirmar). La fecha de entrega usa `entregado_en`, luego `estado_desde` y finalmente `fecha` de la venta. | Decidido; plazo pendiente de confirmar |
| Cálculo del reembolso | Se prorratea el subtotal de cada línea, se descuenta la parte proporcional del cupón y se excluye el envío salvo `DEFECTO`, `DANO_ENVIO` o `PRODUCTO_EQUIVOCADO`. Nunca excede el saldo pendiente de la venta. | Implementado |
| Venta de reemplazo | Una resolución `CAMBIO` crea una venta de canal `CAMBIO` con total `$0.00`, pago `TRANSFERENCIA` aprobado y pedido; se reutilizan los helpers de checkout. No se captura tarjeta ni CVV. | Implementado |
| Dueño de la merma de devolución | El dictamen `MERMA` delega en `merma_service.registrar_merma` con `descontar=False` y `confirmar=False`: la operación completa confirma la transacción. El `REINGRESO` usa `stock_service` con movimiento `REINGRESO`. | Implementado |
| Cancelación administrativa | `ADMIN` puede cancelar pedidos hasta `LISTO_ENVIO`, a diferencia de la cancelación del cliente. Libera reservas, ajusta órdenes, cancela la venta y reembolsa solo el saldo pendiente. | Implementado |
| Venta manual impaga | `estado_pago = PENDIENTE` deja el pedido en `RECIBIDO`, mantiene la reserva y abre `PAGO_PENDIENTE`. No se crea preparación hasta aprobar el cobro. | Implementado |
| Borrado de descuentos | Si el descuento tiene `usos_actuales > 0`, `DELETE` solo lo desactiva para conservar el histórico; si nunca se usó, se elimina físicamente. | Decidido |
| Importes de operativo | El detalle administrativo de pedidos y las devoluciones no exponen costos, márgenes ni precios de compra a `OPERATIVO`. El total de la venta sigue visible para cumplimiento. | Implementado |

## Fase 6 (M18–M22)

| Tema | Decisión | Estado |
|---|---|---|
| Identificador de `/preparacion/{id}/tomar` | El documento usa `{id}` sin precisar si es pedido o preparación. La toma se hace por `pedido_id` porque el pedido es la entidad que cambia a `EN_PREPARACION`; las operaciones de líneas, incidencia, empaque y etiqueta usan `preparacion_id`. | Normalizado |
| Verificación de empaque | Antes de empacar, cada línea requiere `sku_verificado`, `diseno_verificado` y `etiquetas_verificadas`. El empaque consume PEPS con las reglas sembradas: `EMP-BOL` y `EMP-PAP` por prenda, `EMP-TAR` y `EMP-ETE` por pedido. | Implementado |
| Etiqueta y hoja de reparto | El documento no fija formato. Se genera un PDF de una página con `app/utils/pdf.py` y `Content-Type: application/pdf`, sin dependencias adicionales. | Decidido |
| Reingreso por entrega fallida | La salida descuenta `existencia` y `reservado` con `SALIDA_ENVIO`. Un fallo posterior reingresa `+existencia` y `+reservado` con `REINGRESO`, porque la reserva sigue siendo del pedido. | Implementado |
| Intentos de entrega | `max_intentos_entrega = 2` es propuesta editable en `configuracion`; el segundo fallo abre `ENTREGA_FALLIDA` con severidad `CRITICA`. El `CHECK` de `entrega` limita el intento a una entrega por pedido e intento. | Decidido; pendiente de confirmar |
| Reglas de alertas | No se añade una tabla: las once reglas se leen y escriben en `configuracion` mediante `/alertas/reglas`. La alerta abierta con la misma `clave_unica` no se duplica; al cerrarse se libera la clave a `NULL`. | Implementado |
| Elevación y atención de alertas | `alertas_service` expone `elevar` y `atender` además de `abrir` y `cerrar`. La acción desde el endpoint ejecuta el servicio correspondiente y registra la atención. | Implementado |
| Catálogos administrativos | La sintaxis `CRUD de /catalogos/{color,talla,...}` se normalizó a seis recursos explícitos: `/catalogos/color`, `/talla`, `/categoria-producto`, `/categoria-material`, `/causa-merma` y `/tarifa-envio`. No se crea una ruta dinámica para entidades no declaradas. | Normalizado |
| Códigos inmutables en catálogos | `color.codigo`, `talla.codigo` y `categoria-producto.prefijo_sku` participan en el SKU y no se modifican: `409 CODIGO_SKU_INMUTABLE`. Los esquemas de actualización aceptan el campo solo para detectar el cambio y devolver el conflicto. | Implementado |
| `activa` en catálogos | `Color`, `Talla` y `CategoriaMaterial` no tienen columna `activa`. No se agregó sin justificación: la desactivación de catálogos con histórico se resuelve con reglas de uso (`409 CATALOGO_EN_USO`). Si el negocio requiere borrado lógico de estos tres catálogos, se hará en una migración dedicada. | Pendiente de confirmar |
| Dashboard para operativo | `/dashboard/produccion`, `/abastecimiento` y `/logistica` admiten `OPERATIVO`, pero el serializador omite costos, precios de compra, márgenes y utilidades. `/resumen`, `/ventas` y `/exportar` son solo `ADMIN`. | Implementado |
| Universo de workers del scheduler | Supervisor levanta `api` (Gunicorn) y `scheduler` en el mismo contenedor. El scheduler adquiere `GET_LOCK('unique_scheduler', 5)` en MySQL antes de iniciar APScheduler, de modo que varias réplicas no dupliquen tareas. | Implementado |
| JSON y PDF | `/dashboard/exportar` devuelve CSV (`text/csv; charset=utf-8`) con `Content-Disposition: attachment`. La etiqueta de preparación y la hoja de reparto devuelven PDF (`application/pdf`) con `Content-Disposition: inline`. | Documentado |
| Especificación OpenAPI | Se genera `docs/openapi.json` con `scripts/generate_openapi.py` a partir de las rutas Flask registradas. La API expone `GET /api/v1/openapi.json` y `GET /api/v1/docs` (Swagger UI). `docs/endpoints.md` sigue siendo el contrato funcional detallado. | Implementado en Fase 7 |
| Orígenes CORS para Angular | Se permiten `http://localhost:4200` y `http://127.0.0.1:4200` porque Angular puede resolverse con cualquiera de los dos nombres de host. `supports_credentials=True` ya estaba configurado para la cookie de refresco. | Implementado |

## Integración con el frontend Angular

| Tema | Decisión | Estado |
|---|---|---|
| M05 · método de envío | La interfaz mostraba «estándar/exprés» con importes fijos, sin respaldo en el documento. Se eliminó ese selector: el costo y el plazo se toman de la tarifa vigente devuelta por `/checkout/cotizar` para el C.P. de la dirección. | Implementado |
| M05 · Idempotency-Key | La clave la genera `CheckoutServicio` con `crypto.randomUUID()` y se reutiliza mientras el cuerpo sea idéntico, de modo que un reintento de red no duplique la venta. Un cuerpo distinto produce otra clave. | Implementado |
| M06 · líneas de pedido | `PedidoLineaSchema` expone `venta_linea_id`, `variante_id` y `producto_id` como campos de solo lectura. M07 exige esos identificadores para crear la solicitud y ofrecer variantes de reemplazo; el frontend no puede derivarlos de `pedido_linea.id`. No cambia ninguna regla de negocio. | Implementado |
| M07 · vistas por rol | La pantalla de cambios y devoluciones tiene vista de cliente en `/devoluciones` y vista operativa en `/operacion/devoluciones`. El cliente solo solicita y consulta las suyas; aprobación, recepción y dictamen siguen los roles del contrato. Las evidencias se envían como multipart en `datos` y `evidencias`. | Implementado |
| M18–M22 · rutas heredadas | Las rutas antiguas `/preparacion`, `/entregas`, `/dashboard`, `/alertas` y `/sistema` redirigen a `/panel-admin/...`. Así se evita que las pantallas simuladas previas sigan siendo accesibles desde el menú; las rutas canónicas reales viven en `admin-unique`. | Implementado |
| M13 · altas de material por proveedor | El contrato no define reemplazo masivo. La pantalla publica altas, cambios y bajas por separado contra `/proveedores/{id}/materiales`. | Implementado |
| M14/M15 · resultado de borrado | `DELETE /materiales/{id}` y `DELETE /proveedores` responden `204`. La interfaz infiere el baja lógica recargando el catálogo; no inventa un campo de estado en la respuesta. | Implementado |
| M14/M16 · idempotencia | Las claves de recepción y de inicio de producción se generan en los servicios Angular (`crypto.randomUUID()`), nunca en los componentes, y se reutilizan mientras el cuerpo sea idéntico. | Implementado |
| M17 · reversas | El reverso crea una fila nueva con `reversa_de_id`; la fila original no se edita. La marca «reversada» se calcula en la sesión porque `GET /mermas` no expone ese estado tras recargar. | Implementado; pendiente de exponer en el contrato si el negocio lo requiere |
| M02/M05 · tarjeta | El pago usa el medio guardado cuando existe; para una tarjeta nueva se capturan los datos solo en el formulario en memoria y se envían directamente a `/checkout/pagar`. Ningún número completo ni CVV se persiste en el frontend. | Implementado |

## Convención de nombres

Los mensajes de error usan texto en español sin acentos en los códigos (`METODO_NO_PERMITIDO`),
mientras que `mensaje` puede contener acentos. Los nombres de campo de base de datos se
mantienen iguales en las respuestas, según la sección 10 del documento.
