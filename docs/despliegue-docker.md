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
docker compose exec api python -m pytest -q
curl -i http://localhost:8000/api/v1/health
curl -i http://localhost:8000/api/v1/health/db
```

phpMyAdmin: `http://localhost:8080`. El servidor se llama `mysql` y las credenciales son
`MYSQL_USER` / `MYSQL_PASSWORD` de `.env`.

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

Puertos configurables: `API_HOST_PORT` (8000), `MYSQL_HOST_PORT` (3306),
`PHPMYADMIN_PORT` (8080). `MYSQL_HOST_PORT` puede cambiarse si hay conflicto local.

## Reconstrucción y diagnóstico

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
docker compose ps
docker compose logs mysql
docker compose logs api
```

El `healthcheck` de `mysql` usa `mysqladmin ping` con `MYSQL_ROOT_PASSWORD` de forma
interna. El de `api` consulta `/api/v1/health`. `depends_on` con condición
`service_healthy` evita iniciar la API o phpMyAdmin antes de que MySQL acepte conexiones.

## Seguridad

- Sin secretos en el repositorio; `.env` está en `.gitignore` y `.dockerignore`.
- Cabeceras añadidas a todas las respuestas: `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy` y `Content-Security-Policy`.
- CORS restringido a `CORS_ORIGINS`.
- No se exponen puertos internos innecesarios más allá de los tres servicios documentados.
