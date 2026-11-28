"""Esquemas de filtros del dashboard (M20)."""

from marshmallow import Schema, ValidationError, fields, validates_schema


class DashboardFiltrosSchema(Schema):
    desde = fields.Date(allow_none=True)
    hasta = fields.Date(allow_none=True)

    @validates_schema
    def validar_rango(self, datos, **kwargs):
        if datos.get("desde") and datos.get("hasta") and datos["hasta"] < datos["desde"]:
            raise ValidationError("hasta no puede ser anterior a desde", "hasta")
