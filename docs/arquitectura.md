# Arquitectura

## Contenedores

- `api`: `python:3.11-slim`, usuario no root (`uid 10001`), Supervisor con Gunicorn sin
  `--reload` y un proceso `scheduler` único. Contiene todo el runtime Python: aplicación,
  migraciones, tareas programadas y scripts.
- `mysql`: `mysql:8.4.3`, volumen nombrado `mysql_data`.
- `phpmyadmin`: `phpmyadmin:5.2.3`, conecta al servicio `mysql` por nombre de servicio.

No se instala MySQL ni phpMyAdmin dentro del contenedor `api`. La API conecta a MySQL
mediante `mysql` como host, nunca `localhost`.

## Capas de la aplicación

```text
blueprints/  -> rutas HTTP: validan transporte, llaman a servicios, serializan
services/    -> reglas de negocio y transacciones (Fase 1 en adelante)
models/      -> tablas, relaciones, restricciones e índices
schemas/     -> validación y serialización con Marshmallow
security/    -> JWT, hashes, roles y propietario del recurso
jobs/        -> APScheduler, invoca servicios sin duplicar lógica
utils/       -> folios, SKU, conversiones y errores compartidos
```

Las rutas no contienen consultas complejas ni cálculos. El documento lo define como
"regla de oro" en la sección 9.1.

## Arranque

1. Compose espera a que `mysql` esté `healthy`.
2. El contenedor `api` ejecuta `scripts/wait_for_db.py` con reintentos y backoff acotado.
3. Se inicia Supervisor, que levanta Gunicorn enlazado a `APP_HOST:APP_PORT` con
   `WEB_CONCURRENCY` workers y el proceso `scheduler` (`python -m app.jobs`).
4. El scheduler toma `GET_LOCK('unique_scheduler', 5)` en MySQL antes de iniciar APScheduler.
5. `/api/v1/health` responde sin tocar MySQL; `/api/v1/health/db` usa `SELECT 1`.

## Configuración

`app/config.py` lee únicamente variables de entorno. `DEBUG` se fuerza a `False` cuando
`APP_ENV=production`. `create_app()` inicializa SQLAlchemy, Migrate, JWT, CORS y Limiter,
registra el contrato de errores, los blueprints y las cabeceras de seguridad.

## Convención de errores

Toda respuesta de error usa:

```json
{ "codigo": "NO_ENCONTRADO", "mensaje": "Recurso no encontrado", "detalle": [] }
```

Los errores no controlados se registran en el log del servidor y se devuelven al cliente
como `ERROR_INTERNO`, sin trazas ni consultas SQL.
