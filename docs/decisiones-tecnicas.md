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
| Puerto y prefijo de la API | El frontend Angular apunta a `http://127.0.0.1:5000/api`; el contrato canónico es `/api/v1` en el puerto `8000`. No se duplican rutas en la API. La actualización del frontend se coordina en su repositorio. | Pendiente de coordinar |
| Tokens en el frontend | `auth-session.service.ts` guarda el access token en `localStorage`, lo cual contradice la regla de seguridad del documento. El backend no debe usar ese valor como fuente de autorización; se válida únicamente el JWT recibido en `Authorization: Bearer`. | Pendiente de corregir en el frontend |
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

## Convención de nombres

Los mensajes de error usan texto en español sin acentos en los códigos (`METODO_NO_PERMITIDO`),
mientras que `mensaje` puede contener acentos. Los nombres de campo de base de datos se
mantienen iguales en las respuestas, según la sección 10 del documento.
