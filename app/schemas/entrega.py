"""Esquemas de entregas, hojas de reparto y repartidores (M19)."""

from marshmallow import Schema, fields, validate

ESTADOS = ["PROGRAMADA", "EN_RUTA", "ENTREGADA", "FALLIDA", "CANCELADA"]
MOTIVOS = ["AUSENTE", "DIRECCION_INCORRECTA", "RECHAZADO", "OTRO"]


class EntregaCrearSchema(Schema):
    pedido_id = fields.Int(required=True, validate=validate.Range(min=1))
    repartidor_id = fields.Int(required=True, validate=validate.Range(min=1))
    fecha_programada = fields.Date(required=True)
    notas = fields.Str(allow_none=True, validate=validate.Length(max=500))


class EntregaResultadoSchema(Schema):
    entregado = fields.Bool(required=True)
    receptor = fields.Str(allow_none=True, validate=validate.Length(max=100))
    motivo_fallo = fields.Str(allow_none=True, validate=validate.OneOf(MOTIVOS))
    notas = fields.Str(allow_none=True, validate=validate.Length(max=500))


class EntregaSchema(Schema):
    id = fields.Int()
    folio = fields.Str()
    pedido_id = fields.Int()
    estado = fields.Str()
    intento = fields.Int()
    fecha_programada = fields.Str()
    salida_en = fields.Str(allow_none=True)
    resultado_en = fields.Str(allow_none=True)
    receptor = fields.Str(allow_none=True)
    motivo_fallo = fields.Str(allow_none=True)
    notas = fields.Str(allow_none=True)
    repartidor_id = fields.Int()
    repartidor = fields.Str(allow_none=True)
    destinatario = fields.Str(allow_none=True)
    direccion = fields.Str(allow_none=True)
    codigo_postal = fields.Str(allow_none=True)
    telefono = fields.Str(allow_none=True)


class RepartidorCrearSchema(Schema):
    nombre = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    telefono = fields.Str(
        required=True, validate=validate.Regexp(r"^\d{10}$", error="El teléfono debe tener 10 dígitos")
    )
    vehiculo = fields.Str(allow_none=True, validate=validate.Length(max=60))


class RepartidorActualizarSchema(Schema):
    nombre = fields.Str(allow_none=True, validate=validate.Length(min=2, max=100))
    telefono = fields.Str(
        allow_none=True,
        validate=validate.Regexp(r"^\d{10}$", error="El teléfono debe tener 10 dígitos"),
    )
    vehiculo = fields.Str(allow_none=True, validate=validate.Length(max=60))
    activo = fields.Bool(allow_none=True)


class RepartidorSchema(Schema):
    id = fields.Int()
    nombre = fields.Str()
    telefono = fields.Str()
    vehiculo = fields.Str(allow_none=True)
    activo = fields.Bool()
    eliminado_en = fields.Str(allow_none=True)


class HojaRepartoSchema(Schema):
    repartidor = fields.Int(required=True, validate=validate.Range(min=1))
    fecha = fields.Date(required=True)
    pagina = fields.Int(load_default=1, validate=validate.Range(min=1))
    por_pagina = fields.Int(load_default=20, validate=validate.Range(min=1, max=100))


class RepartidosFiltrosSchema(Schema):
    repartidor = fields.Int(allow_none=True, validate=validate.Range(min=1))
    desde = fields.Date(allow_none=True)
    hasta = fields.Date(allow_none=True)


class PorAsignarFiltrosSchema(Schema):
    codigo_postal = fields.Str(
        allow_none=True, validate=validate.Regexp(r"^\d{5}$", error="Código postal inválido")
    )


class RepartidorFiltrosSchema(Schema):
    activo = fields.Bool(allow_none=True)
