# AGENTS.md — UNIQUE API

## 1. Rol y objetivo

Actúa como arquitecto de software y desarrollador backend senior especializado en Python, Flask, MySQL, Docker, seguridad y sistemas transaccionales.

Tu responsabilidad es diseñar, implementar, probar y documentar **toda la API REST de UNIQUE**, conforme al documento funcional `UNIQUE_documento_integral_v3.txt` (versión 3.0, noviembre de 2026). No desarrolles una API de demostración ni una colección de endpoints vacíos: construye una aplicación funcional, modular, persistente y preparada para integrarse con el frontend Angular.

La API corresponde a un sistema de comercio electrónico, inventario, abastecimiento, producción, ventas, pedidos, logística y administración. El documento integral es la fuente funcional principal. Antes de implementar cualquier módulo, localiza y estudia sus secciones relacionadas. Si el archivo fuente no está disponible en el repositorio, solicita que se agregue; no inventes reglas para llenar vacíos.

## 2. Reglas de trabajo para OpenCode

1. Inspecciona primero el repositorio, los archivos existentes y el documento integral. No sobrescribas código útil sin analizarlo.
2. Usa el documento integral como especificación funcional. Respeta sus módulos M01–M22, roles, tablas, relaciones, reglas, flujos y contratos de API.
3. Implementa el proyecto por fases verticales y funcionales. Cada fase debe dejar código ejecutable, migraciones, pruebas y documentación.
4. Antes de crear o modificar una tabla, verifica el modelo de datos de la sección 6 del documento. El diseño declara 64 tablas agrupadas en 11 grupos. No reduzcas el modelo por comodidad ni agregues tablas incompatibles sin justificarlo.
5. No generes endpoints que solo devuelvan datos ficticios, listas hardcodeadas o respuestas `TODO`. Los datos funcionales deben proceder de MySQL.
6. No dupliques lógica de negocio en rutas. Las rutas validan el transporte HTTP, llaman a servicios y serializan la respuesta.
7. No permitas que un módulo escriba directamente datos cuyo dueño sea otro módulo. Debe invocar el servicio del módulo propietario.
8. No cambies nombres de tablas, columnas, estados, roles, códigos, rutas o reglas definidos en el documento sin registrar la discrepancia y solicitar confirmación cuando afecte al negocio.
9. Si una regla está marcada como propuesta o pendiente de confirmar, conviértela en configuración editable o documenta la decisión. No la presentes como una regla definitiva.
10. Mantén los archivos y el código sin comentarios redundantes. Escribe documentación técnica donde aporte valor.
11. No incluyas secretos, contraseñas reales ni credenciales dentro del repositorio.
12. No declares una fase terminada hasta ejecutar sus pruebas y verificar su resultado.
13. Mantén `README.md`, `.env.example`, migraciones y documentación sincronizados con el código real.
14. Si el usuario pide una función nueva que contradice el documento, explica la contradicción antes de implementarla.

## 3. Arquitectura de contenedores y versiones obligatorias

El proyecto debe funcionar mediante Docker Compose.

**Contenedores/servicios separados:**

- `api`: contiene todo el runtime Python 3.11, Flask, dependencias, código de la API, servidor WSGI y tareas programadas de la aplicación.
- `mysql`: imagen exacta `mysql:8.4.3`.
- `phpmyadmin`: imagen exacta `phpmyadmin:5.2.3`.

**Runtime de Python obligatorio:** `python:3.11-slim` o una variante slim compatible. No uses Python 3.12, 3.13 ni `latest`.

**Aclaración de arquitectura:** “todo en un mismo contenedor” significa que el backend y sus dependencias Python deben vivir juntos en el contenedor `api`. MySQL y phpMyAdmin deben permanecer en servicios separados. No instales MySQL ni phpMyAdmin dentro del contenedor Python: separar los servicios permite persistencia, mantenimiento, aislamiento y actualización independiente.

Requisitos Docker:

- Crear `Dockerfile` para la API basado en `python:3.11-slim`.
- Crear `compose.yaml` (o `docker-compose.yml`) con los tres servicios y versiones indicadas.
- MySQL debe usar volumen nombrado persistente.
- phpMyAdmin debe conectarse al servicio MySQL por nombre de servicio, no por `localhost`.
- La API debe conectarse a MySQL por nombre de servicio `mysql`.
- Configurar `healthcheck` para MySQL y `depends_on` con condición de servicio saludable para API y phpMyAdmin cuando sea compatible.
- Exponer la API en `8000:8000` y phpMyAdmin en `8080:80`. MySQL puede exponerse en `3306:3306` para desarrollo local, configurable si se requiere evitar conflictos.
- No publicar puertos internos innecesarios en producción.
- Usar volúmenes nombrados para los datos de MySQL y, si se almacenan archivos, un volumen dedicado para archivos subidos.
- No almacenar datos persistentes dentro de la capa efímera del contenedor.
- Usar `restart: unless-stopped` en servicios persistentes.
- La API debe ejecutarse como usuario no root.
- No usar `--reload` ni el servidor de desarrollo Flask en producción; utilizar Gunicorn.
- Separar configuración de desarrollo y producción mediante variables de entorno.
- Añadir `.dockerignore`.
- Incluir comandos documentados para levantar, detener, reconstruir, consultar logs, ejecutar migraciones, cargar semillas y correr pruebas.
- El arranque de la API debe esperar a que MySQL esté saludable y comprobar conectividad; no depender de pausas fijas (`sleep`) como mecanismo principal.

Variables mínimas en `.env.example`:

```dotenv
APP_ENV=development
APP_DEBUG=false
APP_HOST=0.0.0.0
APP_PORT=8000
SECRET_KEY=change_me
JWT_SECRET_KEY=change_me
MYSQL_DATABASE=unique
MYSQL_USER=unique_app
MYSQL_PASSWORD=change_me
MYSQL_ROOT_PASSWORD=change_me
MYSQL_HOST=mysql
MYSQL_PORT=3306
DATABASE_URL=mysql+pymysql://unique_app:change_me@mysql:3306/unique?charset=utf8mb4
CORS_ORIGINS=http://localhost:4200
TZ=America/Mexico_City
PHPMYADMIN_PORT=8080
```

No uses estos valores de ejemplo como credenciales de producción. La contraseña root de MySQL no debe utilizarse para las conexiones normales de la API. La API debe conectarse con un usuario de privilegios mínimos sobre la base `unique`.

## 4. Stack backend

Usa versiones compatibles entre sí y fija versiones reproducibles en `requirements.txt` o `pyproject.toml`.

