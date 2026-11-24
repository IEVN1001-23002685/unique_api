"""Generación de folios a partir de secuencias transaccionales."""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import SecuenciaFolio

LONGITUDES = {
    "UNQ": 6,
    "OP": 4,
    "REQ": 6,
    "OC": 6,
    "REC": 6,
    "LT": 6,
    "DEV": 6,
    "EN": 6,
}


def generar_folio(prefijo: str) -> str:
    anio = datetime.now(timezone.utc).year
    secuencia = db.session.get(SecuenciaFolio, (prefijo, anio), with_for_update=True)
    if secuencia is None:
        secuencia = SecuenciaFolio(prefijo=prefijo, anio=anio, ultimo=0)
        try:
            with db.session.begin_nested():
                db.session.add(secuencia)
        except IntegrityError:
            secuencia = db.session.get(
                SecuenciaFolio, (prefijo, anio), with_for_update=True
            )

    secuencia.ultimo += 1
    db.session.flush()
    return f"{prefijo}-{anio}-{secuencia.ultimo:0{LONGITUDES[prefijo]}d}"
