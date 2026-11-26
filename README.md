# UNIQUE API

Backend REST de UNIQUE (Flask + MySQL), construido según `UNIQUE_documento_integral_v3.txt`.

**Estado actual: Fase 7 en cierre.** Se implementaron M01–M22, Docker, migraciones, semillas,
pruebas contra MySQL y especificación OpenAPI/Swagger (`/api/v1/openapi.json`, `/api/v1/docs`).
Quedan pendientes de negocio las reglas propuestas y decisiones marcadas en
`docs/decisiones-tecnicas.md`.

## Requisitos

- Docker Engine + Docker Compose v2 (`docker compose`).
- No se requiere Python, Flask ni MySQL instalados en el host.

## Configuración inicial

```bash
cp .env.example .env
```

Edite `.env` antes de arrancar: reemplace `SECRET_KEY`, `JWT_SECRET_KEY`,
`MYSQL_PASSWORD` y `MYSQL_ROOT_PASSWORD` por valores propios. `.env` está excluido
del repositorio y de la imagen Docker.

## Arranque

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f api
```

Servicios:

| Servicio | Imagen | Puerto host | Uso |
|---|---|---:|---|
| `api` | `python:3.11-slim` (propia) | 8001 (`API_HOST_PORT`; interno 8000) | Supervisor: Gunicorn + scheduler |
| `mysql` | `mysql:8.4.3` | 3307 (`MYSQL_HOST_PORT`; interno 3306) | Persistencia |
| `phpmyadmin` | `phpmyadmin:5.2.3` | 8081 (`PHPMYADMIN_PORT`; interno 80) | Administración de MySQL |

phpMyAdmin se conecta a MySQL por el nombre de servicio `mysql`, no por `localhost`.

## Health check

```bash
curl.exe -i http://localhost:8001/api/v1/health
curl.exe -i http://localhost:8001/api/v1/health/db
```

- `/api/v1/health`: liveness, no consulta la base de datos.
- `/api/v1/health/db`: readiness, ejecuta `SELECT 1`; responde `503` si MySQL falla.

El contenedor `api` espera a MySQL con `scripts/wait_for_db.py` antes de iniciar Supervisor.
Supervisor levanta dos procesos: `api` (Gunicorn, sin `--reload`) y `scheduler`
(`python -m app.jobs`, con `GET_LOCK('unique_scheduler', 5)` en MySQL para no duplicar tareas
entre réplicas). El `healthcheck` de Compose usa `/api/v1/health`.

## Migraciones, semillas y pruebas

```bash
docker compose exec api python scripts/wait_for_db.py
docker compose exec api flask db upgrade
docker compose exec api python -m pytest -q
```

Si la API no conecta con MySQL: `docker compose exec api python scripts/diagnose_db.py`.
Cualquier cambio en código requiere `docker compose build` antes de `up -d`.

`flask db upgrade` aplica tres revisiones: Fase 1 (modelo completo, vistas e índices), vistas de
lectura y `b2c3d4e5f6a7` (reversos de merma y neteo de `v_merma_resumen`). Las Fases 2 a 6 no
añadieron tablas funcionales: reutilizan el modelo y la tabla de infraestructura
`idempotencia_operacion` (alcances `checkout:pagar`, `recepciones:registrar` y
`produccion:iniciar`). Después ejecute las semillas, que son idempotentes:

```bash
docker compose exec api python -m scripts.seed
docker compose exec api python -m scripts.seed   # segunda ejecución: 0 inserciones
```

Las cuentas iniciales se crean solo si configura `ADMIN_EMAIL`/`ADMIN_PASSWORD` y
`OPERATIVO_EMAIL`/`OPERATIVO_PASSWORD` en `.env`; también puede crearlas de forma interactiva:

```bash
docker compose exec api python -m scripts.create_admin admin
docker compose exec api python -m scripts.create_admin operativo
```

No hay contraseñas fijas en el código ni en las semillas.

La Fase 3 está cubierta por `tests/integration/test_fase3_productos.py`,
`test_fase3_materiales.py` y `test_fase3_compras.py`: SKU y folios, activación de productos y
recetas, receta `VIGENTE` no editable, ajustes con movimientos inmutables, PEPS, recepciones
idempotentes con merma por rechazo, permisos Admin/Operativo y ocultamiento de costos. La Fase 4
añade `tests/integration/test_fase4_produccion_mermas.py`: ciclo completo de orden de producción,
reserva y semáforo, solicitud de compra, inicio idempotente con PEPS, rollback con material
insuficiente, dictamen con asignación FIFO a pedidos, reverso de mermas e indicadores, roles y
transiciones inválidas. La Fase 5 añade `tests/integration/test_fase5_comercial.py`: venta manual
con pago pendiente, reembolsos, descuentos, permisos, devolución con reingreso, cambio con venta
de reemplazo y transiciones de pedidos. La Fase 6 añade `tests/integration/test_fase6_logistica.py`:
cola de preparación con verificación y empaque PEPS, etiqueta y hoja de reparto en PDF, ciclo de
entrega con reingreso, dos fallos con alerta crítica, KPIs y permisos de dashboard, alertas y sus
reglas, catálogos con códigos inmutables, bitácora y las seis tareas programadas. La suite
completa verificada es `75 passed`. Las imágenes se guardan en el volumen de uploads, se validan
con Pillow y se rechazan si superan 2 MB.

## Detener y reiniciar

```bash
docker compose down
docker compose up -d
```

Los datos de MySQL y los archivos subidos viven en volúmenes nombrados y sobreviven a `down`.
**Nunca ejecute `docker compose down -v` sin autorización explícita**: elimina los volúmenes.

## Despliegue en Railway

Railway no ejecuta `compose.yaml`; despliega servicios separados desde el `Dockerfile`.

1. Crea un servicio **MySQL** en Railway y un servicio **API** desde este repo.
2. En el servicio API configura variables de entorno:
   - `APP_ENV=production`
   - `APP_DEBUG=false`
   - `SECRET_KEY` y `JWT_SECRET_KEY` con valores aleatorios largos y diferentes (por ejemplo, generados con `python -c "import secrets; print(secrets.token_urlsafe(48))"`). No reutilices estos secretos entre entornos.
   - `DATABASE_URL=${{MySQL.MYSQL_URL}}`, sustituyendo `MySQL` por el nombre exacto del servicio de base de datos. Railway entrega `mysql://...`; la app y el script de espera lo normalizan a `mysql+pymysql://...`. Si la referencia no aplica, construye la URL como `mysql+pymysql://<usuario>:<contraseña-url-encoded>@<host-privado>:<puerto>/<base>?charset=utf8mb4`.
   - `CORS_ORIGINS=https://<dominio-frontend>` con el origen real, sin ruta final; para varios orígenes, sepáralos por comas.
   - `JWT_COOKIE_SECURE=true`
   - `TZ=America/Mexico_City`
   - `WEB_CONCURRENCY=1`
