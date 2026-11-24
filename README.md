# UNIQUE API

Backend REST de UNIQUE (Flask + MySQL), construido según `UNIQUE_documento_integral_v3.txt`.

**Estado actual: Fase 0 (infraestructura).** No hay modelos de negocio, migraciones de tablas ni
endpoints funcionales todavía. No se avanzará a los módulos M01–M22 hasta verificar los tres
servicios Docker, la salud de MySQL y la conexión desde Flask.

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
| `api` | `python:3.11-slim` (propia) | 8001 (`API_HOST_PORT`; interno 8000) | Flask + Gunicorn |
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

El contenedor `api` espera a MySQL con `scripts/wait_for_db.py` antes de iniciar Gunicorn.
El `healthcheck` de Compose usa `/api/v1/health`.

## Migraciones, semillas y pruebas

```bash
docker compose exec api python scripts/wait_for_db.py
docker compose exec api flask db upgrade
docker compose exec api python -m pytest -q
```

Si la API no conecta con MySQL: `docker compose exec api python scripts/diagnose_db.py`.
Cualquier cambio en código requiere `docker compose build` antes de `up -d`.

`flask db upgrade` no crea tablas porque en esta fase aún no hay revisiones. Las semillas
(`scripts/seed.py`) y el administrador inicial (`scripts/create_admin.py`) se crean en la Fase 1.

## Detener y reiniciar

```bash
docker compose down
docker compose up -d
```

Los datos de MySQL y los archivos subidos viven en volúmenes nombrados y sobreviven a `down`.
**Nunca ejecute `docker compose down -v` sin autorización explícita**: elimina los volúmenes.

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

## Detalles

- Arquitectura: `docs/arquitectura.md`
- Modelo de datos: `docs/modelo-datos.md`
- Contrato HTTP: `docs/endpoints.md`
- Decisiones técnicas: `docs/decisiones-tecnicas.md`
- Despliegue: `docs/despliegue-docker.md`