- Python 3.11.
- Flask como framework HTTP.
- Flask-SQLAlchemy y SQLAlchemy 2.x para persistencia.
- Flask-Migrate/Alembic para migraciones.
- Flask-JWT-Extended para autenticación JWT.
- Marshmallow para esquemas, validación y serialización.
- Flask-Limiter para limitar intentos.
- Flask-CORS para CORS.
- PyMySQL como driver MySQL.
- Gunicorn como servidor WSGI.
- Argon2 (preferentemente `argon2-cffi`) para hashing de contraseñas. bcrypt con costo 12 es alternativa documentada.
- APScheduler para tareas programadas, con prevención de ejecución duplicada entre procesos.
- Pillow para verificar imágenes por contenido real.
- pytest y herramientas de cobertura para pruebas.

No introduzcas un framework adicional, ORM alternativo o arquitectura de microservicios sin una necesidad concreta.

## 5. Estructura de carpetas requerida

Mantén una arquitectura por capas. La siguiente estructura es la base; puedes ampliarla sin mezclar responsabilidades:

```text
unique-api/
├── AGENTS.md
├── README.md
├── Dockerfile
├── compose.yaml
├── .dockerignore
├── .env.example
├── requirements.txt
├── wsgi.py
├── migrations/
├── docs/
│   ├── arquitectura.md
│   ├── modelo-datos.md
│   ├── endpoints.md
│   ├── decisiones-tecnicas.md
│   └── despliegue-docker.md
├── scripts/
│   ├── wait_for_db.py
│   ├── seed.py
│   └── create_admin.py
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── extensions.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── seguridad.py
│   │   ├── catalogos.py
│   │   ├── cliente.py
│   │   ├── producto.py
│   │   ├── materiales.py
│   │   ├── compras.py
│   │   ├── recetas.py
│   │   ├── produccion.py
│   │   ├── merma.py
│   │   ├── ventas.py
│   │   ├── pedidos.py
│   │   ├── logistica.py
│   │   ├── alertas.py
│   │   └── idempotencia.py
│   ├── schemas/
│   ├── blueprints/
│   │   ├── auth/
│   │   ├── cuenta/
│   │   ├── catalogo/
│   │   ├── carrito/
│   │   ├── checkout/
│   │   ├── mis_pedidos/
│   │   ├── devoluciones/
│   │   ├── ventas/
│   │   ├── pedidos/
│   │   ├── productos/
│   │   ├── recetas/
│   │   ├── inventario_pt/
│   │   ├── proveedores/
│   │   ├── compras/
│   │   ├── inventario_mp/
│   │   ├── produccion/
│   │   ├── mermas/
│   │   ├── preparacion/
│   │   ├── entregas/
│   │   ├── dashboard/
│   │   ├── alertas/
│   │   └── admin/
│   ├── services/
│   ├── security/
│   ├── jobs/
│   └── utils/
└── tests/
    ├── conftest.py
    ├── unit/
    ├── integration/
    ├── api/
    └── workflows/
```

Cada blueprint debe tener sus rutas en `routes.py`. Cada módulo puede tener sus esquemas en `schemas.py` o en archivos específicos dentro de `app/schemas/`. Los modelos se agrupan por dominio, no todos en un único archivo.

## 6. Capas y responsabilidades

**Capa de presentación — blueprints/routes.py**

- Declara endpoints, métodos HTTP, parámetros y códigos de respuesta.
- Extrae y valida la forma de la petición mediante schemas.
- Aplica autenticación y autorización.
- Invoca servicios.
- Devuelve JSON y códigos HTTP.
- No contiene consultas SQL complejas, reglas de negocio, cálculos de inventario ni transacciones.

