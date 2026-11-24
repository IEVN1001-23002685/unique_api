# Despliegue con Docker Compose

## Requisitos previos

Docker Engine con daemon activo y Docker Compose v2. Verificar:

```bash
docker version --format '{{.Server.Version}}'
docker compose version
```

Si el primer comando falla con `cannot connect to the Docker daemon`, inicie Docker Desktop.

## Instalación limpia

```bash
cp .env.example .env
# editar .env: secretos, puertos y CORS_ORIGINS
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f api
```

Comprobaciones:

```bash
docker compose exec api python scripts/wait_for_db.py
docker compose exec api flask db upgrade
docker compose exec api python -m scripts.seed
docker compose exec api python -m pytest -q
curl.exe -i http://localhost:8001/api/v1/health
curl.exe -i http://localhost:8001/api/v1/health/db
```

phpMyAdmin: `http://localhost:8081` (valor configurado en este entorno; `PHPMYADMIN_PORT`).
El servidor se llama `mysql` y las credenciales son `MYSQL_USER` / `MYSQL_PASSWORD` de `.env`.

## Imágenes y versiones

| Servicio | Imagen | Observaciones |
|---|---|---|
| `api` | `python:3.11-slim` | Dockerfile propio, Gunicorn, usuario `app` (no root) |
| `mysql` | `mysql:8.4.3` | Exacta, volumen `mysql_data` |
| `phpmyadmin` | `phpmyadmin:5.2.3` | Exacta, `PMA_HOST=mysql` |

## Persistencia

- `mysql_data`: `/var/lib/mysql`.
- `uploads_data`: `/var/lib/unique/uploads`.

Ambos son volúmenes nombrados. `docker compose down` los conserva. Nunca usar
`docker compose down -v` sin autorización explícita.

## Variables de entorno

Las variables mínimas están en `.env.example`. `SECRET_KEY`, `JWT_SECRET_KEY`,
`MYSQL_PASSWORD` y `MYSQL_ROOT_PASSWORD` deben cambiarse antes de desplegar. La API usa
`MYSQL_USER`, nunca `root`. `DEBUG` se fuerza a `false` en producción.

Las cuentas iniciales se crean con `ADMIN_EMAIL`/`ADMIN_PASSWORD` y
`OPERATIVO_EMAIL`/`OPERATIVO_PASSWORD`; también pueden crearse con
`python -m scripts.create_admin admin|operativo`. No existen contraseñas fijas.

`WEB_CONCURRENCY=1` mantiene el contador de Flask-Limiter en un solo proceso. Si se aumenta,
defina `RATELIMIT_STORAGE_URI` con un almacén compartido; véase `decisiones-tecnicas.md`.

Puertos configurables: `API_HOST_PORT`, `MYSQL_HOST_PORT` y `PHPMYADMIN_PORT`.
En este entorno se usan **8001, 3307 y 8081** porque 8000, 3306 y 8080 están ocupados
por contenedores de otro proyecto (`hospital_dr`, `mysql_db` y `phpmyadmin`).
Los puertos internos no cambian: API 8000, MySQL 3306 y phpMyAdmin 80.
Para detectar conflictos en Windows:

```powershell
Get-NetTCPConnection -LocalPort 8001,3307,8081 -ErrorAction SilentlyContinue
```

## Reconstrucción y diagnóstico

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
docker compose ps
docker compose logs mysql
docker compose logs api
```

El código se copia dentro de la imagen (no hay bind mount), por lo que **cualquier cambio
en `app/`, `scripts/` o `migrations/` requiere `docker compose build`** antes de
`docker compose up -d`.

Si `api` no logra conectar con MySQL, ejecutar:

```bash
docker compose exec api python scripts/diagnose_db.py
```

El comando muestra la URL con la contraseña oculta y el error real sin secretos.

El `healthcheck` de `mysql` usa `mysqladmin ping` con `MYSQL_ROOT_PASSWORD` de forma
interna. El de `api` consulta `/api/v1/health`. `depends_on` con condición
`service_healthy` evita iniciar la API o phpMyAdmin antes de que MySQL acepte conexiones.

## Seguridad

- Sin secretos en el repositorio; `.env` está en `.gitignore` y `.dockerignore`.
- Cabeceras añadidas a todas las respuestas: `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy` y `Content-Security-Policy`.
- CORS restringido a `CORS_ORIGINS`.
- No se exponen puertos internos innecesarios más allá de los tres servicios documentados.
