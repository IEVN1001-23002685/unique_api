# Despliegue de la API UNIQUE en Railway

Este documento describe el servicio **API** (`unique_api`) dentro del mismo proyecto de Railway
que el frontend `unique` y MySQL. La API se sirve con Gunicorn bajo Supervisor, usa MySQL por red
privada, guarda imágenes en un volumen persistente y no contiene secretos en el repositorio.

## 1. Servicios del proyecto

| Servicio | Origen | Función |
|---|---|---|
| `MySQL` | Servicio de base de datos de Railway | Persistencia privada; no exponer al público |
| `API` | Repositorio `unique_api`, rama actual `main` | Flask + Gunicorn + Supervisor + scheduler |
| `Frontend` | Repositorio `unique`, rama actual `saul/modulos` | Angular servido por Nginx |

Las referencias `${{MySQL.MYSQL_URL}}` y `${{API.RAILWAY_PUBLIC_DOMAIN}}` asumen esos nombres de
servicio; sustituirlos por los nombres reales. No se inventan dominios aquí.

## 2. Variables de entorno de la API

| Variable | Valor en Railway | Obligatoria | Notas |
|---|---|---|---|
| `APP_ENV` | `production` | Sí | Con `APP_ENV` inválido, o con `RAILWAY_ENVIRONMENT` presente, la app falla cerrado si faltan secretos |
| `APP_DEBUG` | `false` | Sí | Se fuerza a `false` en producción |
| `SECRET_KEY` | Valor aleatorio largo y único | Sí | Rechaza `change_me`/vacío en producción |
| `JWT_SECRET_KEY` | Valor aleatorio largo y diferente del anterior | Sí | Rechaza `change_me`/vacío en producción |
| `DATABASE_URL` | `${{MySQL.MYSQL_URL}}` | Sí | Railway entrega `mysql://...`; se normaliza a `mysql+pymysql://...` |
| `CORS_ORIGINS` | `https://<dominio-real-del-frontend>` | Sí | Origen exacto, sin `/`; varios separados por comas; prohibido `*` |
| `JWT_COOKIE_SECURE` | `true` | Sí | Obligatorio con `SameSite=None` |
| `JWT_COOKIE_SAMESITE` | `None` | Sí | Necesario porque frontend y API están en sitios distintos |
| `JWT_COOKIE_CSRF_PROTECT` | `true` | Sí | Activo por defecto; valida doble envío en `refrescar` y `logout` |
| `TZ` | `America/Mexico_City` | Sí | Zona del scheduler |
| `WEB_CONCURRENCY` | `1` | Sí | El rate limit usa `memory://`; ver nota de escalado |
| `RATELIMIT_STORAGE_URI` | `redis://...` solo si escala | No | `memory://` no se comparte entre réplicas; no usar MySQL como almacén |
| `UPLOAD_FOLDER` | `/var/lib/unique/uploads` | No | Coincide con el volumen; no cambiar salvo prueba local |
| `DB_WAIT_TIMEOUT` | `60` | No | Debe ser entero positivo |
| `PORT` | Lo asigna Railway | Sí | Gunicorn escucha en `0.0.0.0:$PORT` |
| `FLASK_APP` | `wsgi:app` | No | Ya viene en la imagen |

Generar secretos fuera del repositorio, por ejemplo:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

No reutilizar secretos entre entornos ni pegarlos en tickets, logs o documentación.

## 3. Red, CORS, cookies y CSRF

- La API debe alcanzar MySQL por la red privada de Railway usando la referencia interna
  `${{MySQL.MYSQL_URL}}`. No usar el endpoint público de MySQL.
- `CORS_ORIGINS` debe ser exactamente el origen del frontend
  (`https://<dominio-real-del-frontend>`). `supports_credentials=True` está activo; un `*` con
  credenciales queda rechazado en el arranque.
- El login emite una cookie de refresco `httpOnly` y, con CSRF activo, la cookie legible
  `csrf_refresh_token`. El frontend envía `X-CSRF-TOKEN` desde esa cookie al refrescar y al
  cerrar sesión. El backend valida el claim `csrf` del JWT aunque lea la cookie manualmente.
- El access token viaja en `Authorization: Bearer`; no se emite access token en cookie.

## 4. Volumen de imágenes

- Montar un **Volume** de Railway en `/var/lib/unique/uploads`.
- Railway monta volúmenes como `root`. El `docker-entrypoint.sh` crea el directorio si hace falta
  y hace `chown app:app`.
- Supervisor permanece como root porque los pipes de logs de Railway (`/dev/stdout`,
  `/dev/stderr`) pertenecen a root y un proceso no root no puede reabrirlos. Gunicorn y el
  scheduler bajan a `app` (uid 10001) con `gosu` desde `supervisord.conf`; el código de la API
  nunca se ejecuta como root.
- **No configurar `RAILWAY_RUN_UID=0`**: ya no es necesario y anularía el usuario no root de
  los procesos de la API.
- Las imágenes se sirven desde `GET /uploads/{nombre}`, fuera de `/api/v1`. El frontend resuelve
  esa ruta relativa contra el origen de su `API_BASE_URL`.

## 5. Health checks y arranque

| Endpoint | Uso | Comportamiento |
|---|---|---|
| `GET /api/v1/health` | Liveness | `200` sin consultar MySQL |
| `GET /api/v1/health/db` | Readiness | `200` solo si MySQL responde **y** existe `alembic_version` |
| `GET /api/v1/docs` | Documentación | Swagger UI con CSP propia; no debilita la CSP global |
| `GET /api/v1/openapi.json` | Especificación | Contrato HTTP |

Configurar el Healthcheck Path de Railway API como `/api/v1/health/db`. El healthcheck interno
del contenedor también usa ese endpoint y respeta `PORT`.

