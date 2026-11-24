# Decisiones técnicas

Registro de decisiones que no están especificadas, que difieren del documento o que requieren
confirmación del equipo.

| Tema | Decisión | Estado |
|---|---|---|
| Versión de MySQL | El documento menciona MySQL 8.0, pero `AGENTS.md` exige la imagen exacta `mysql:8.4.3`. Prevalece `8.4.3`. | Definido |
| Etiqueta de phpMyAdmin | `AGENTS.md` exige la imagen exacta `phpmyadmin:5.2.3`. No se confirmó su disponibilidad en Docker Hub porque el daemon y la consulta externa no estuvieron disponibles. No se sustituye la etiqueta sin autorización; verificar durante `docker compose build`. | Requiere verificación |
| Conflictos de puertos en el host | Los puertos 8000, 3306 y 8080 están ocupados por contenedores de otro proyecto (`hospital_dr`, `mysql_db`, `phpmyadmin`). Se configuraron `API_HOST_PORT=8001`, `MYSQL_HOST_PORT=3307` y `PHPMYADMIN_PORT=8081` en `.env` y en `.env.example`. Los puertos internos y `DATABASE_URL` no cambian; `MYSQL_PORT` sigue siendo 3306. | Resuelto en este entorno |
| Configuración de Alembic | Flask-Migrate requiere `migrations/alembic.ini` además de `env.py` y `script.py.mako`. Se añadió con las secciones de logging y `script_location = %(here)s`. | Corregido |
| Autenticación de MySQL | PyMySQL necesita `cryptography` para `caching_sha2_password`, el plugin por defecto de MySQL 8.4. Se añadió `cryptography==43.0.3` a `requirements.txt`. | Corregido |
| Puerto y prefijo de la API | El frontend Angular apunta a `http://127.0.0.1:5000/api`; el contrato canónico es `/api/v1` en el puerto `8000`. No se duplican rutas en la API. La actualización del frontend se coordina en su repositorio. | Pendiente de coordinar |
| Tokens en el frontend | `auth-session.service.ts` guarda el access token en `localStorage`, lo cual contradice la regla de seguridad del documento. El backend no debe usar ese valor como fuente de autorización; se válida únicamente el JWT recibido en `Authorization: Bearer`. | Pendiente de corregir en el frontend |
| Idempotencia | El documento exige persistencia de `Idempotency-Key` pero no lista una tabla para ella. Se añadirá una tabla de infraestructura `idempotencia_operacion` (clave, alcance, hash de petición, estado y respuesta), separada de las 64 tablas funcionales. | Definido; confirmar nombre |
| Rate limit entre workers | Flask-Limiter usa `memory://` en Fase 0. Con varios workers, cada proceso tendrá su propio contador. Antes de producción debe migrarse a un almacén compartido (por ejemplo SQLAlchemy sobre MySQL, sin añadir un cuarto servicio). | Pendiente para Fase 1/producción |
| CSRF de refresh cookie | `JWT_COOKIE_CSRF_PROTECT` queda activo por defecto. El frontend deberá enviar el token CSRF de doble envío al refrescar. Configurable por entorno. | Pendiente de integrar |
| Código del readiness | `/api/v1/health/db` responde `503` cuando MySQL falla. El código no está listado en el contrato general, pero se justifica por ser un endpoint de infraestructura. | Definido |
| Valores propuestos del documento | `dias_devolucion`, `max_intentos_entrega`, `dias_produccion_estandar`, `max_piezas_por_linea`, `saldo_inicial_cuenta_simulada` y tarifa «Local León» se cargarán como configuración editable y se marcarán como pendientes de confirmar. | Pendiente de confirmar |
| Normalización de rutas ambiguas | Si una ruta del documento es ambigua por su representación en texto, se conserva la intención funcional y se registra aquí la URL normalizada. No se duplican rutas que colisionen. | Mecanismo definido |

## Convención de nombres

Los mensajes de error usan texto en español sin acentos en los códigos (`METODO_NO_PERMITIDO`),
mientras que `mensaje` puede contener acentos. Los nombres de campo de base de datos se
mantienen iguales en las respuestas, según la sección 10 del documento.
