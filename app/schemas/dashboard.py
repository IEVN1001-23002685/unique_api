"""Esquemas de filtros del dashboard (M20)."""

from marshmallow import Schema, fields


class DashboardFiltrosSchema(Schema):
    desde = fields.Date(allow_none=True)
    hasta = fields.Date(allow_none=True)