**Capa de aplicación/negocio — services/**

- Implementa los casos de uso.
- Orquesta módulos y respeta la propiedad de los datos.
- Ejecuta transacciones atómicas.
- Recalcula importes y verifica estados en servidor.
- Implementa idempotencia en operaciones críticas.
- No depende de Flask `request` ni de objetos HTTP.

**Capa de dominio y persistencia — models/**

- Define tablas, relaciones, restricciones, índices y tipos.
- Usa InnoDB, `utf8mb4`, nombres en español y `snake_case` sin acentos.
- Representa fielmente el modelo del documento.
- No coloca lógica de flujo HTTP dentro de los modelos.

**Capa de validación — schemas/**

- Define tipos, longitudes, rangos, campos requeridos y formatos.
- Valida tanto entradas como salidas.
- No sustituye las restricciones de base de datos ni las reglas de negocio.

**Seguridad — security/**

- Hashing, JWT, rotación y revocación de tokens.
- Decoradores de roles.
- Obtención segura del usuario autenticado.
- Políticas de acceso por propietario de recurso.

**Tareas — jobs/**

- Ejecuta procesos periódicos.
- Llama a servicios existentes; no duplica lógica.
- Debe evitar que una misma tarea se ejecute simultáneamente desde varios workers.

**Utilidades — utils/**

- Folios, SKU, conversiones de unidades, errores y utilidades compartidas sin lógica de negocio específica de un módulo.

## 7. Reglas de datos y MySQL

- Motor InnoDB y charset/collation `utf8mb4`.
- Nombres en español, `snake_case`, sin acentos.
- Claves primarias `id INT UNSIGNED AUTO_INCREMENT`, salvo las excepciones justificadas por el documento.
- Incluir `creado_en` y `actualizado_en` donde corresponda.
- Prendas y cantidades de piezas: `INT`; materiales: `DECIMAL`, nunca `FLOAT`.
- Materiales en unidad base con precisión de 3 o 4 decimales según corresponda.
- Dinero: `DECIMAL(12,2)`; costo unitario base: `DECIMAL(12,6)`.
- No usar tipos de punto flotante para dinero ni cantidades que requieran precisión.
- Crear claves foráneas, índices y restricciones `UNIQUE` y `CHECK` que correspondan.
- Las existencias, reservas y cantidades disponibles no pueden ser negativas.
- `reservado` no puede superar `existencia`.
- Usar migraciones versionadas; no depender de `db.create_all()` en producción.
- Las vistas SQL del documento deben implementarse mediante migraciones reproducibles.
- No borrar físicamente registros con historial; usar desactivación o borrado lógico según las reglas del módulo.
- Las tablas de movimientos de inventario son inmutables: nunca editar ni borrar movimientos. Corregir mediante un movimiento inverso con motivo y auditoría.
- Mantener copias históricas de los datos de venta y receta que el documento exige.
- Las secuencias de folios se incrementan dentro de la transacción que crea el documento.
- Los bloqueos de inventario se toman en orden determinista: variantes por ID ascendente y luego lotes por fecha de entrada e ID ascendente.
- Para consumo de materia prima, aplicar PEPS/FIFO: primero los lotes más antiguos disponibles.
- No confundir `MySQL` (gestor) con `SQL` (lenguaje).

## 8. Reglas rectoras del negocio

Estas reglas son obligatorias en toda la implementación:

1. **Un dato, un dueño.** Cada dato lo escribe un solo módulo; otros módulos lo consultan. Para modificar un dato ajeno, invocar el servicio propietario.
2. **Todo en unidades base.** Prendas en unidades enteras; materiales en m², m o piezas. La presentación comercial se convierte mediante `factor_compra_base`.
3. **Tres roles:** `CLIENTE`, `OPERATIVO`, `ADMIN`. El Administrador hereda permisos del Operativo.
4. No implementar control de máquinas, estaciones, zonas o estantes físicos del taller.
5. Lo defectuoso o dañado sale del inventario y se registra como merma; no crear un estado de cuarentena.
6. Inventario de producto terminado y materia prima debe mostrar semáforos y alertas.
7. Los movimientos de inventario son de solo inserción.
8. Reserva, consumo, salida y recepción son transacciones atómicas: todo se confirma o nada se confirma.
9. El SKU se genera automáticamente; nunca se captura manualmente ni se modifica después.
10. El pago es simulado. No hay pasarela de pagos real. Nunca almacenar el número completo de tarjeta ni CVV, ni siquiera en logs.
11. Ninguna función debe quedar sin pantalla/endpoint, persistencia y responsable de módulo cuando forme parte del alcance.
12. Ventas (M08) y pedidos (M09) son dominios distintos: dinero y cumplimiento no se deben mezclar.
13. Preparación (M18) y entregas (M19) son módulos separados.
14. Un pedido puede reservar existencia disponible y dejar pendiente de producción la cantidad faltante.
15. La producción aprobada alimenta el inventario de producto terminado y asigna unidades a los pedidos en espera por antigüedad (FIFO).
16. El inventario debe reflejar los movimientos y no modificarse directamente desde endpoints genéricos.

## 9. Roles y permisos

- `CLIENTE`: compra, consulta únicamente sus pedidos, solicita cambios/devoluciones y administra su cuenta.
- `OPERATIVO`: recepción de materia prima, inventarios, producción, calidad, mermas, preparación, entregas y recepciones. No puede consultar costos, precios de compra ni utilidades.
- `ADMIN`: acceso completo, administración de usuarios, catálogos, productos, recetas, costos, proveedores, compras, ventas, descuentos, dashboard y configuración. Puede ejecutar las acciones del Operativo.

Las cuentas Operativo y Administrador solo las crea un Administrador. El registro público siempre crea un Cliente.

La autorización debe comprobarse en Flask en cada endpoint. Ocultar controles en Angular no es una medida de seguridad. Las consultas del Cliente deben filtrar por el ID del usuario autenticado; nunca confiar en un `usuario_id` enviado por el navegador para consultar datos propios.

## 10. Contrato HTTP de la API

- Prefijo global: `/api/v1`.
- JSON en español para mensajes y nombres de campo iguales a los de la base.
- Respuestas correctas: datos directos.
- Listas paginadas: `{ "items": [], "total": 0, "pagina": 1, "por_pagina": 20 }`.
- Error: `{ "codigo": "STOCK_INSUFICIENTE", "mensaje": "Descripción legible", "detalle": [] }`.
- Códigos HTTP:
  - `200`: consulta o modificación correcta.
  - `201`: recurso creado.
  - `204`: eliminación/desactivación sin cuerpo cuando aplique.
  - `400`: validación o petición incorrecta.
  - `401`: sesión ausente o inválida.
  - `403`: rol o permiso insuficiente.
  - `404`: recurso inexistente.
  - `409`: conflicto de negocio, stock o estado inválido.
  - `422`: regla de negocio incumplida.
  - `429`: demasiados intentos.
  - `500`: error interno genérico, sin filtrar detalles sensibles.
- Dinero serializado como cadena decimal con dos decimales.
- Cantidades de materiales serializadas con hasta cuatro decimales.
- Fechas en ISO 8601, con zona horaria definida.
- No exponer trazas, consultas SQL, secretos o datos internos al cliente.
- Documentar endpoints con OpenAPI/Swagger y mantener el contrato actualizado.

## 11. Endpoints requeridos

Implementa los siguientes blueprints bajo `/api/v1`. Los roles indicados son: `P` público, `C` Cliente, `O` Operativo y `A` Administrador. `A` también puede realizar las acciones de `O` cuando el documento así lo establece.

### auth (M01)
- `POST /auth/registro` — P
- `POST /auth/login` — P
- `POST /auth/refrescar` — P, con cookie de refresco
- `POST /auth/logout` — todos
- `POST /auth/recuperar` — P
- `POST /auth/restablecer` — P

### cuenta (M02)
- `GET`, `PATCH /cuenta` — C
- `PATCH /cuenta/contrasena` — todos
- `GET`, `POST`, `PATCH`, `DELETE /cuenta/direcciones` — C
- `GET`, `POST`, `PATCH`, `DELETE /cuenta/medios-pago` — C
- `GET /envio/cobertura?cp=` — P

### catalogo (M03)
- `GET /catalogo?categoria&color&talla&q&disponibles` — P
- `GET /catalogo/{producto_id}` — P; incluye disponibilidad por variante, sin revelar cantidades exactas.

### carrito (M04)
- `GET /carrito` — C
- `PUT /carrito/lineas` — C
- `DELETE /carrito/lineas/{variante_id}` — C
- `POST /carrito/fusionar` — C

### checkout (M05)
- `POST /checkout/cotizar` — C; calcula totales, envío y descuento.
- `POST /checkout/descuento` — C; valida cupón.
- `POST /checkout/pagar` — C; exige `Idempotency-Key`.

### mis_pedidos (M06)
- `GET /mis-pedidos` — C
- `GET /mis-pedidos/{id}` — C
- `POST /mis-pedidos/{id}/cancelar` — C
- `GET /mis-pedidos/{id}/comprobante` — C

### devoluciones (M07)
- `POST /devoluciones` — C
- `GET /devoluciones` — C (propias), A y O
- `PATCH /devoluciones/{id}/aprobar` — A
- `PATCH /devoluciones/{id}/rechazar` — A
- `POST /devoluciones/{id}/recibir` — O
- `POST /devoluciones/{id}/dictamen` — O
- `POST /devoluciones/{id}/resolver` — A

### ventas (M08)
- `GET /ventas` — A
- `GET /ventas/{id}` — A
- `POST /ventas/manual` — A
- `POST /ventas/{id}/pago` — A
- `POST /ventas/{id}/cancelar` — A
- `POST /ventas/{id}/reembolso` — A
- `GET`, `POST`, `PATCH`, `DELETE /descuentos` — A

### pedidos (M09)
- `GET /pedidos` y `GET /pedidos/{id}` — A, O
- `GET /pedidos/pendientes-produccion` — A, O
- `PATCH /pedidos/{id}` — A; solo prioridad y nota.
- `POST /pedidos/{id}/cancelar` — A

### productos (M10)
- `GET`, `POST`, `PATCH`, `DELETE /productos` — A; POST genera variantes y SKU.
- `POST /productos/{id}/imagenes` — A
- `PATCH /variantes/{id}` — A
- `POST /productos/{id}/activar` — A

### recetas (M11)
- `GET /recetas` — A, O
- `GET`, `POST`, `PATCH /recetas/{id}` — A
- `POST /recetas/{id}/lineas` — A
- `POST /recetas/previsualizar` — A
- `POST /recetas/{id}/copiar` — A
- `POST /recetas/{id}/activar` — A
- `GET /recetas/costeo` — A
- `GET`, `POST`, `PATCH`, `DELETE /disenos` — A

### inventario_pt (M12)
- `GET /inventario/producto` — O
- `GET /inventario/producto/movimientos` — O
- `POST /inventario/producto/ajuste` — O
- `PATCH /inventario/producto/{variante_id}/reglas` — A

### proveedores (M13)
- `GET`, `POST`, `PATCH`, `DELETE /proveedores` — A
- `GET`, `POST`, `PATCH`, `DELETE /proveedores/{id}/materiales` — A
- `GET /proveedores/evaluacion` — A

### compras (M14)
- `GET`, `POST`, `PATCH`, `DELETE /requisiciones` — A, O
- `POST /requisiciones/{id}/cotizaciones` — A
- `POST /cotizaciones/{id}/elegir` — A
- `GET`, `POST`, `PATCH`, `DELETE /ordenes-compra` — A
- `POST /ordenes-compra/{id}/emitir` — A
- `POST /ordenes-compra/{id}/cancelar` — A
- `GET /ordenes-compra/{id}/pdf` — A
- `POST /recepciones` — O; exige `Idempotency-Key`.

### inventario_mp (M15)
- `GET /inventario/material` — O; por categoría.
- `GET /inventario/material/lotes` — O
- `GET /inventario/material/movimientos` — O
- `POST /inventario/material/ajuste` — O
- `GET`, `POST`, `PATCH`, `DELETE /materiales` — A; lectura O.
- `PATCH /inventario/material/{id}/politica` — A

### produccion (M16)
- `GET /produccion/ordenes` y `GET /produccion/ordenes/{id}` — O
- `POST /produccion/ordenes` — O
- `POST /produccion/ordenes/{id}/reservar` — O
- `POST /produccion/ordenes/{id}/solicitar-compra` — O
- `POST /produccion/ordenes/{id}/iniciar` — O; exige `Idempotency-Key`.
- `POST /produccion/ordenes/{id}/revision` — O
- `POST /produccion/ordenes/{id}/dictamen` — O
- `POST /produccion/ordenes/{id}/cancelar` — O
- `GET /produccion/plan-sugerido` — O

### mermas (M17)
- `GET /mermas` — O
- `POST /mermas` — O
- `POST /mermas/{id}/reversar` — A
- `GET /mermas/indicadores` — A

### preparacion (M18)
- `GET /preparacion/cola` — O
- `POST /preparacion/{pedido_id}/tomar` — O
- `PATCH /preparacion/{id}/lineas` — O; surtir y verificar.
- `POST /preparacion/{id}/incidencia` — O
- `POST /preparacion/{id}/empacar` — O
- `GET /preparacion/{id}/etiqueta` — O

### entregas (M19)
- `GET /entregas/por-asignar` — O
- `POST /entregas` — O; asignar.
- `POST /entregas/{id}/salida` — O
- `POST /entregas/{id}/resultado` — O
- `GET /entregas/hoja-reparto?repartidor&fecha` — O
- `GET /entregas/productos-repartidos` — O
- `GET`, `POST`, `PATCH`, `DELETE /repartidores` — A

### dashboard (M20)
- `GET /dashboard/resumen` — A
- `GET /dashboard/ventas` — A
- `GET /dashboard/produccion` — A y O solo datos operativos.
- `GET /dashboard/abastecimiento` — A y O solo datos operativos.
- `GET /dashboard/logistica` — A y O solo datos operativos.
- `GET /dashboard/exportar` — A

### alertas (M21)
- `GET /alertas` — A, O
- `POST /alertas/{id}/accion` — A, O
- `GET /alertas/resueltas` — A, O
- `GET`, `PATCH /alertas/reglas` — A

### admin (M22)
- `GET`, `POST`, `PATCH`, `DELETE /usuarios` — A
- `GET /clientes` y `GET /clientes/{id}` — A
- CRUD de `/catalogos/{color,talla,categoria-producto,categoria-material,causa-merma,tarifa-envio}` — A
- `GET`, `PATCH /configuracion` — A
- `GET /bitacora` — A

Si el documento integral contiene una ruta ambigua por su representación en texto, conserva la intención funcional y registra la normalización de URL en `docs/decisiones-tecnicas.md`. No dupliques rutas que colisionen: usa rutas específicas antes que rutas genéricas y pruebas de resolución.

## 12. Servicios de negocio obligatorios

Implementa los siguientes servicios reutilizables. Los nombres pueden ajustarse a convenciones Python, pero su responsabilidad debe conservarse:

- `generar_folio(prefijo)`: incrementa `secuencia_folio` y construye el folio dentro de la transacción que lo utiliza.
- `generar_sku(producto, talla, color)`: formato categoría-producto, talla y color; utiliza códigos del catálogo.
- `crear_producto(datos)`: crea producto, variantes, SKU, stock y recetas en borrador.
- `calcular_receta(receta)`: cantidad bruta, costo de materia prima, empaque, costo estándar, precio sugerido y margen.
- `activar_receta(id)`: valida, archiva la receta vigente anterior y activa la nueva en una transacción.
- `explotar_materiales(orden)`: agrega necesidades de receta y bordado por material y color.
- `reservar_materiales(orden)`: reserva disponibilidad posible, actualiza detalle y semáforo en una transacción.
- `iniciar_produccion(orden)`: consume materiales por PEPS; cambia estado en una transacción.
- `calcular_semaforo_orden(orden)`: determina VERDE, ÁMBAR o ROJO según faltantes, compras y fechas.
- `registrar_dictamen(linea, aprobadas, reproceso, merma)`: valida cantidades, registra merma, incrementa producto terminado y asigna unidades a pedidos.
- `asignar_pt_a_pedidos(variante)`: reserva producción nueva para pedidos pendientes por antigüedad.
- `crear_pedido(carrito, datos, clave)`: checkout integral y atómico.
- `validar_descuento(carrito, codigo, usuario)`: calcula descuento aplicable conforme a reglas.
- `calcular_envio(cp)`: localiza tarifa vigente por rango de código postal.
- `reservar_stock` y `liberar_reservas`: actualizan reservado y generan movimientos.
- `cancelar_pedido(id, motivo)`: libera reservas, ajusta órdenes y genera el reembolso simulado correspondiente.
- `vincular_o_crear_orden(variante, cantidad, pedido_linea)`: acumula demanda en orden abierta del mismo SKU o crea una.
- `generar_requisicion(origen, faltantes)`: genera requisición y cantidad sugerida según presentación comercial.
- `registrar_recepcion(oc, lineas, clave)`: crea lotes por cantidades aceptadas, registra rechazo como merma y actualiza orden de compra.
- `consumir_peps(inventario_material, cantidad)`: consume lotes antiguos y devuelve costo real.
- `registrar_merma(datos)`: descuenta inventario y registra la merma en una transacción.
- `tomar_pedido` y `marcar_empaque`: administran preparación y consumo de empaque.
- `asignar_entrega`, `confirmar_salida`, `registrar_resultado`: administran asignación, salida, entrega fallida y reingreso.
- `resolver_devolucion(id, resolucion)`: ejecuta reembolso simulado o venta de reemplazo.
- `evaluar_alertas(entidad)`: abre, actualiza o cierra alertas según reglas.
- `kpis(filtros)`: consulta vistas y agrega indicadores del dashboard.

## 13. Transacciones críticas e idempotencia

Usa transacciones SQLAlchemy explícitas. Una operación crítica debe confirmar todas sus escrituras o revertirlas todas. No atrapes una excepción y continúes con una transacción parcialmente fallida.

### Checkout / crear_pedido

La operación debe seguir el flujo de la sección 9.5 del documento:

1. Buscar si la `Idempotency-Key` ya tiene una respuesta almacenada; si existe, devolver exactamente esa respuesta.
2. Abrir transacción.
3. Validar variantes activas y cantidades, incluido el máximo por línea configurable.
4. Bloquear filas de `stock_variante` en orden ascendente por ID con `SELECT ... FOR UPDATE`.
5. Validar cobertura de envío por CP.
6. Validar y calcular descuento en servidor.
7. Calcular subtotal, envío y total en servidor.
8. Ejecutar pago simulado. Aplicar validación de tarjeta (Luhn y vigencia) cuando corresponda; el valor de prueba `0000` rechaza. No guardar número completo ni CVV.
9. Si el pago es rechazado, hacer rollback: no debe quedar venta, pedido ni reserva; el carrito debe conservarse.
10. Crear venta, líneas históricas, direcciones históricas y pago.
11. Crear pedido y líneas.
12. Reservar `min(disponible, cantidad)`; registrar movimiento `RESERVA`. La diferencia queda pendiente de producción.
13. Vincular la demanda pendiente con una orden abierta del SKU o crearla.
14. Establecer `CONFIRMADO` si todo está reservado; de lo contrario `EN_PRODUCCION`.
15. Crear preparación `POR_SURTIR` cuando corresponda.
16. Registrar eventos, uso de descuento y conversión de carrito.
17. Evaluar alertas de variantes afectadas.
18. Confirmar transacción y guardar la respuesta asociada a la clave idempotente.

### Inicio de producción

- Bloquear orden y materiales/lotes con orden determinista.
- Consumir por PEPS únicamente si existe cantidad suficiente para todos los materiales.
- Si algún material es insuficiente, rollback completo y devolver `MATERIAL_INSUFICIENTE` con faltantes.
- Si todo alcanza, registrar movimientos `CONSUMO`, costo real por lote y estado `EN_PROCESO`.

### Dictamen de calidad

- Validar `aprobadas + reproceso + merma == cantidad_revisada`.
- Registrar merma cuando corresponda.
- Incrementar existencia únicamente con unidades aprobadas.
- Registrar movimiento `PRODUCCION`.
- Asignar unidades nuevas a pedidos pendientes por FIFO.
- Cerrar o mantener la orden según cantidades pendientes y reproceso.

### Recepción de compra

- Validar `aceptada + rechazada == cantidad_medida`.
- Crear lote únicamente con la cantidad aceptada y costo real correspondiente.
- Registrar movimiento `ENTRADA`.
- Registrar cantidad rechazada como merma por rechazo de recepción.
- Actualizar orden de compra a `PARCIAL` o `RECIBIDA`.
- Revaluar órdenes de producción pendientes y alertas.

### Idempotency-Key

Es obligatoria en operaciones que no deben duplicarse: pago/checkout, inicio o registro de producción según operación, y recepción. Implementa almacenamiento persistente de clave, alcance, hash o identificación de petición, estado y respuesta final. La misma clave y misma operación deben devolver la respuesta original; la misma clave con una petición distinta debe producir conflicto `409`. La concurrencia sobre una misma clave debe estar protegida por restricción única y transacción.

## 14. Seguridad obligatoria

- JWT con `flask-jwt-extended`.
- Access token: 15 minutos, enviado como `Authorization: Bearer`.
- Refresh token: 7 días en cookie `httpOnly`, `Secure` en HTTPS y `SameSite=Strict`; almacenar hash en `token_refresco` y rotar en cada uso.
- Logout revoca el refresh token.
- Contraseñas con Argon2 (o bcrypt costo 12).
- No escribir contraseñas, tokens, números de tarjeta ni CVV en logs.
- Aplicar decoradores de roles a cada ruta protegida.
- Las consultas del Cliente deben filtrar por usuario autenticado.
- Todas las entradas deben pasar por schemas y reglas de negocio del servidor.
- El servidor recalcula todos los importes, descuentos, impuestos, disponibilidad y costos.
- Usar exclusivamente consultas parametrizadas/ORM; prohibido concatenar SQL con entrada del usuario.
- Rate limit de login: 5 intentos por minuto por IP y por correo, además del bloqueo de cuenta.
- CORS limitado al origen Angular configurado.
- Añadir cabeceras de seguridad, al menos `X-Content-Type-Options: nosniff`, protección de framing y política CSP adecuada al despliegue.
- Archivos permitidos: JPG, PNG y WebP, máximo 2 MB; verificar contenido real con Pillow, renombrar con identificador aleatorio y guardar fuera del código.
- No guardar número completo de tarjeta ni CVV en ninguna tabla, bitácora, log, respuesta o excepción.
- El serializador de Operativo debe omitir `costo_estandar`, `precio_compra`, `costo_total`, márgenes y cualquier dato financiero reservado.
- Registrar acciones sensibles en `bitacora`: cambios de rol, precio, receta, ajustes, cancelaciones, configuración y reversos de merma.
- Secretos exclusivamente mediante variables de entorno.
- `DEBUG` desactivado por defecto y siempre en producción.
- No usar `localStorage` para tokens.
- Mensajes de login y recuperación no deben revelar si un correo está registrado.
- No desactivar al último Administrador.

## 15. Tareas programadas

Implementa con APScheduler, invocando servicios de dominio:

| Tarea | Frecuencia | Responsabilidad |
|---|---:|---|
| `evaluar_estancamientos` | Cada 15 minutos | Revisar pedidos estancados, órdenes vencidas y compras retrasadas; abrir alertas. |
| `recalcular_semaforos` | Cada 15 minutos | Actualizar semáforos de órdenes abiertas. |
| `cerrar_alertas_resueltas` | Cada 15 minutos | Cerrar alertas cuya condición ya no exista. |
| `abandonar_carritos` | Diaria | Cambiar a `ABANDONADO` carritos sin cambios por 7 días. |
| `evaluar_proveedores` | Diaria | Recalcular entregas a tiempo y marcar `EN_REVISION` si cae por debajo de 80 %. |
| `limpiar_tokens` | Diaria | Eliminar o depurar tokens vencidos o revocados conforme a política. |

En despliegue con múltiples workers, no permitas que cada worker ejecute el mismo scheduler sin coordinación. Usa un proceso scheduler separado dentro del mismo proyecto/contenedor mediante comando dedicado, o un mecanismo distribuido de exclusión. No levantes múltiples schedulers por accidente.

## 16. Catálogos y semillas iniciales

Crea un proceso de semillas idempotente: ejecutarlo más de una vez no debe duplicar catálogos ni datos base. No debe sobrescribir datos operativos ni contraseñas existentes.

### Roles
- `CLIENTE`
- `OPERATIVO`
- `ADMIN`

### Catálogos
- Colores: `BL` Blanco, `NG` Negro, `GR` Gris y `NA` No aplica.
- Tallas: `CH` Chica, `MD` Mediana, `GD` Grande y `UN` Única.
- Categorías de producto: Sudadera (`SD`, con tallas), Playera (`PL`, con tallas), Pantalón (`PN`, con tallas), Gorro (`GO`, talla única), Bolsa de tela (`BO`, talla única).
- Categorías de material: Tela, Hilo, Estabilizador, Avío, Etiqueta y Empaque.
- Causas de merma: Defecto de tela, Rechazo en recepción, Error de corte, Error de tejido, Defecto de bordado, Error de confección, Defecto de acabado, Daño en almacén, Daño en envío, Devolución de cliente dañada, Encogimiento o desgaste, Sobrante inservible y Otro.
- Diseños iniciales en estado `PENDIENTE`: DIS-001 Sudadera 22×15 cm; DIS-002 Playera 22×15 cm; DIS-003 Pantalón tubo 55×15 cm; DIS-004 Pantalón bolsillo 5×5 cm; DIS-005 Gorro 5×5 cm; DIS-006 Bolsa 20×20 cm.

### Materiales

Cargar los códigos, categorías, unidades, presentaciones, factores, costos estándar, porcentajes de merma y colores exactamente como están en las tablas 11.2 del documento:

- `TEL-FEL`: Felpa, Tela, m², costo base 89.1975, merma 15 %, con color.
- `TEL-JER`: Jersey peinado, Tela, m², costo base 25.7310, merma 15 %, con color.
- `TEL-RIB`: Tejido acanalado (rib), Tela, m², costo base 50.2857, merma 20 %, con color.
- `TEL-LON`: Loneta, Tela, m², costo base 76.5333, merma 10 %, con color.
- `HIL-EST`: Estambre acrílico, Hilo, m, costo base 0.247619, merma 5 %, con color.
- `HIL-COS`: Hilo de costura 40/2, Hilo, m, costo base 0.012741, merma 10 %, sin color.
- `HIL-BOR-001` a `HIL-BOR-003`: Hilo de bordado 120D/2, Hilo, m, costo base 0.010600, merma 0 %, sin color.
- `EST-HOJ`: Estabilizador de corte hoja, pieza, costo base 5.0000, merma 0 %, sin color.
- `EST-ROL`: Estabilizador de corte rollo, m, costo base 21.9593, merma 0 %, sin color.
- `AVI-COR`: Cordón redondo de poliéster, pieza, costo base 32.7750, merma 0 %, sin color.
- `AVI-OJI`: Ojillos metálicos de 8 mm, pieza, costo base 0.4200, merma 0 %, sin color.
- `ETQ-MAR`: Etiqueta de marca, pieza, costo base 0.6500, merma 0 %, sin color.
- `ETQ-TAL-CH`, `ETQ-TAL-MD`, `ETQ-TAL-GD`: Etiqueta de talla, pieza, costo base 0.6500, merma 0 %, sin color.
- `ETQ-COM-SD`, `ETQ-COM-PL`, `ETQ-COM-PN`, `ETQ-COM-GO`, `ETQ-COM-BO`: Etiqueta de composición y cuidado, pieza, costo base 0.6500, merma 0 %, sin color.
- `EMP-BOL`: Bolsa individual kraft mediana, pieza, costo base 12.0000.
- `EMP-PAP`: Papel protector, pieza, costo base 2.5000.
- `EMP-TAR`: Tarjeta personalizada con QR, pieza, costo base 5.0000.
- `EMP-ETE`: Etiqueta de envío, pieza, costo base 0.0000 provisional.

Los materiales con color deben generar inventario por colores BL, NG y GR; los materiales sin color usan NA. El documento establece 36 registros iniciales de `inventario_material`: 15 para materiales con color y 21 para materiales sin color.

### Recetas

Cargar las 11 recetas semilla por producto y talla, incluyendo líneas de material, cantidades netas, factor de consumo, merma, etiquetas y bordado pendiente, conforme a las tablas 11.3 y 11.4. Calcular cantidad bruta mediante:

`cantidad_bruta = cantidad_neta * factor_consumo / (1 - merma_pct / 100)`

No activar automáticamente recetas con observaciones pendientes. En particular, verificar el consumo de Playera CH antes de activar porque el documento indica una nota de patrón pendiente. El hilo de bordado inicia en 0 m mientras el diseño permanezca `PENDIENTE`.

### Configuración inicial

Cargar en `configuracion`:

- `iva_pct = 16`
- `margen_objetivo_pct = 55`
- `merma_meta_pct = 5`
- `proveedor_minimo_a_tiempo_pct = 80`
- `dias_devolucion = 15` (propuesta por confirmar)
- `max_intentos_entrega = 2` (propuesta por confirmar)
- `dias_produccion_estandar = 5` (propuesta por confirmar)
- `max_piezas_por_linea = 10` (propuesta por confirmar)
- `saldo_inicial_cuenta_simulada = 5000.00` (propuesta por confirmar)
- `envio_gratis_desde = 0` (desactivado)
- `horas_max_recibido = 2`
- `horas_max_confirmado = 24`
- `dias_max_en_produccion = 7`
- `horas_max_en_preparacion = 24`
- `horas_max_listo_envio = 24`
- `horas_max_en_reparto = 24`
- `horas_alerta_devolucion = 48`
- `dias_carrito_abandonado = 7`
- `intentos_login_max = 5`
- `bloqueo_login_min = 15`
- `vigencia_recuperacion_min = 30`

Además:
- Descuento «Primera compra»: 10 %, aplicación `AUTOMATICO`, solo primera compra, activo.
- Reglas de empaque: `EMP-BOL` por prenda (1), `EMP-PAP` por prenda (1), `EMP-TAR` por pedido (1), `EMP-ETE` por pedido (1).
- Tarifa «Local León» para CP 37000–37999; costo y días deben quedar configurables y confirmarse con el equipo. El prototipo muestra $200.00 como referencia, no como dato definitivo.
- Stock inicial de variantes: existencia 0; stock mínimo y cantidad de reposición configurables. La propuesta del documento es 5 y 20.

Crear un Administrador inicial y un Operativo de prueba mediante variables de entorno o comando interactivo seguro. Nunca dejar una contraseña conocida fija en el código o en semillas. Los Clientes se registran públicamente.

## 17. SKU y folios

El SKU se genera en el servicio al crear el producto, bloqueando la fila de categoría cuando se requiera consecutivo para evitar duplicados. Se almacena en `variante_producto.sku` y no se modifica aunque cambie el nombre del producto.

Códigos y formato deben seguir el documento: tres segmentos para todos los SKU, incluyendo `UN` para talla única. Ejemplos: `PL-MD-GR`, `GO-UN-NG`.

Folios, generados mediante `secuencia_folio` dentro de transacción:

- Venta y pedido: `UNQ-AAAA-NNNNNN`.
- Orden de producción: `OP-AAAA-NNNN`.
- Requisición: `REQ-AAAA-NNNNNN`.
- Orden de compra: `OC-AAAA-NNNNNN`.
- Recepción: `REC-AAAA-NNNNNN`.
- Lote de material: `LT-AAAA-NNNNNN`.
- Devolución: `DEV-AAAA-NNNNNN`.
- Entrega/guía: `EN-AAAA-NNNNNN`.

Respeta los prefijos y longitudes definidos en el documento. No uses `MAX(id)+1` para generar folios.

## 18. Alertas

Implementa las reglas y catálogo de alertas del documento, entre ellas:

- `PT_AGOTADO_DEMANDA`
- `PT_STOCK_MINIMO`
- `MP_INSUFICIENTE`
- `MP_REORDEN`
- `ORDEN_ROJA`
- `OC_RETRASADA`
- `PEDIDO_ESTANCADO`
- `MERMA_ALTA`
- `DIFERENCIA_CONTEO`
- `ENTREGA_FALLIDA`
- `DEVOLUCION_PENDIENTE`
- `PAGO_PENDIENTE`
- `PROVEEDOR_EN_REVISION`
- `DISENO_PENDIENTE`

Las alertas deben generarse por eventos y tareas programadas. Una alerta abierta con la misma clave de negocio no debe duplicarse. Debe cerrarse automáticamente cuando desaparezca la condición (`RESUELTA_AUTO`). La acción desde la alerta debe ejecutar el servicio correspondiente y registrar su atención.

## 19. Vistas y consultas de lectura

Implementa las vistas que el documento requiere, entre ellas `v_inventario_material`, `v_ventas_sku`, `v_merma_resumen`, `v_capacidad_variante` y `v_pedidos_estancados`, además de las demás vistas mencionadas en el documento. Mantén sus definiciones en migraciones SQL/Alembic.

Las consultas de dashboard deben usar vistas y consultas agregadas eficientes, filtros parametrizados e índices. El rol Operativo solo recibe datos operativos; nunca costos ni utilidades.

Para PEPS, seleccionar lotes disponibles por `fecha_entrada` e ID ascendente y bloquearlos con `FOR UPDATE`. Para punto de reorden, usar consumo diario calculado con movimientos de los últimos 30 días o el valor manual cuando no haya historial.

## 20. Pruebas obligatorias

Cada endpoint debe contar con pruebas de autenticación/autorización, validación, respuesta y persistencia. Añade pruebas unitarias para cálculos y pruebas de integración con MySQL real de la versión del proyecto. SQLite puede usarse para pruebas unitarias aisladas, pero no sustituye las pruebas de integración de MySQL ni valida por sí solo bloqueos, `CHECK`, vistas o comportamiento InnoDB.

Pruebas mínimas de aceptación tomadas del documento:

1. Dos compras simultáneas de la última unidad: solo una reserva; la otra queda pendiente de producción.
2. El mismo pago enviado dos veces con la misma clave idempotente: una sola venta.
3. Pago rechazado: no queda venta, pedido ni reserva.
4. Inicio de producción con material insuficiente: no se descuenta ningún lote.
5. Recepción con material rechazado: el lote contiene solo lo aceptado y existe el registro de merma.
6. Cancelar pedido `EN_PRODUCCION`: reservas y orden se ajustan correctamente.
7. Un Operativo no puede ver costos y un Cliente no puede consultar pedidos de otro.
8. Dos intentos de entrega fallidos: alerta crítica y reingreso correcto de existencias.

Añade además pruebas para:
- Refresh token rotado y revocado.
- Acceso de un usuario desactivado/bloqueado.
- Último Administrador no desactivable.
- Repetición de `Idempotency-Key` con payload diferente.
- Folios concurrentes sin duplicidad.
- Reverso de movimiento mediante movimiento contrario, sin editar historial.
- Desactivación de catálogo con registros relacionados.
- Imágenes inválidas, archivos mayores a 2 MB y MIME falso.
- Validación de código postal y rangos de tarifas sin solapamiento.
- Ocultamiento de datos financieros del Operativo.
- Reglas de transición de estados en pedidos, compras, producción y entregas.

## 21. Orden de construcción

Desarrolla el backend de manera incremental. No intentes implementar los 22 módulos en una sola entrega sin pruebas.

### Fase 0 — Inspección y diseño técnico
- Inspeccionar repositorio y documento integral.
- Crear arquitectura, configuración, Docker, Compose, `.env.example`, dependencias y README.
- Definir decisiones técnicas pendientes.
- Crear health endpoint y comprobación de conexión MySQL.

### Fase 1 — Base de datos y seguridad
- Modelos y migraciones de los 64 objetos/tablas del documento agrupados en 11 grupos.
- Restricciones, índices y vistas.
- Semillas idempotentes de roles, catálogos y configuración.
- Auth, usuarios, roles, refresh tokens, recuperación, bitácora y rate limit.
- Pruebas de permisos y seguridad.

### Fase 2 — Cliente y tienda
- Cuenta, direcciones y medios de pago simulados.
- Catálogo, variantes, SKU y disponibilidad.
- Carrito y fusión de carrito.
- Cobertura de envío y descuentos.
- Checkout simulado con idempotencia, venta, pedido y reservas.

### Fase 3 — Producto y abastecimiento
- Productos, recetas, diseños y costeo.
- Inventario de producto terminado.
- Proveedores, materiales, inventario de materia prima.
- Requisiciones, cotizaciones, órdenes de compra y recepciones.
- PEPS, lotes, movimientos y mermas.

### Fase 4 — Producción
- Órdenes, explosión de materiales, reservas y semáforos.
- Inicio de producción, consumo PEPS, revisión y dictamen.
- Reproceso, merma, producción aprobada y asignación FIFO a pedidos.

### Fase 5 — Ventas, pedidos y posventa
- Ventas manuales, pagos, cancelaciones, reembolsos y descuentos.
- Pedidos, eventos, seguimiento y comprobantes.
- Cambios y devoluciones, inspección, reingreso o merma y venta de reemplazo.

### Fase 6 — Logística y control
- Preparación, picking, verificación, empaque y etiqueta.
- Repartidores, entregas, salidas, resultados, reintentos y guías.
- Alertas, dashboard, KPIs, exportación y administración.

### Fase 7 — Cierre
- Completar cobertura de pruebas.
- Revisar seguridad y rendimiento.
- Verificar instalación limpia con Docker Compose.
- Documentar endpoints, roles, variables, semillas, migraciones y comandos.
- Verificar que Angular pueda consumir los contratos API.

Cada fase debe terminar con: código implementado, migraciones, semillas necesarias, pruebas ejecutadas, endpoints documentados y lista de pendientes reales.

## 22. Docker: criterios de aceptación

La instalación limpia debe funcionar con estos comandos, documentados y probados:

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f api
docker compose exec api flask db upgrade
docker compose exec api python -m scripts.seed
```

Adapta los comandos al entrypoint real del proyecto y documenta el comando seguro para crear el Administrador inicial.

Criterios:
- `api` usa Python 3.11 slim y arranca con Gunicorn.
- `mysql` usa exactamente `mysql:8.4.3`.
- `phpmyadmin` usa exactamente `phpmyadmin:5.2.3`.
- Los datos sobreviven a `docker compose down` y a la recreación del contenedor, siempre que no se use `-v`.
- phpMyAdmin puede iniciar sesión en el servidor MySQL con las credenciales configuradas.
- La API puede ejecutar health check y consultar MySQL.
- No se requiere instalar Python, Flask o MySQL en el host para ejecutar el proyecto.
- Las migraciones se pueden ejecutar desde el contenedor API.
- El entorno se puede reconstruir desde cero con `.env.example` y pasos documentados.
- Nunca ejecutar `docker compose down -v` sin autorización explícita porque elimina volúmenes y datos persistentes.

## 23. Criterios de calidad y entrega

Antes de considerar el proyecto terminado:

- Todos los endpoints del alcance están implementados y documentados.
- Todos los endpoints protegidos aplican autenticación y roles.
- Las reglas de negocio viven en servicios.
- Las operaciones críticas son atómicas e idempotentes.
- Las tablas, relaciones, vistas y restricciones coinciden con el documento.
- Los movimientos de inventario son inmutables.
- Las cifras monetarias y cantidades usan precisión decimal.
- Las semillas son repetibles y no destruyen datos.
- Los errores siguen el contrato común.
- No hay secretos en Git.
- Las pruebas unitarias, de integración y flujos críticos pasan.
- El stack levanta en Docker desde una instalación limpia.
- `README.md` explica instalación, configuración, ejecución, migraciones, semillas, pruebas, phpMyAdmin y solución de problemas.
- `docs/endpoints.md` contiene método, ruta, rol, parámetros, esquema, respuesta y errores por endpoint.
- `docs/modelo-datos.md` explica tablas, claves, relaciones y vistas.
- `docs/decisiones-tecnicas.md` registra decisiones que no estén especificadas o que requieran confirmación.

## 24. Instrucción inicial para comenzar

Al iniciar el trabajo:

1. Inspecciona el repositorio y localiza `UNIQUE_documento_integral_v3.txt`.
2. Lee especialmente las secciones 3, 5, 6, 7, 8, 9 y 11; consulta las demás cuando implementes los módulos correspondientes.
3. Resume brevemente la arquitectura actual y detecta archivos que puedan reutilizarse.
4. Presenta un plan de implementación con fases y archivos a crear.
5. Comienza por la Fase 0: estructura, Docker Compose, configuración, conexión MySQL y health check.
6. No avances a lógica de negocio hasta verificar que los tres servicios Docker arrancan, MySQL está saludable y Flask puede conectarse.
7. Después implementa por fases, ejecutando pruebas en cada una.

**Prioridad absoluta:** fidelidad al documento funcional, integridad de datos, seguridad, transacciones correctas y despliegue reproducible. No sacrifiques estas propiedades por generar código rápidamente.
