"""Fabrica de la aplicacion Flask de UNIQUE."""

from flask import Flask

from app.blueprints.admin import admin_bp
from app.blueprints.auth import auth_bp
from app.blueprints.carrito import carrito_bp
from app.blueprints.catalogo import catalogo_bp
from app.blueprints.checkout import checkout_bp
from app.blueprints.compras import compras_bp
from app.blueprints.cuenta import cuenta_bp
from app.blueprints.health import health_bp
from app.blueprints.inventario_mp import inventario_mp_bp
from app.blueprints.inventario_pt import inventario_pt_bp
from app.blueprints.mis_pedidos import mis_pedidos_bp
from app.blueprints.productos import productos_bp
from app.blueprints.proveedores import proveedores_bp
from app.blueprints.recetas import recetas_bp
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
    app.register_blueprint(auth_bp)
    app.register_blueprint(cuenta_bp)
    app.register_blueprint(catalogo_bp)
    app.register_blueprint(carrito_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(mis_pedidos_bp)
    app.register_blueprint(productos_bp)
    app.register_blueprint(recetas_bp)
    app.register_blueprint(inventario_pt_bp)
    app.register_blueprint(proveedores_bp)
    app.register_blueprint(inventario_mp_bp)
    app.register_blueprint(compras_bp)
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


def _registrar_cabeceras_de_seguridad(app: Flask) -> None:
    @app.after_request
    def aplicar(respuesta):
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["X-Frame-Options"] = "DENY"
        respuesta.headers["Referrer-Policy"] = "no-referrer"
        respuesta.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
        return respuesta
