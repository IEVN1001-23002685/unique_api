"""Esquemas de entrada y salida del módulo de autenticación."""

from marshmallow import Schema, fields, validate


class RegistroSchema(Schema):
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    apellidos = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    correo = fields.Email(required=True, validate=validate.Length(max=120))
    telefono = fields.Str(required=True, validate=validate.Regexp(r"^\d{10}$"))
    password = fields.Str(required=True, validate=validate.Length(min=8, max=128))
    acepta_privacidad = fields.Bool(required=True, validate=validate.Equal(True))
    acepta_promociones = fields.Bool(load_default=False)


class LoginSchema(Schema):
    correo = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=1, max=128))


class RecuperarSchema(Schema):
    correo = fields.Email(required=True)


class RestablecerSchema(Schema):
    token = fields.Str(required=True, validate=validate.Length(min=20))
    password = fields.Str(required=True, validate=validate.Length(min=8, max=128))


class UsuarioSchema(Schema):
    id = fields.Int()
    nombre = fields.Str()
    apellidos = fields.Str()
    correo = fields.Email()
    telefono = fields.Str()
    estado_cuenta = fields.Str()
    acepta_privacidad = fields.Bool()
    acepta_promociones = fields.Bool()
    rol = fields.Str(attribute="rol.codigo")
    creado_en = fields.DateTime(format="iso")
    actualizado_en = fields.DateTime(format="iso")


class UsuarioCrearSchema(Schema):
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    apellidos = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    correo = fields.Email(required=True)
    telefono = fields.Str(required=True, validate=validate.Regexp(r"^\d{10}$"))
    password = fields.Str(required=True, validate=validate.Length(min=8, max=128))
    rol = fields.Str(required=True, validate=validate.OneOf(["CLIENTE", "OPERATIVO", "ADMIN"]))
    acepta_promociones = fields.Bool(load_default=False)


class UsuarioActualizarSchema(Schema):
    nombre = fields.Str(validate=validate.Length(min=1, max=80))
    apellidos = fields.Str(validate=validate.Length(min=1, max=120))
    telefono = fields.Str(validate=validate.Regexp(r"^\d{10}$"))
    rol = fields.Str(validate=validate.OneOf(["CLIENTE", "OPERATIVO", "ADMIN"]))
    estado_cuenta = fields.Str(validate=validate.OneOf(["ACTIVA", "SIN_ACCESO", "BLOQUEADA", "INACTIVA"]))
    acepta_promociones = fields.Bool()


class CuentaActualizarSchema(Schema):
    nombre = fields.Str(validate=validate.Length(min=1, max=80))
    apellidos = fields.Str(validate=validate.Length(min=1, max=120))
    telefono = fields.Str(validate=validate.Regexp(r"^\d{10}$"))
    correo = fields.Email(validate=validate.Length(max=120))
    contrasena_actual = fields.Str(validate=validate.Length(min=1, max=128))
    acepta_promociones = fields.Bool()


class ConfiguracionSchema(Schema):
    clave = fields.Str()
    valor = fields.Str()
    descripcion = fields.Str(allow_none=True)


class ConfiguracionActualizarSchema(Schema):
    valor = fields.Str(required=True, validate=validate.Length(max=120))


class BitacoraSchema(Schema):
    id = fields.Int()
    usuario_id = fields.Int(allow_none=True)
    accion = fields.Str()
    entidad = fields.Str()
    entidad_id = fields.Int(allow_none=True)
    detalle = fields.Dict()
    fecha = fields.DateTime(format="iso")


class CambiarContrasenaSchema(Schema):
    contrasena_actual = fields.Str(required=True, validate=validate.Length(min=1, max=128))
    contrasena_nueva = fields.Str(required=True, validate=validate.Length(min=8, max=128))
