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
  `csrf_refresh_token`. El frontend envía `X-CSRF-TOKEN` al refrescar y al cerrar sesión. El
  backend valida el claim `csrf` del JWT aunque lea la cookie manualmente. Como los dominios son
  distintos, el frontend obtiene ese token de `GET /api/v1/auth/csrf` (CORS al origen exacto) y lo
  guarda solo en memoria; si la respuesta indica `con_refresco: false`, omite `/auth/refrescar`.
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

> `python -m scripts.seed` **no publica productos**. Es idempotente y solo inserta filas que
> faltan: si ya existen, termina con `Registros insertados: {}`. Los productos y variantes se
> crean deliberadamente con `activo = 0`, `precio_venta = 0` y `existencia = 0`; las recetas
> quedan en `BORRADOR` y no se crean imágenes. Por eso `/api/v1/catalogo` sigue devolviendo `[]`
> después de sembrar. Las variables `ADMIN_EMAIL`/`ADMIN_PASSWORD` y
> `OPERATIVO_EMAIL`/`OPERATIVO_PASSWORD` deben existir en el **entorno del servicio en Railway**;
> un `.env` local no se carga dentro del contenedor.

Para diagnosticar por qué un producto no aparece:

```sql
SELECT p.id, p.nombre, p.activo, p.eliminado_en, p.precio_venta,
       COUNT(v.id) AS variantes, SUM(v.activa = 1) AS variantes_activas
FROM producto p
LEFT JOIN variante_producto v ON v.producto_id = p.id
GROUP BY p.id
ORDER BY p.id;
```

`/api/v1/catalogo` exige `producto.activo = 1`, `eliminado_en IS NULL` y **al menos una**
`variante_producto.activa = 1`. Si falta la segunda condición, el producto se omite aunque esté
marcado como activo y tenga precio. `/api/v1/catalogo?disponibles=true` además exige
`stock_variante.existencia > stock_variante.reservado`.

Para publicar borradores que **ya existen en MySQL**, hacer backup y ejecutar desde el shell del
servicio API de Railway:

```bash
# Informe: revisa precio, imágenes, variantes y recetas reales. No escribe nada.
python -m scripts.publicar_semilla

# Aplicar solo los candidatos que pasaron todas las validaciones.
python -m scripts.publicar_semilla --aplicar
```

El script no crea productos, no inventa precios, no rellena URLs y no publica nada que tenga
precio 0, imágenes ausentes o de prueba, sin variantes o sin receta `VIGENTE`. Cada producto
publicado queda registrado en bitácora con la acción `PUBLICACION_SEMILLA`. Para limitar la revisión
a un producto o activar una receta BORRADOR ya revisada:

```bash
python -m scripts.publicar_semilla --producto-id 818
python -m scripts.publicar_semilla --producto-id 818 --activar-receta 12 --aplicar
```

Si un producto aparece en `omitidos`, corregir primero los datos reales en MySQL o subir la imagen
con la API de administración; no relajar las validaciones del script. Para activar un producto
nuevo desde cero, usar la API de administración: precio real, imagen real, recetas `VIGENTE` y
`POST /api/v1/productos/<id>/activar`.

### Migración de los productos reales desde la BD local

Si el seed de Railway dejó los productos vacíos (`precio_venta = 0`, sin imágenes y con recetas en
`BORRADOR`), pero la BD local sí contiene los productos reales, usar este flujo. No copia IDs:
empareja por SKU (`SD`, `PL`, `PN`, `GO`, `BO`).

1. En la máquina local, exportar los datos reales. El archivo generado es
   `datos_reales.json` y no contiene secretos:

   ```bash
   python -m scripts.exportar_datos_reales datos_reales.json
   ```

   Debe ejecutarse donde esté disponible el volumen `unique_uploads_data` montado en
   `/var/lib/unique/uploads`; el script verifica que cada imagen real exista.

2. Crear en Railway la cuenta ADMIN si aún no existe:

   ```bash
   python -m scripts.create_admin admin
   ```

3. Subir las imágenes reales a Railway por la API de administración. Esto genera
   `datos_reales_railway.json` con las URLs reales devueltas por Railway:

   ```bash
   export API_BASE_URL='https://<dominio-real-de-la-api>/api/v1'
   export ADMIN_EMAIL='<correo-admin>'
   read -rs ADMIN_PASSWORD; export ADMIN_PASSWORD

   python -m scripts.subir_imagenes_reales \
     datos_reales.json \
     --uploads /var/lib/unique/uploads \
     --salida datos_reales_railway.json
   ```

