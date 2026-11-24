"""Fabrica de la aplicacion Flask de UNIQUE."""

from flask import Flask

from app.blueprints.health import health_bp
from app.config import Config
from app.extensions import cors, db, jwt, limiter, migrate
from app.utils.errores import registrar_manejadores_de_error


def create_app(configuracion=None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(configuracion or Config)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app, origins=app.config["CORS_ORIGINS"], supports_credentials=True)
    limiter.init_app(app)

    registrar_manejadores_de_error(app)
    app.register_blueprint(health_bp)
    _registrar_cabeceras_de_seguridad(app)

    return app


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
