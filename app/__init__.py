"""Fabrica de la aplicacion Flask de UNIQUE."""

from flask import Flask, request

from app.blueprints.admin import admin_bp
from app.blueprints.alertas import alertas_bp
from app.blueprints.auth import auth_bp
from app.blueprints.carrito import carrito_bp
from app.blueprints.catalogo import catalogo_bp
from app.blueprints.checkout import checkout_bp
from app.blueprints.compras import compras_bp
from app.blueprints.cuenta import cuenta_bp
from app.blueprints.dashboard import dashboard_bp
from app.blueprints.devoluciones import devoluciones_bp
from app.blueprints.entregas import entregas_bp
from app.blueprints.health import health_bp
from app.blueprints.imagenes import imagenes_bp
from app.blueprints.inventario_mp import inventario_mp_bp
from app.blueprints.inventario_pt import inventario_pt_bp
from app.blueprints.mermas import mermas_bp
from app.blueprints.mis_pedidos import mis_pedidos_bp
from app.blueprints.pedidos import pedidos_bp
from app.blueprints.preparacion import preparacion_bp
from app.blueprints.produccion import produccion_bp
from app.blueprints.productos import productos_bp
from app.blueprints.proveedores import proveedores_bp
from app.blueprints.recetas import recetas_bp
from app.blueprints.ventas import ventas_bp
from app.config import Config
from app.extensions import cors, db, jwt, limiter, migrate
from app.utils.errores import ApiError, registrar_manejadores_de_error


def create_app(configuracion=None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(configuracion or Config)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, origins=app.config["CORS_ORIGINS"], supports_credentials=True)
    limiter.init_app(app)

    registrar_manejadores_de_error(app)
    _registrar_errores_jwt(jwt)
    app.register_blueprint(health_bp)
    app.register_blueprint(imagenes_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cuenta_bp)
    app.register_blueprint(catalogo_bp)
    app.register_blueprint(carrito_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(mis_pedidos_bp)
    app.register_blueprint(devoluciones_bp)
    app.register_blueprint(ventas_bp)
    app.register_blueprint(pedidos_bp)
    app.register_blueprint(productos_bp)
    app.register_blueprint(recetas_bp)
    app.register_blueprint(inventario_pt_bp)
    app.register_blueprint(proveedores_bp)
    app.register_blueprint(inventario_mp_bp)
    app.register_blueprint(compras_bp)
    app.register_blueprint(produccion_bp)
    app.register_blueprint(mermas_bp)
    app.register_blueprint(preparacion_bp)
    app.register_blueprint(entregas_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(alertas_bp)
    app.register_blueprint(admin_bp)
    _registrar_cabeceras_de_seguridad(app)

    return app


def _registrar_errores_jwt(manager) -> None:
    @jwt.unauthorized_loader
    def _sin_token(_motivo):
        return ApiError("NO_AUTENTICADO", "Se requiere una sesión válida", 401).respuesta()

    @jwt.invalid_token_loader
    def _token_invalido(_motivo):
        return ApiError("SESION_INVALIDA", "Sesión inválida", 401).respuesta()

    @jwt.expired_token_loader
    def _token_expirado(_cabecera, _datos):
        return ApiError("SESION_EXPIRADA", "La sesión ha expirado", 401).respuesta()


CSP_API = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)
# CSP exclusiva de Swagger UI: no se relaja la del resto de la API.
CSP_DOCS = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; "
    "script-src 'self' https://unpkg.com; style-src https://unpkg.com 'unsafe-inline'; "
    "font-src https://unpkg.com data:; img-src 'self' data:; connect-src 'self'"
)


def _registrar_cabeceras_de_seguridad(app: Flask) -> None:
    @app.after_request
    def aplicar(respuesta):
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["X-Frame-Options"] = "DENY"
        respuesta.headers["Referrer-Policy"] = "no-referrer"
        respuesta.headers["Content-Security-Policy"] = (
            CSP_DOCS if request.path == "/api/v1/docs" else CSP_API
        )
        return respuesta