Supervisor levanta:

1. `scripts/wait_for_db.py` con espera acotada y secretos ofuscados en logs.
2. Gunicorn en `0.0.0.0:${PORT:-8000}`, sin `--reload`.
3. `python -m app.jobs`, con bloqueo MySQL `unique_scheduler`; antes de cada tarea se comprueba
   que la conexión siga siendo la dueña del lock con `ping(reconnect=False)`, se mantiene viva con
   un latido de 60 s y los jobs corren en un único hilo. Si el lock se pierde, APScheduler se
   detiene una sola vez, se libera la conexión y se reintenta en 30 s, sin tormenta de
   `SchedulerNotRunningError`.

## 6. Primer deploy

1. Crear el servicio MySQL en Railway y el servicio API desde `unique_api` en el mismo proyecto.
2. Configurar todas las variables de la sección 2. Verificar que `APP_ENV=production` y que
   `SECRET_KEY`/`JWT_SECRET_KEY` no sean los valores de ejemplo.
3. Montar el volumen en `/var/lib/unique/uploads`.
4. Configurar el **Pre-Deploy Command** de Railway:

```sh
sh scripts/pre_deploy.sh
```

Ese script ejecuta `wait_for_db.py` y `flask db upgrade`. No ejecuta semillas ni crea usuarios.

5. Desplegar. Si `flask db upgrade` falla en la migración de triggers
   (`c4d5e6f7a8b9`), revisar privilegios TRIGGER del usuario de la app y el parámetro
   `log_bin_trust_function_creators` de MySQL en Railway. No omitir la migración ni aplicar
   `downgrade()`.
6. Antes de sembrar datos, hacer backup de la base de datos de Railway. Solo entonces, de forma
   explícita y una sola vez:

```bash
python -m scripts.seed
python -m scripts.create_admin admin
```

`create_admin` pide la contraseña por prompt; no pasar contraseñas en la línea de comandos.
Las semillas no se ejecutan automáticamente en arranques ni deploys posteriores.

7. Verificación mínima:

```bash
curl -i https://<dominio-real-de-la-api>/api/v1/health
curl -i https://<dominio-real-de-la-api>/api/v1/health/db
curl -i https://<dominio-real-de-la-api>/api/v1/docs
```

Después, probar `POST /api/v1/auth/login` desde el frontend real (CORS/cookies/CSRF), cargar el
catálogo y subir una imagen para confirmar que persiste tras reiniciar el servicio API.

## 7. Deploys posteriores

- El Pre-Deploy vuelve a ejecutar `flask db upgrade`; Alembic aplica solo revisiones pendientes.
  La cadena actual termina en `d5e6f7a8b9c0` (ver `flask db current`).
- No ejecutar `flask db downgrade`, `db.drop_all()` ni seeds automáticos en producción.
- Reiniciar la API no borra el volumen de imágenes. Si se recrea el volumen, copiar antes los
  archivos a un destino seguro.
- Si cambia el dominio del frontend, actualizar `CORS_ORIGINS` en la API y `API_BASE_URL` en el
  frontend; ambos deben apuntar al mismo entorno.
- Para escalar a más de una réplica: añadir Redis, definir `RATELIMIT_STORAGE_URI=redis://...` y
  verificar el lock del scheduler. Mantener `WEB_CONCURRENCY=1` mientras se use `memory://`.

## 8. Migraciones

- `upgrade()` no contiene `DROP TABLE`; las operaciones delicadas son vistas y triggers
  (`CREATE OR REPLACE VIEW`, `DROP VIEW IF EXISTS`, `DROP TRIGGER IF EXISTS`) y son reproducibles.
- `downgrade()` sí elimina columnas, restricciones y, en la revisión base, tablas: usarlo solo en
  un entorno descartable.
- Verificar siempre la revisión antes de desplegar:

```bash
flask db current
flask db heads
```

## 9. Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| Arranca `SECRET_KEY debe configurarse...` | `APP_ENV=production` sin secretos | Definir secretos reales y redeploy |
| `CORS_ORIGINS debe usar HTTPS` | Variable con `http://` o `*` | Corregir al origen HTTPS exacto del frontend |
| `/api/v1/health/db` devuelve 503 | MySQL caído o esquema sin migrar | Revisar red privada y ejecutar Pre-Deploy correctamente |
| Login desde el navegador sin sesión | `SameSite`/`Secure`/CORS incorrectos | `None` + `Secure` + `CSRF_PROTECT=true`, y origen exacto |
| `401 CSRF_INVALIDO` al refrescar | Falta `X-CSRF-TOKEN` o cambió la cookie | Confirmar que el frontend envía la cabecera y que no hay scripts de terceros leyendo cookies |
| Error al subir imágenes | Volumen no montado o propiedad incorrecta | Revisar `/var/lib/unique/uploads` y que no se use `RAILWAY_RUN_UID=0` |
| Scheduler duplicado | Múltiples réplicas tras pérdida de conexión | Verificar logs de `unique_scheduler`; mantener una réplica si no se ha probado el lock |
| `SchedulerNotRunningError` o `Bloqueo perdido` repetido | Jobs concurrentes compartiendo la conexión del lock | Usar el scheduler actual (mutex, latido, un solo hilo y apagado protegido) y observar al menos un tick de 15 min |
| Rate limit inconsistente | Múltiples workers/réplicas con `memory://` | Reducir a un worker o configurar Redis |
| Swagger en blanco | CSP global aplicada a `/docs` | Verificar que se usa el código actual con CSP específica para `/docs` |

Este documento no incluye secretos ni dominios definitivos; sustituir los marcadores por los
valores reales del proyecto Railway.
