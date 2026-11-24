"""Parámetros de paginación compartidos por los endpoints de listado."""

from flask import request

from app.utils.errores import ApiError


def parametros_paginacion(maximo=100):
    try:
        pagina = int(request.args.get("pagina", 1))
        por_pagina = int(request.args.get("por_pagina", 20))
    except (TypeError, ValueError):
        raise ApiError("PAGINACION_INVALIDA", "pagina y por_pagina deben ser enteros", 400)
    if pagina < 1 or por_pagina < 1 or por_pagina > maximo:
        raise ApiError(
            "PAGINACION_INVALIDA",
            f"pagina debe ser >= 1 y por_pagina entre 1 y {maximo}",
            400,
        )
    return pagina, por_pagina
