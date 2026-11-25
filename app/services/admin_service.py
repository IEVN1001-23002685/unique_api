"""Administración de catálogos, historial de clientes y bitácora (M22)."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    Bitacora,
    CausaMerma,
    CategoriaMaterial,
    CategoriaProducto,
    Color,
    InventarioMaterial,
    Material,
    Merma,
    Pedido,
    Producto,
    Rol,
    Talla,
    TarifaEnvio,
    Usuario,
    Venta,
    VarianteProducto,
)
from app.models.base import ahora_utc
from app.services.bitacora_service import registrar_bitacora
from app.utils.errores import ApiError

CATALOGOS = {
    "color": Color,
    "talla": Talla,
    "categoria-producto": CategoriaProducto,
    "categoria-material": CategoriaMaterial,
    "causa-merma": CausaMerma,
    "tarifa-envio": TarifaEnvio,
}

CAMPOS = {
    "color": ("codigo", "nombre", "hex", "es_comercial"),
    "talla": ("codigo", "nombre", "orden"),
    "categoria-producto": ("nombre", "prefijo_sku", "usa_tallas", "activa"),
    "categoria-material": ("nombre", "descripcion"),
    "causa-merma": ("nombre", "aplica_a", "etapa_sugerida", "activa"),
    "tarifa-envio": ("nombre", "cp_inicio", "cp_fin", "costo", "dias_estimados", "activa"),
}

CODIGOS_SKU = ("color", "talla", "categoria-producto")


def _modelo(catalogo):
    modelo = CATALOGOS.get(catalogo)
    if modelo is None:
        raise ApiError("CATALOGO_NO_ENCONTRADO", "Catálogo no encontrado", 404)
    return modelo


def _serializar(fila, catalogo) -> dict:
    datos = {"id": fila.id, "creado_en": fila.creado_en.isoformat()}
    for campo in CAMPOS[catalogo]:
        valor = getattr(fila, campo)
        if catalogo == "tarifa-envio" and campo == "costo":
            valor = f"{Decimal(valor):.2f}"
        elif isinstance(valor, datetime):
            valor = valor.isoformat()
        datos[campo] = valor
    if catalogo in ("categoria-producto", "causa-merma", "tarifa-envio"):
        datos["activa"] = fila.activa
    return datos


def listar(catalogo, filtros=None, pagina=1, por_pagina=20) -> dict:
    modelo = _modelo(catalogo)
    filtros = filtros or {}
    consulta = select(modelo)
    if "activa" in CAMPOS[catalogo] and filtros.get("activa") is not None:
        consulta = consulta.where(modelo.activa == filtros["activa"])
    if filtros.get("q"):
        consulta = consulta.where(modelo.nombre.like(f"%{filtros['q']}%"))
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.session.execute(
        consulta.order_by(modelo.id)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars().all()
    return {
        "items": [_serializar(fila, catalogo) for fila in filas],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def obtener(catalogo, elemento_id: int) -> dict:
    modelo = _modelo(catalogo)
    fila = db.session.get(modelo, elemento_id)
    if fila is None:
        raise ApiError("ELEMENTO_NO_ENCONTRADO", "Elemento no encontrado", 404)
    return _serializar(fila, catalogo)


def _validar_tarifa(catalogo, datos, excluir_id=None):
    if catalogo != "tarifa-envio":
        return
    inicio, fin = datos["cp_inicio"], datos["cp_fin"]
    if inicio > fin:
        raise ApiError("RANGO_INVALIDO", "El código postal inicial debe ser menor al final", 422)
    consulta = select(TarifaEnvio.id).where(
        TarifaEnvio.cp_inicio <= fin,
        TarifaEnvio.cp_fin >= inicio,
    )
    if excluir_id is not None:
        consulta = consulta.where(TarifaEnvio.id != excluir_id)
    if db.session.scalar(consulta.limit(1)) is not None:
        raise ApiError(
            "RANGO_TARIFA_SOLAPADO",
            "El rango de códigos postales se solapa con otra tarifa",
            409,
        )


def crear(catalogo, datos: dict, usuario_id, ip=None) -> dict:
    modelo = _modelo(catalogo)
    _validar_tarifa(catalogo, datos)
    fila = modelo(**{campo: datos[campo] for campo in CAMPOS[catalogo] if campo in datos})
    db.session.add(fila)
    db.session.flush()
    registrar_bitacora(
        usuario_id,
        "CATALOGO_CREADO",
        catalogo,
        fila.id,
        {"campos": sorted(datos)},
        ip,
    )
    db.session.commit()
    return _serializar(fila, catalogo)


def _relaciones(catalogo, elemento_id: int) -> list:
    consultas = {
        "color": [
            (VarianteProducto, VarianteProducto.color_id),
            (InventarioMaterial, InventarioMaterial.color_id),
        ],
        "talla": [
            (VarianteProducto, VarianteProducto.talla_id),
        ],
        "categoria-producto": [
            (Producto, Producto.categoria_id),
        ],
        "categoria-material": [
            (Material, Material.categoria_material_id),
        ],
        "causa-merma": [
            (Merma, Merma.causa_id),
        ],
        "tarifa-envio": [
            (Venta, Venta.tarifa_envio_id),
        ],
    }
    resultados = []
    for modelo, columna in consultas.get(catalogo, []):
        total = db.session.scalar(select(func.count()).where(columna == elemento_id)) or 0
        if total:
            resultados.append({"entidad": modelo.__tablename__, "registros": int(total)})
    return resultados


def actualizar(catalogo, elemento_id: int, datos: dict, usuario_id, ip=None) -> dict:
    modelo = _modelo(catalogo)
    fila = db.session.get(modelo, elemento_id)
    if fila is None:
        raise ApiError("ELEMENTO_NO_ENCONTRADO", "Elemento no encontrado", 404)
    if catalogo in CODIGOS_SKU:
        for campo in ("codigo", "prefijo_sku"):
            if campo in datos and str(getattr(fila, campo)) != str(datos[campo]):
                raise ApiError(
                    "CODIGO_SKU_INMUTABLE",
                    "El código usado en SKU no puede modificarse",
                    409,
                )
    if catalogo == "categoria-producto" and fila.activa and datos.get("activa") is False:
        if _relaciones(catalogo, elemento_id):
            raise ApiError(
                "CATALOGO_EN_USO",
                "No se puede desactivar una categoría con productos relacionados",
                409,
            )
    if catalogo == "tarifa-envio":
        valores = {campo: datos.get(campo, getattr(fila, campo)) for campo in CAMPOS[catalogo]}
        _validar_tarifa(catalogo, valores, excluir_id=elemento_id)
    for campo in CAMPOS[catalogo]:
        if campo in datos:
            setattr(fila, campo, datos[campo])
    registrar_bitacora(
        usuario_id,
        "CATALOGO_ACTUALIZADO",
        catalogo,
        elemento_id,
        {"campos": sorted(datos)},
        ip,
    )
    db.session.commit()
    return _serializar(fila, catalogo)


def eliminar(catalogo, elemento_id: int, usuario_id, ip=None) -> None:
    modelo = _modelo(catalogo)
    fila = db.session.get(modelo, elemento_id)
    if fila is None:
        raise ApiError("ELEMENTO_NO_ENCONTRADO", "Elemento no encontrado", 404)
    relaciones = _relaciones(catalogo, elemento_id)
    if relaciones:
        raise ApiError(
            "CATALOGO_EN_USO",
            "El catálogo tiene registros relacionados",
            409,
            relaciones,
        )
    registrar_bitacora(
        usuario_id,
        "CATALOGO_ELIMINADO",
        catalogo,
        elemento_id,
        {"tipo": catalogo},
        ip,
    )
    db.session.delete(fila)
    db.session.commit()


def cliente_detalle(cliente_id: int) -> dict:
    rol_id = db.session.scalar(select(Rol.id).where(Rol.codigo == "CLIENTE"))
    cliente = db.session.get(Usuario, cliente_id)
    if cliente is None or cliente.rol_id != rol_id:
        raise ApiError("CLIENTE_NO_ENCONTRADO", "Cliente no encontrado", 404)
    ventas = db.session.execute(
        select(Venta)
        .where(Venta.usuario_id == cliente_id)
        .order_by(Venta.fecha.desc())
        .limit(20)
    ).scalars().all()
    pedidos = db.session.execute(
        select(Pedido)
        .join(Venta, Venta.id == Pedido.venta_id)
        .where(Venta.usuario_id == cliente_id)
        .order_by(Pedido.id.desc())
        .limit(20)
    ).scalars().all()
    total = db.session.scalar(
        select(func.coalesce(func.sum(Venta.total), 0)).where(
            Venta.usuario_id == cliente_id, Venta.estado == "ACTIVA"
        )
    ) or Decimal("0")
    return {
        "cliente": {
            "id": cliente.id,
            "nombre": cliente.nombre,
            "correo": cliente.correo,
            "telefono": cliente.telefono,
            "estado_cuenta": cliente.estado_cuenta,
            "creado_en": cliente.creado_en.isoformat(),
        },
        "resumen": {
            "ventas": len(ventas),
            "pedidos": len(pedidos),
            "importe_total": f"{Decimal(total):.2f}",
        },
        "ventas": [
            {
                "id": venta.id,
                "folio": venta.folio,
                "fecha": venta.fecha.isoformat(),
                "estado": venta.estado,
                "total": f"{Decimal(venta.total):.2f}",
            }
            for venta in ventas
        ],
        "pedidos": [
            {
                "id": pedido.id,
                "venta_folio": pedido.venta.folio,
                "estado": pedido.estado,
                "prioridad": pedido.prioridad,
                "fecha_promesa": (
                    pedido.fecha_promesa.isoformat() if pedido.fecha_promesa else None
                ),
            }
            for pedido in pedidos
        ],
    }


def listar_bitacora(filtros=None, pagina=1, por_pagina=20) -> dict:
    filtros = filtros or {}
    consulta = select(Bitacora)
    if filtros.get("accion"):
        consulta = consulta.where(Bitacora.accion == filtros["accion"])
    if filtros.get("entidad"):
        consulta = consulta.where(Bitacora.entidad == filtros["entidad"])
    if filtros.get("usuario_id"):
        consulta = consulta.where(Bitacora.usuario_id == filtros["usuario_id"])
    if filtros.get("desde"):
        consulta = consulta.where(
            Bitacora.fecha >= datetime.combine(filtros["desde"], time.min)
        )
    if filtros.get("hasta"):
        consulta = consulta.where(
            Bitacora.fecha
            < datetime.combine(filtros["hasta"] + timedelta(days=1), time.min)
        )
    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.session.execute(
        consulta.order_by(Bitacora.id.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).scalars().all()
    return {
        "items": [
            {
                "id": fila.id,
                "usuario_id": fila.usuario_id,
                "accion": fila.accion,
                "entidad": fila.entidad,
                "entidad_id": fila.entidad_id,
                "detalle": fila.detalle,
                "ip": fila.ip,
                "fecha": fila.fecha.isoformat(),
            }
            for fila in filas
        ],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }
