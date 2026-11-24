"""Catálogo de materiales, inventario en unidades base, lotes y kardex (M15).

Las operaciones ``registrar_entrada``, ``registrar_rechazo_recepcion`` y
``consumir_peps`` solo hacen ``flush``: el módulo que las invoca (M14 o M16)
debe confirmar la transacción completa. ``generar_requisicion_automatica``
también deja la escritura pendiente de confirmación para el llamador.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_CEILING

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    CausaMerma,
    CategoriaMaterial,
    Color,
    DisenoBordadoHilo,
    EmpaqueRegla,
    InventarioMaterial,
    LoteMaterial,
    Material,
    Merma,
    MovimientoMaterial,
    OrdenCompra,
    OrdenCompraLinea,
    OrdenMaterial,
    OrdenProduccion,
    Proveedor,
    ProveedorMaterial,
    RecetaLinea,
    Requisicion,
    RequisicionLinea,
)
from app.models.base import ahora_utc
from app.services import alertas_service, bitacora_service
from app.utils.dinero import decimal_valor, dinero, material as material_texto, redondear
from app.utils.errores import ApiError
from app.utils.folios import generar_folio

ESTADOS_ORDEN_ABIERTOS = ("PLANEADA", "LISTA", "EN_PROCESO", "EN_REVISION")
ESTADOS_ORDEN_CONFIRMADOS = ("LISTA", "EN_PROCESO", "EN_REVISION")
ESTADOS_OC_PENDIENTES = ("EMITIDA", "PARCIAL")
COLORES_MATERIAL = ("BL", "NG", "GR")


def _d(valor) -> Decimal:
    return decimal_valor(valor)


def _costo_texto(valor) -> str:
    """Costo unitario base con hasta seis decimales, sin ceros sobrantes."""
    return f"{redondear(valor, '0.000001'):.6f}".rstrip("0").rstrip(".")


def _fecha(valor):
    if isinstance(valor, date):
        return valor
    if valor is None:
        return ahora_utc().date()
    try:
        return date.fromisoformat(str(valor))
    except ValueError:
        raise ApiError("FECHA_INVALIDA", "La fecha debe estar en formato ISO", 400)


def _paginacion(filtros):
    paginado = "pagina" in filtros or "por_pagina" in filtros
    try:
        pagina = int(filtros.get("pagina", 1))
        por_pagina = int(filtros.get("por_pagina", 20))
    except (TypeError, ValueError):
        raise ApiError("PAGINACION_INVALIDA", "pagina y por_pagina deben ser enteros", 400)
    if pagina < 1 or por_pagina < 1 or por_pagina > 100:
        raise ApiError(
            "PAGINACION_INVALIDA",
            "pagina debe ser >= 1 y por_pagina entre 1 y 100",
            400,
        )
    return paginado, pagina, por_pagina


def _resultado(filas, serializar, paginado, pagina, por_pagina, total=None):
    if not paginado:
        return [serializar(fila) for fila in filas]
    return {
        "items": [serializar(fila) for fila in filas],
        "total": int(total or 0),
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


def _proveedor_principal(material_id: int):
    hoy = date.today()
    fila = db.session.execute(
        select(ProveedorMaterial, Proveedor)
        .join(Proveedor, Proveedor.id == ProveedorMaterial.proveedor_id)
        .where(
            ProveedorMaterial.material_id == material_id,
            ProveedorMaterial.es_principal.is_(True),
            ProveedorMaterial.activo.is_(True),
            Proveedor.eliminado_en.is_(None),
            or_(
                ProveedorMaterial.vigencia_hasta.is_(None),
                ProveedorMaterial.vigencia_hasta >= hoy,
            ),
        )
        .order_by(ProveedorMaterial.plazo_dias, ProveedorMaterial.id)
    ).first()
    if fila is None:
        return None, 0
    return fila[0], int(fila[0].plazo_dias or 0)


def _metricas(inventario_material_id: int) -> dict:
    """Calcula físico, reservado, compras, consumo y semáforo desde MySQL."""
    inventario = db.session.get(InventarioMaterial, inventario_material_id)
    if inventario is None:
        raise ApiError("INVENTARIO_MATERIAL_NO_ENCONTRADO", "Inventario no encontrado", 404)

    fisico = _d(
        db.session.scalar(
            select(func.coalesce(func.sum(LoteMaterial.cantidad_base_disponible), 0)).where(
                LoteMaterial.inventario_material_id == inventario_material_id
            )
        )
    )
    reservado = max(
        Decimal("0"),
        _d(
            db.session.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            OrdenMaterial.cantidad_reservada
                            - OrdenMaterial.cantidad_consumida
                        ),
                        0,
                    )
                )
                .join(OrdenProduccion, OrdenProduccion.id == OrdenMaterial.orden_id)
                .where(
                    OrdenMaterial.inventario_material_id == inventario_material_id,
                    OrdenProduccion.estado.in_(ESTADOS_ORDEN_ABIERTOS),
                )
            )
        ),
    )
    confirmadas = max(
        Decimal("0"),
        _d(
            db.session.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            OrdenMaterial.cantidad_reservada
                            - OrdenMaterial.cantidad_consumida
                        ),
                        0,
                    )
                )
                .join(OrdenProduccion, OrdenProduccion.id == OrdenMaterial.orden_id)
                .where(
                    OrdenMaterial.inventario_material_id == inventario_material_id,
                    OrdenProduccion.estado.in_(ESTADOS_ORDEN_CONFIRMADOS),
                )
            )
        ),
    )
    compra_pendiente, aceptada = db.session.execute(
        select(
            func.coalesce(func.sum(OrdenCompraLinea.cantidad_compra), 0),
            func.coalesce(func.sum(OrdenCompraLinea.cantidad_base_aceptada), 0),
        )
        .join(OrdenCompra, OrdenCompra.id == OrdenCompraLinea.orden_compra_id)
        .where(
            OrdenCompraLinea.inventario_material_id == inventario_material_id,
            OrdenCompra.estado.in_(ESTADOS_OC_PENDIENTES),
        )
    ).one()
    en_compra = max(
        Decimal("0"),
        _d(compra_pendiente) * _d(inventario.material.factor_compra_base)
        - _d(aceptada),
    )
    consumo_30d = _d(
        db.session.scalar(
            select(func.coalesce(func.sum(-MovimientoMaterial.cantidad_base), 0))
            .join(LoteMaterial, LoteMaterial.id == MovimientoMaterial.lote_id)
            .where(
                LoteMaterial.inventario_material_id == inventario_material_id,
                MovimientoMaterial.tipo == "CONSUMO",
                MovimientoMaterial.fecha >= ahora_utc() - timedelta(days=30),
            )
        )
    )
    consumo = (
        consumo_30d / Decimal("30")
        if consumo_30d > 0
        else _d(inventario.consumo_diario_manual)
    )
    if consumo < 0:
        consumo = Decimal("0")

    principal, plazo = _proveedor_principal(inventario.material_id)
    minimo_compra = _d(principal.minimo_compra) if principal is not None else None
    factor = _d(inventario.material.factor_compra_base)
    stock_minimo = _d(inventario.stock_minimo)
    stock_seguridad = _d(inventario.stock_seguridad)
    punto_reorden = consumo * Decimal(plazo) + stock_seguridad
    disponible = max(Decimal("0"), fisico - reservado)
    posicion = disponible + en_compra

    if disponible <= stock_minimo or confirmadas > fisico:
        semaforo = "ROJO"
    elif punto_reorden > 0 and disponible <= punto_reorden:
        semaforo = "AMBAR"
    else:
        semaforo = "VERDE"

    return {
        "inventario": inventario,
        "fisico": fisico,
        "reservado": reservado,
        "confirmadas": confirmadas,
        "disponible": disponible,
        "en_compra": en_compra,
        "posicion": posicion,
        "consumo_diario": consumo,
        "punto_reorden": punto_reorden,
        "cobertura_dias": (
            (disponible / consumo).quantize(Decimal("0.01")) if consumo > 0 else None
        ),
        "semaforo": semaforo,
        "proveedor_principal_id": principal.proveedor_id if principal else None,
        "plazo_dias": plazo,
        "minimo_compra": minimo_compra,
        "factor_compra_base": factor,
    }


def serializar_inventario(fila, incluir_costos=True, metricas=None) -> dict:
    """Serializa una fila de inventario con importes como cadenas decimales."""
    datos = metricas or _metricas(fila.id)
    material = fila.material
    salida = {
        "id": fila.id,
        "material_id": fila.material_id,
        "material_codigo": material.codigo,
        "material_nombre": material.nombre,
        "categoria": material.categoria.nombre if material.categoria else None,
        "color_id": fila.color_id,
        "color_codigo": fila.color.codigo if fila.color else None,
        "unidad_base": material.unidad_base,
        "fisico": material_texto(datos["fisico"]),
        "reservado": material_texto(datos["reservado"]),
        "disponible": material_texto(datos["disponible"]),
        "en_compra": material_texto(datos["en_compra"]),
        "posicion": material_texto(datos["posicion"]),
        "consumo_diario": material_texto(datos["consumo_diario"]),
        "punto_reorden": (
            material_texto(datos["punto_reorden"])
            if datos["punto_reorden"] is not None
            else None
        ),
        "cobertura_dias": (
            str(datos["cobertura_dias"])
            if datos["cobertura_dias"] is not None
            else None
        ),
        "semaforo": datos["semaforo"],
        "stock_minimo": material_texto(fila.stock_minimo),
        "stock_seguridad": material_texto(fila.stock_seguridad),
        "proveedor_principal_id": datos["proveedor_principal_id"],
        "plazo_dias": datos["plazo_dias"],
        "factor_compra_base": material_texto(datos["factor_compra_base"]),
        "activo": fila.activo,
    }
    if incluir_costos:
        salida["costo_estandar_base"] = _costo_texto(material.costo_estandar_base)
        salida["minimo_compra"] = (
            material_texto(datos["minimo_compra"])
            if datos["minimo_compra"] is not None
            else None
        )
    return salida


def listar(filtros=None, incluir_costos=True):
    """Catálogo de materiales; con paginación devuelve el contrato de listas."""
    filtros = filtros or {}
    paginado, pagina, por_pagina = _paginacion(filtros)
    condiciones = []
    if not filtros.get("incluir_inactivos"):
        condiciones.append(Material.activo.is_(True))
    if filtros.get("categoria"):
        condiciones.append(
            Material.categoria.has(
                CategoriaMaterial.nombre == str(filtros["categoria"])
            )
        )
    if filtros.get("codigo"):
        condiciones.append(Material.codigo == filtros["codigo"])
    if filtros.get("por_color") is not None:
        condiciones.append(Material.por_color.is_(bool(filtros["por_color"])))
    if filtros.get("q"):
        busqueda = f"%{filtros['q']}%"
        condiciones.append(
            or_(Material.codigo.like(busqueda), Material.nombre.like(busqueda))
        )

    consulta = select(Material).where(*condiciones).order_by(Material.codigo, Material.id)
    if paginado:
        total = db.session.scalar(
            select(func.count()).select_from(Material).where(*condiciones)
        )
        filas = db.session.execute(
            consulta.offset((pagina - 1) * por_pagina).limit(por_pagina)
        ).scalars()
    else:
        total = None
        filas = db.session.execute(consulta).scalars()

    def serializar(fila):
        return {
            "id": fila.id,
            "categoria_material_id": fila.categoria_material_id,
            "categoria": fila.categoria.nombre if fila.categoria else None,
            "codigo": fila.codigo,
            "nombre": fila.nombre,
            "unidad_base": fila.unidad_base,
            "unidad_compra": fila.unidad_compra,
            "factor_compra_base": material_texto(fila.factor_compra_base),
            "costo_estandar_base": _costo_texto(fila.costo_estandar_base),
            "merma_estandar_pct": material_texto(fila.merma_estandar_pct),
            "por_color": fila.por_color,
            "activo": fila.activo,
            "eliminado_en": fila.eliminado_en.isoformat() if fila.eliminado_en else None,
        }

    resultado = _resultado(filas, serializar, paginado, pagina, por_pagina, total)
    if not incluir_costos:
        if isinstance(resultado, dict):
            for fila in resultado["items"]:
                fila.pop("costo_estandar_base", None)
        else:
            for fila in resultado:
                fila.pop("costo_estandar_base", None)
    return resultado


def obtener(id: int) -> Material:
    material = db.session.get(Material, id)
    if material is None or material.eliminado_en is not None:
        raise ApiError("MATERIAL_NO_ENCONTRADO", "Material no encontrado", 404)
    return material


def _asegurar_inventario(material: Material) -> None:
    codigos = COLORES_MATERIAL if material.por_color else ("NA",)
    colores = {
        fila.codigo: fila
        for fila in db.session.execute(
            select(Color).where(Color.codigo.in_(codigos))
        ).scalars()
    }
    if len(colores) != len(codigos):
        raise ApiError(
            "CATALOGO_COLORES_INCOMPLETO",
            "Faltan colores base para generar el inventario del material",
            422,
        )
    existentes = set(
        db.session.scalars(
            select(InventarioMaterial.color_id).where(
                InventarioMaterial.material_id == material.id
            )
        )
    )
    for codigo in codigos:
        color = colores[codigo]
        if color.id not in existentes:
            db.session.add(
                InventarioMaterial(
                    material_id=material.id,
                    color_id=color.id,
                    stock_minimo=0,
                    stock_seguridad=0,
                    activo=True,
                )
            )


def _validar_categoria(categoria_id) -> CategoriaMaterial:
    categoria = db.session.get(CategoriaMaterial, categoria_id)
    if categoria is None:
        raise ApiError("CATEGORIA_MATERIAL_NO_ENCONTRADA", "Categoría no encontrada", 422)
    return categoria


def crear(datos, usuario_id, ip=None) -> Material:
    _validar_categoria(datos["categoria_material_id"])
    if db.session.scalar(select(Material.id).where(Material.codigo == datos["codigo"])):
        raise ApiError("MATERIAL_DUPLICADO", "El código de material ya existe", 409)
    material = Material(
        categoria_material_id=datos["categoria_material_id"],
        codigo=datos["codigo"],
        nombre=datos["nombre"],
        unidad_base=datos["unidad_base"],
        unidad_compra=datos["unidad_compra"],
        factor_compra_base=datos["factor_compra_base"],
        costo_estandar_base=datos["costo_estandar_base"],
        merma_estandar_pct=datos["merma_estandar_pct"],
        por_color=datos.get("por_color", False),
        activo=datos.get("activo", True),
    )
    db.session.add(material)
    db.session.flush()
    _asegurar_inventario(material)
    bitacora_service.registrar_bitacora(
        usuario_id,
        "MATERIAL_CREADO",
        "material",
        material.id,
        {"codigo": material.codigo, "por_color": material.por_color},
        ip,
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("MATERIAL_DUPLICADO", "El código de material ya existe", 409)
    return material


CAMPOS_EDITABLES_MATERIAL = (
    "categoria_material_id",
    "codigo",
    "nombre",
    "unidad_base",
    "unidad_compra",
    "factor_compra_base",
    "costo_estandar_base",
    "merma_estandar_pct",
    "por_color",
    "activo",
)


def actualizar(id: int, datos, usuario_id, ip=None) -> Material:
    material = obtener(id)
    cambios = {}
    for campo in CAMPOS_EDITABLES_MATERIAL:
        if campo not in datos:
            continue
        valor = datos[campo]
        if campo == "categoria_material_id":
            _validar_categoria(valor)
        anterior = getattr(material, campo)
        if str(anterior) != str(valor):
            cambios[campo] = {"anterior": str(anterior), "nuevo": str(valor)}
        setattr(material, campo, valor)
    if "codigo" in datos and db.session.scalar(
        select(Material.id).where(Material.codigo == datos["codigo"], Material.id != id)
    ):
        db.session.rollback()
        raise ApiError("MATERIAL_DUPLICADO", "El código de material ya existe", 409)
    if "por_color" in datos:
        _asegurar_inventario(material)
    bitacora_service.registrar_bitacora(
        usuario_id, "MATERIAL_ACTUALIZADO", "material", material.id, cambios, ip
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("MATERIAL_DUPLICADO", "El código de material ya existe", 409)
    return material


def _referencias_directas(material_id: int) -> bool:
    inventarios = select(InventarioMaterial.id).where(
        InventarioMaterial.material_id == material_id
    )
    consultas = (
        select(LoteMaterial.id)
        .join(InventarioMaterial, InventarioMaterial.id == LoteMaterial.inventario_material_id)
        .where(InventarioMaterial.material_id == material_id)
        .limit(1),
        select(RecetaLinea.id).where(RecetaLinea.material_id == material_id).limit(1),
        select(ProveedorMaterial.id)
        .where(ProveedorMaterial.material_id == material_id)
        .limit(1),
        select(EmpaqueRegla.id).where(EmpaqueRegla.material_id == material_id).limit(1),
        select(DisenoBordadoHilo.id)
        .where(DisenoBordadoHilo.material_id == material_id)
        .limit(1),
        select(OrdenMaterial.id)
        .where(OrdenMaterial.inventario_material_id.in_(inventarios))
        .limit(1),
        select(OrdenCompraLinea.id)
        .where(OrdenCompraLinea.inventario_material_id.in_(inventarios))
        .limit(1),
        select(RequisicionLinea.id)
        .where(RequisicionLinea.inventario_material_id.in_(inventarios))
        .limit(1),
        select(Merma.id)
        .where(Merma.inventario_material_id.in_(inventarios))
        .limit(1),
    )
    return any(db.session.scalar(consulta) is not None for consulta in consultas)


def desactivar(id: int, usuario_id, ip=None) -> None:
    material = obtener(id)
    modo = "LOGICO"
    if _referencias_directas(material.id):
        material.activo = False
        material.eliminado_en = ahora_utc()
        db.session.execute(
            update(InventarioMaterial)
            .where(InventarioMaterial.material_id == material.id)
            .values(activo=False)
        )
    else:
        db.session.execute(
            delete(InventarioMaterial).where(InventarioMaterial.material_id == material.id)
        )
        db.session.delete(material)
        modo = "FISICO"
    bitacora_service.registrar_bitacora(
        usuario_id,
        "MATERIAL_DESACTIVADO",
        "material",
        material.id,
        {"modo": modo, "codigo": material.codigo},
        ip,
    )
    db.session.commit()


def listar_inventario(filtros=None, incluir_costos=True):
    filtros = filtros or {}
    paginado, pagina, por_pagina = _paginacion(filtros)
    condiciones = []
    if filtros.get("material_id"):
        condiciones.append(InventarioMaterial.material_id == filtros["material_id"])
    if filtros.get("color_id"):
        condiciones.append(InventarioMaterial.color_id == filtros["color_id"])
    if filtros.get("activo") is not None:
        condiciones.append(InventarioMaterial.activo.is_(bool(filtros["activo"])))
    elif not filtros.get("incluir_inactivos"):
        condiciones.append(InventarioMaterial.activo.is_(True))
    if filtros.get("categoria"):
        condiciones.append(
            InventarioMaterial.material.has(
                Material.categoria.has(
                    CategoriaMaterial.nombre == str(filtros["categoria"])
                )
            )
        )

    consulta = (
        select(InventarioMaterial)
        .join(Material, Material.id == InventarioMaterial.material_id)
        .where(*condiciones)
        .order_by(Material.codigo, InventarioMaterial.color_id, InventarioMaterial.id)
    )
    if paginado:
        total = db.session.scalar(
            select(func.count())
            .select_from(InventarioMaterial)
            .join(Material, Material.id == InventarioMaterial.material_id)
            .where(*condiciones)
        )
        filas = db.session.execute(
            consulta.offset((pagina - 1) * por_pagina).limit(por_pagina)
        ).scalars()
    else:
        total = None
        filas = db.session.execute(consulta).scalars()

    def serializar(fila):
        metricas = _metricas(fila.id)
        metricas["inventario"] = fila
        return serializar_inventario(fila, incluir_costos, metricas)

    return _resultado(filas, serializar, paginado, pagina, por_pagina, total)


def obtener_inventario(id: int) -> InventarioMaterial:
    inventario = db.session.get(InventarioMaterial, id)
    if inventario is None:
        raise ApiError("INVENTARIO_MATERIAL_NO_ENCONTRADO", "Inventario no encontrado", 404)
    return inventario


def listar_lotes(filtros=None):
    filtros = filtros or {}
    paginado, pagina, por_pagina = _paginacion(filtros)
    condiciones = []
    if filtros.get("inventario_material_id"):
        condiciones.append(
            LoteMaterial.inventario_material_id == filtros["inventario_material_id"]
        )
    if filtros.get("material_id"):
        condiciones.append(
            LoteMaterial.inventario_material.has(
                InventarioMaterial.material_id == filtros["material_id"]
            )
        )
    if filtros.get("color_id"):
        condiciones.append(
            LoteMaterial.inventario_material.has(
                InventarioMaterial.color_id == filtros["color_id"]
            )
        )
    if filtros.get("proveedor_id"):
        condiciones.append(LoteMaterial.proveedor_id == filtros["proveedor_id"])
    if filtros.get("folio"):
        condiciones.append(LoteMaterial.folio.like(f"%{filtros['folio']}%"))
    if filtros.get("fecha_desde"):
        condiciones.append(LoteMaterial.fecha_entrada >= _fecha(filtros["fecha_desde"]))
    if filtros.get("fecha_hasta"):
        condiciones.append(LoteMaterial.fecha_entrada <= _fecha(filtros["fecha_hasta"]))

    consulta = (
        select(LoteMaterial)
        .where(*condiciones)
        .order_by(LoteMaterial.fecha_entrada, LoteMaterial.id)
    )
    if paginado:
        total = db.session.scalar(
            select(func.count()).select_from(LoteMaterial).where(*condiciones)
        )
        filas = db.session.execute(
            consulta.offset((pagina - 1) * por_pagina).limit(por_pagina)
        ).scalars()
    else:
        total = None
        filas = db.session.execute(consulta).scalars()
    return _resultado(filas, lambda fila: fila, paginado, pagina, por_pagina, total)


def listar_movimientos(filtros=None):
    filtros = filtros or {}
    paginado, pagina, por_pagina = _paginacion(filtros)
    condiciones = []
    if filtros.get("lote_id"):
        condiciones.append(MovimientoMaterial.lote_id == filtros["lote_id"])
    if filtros.get("inventario_material_id"):
        condiciones.append(
            MovimientoMaterial.lote.has(
                LoteMaterial.inventario_material_id == filtros["inventario_material_id"]
            )
        )
    if filtros.get("material_id"):
        condiciones.append(
            MovimientoMaterial.lote.has(
                LoteMaterial.inventario_material.has(
                    InventarioMaterial.material_id == filtros["material_id"]
                )
            )
        )
    if filtros.get("color_id"):
        condiciones.append(
            MovimientoMaterial.lote.has(
                LoteMaterial.inventario_material.has(
                    InventarioMaterial.color_id == filtros["color_id"]
                )
            )
        )
    if filtros.get("tipo"):
        condiciones.append(MovimientoMaterial.tipo == filtros["tipo"])
    if filtros.get("fecha_desde"):
        condiciones.append(
            MovimientoMaterial.fecha
            >= datetime.combine(_fecha(filtros["fecha_desde"]), time.min)
        )
    if filtros.get("fecha_hasta"):
        condiciones.append(
            MovimientoMaterial.fecha
            < datetime.combine(_fecha(filtros["fecha_hasta"]) + timedelta(days=1), time.min)
        )

    consulta = (
        select(MovimientoMaterial)
        .where(*condiciones)
        .order_by(MovimientoMaterial.fecha.desc(), MovimientoMaterial.id.desc())
    )
    if paginado:
        total = db.session.scalar(
            select(func.count()).select_from(MovimientoMaterial).where(*condiciones)
        )
        filas = db.session.execute(
            consulta.offset((pagina - 1) * por_pagina).limit(por_pagina)
        ).scalars()
    else:
        total = None
        filas = db.session.execute(consulta).scalars()
    return _resultado(filas, lambda fila: fila, paginado, pagina, por_pagina, total)


def registrar_entrada(
    inventario_id,
    cantidad_aceptada,
    costo_unitario_base,
    fecha_entrada,
    proveedor_id,
    recepcion_linea_id,
    usuario_id,
    motivo=None,
) -> LoteMaterial:
    """Crea un lote, su folio y su movimiento ENTRADA; no confirma la transacción."""
    inventario = db.session.get(InventarioMaterial, inventario_id)
    if inventario is None:
        raise ApiError("INVENTARIO_MATERIAL_NO_ENCONTRADO", "Inventario no encontrado", 404)
    cantidad = _d(cantidad_aceptada)
    costo = _d(costo_unitario_base)
    if cantidad <= 0:
        raise ApiError("CANTIDAD_INVALIDA", "La cantidad aceptada debe ser mayor a cero", 422)
    if costo < 0:
        raise ApiError("COSTO_INVALIDO", "El costo unitario no puede ser negativo", 422)
    lote = LoteMaterial(
        inventario_material_id=inventario_id,
        folio=generar_folio("LT"),
        recepcion_linea_id=recepcion_linea_id,
        proveedor_id=proveedor_id,
        fecha_entrada=_fecha(fecha_entrada),
        cantidad_base_recibida=cantidad,
        cantidad_base_disponible=cantidad,
        costo_total=redondear(cantidad * costo, "0.01"),
        costo_unitario_base=costo,
        estado="DISPONIBLE",
    )
    db.session.add(lote)
    db.session.flush()
    db.session.add(
        MovimientoMaterial(
            lote_id=lote.id,
            tipo="ENTRADA",
            cantidad_base=cantidad,
            costo_unitario_base=costo,
            documento_tipo="RECEPCION" if recepcion_linea_id else "AJUSTE",
            documento_id=int(recepcion_linea_id or inventario_id),
            motivo=motivo,
            usuario_id=usuario_id,
            fecha=ahora_utc(),
        )
    )
    db.session.flush()
    return lote


def _causa_rechazo(causa_merma_id=None) -> CausaMerma:
    if causa_merma_id:
        causa = db.session.get(CausaMerma, causa_merma_id)
        if causa is not None:
            return causa
    causa = db.session.execute(
        select(CausaMerma)
        .where(
            CausaMerma.nombre.in_(("Rechazo en recepción", "Rechazo en recepcion"))
        )
        .order_by(CausaMerma.id)
    ).scalars().first()
    if causa is None:
        raise ApiError(
            "CAUSA_MERMA_NO_ENCONTRADA",
            "No existe la causa de merma 'Rechazo en recepción'",
            422,
        )
    return causa


def registrar_rechazo_recepcion(
    inventario_id,
    cantidad_rechazada,
    costo_unitario_base,
    recepcion_linea_id,
    usuario_id,
    motivo,
) -> Merma:
    """Registra la merma por rechazo; la cantidad rechazada nunca entra como lote."""
    if db.session.get(InventarioMaterial, inventario_id) is None:
        raise ApiError("INVENTARIO_MATERIAL_NO_ENCONTRADO", "Inventario no encontrado", 404)
    cantidad = _d(cantidad_rechazada)
    if cantidad <= 0:
        raise ApiError("CANTIDAD_INVALIDA", "La cantidad rechazada debe ser mayor a cero", 422)
    causa = _causa_rechazo()
    from app.services import merma_service

    return merma_service.registrar_merma(
        {
            "origen": "MATERIAL",
            "inventario_material_id": inventario_id,
            "recepcion_linea_id": recepcion_linea_id,
            "etapa": "RECEPCION",
            "causa_id": causa.id,
            "cantidad": cantidad,
            "costo_total": redondear(cantidad * _d(costo_unitario_base), "0.01"),
            "descripcion": motivo,
            "fecha": ahora_utc(),
            "folio_origen": f"recepción {recepcion_linea_id}",
        },
        usuario_id,
        descontar=False,
        confirmar=False,
    )


def consumir_peps(
    inventario_id,
    cantidad,
    documento_tipo,
    documento_id,
    usuario_id,
    motivo=None,
    tipo="CONSUMO",
) -> list:
    """Consume lotes por PEPS con FOR UPDATE; sin escribir si no hay suficiente."""
    requerida = _d(cantidad)
    if requerida <= 0:
        raise ApiError("CANTIDAD_INVALIDA", "La cantidad a consumir debe ser mayor a cero", 422)
    lotes = db.session.execute(
        select(LoteMaterial)
        .where(
            LoteMaterial.inventario_material_id == inventario_id,
            LoteMaterial.estado == "DISPONIBLE",
            LoteMaterial.cantidad_base_disponible > 0,
        )
        .order_by(LoteMaterial.fecha_entrada, LoteMaterial.id)
        .with_for_update()
    ).scalars().all()
    total = sum((_d(lote.cantidad_base_disponible) for lote in lotes), Decimal("0"))
    if total < requerida:
        raise ApiError(
            "MATERIAL_INSUFICIENTE",
            "No hay suficiente material disponible para el consumo",
            409,
            [
                {
                    "inventario_material_id": inventario_id,
                    "faltante": material_texto(requerida - total),
                }
            ],
        )

    restante = requerida
    consumo = []
    for lote in lotes:
        if restante <= 0:
            break
        disponible = _d(lote.cantidad_base_disponible)
        tomado = min(disponible, restante)
        lote.cantidad_base_disponible = disponible - tomado
        if lote.cantidad_base_disponible == 0:
            lote.estado = "AGOTADO"
        db.session.add(
            MovimientoMaterial(
                lote_id=lote.id,
                tipo=tipo,
                cantidad_base=-tomado,
                costo_unitario_base=lote.costo_unitario_base,
                documento_tipo=documento_tipo,
                documento_id=int(documento_id),
                motivo=motivo,
                usuario_id=usuario_id,
                fecha=ahora_utc(),
            )
        )
        consumo.append(
            {
                "lote_id": lote.id,
                "folio": lote.folio,
                "cantidad_base": material_texto(tomado),
                "costo_unitario_base": _costo_texto(lote.costo_unitario_base),
                "costo_total": dinero(tomado * _d(lote.costo_unitario_base)),
                "fecha_entrada": lote.fecha_entrada.isoformat(),
            }
        )
        restante -= tomado
    db.session.flush()
    return consumo


def _alerta_reorden(inventario_id, titulo, detalle):
    alerta = alertas_service.abrir(
        "MP_REORDEN",
        "PREVENTIVA",
        titulo,
        detalle,
        "inventario_material",
        inventario_id,
        rol_destino="ADMIN",
        clave_unica=f"MP_REORDEN:{inventario_id}",
        accion_sugerida="Emitir solicitud de compra",
    )
    if alerta is not None and alerta.estado != "ABIERTA":
        alerta.estado = "ABIERTA"
        alerta.atendida_por = None
        alerta.atendida_en = None


def generar_requisicion_automatica(inventario_id, usuario_id):
    """Genera una requisición ALERTA deduplicada al llegar al punto de reorden.

    El modelo no tiene una columna de clave de negocio, por eso se usa
    ``Requisicion.notas`` con el prefijo ``AUTO_REORDEN:``. No confirma la
    transacción: M14 o la tarea programada debe hacerlo.
    """
    inventario = db.session.get(InventarioMaterial, inventario_id)
    if inventario is None or not inventario.activo:
        return None
    datos = _metricas(inventario_id)
    if datos["punto_reorden"] <= 0 or datos["posicion"] > datos["punto_reorden"]:
        return None

    clave = f"AUTO_REORDEN:{inventario_id}"
    duplicada = db.session.execute(
        select(Requisicion.id)
        .join(RequisicionLinea, RequisicionLinea.requisicion_id == Requisicion.id)
        .where(
            Requisicion.notas == clave,
            Requisicion.estado.in_(("PENDIENTE", "EN_COTIZACION")),
            RequisicionLinea.inventario_material_id == inventario_id,
        )
    ).first()
    if duplicada is not None:
        return db.session.get(Requisicion, duplicada[0])

    principal, _plazo = _proveedor_principal(inventario.material_id)
    if principal is None:
        _alerta_reorden(
            inventario_id,
            "Material en punto de reorden sin proveedor principal",
            f"El inventario {inventario_id} requiere un proveedor principal.",
        )
        return None

    factor = datos["factor_compra_base"]
    if factor <= 0:
        return None
    faltante = max(Decimal("0"), datos["punto_reorden"] - datos["posicion"])
    presentaciones = int((faltante / factor).to_integral_value(rounding=ROUND_CEILING))
    sugerida = max(
        Decimal(presentaciones),
        datos["minimo_compra"] or Decimal("0"),
        Decimal("1"),
    ).quantize(Decimal("0.01"), rounding=ROUND_CEILING)

    requisicion = Requisicion(
        folio=generar_folio("REQ"),
        origen="ALERTA",
        estado="PENDIENTE",
        prioridad="URGENTE" if datos["semaforo"] == "ROJO" else "NORMAL",
        solicitada_por=usuario_id,
        fecha=ahora_utc(),
        notas=clave,
    )
    db.session.add(requisicion)
    db.session.flush()
    db.session.add(
        RequisicionLinea(
            requisicion_id=requisicion.id,
            inventario_material_id=inventario_id,
            cantidad_base_faltante=redondear(faltante, "0.0001"),
            cantidad_compra_sugerida=sugerida,
            cantidad_compra_atendida=0,
        )
    )
    _alerta_reorden(
        inventario_id,
        "Material en punto de reorden",
        f"El inventario {inventario_id} alcanzó su punto de reorden.",
    )
    db.session.flush()
    return requisicion


def ajustar(datos, usuario_id):
    """Conteo físico: genera un movimiento de corrección, nunca edita el kardex."""
    inventario = obtener_inventario(datos["inventario_material_id"])
    motivo = datos["motivo"]
    metricas = _metricas(inventario.id)
    contada = _d(datos["cantidad_contada"])
    diferencia = contada - metricas["fisico"]
    destino = "SIN_CAMBIO"

    if diferencia > 0:
        registrar_entrada(
            inventario.id,
            diferencia,
            inventario.material.costo_estandar_base,
            ahora_utc().date(),
            None,
            None,
            usuario_id,
            motivo=f"Ajuste por conteo: {motivo}",
        )
        destino = "ENTRADA"
    elif diferencia < 0:
        consumos = consumir_peps(
            inventario.id,
            -diferencia,
            "AJUSTE",
            inventario.id,
            usuario_id,
            motivo=f"Ajuste por conteo: {motivo}",
            tipo="AJUSTE",
        )
        destino = "AJUSTE"
        if datos.get("mandar_a_merma"):
            causa = None
            if datos.get("causa_merma_id"):
                causa = db.session.get(CausaMerma, datos["causa_merma_id"])
            if causa is None:
                causa = db.session.execute(
                    select(CausaMerma)
                    .where(CausaMerma.nombre.in_(("Daño en almacén", "Daño en almacen")))
                    .order_by(CausaMerma.id)
                ).scalars().first()
            if causa is None:
                raise ApiError(
                    "CAUSA_MERMA_NO_ENCONTRADA",
                    "No existe la causa de merma para el ajuste",
                    422,
                )
            from app.services import merma_service

            merma_service.registrar_merma(
                {
                    "origen": "MATERIAL",
                    "inventario_material_id": inventario.id,
                    "etapa": "ALMACEN",
                    "causa_id": causa.id,
                    "cantidad": -diferencia,
                    "costo_total": sum(
                        (_d(item["costo_total"]) for item in consumos), Decimal("0")
                    ),
                    "descripcion": motivo,
                    "fecha": ahora_utc(),
                },
                usuario_id,
                descontar=False,
                confirmar=False,
            )
            destino = "MERMA"

    bitacora_service.registrar_bitacora(
        usuario_id,
        "AJUSTE_INVENTARIO_MATERIAL",
        "inventario_material",
        inventario.id,
        {
            "fisico": material_texto(metricas["fisico"]),
            "contado": material_texto(contada),
            "diferencia": material_texto(diferencia),
            "motivo": motivo,
            "destino": destino,
        },
    )
    generar_requisicion_automatica(inventario.id, usuario_id)
    db.session.commit()
    return inventario


def actualizar_politica(id: int, datos, usuario_id, ip=None) -> InventarioMaterial:
    inventario = db.session.get(InventarioMaterial, id)
    if inventario is None:
        raise ApiError("INVENTARIO_MATERIAL_NO_ENCONTRADO", "Inventario no encontrado", 404)
    cambios = {}
    for campo in ("stock_minimo", "stock_seguridad", "consumo_diario_manual"):
        if campo in datos:
            anterior = getattr(inventario, campo)
            if str(anterior) != str(datos[campo]):
                cambios[campo] = {
                    "anterior": str(anterior) if anterior is not None else None,
                    "nuevo": str(datos[campo]) if datos[campo] is not None else None,
                }
            setattr(inventario, campo, datos[campo])
    bitacora_service.registrar_bitacora(
        usuario_id, "POLITICA_MATERIAL_ACTUALIZADA", "inventario_material", id, cambios, ip
    )
    generar_requisicion_automatica(id, usuario_id)
    db.session.commit()
    return inventario


__all__ = [
    "actualizar",
    "actualizar_politica",
    "ajustar",
    "consumir_peps",
    "crear",
    "desactivar",
    "generar_requisicion_automatica",
    "listar",
    "listar_inventario",
    "listar_lotes",
    "listar_movimientos",
    "obtener",
    "obtener_inventario",
    "registrar_entrada",
    "registrar_rechazo_recepcion",
    "serializar_inventario",
]