3. Railway asigna `PORT`; el contenedor ya lo usa automáticamente. No fijes `APP_PORT` salvo pruebas locales.
4. Monta un **Volume** en `/var/lib/unique/uploads` para conservar imágenes. Añade `RAILWAY_RUN_UID=0` al servicio API: Railway monta los volúmenes como `root` y la imagen ejecuta con el usuario no-root `app`.
5. Ejecuta una vez en el shell del servicio API:

```bash
flask db upgrade
python -m scripts.seed
python -m scripts.create_admin admin
```

6. Después del deploy, verifica `GET /api/v1/health`, `GET /api/v1/health/db` y un inicio de sesión en `POST /api/v1/auth/login`.

Notas: no instales phpMyAdmin dentro de la API. Si escalas a más de una réplica, configura `RATELIMIT_STORAGE_URI` con un almacén compartido; el límite en memoria no se comparte entre instancias. Si escribes `DATABASE_URL` manualmente, URL-encodea los caracteres reservados de usuario/contraseña; Railway recomienda usar la referencia privada `MYSQL_URL` dentro del mismo proyecto en vez del endpoint público.

## Solución de problemas

- `cannot connect to the Docker daemon`: inicie Docker Desktop; Compose está instalado pero el
  daemon no responde.
- `api` en estado `unhealthy`: revise `docker compose logs api` y compruebe `DATABASE_URL`.
- `mysql` en estado `unhealthy`: revise `docker compose logs mysql`; el healthcheck usa
  `MYSQL_ROOT_PASSWORD` solo internamente.
- `Bind for 0.0.0.0:<puerto> failed: port is already allocated`: otro proceso del host ocupa
  el puerto publicado. Cambie `MYSQL_HOST_PORT`, `PHPMYADMIN_PORT` o `API_HOST_PORT` en `.env`
  y vuelva a ejecutar `docker compose up -d`. Los puertos internos no se modifican.
- Error de CORS: `CORS_ORIGINS` debe contener el origen Angular exacto, separado por comas si
  hay varios.

## OpenAPI

```bash
docker compose exec api sh -c 'cd /app && PYTHONPATH=/app python scripts/generate_openapi.py'
```

- `GET /api/v1/openapi.json`
- `GET /api/v1/docs`

## Detalles

- Arquitectura: `docs/arquitectura.md`
- Modelo de datos: `docs/modelo-datos.md`
- Contrato HTTP: `docs/endpoints.md`
- OpenAPI: `docs/openapi.json`
- Decisiones técnicas: `docs/decisiones-tecnicas.md`
- Despliegue: `docs/despliegue-docker.md`
