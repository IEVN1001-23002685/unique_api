# UNIQUE API

Backend REST de UNIQUE (Flask + MySQL), construido según `UNIQUE_documento_integral_v3.txt`.

**Estado actual: Fase 1 en verificación.** La Fase 0 (infraestructura) quedó verificada. La Fase 1
ya creó el modelo completo, migraciones, vistas, semillas, autenticación JWT y administración
básica; se ejecutarán las pruebas antes de declararla terminada.

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

`flask db upgrade` aplica las revisiones de Fase 1 (modelo completo y vistas). Después ejecute
las semillas, que son idempotentes:

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