4. Copiar `datos_reales_railway.json` al contenedor de Railway y, desde el shell del servicio
   API, revisar primero:

   ```bash
   python -m scripts.importar_datos_reales datos_reales_railway.json
   ```

   El informe muestra SKU, precio, número de variantes, imágenes y recetas. Solo después de
   revisarlo:

   ```bash
   python -m scripts.importar_datos_reales datos_reales_railway.json --aplicar
   ```

El importador aplica todo en una sola transacción, activa las recetas validadas, publica los
productos y deja constancia en bitácora con `IMPORTACION_DATOS_REALES`. Si falta algún archivo de
imagen en el volumen de Railway, se detiene antes de escribir. Para generar solo un informe sin
verificar archivos, usar `--no-verificar-archivos`.

> Estos scripts deben existir en la imagen desplegada en Railway. Si el contenedor aún no los
> incluye, hay que desplegar primero los cambios del repositorio backend; no basta con copiar el
> JSON.

### Corrección de la galería en una base ya sembrada

`importar_datos_reales.py` empareja por URL y **no reordena** las imágenes que ya existen. Para
que la variante blanca de la bolsa (`BO-UN-BL`) sea la imagen principal sin duplicar filas:

1. La imagen real blanca viaja en `seed_uploads/` como
   `84160d6b830aae8b9bc735679c911aae.png`; `docker-entrypoint.sh` la copia al volumen si falta.
2. `datos_reales.json` y `datos_reales_railway.json` declaran esa URL con `color: BL` y `orden: 0`;
   la negra pasa a `orden: 1` y la gris a `orden: 2`.
3. Tras desplegar la imagen, desde el shell de la API:

   ```bash
   python -m scripts.sincronizar_imagenes_reales datos_reales_railway.json --sku BO
   python -m scripts.sincronizar_imagenes_reales datos_reales_railway.json --sku BO --aplicar
   ```

El script crea la fila que falta, corrige `color_id`/`orden` de las existentes y no elimina nada.
Es idempotente: una segunda ejecución informa 0 creadas y 0 actualizadas. Sin `--aplicar` solo
muestra el informe. Para todas las imágenes del paquete, omitir `--sku BO`.

### Actualización de una base ya desplegada

Cuando la base de Railway ya tiene datos operativos pero le faltan claves de `configuracion`
(M22 devuelve `[]`) o tiene la galería desordenada, ejecutar el script que agrupa ambas
correcciones en una sola transacción:

```bash
python -m scripts.actualizar_base_existente datos_reales_railway.json --sku BO
python -m scripts.actualizar_base_existente datos_reales_railway.json --sku BO --aplicar
```

El script usa el seed de `configuracion` solo para insertar las claves ausentes; **no sobrescribe
los valores existentes**. Después alinea las imágenes del SKU indicado. Para procesar todos los
productos del archivo, omitir `--sku BO`. Sin `--aplicar` solo imprime el informe.

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
- Las 15 imágenes reales publicadas también viajan dentro de la imagen en `seed_uploads/`.
  `docker-entrypoint.sh` las copia a `UPLOAD_FOLDER` **solo si faltan**, así que un redeploy
  vuelve a servirlas aunque Railway no tenga un Volume configurado. No sobrescriben imágenes
  subidas después desde el panel de administración.
- Para validarlas después de cada deploy:

```bash
python -m scripts.verificar_imagenes \
  --api-base-url https://<dominio-real-de-la-api>/api/v1
```

  El informe debe mostrar `correctas` igual a `total` y `http: 200` en cada imagen.
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
| Catálogo o carrito sin imagen | `/uploads/{nombre}` devuelve 404 | Ejecutar `scripts.verificar_imagenes`; confirmar que `seed_uploads/` esté en la imagen y que el entrypoint copie los archivos al arrancar |
| Scheduler duplicado | Múltiples réplicas tras pérdida de conexión | Verificar logs de `unique_scheduler`; mantener una réplica si no se ha probado el lock |
| `SchedulerNotRunningError` o `Bloqueo perdido` repetido | Jobs concurrentes compartiendo la conexión del lock | Usar el scheduler actual (mutex, latido, un solo hilo y apagado protegido) y observar al menos un tick de 15 min |
| Rate limit inconsistente | Múltiples workers/réplicas con `memory://` | Reducir a un worker o configurar Redis |
| Swagger en blanco | CSP global aplicada a `/docs` | Verificar que se usa el código actual con CSP específica para `/docs` |

Este documento no incluye secretos ni dominios definitivos; sustituir los marcadores por los
valores reales del proyecto Railway.
