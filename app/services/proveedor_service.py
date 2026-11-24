"""Padrón de proveedores, catálogo que surten y evaluación de desempeño (M13)."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Alerta,
    Cotizacion,
    LoteMaterial,
    Material,
    OrdenCompra,
    Proveedor,
    ProveedorMaterial,
    Recepcion,
    RecepcionLinea,
)
from app.models.base import ahora_utc
from app.services import alertas_service, bitacora_service, configuracion_service
from app.utils.dinero import decimal_valor, dinero, material as material_texto
from app.utils.errores import ApiError

MATERIALES_CRITICOS = ("TEL-FEL", "TEL-JER", "TEL-RIB", "HIL-EST")
CAMPOS_PROVEEDOR = (
    "razon_social",
    "nombre_comercial",
    "rfc",
    "contacto",
    "telefono",
    "correo",
    "direccion",
    "condiciones_pago",
    "notas",
    "estatus",
)


def _d(valor) -> Decimal:
    return decimal_valor(valor)


def _porcentaje(numerador, denominador) -> Decimal:
    if denominador <= 0:
        return Decimal("100.00")
    return (_d(numerador) * Decimal("100") / _d(denominador)).quantize(Decimal("0.01"))


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


def _serializar(proveedor: Proveedor) -> dict:
    return {
        "id": proveedor.id,
        "razon_social": proveedor.razon_social,
        "nombre_comercial": proveedor.nombre_comercial,
        "rfc": proveedor.rfc,
        "contacto": proveedor.contacto,
        "telefono": proveedor.telefono,
        "correo": proveedor.correo,
        "direccion": proveedor.direccion,
        "condiciones_pago": proveedor.condiciones_pago,
        "estatus": proveedor.estatus,
        "notas": proveedor.notas,
        "eliminado_en": proveedor.eliminado_en.isoformat() if proveedor.eliminado_en else None,
    }


def listar(filtros=None):
    """Padrón de proveedores filtrable por texto, estatus y material surtido."""
    filtros = filtros or {}
    paginado, pagina, por_pagina = _paginacion(filtros)
    condiciones = [Proveedor.eliminado_en.is_(None)]
    if not filtros.get("incluir_inactivos") and filtros.get("estatus") != "INACTIVO":
        condiciones.append(Proveedor.estatus != "INACTIVO")
    if filtros.get("estatus"):
        condiciones.append(Proveedor.estatus == filtros["estatus"])
    if filtros.get("q"):
        busqueda = f"%{filtros['q']}%"
        condiciones.append(
            or_(
                Proveedor.razon_social.like(busqueda),
                Proveedor.nombre_comercial.like(busqueda),
                Proveedor.rfc.like(busqueda),
            )
        )
    if filtros.get("material_id"):
        condiciones.append(
            Proveedor.id.in_(
                select(ProveedorMaterial.proveedor_id).where(
                    ProveedorMaterial.material_id == filtros["material_id"],
                    ProveedorMaterial.activo.is_(True),
                )
            )
        )

    consulta = (
        select(Proveedor)
        .where(*condiciones)
        .order_by(Proveedor.nombre_comercial, Proveedor.id)
    )
    if paginado:
        total = db.session.scalar(
            select(func.count()).select_from(Proveedor).where(*condiciones)
        )
        filas = db.session.execute(
            consulta.offset((pagina - 1) * por_pagina).limit(por_pagina)
        ).scalars()
        return {
            "items": [_serializar(fila) for fila in filas],
            "total": int(total or 0),
            "pagina": pagina,
            "por_pagina": por_pagina,
        }
    return [_serializar(fila) for fila in db.session.execute(consulta).scalars()]


def obtener(id: int) -> Proveedor:
    proveedor = db.session.get(Proveedor, id)
    if proveedor is None or proveedor.eliminado_en is not None:
        raise ApiError("PROVEEDOR_NO_ENCONTRADO", "Proveedor no encontrado", 404)
    return proveedor


def crear(datos, usuario_id, ip=None) -> Proveedor:
    if datos.get("rfc") and db.session.scalar(
        select(Proveedor.id).where(Proveedor.rfc == datos["rfc"])
    ):
        raise ApiError("PROVEEDOR_DUPLICADO", "El RFC ya está registrado", 409)
    valores = {
        campo: datos[campo]
        for campo in CAMPOS_PROVEEDOR
        if campo in datos and campo != "estatus"
    }
    proveedor = Proveedor(**valores, estatus="ACTIVO")
    db.session.add(proveedor)
    bitacora_service.registrar_bitacora(
        usuario_id,
        "PROVEEDOR_CREADO",
        "proveedor",
        proveedor.id,
        {"nombre_comercial": proveedor.nombre_comercial},
        ip,
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("PROVEEDOR_DUPLICADO", "El proveedor ya está registrado", 409)
    return proveedor


def actualizar(id: int, datos, usuario_id, ip=None) -> Proveedor:
    proveedor = obtener(id)
    if datos.get("rfc") and db.session.scalar(
        select(Proveedor.id).where(Proveedor.rfc == datos["rfc"], Proveedor.id != id)
    ):
        raise ApiError("PROVEEDOR_DUPLICADO", "El RFC ya está registrado", 409)
    cambios = {}
    for campo in CAMPOS_PROVEEDOR:
        if campo not in datos:
            continue
        anterior = getattr(proveedor, campo)
        if str(anterior) != str(datos[campo]):
            cambios[campo] = {"anterior": str(anterior), "nuevo": str(datos[campo])}
        setattr(proveedor, campo, datos[campo])
    bitacora_service.registrar_bitacora(
        usuario_id, "PROVEEDOR_ACTUALIZADO", "proveedor", id, cambios, ip
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("PROVEEDOR_DUPLICADO", "El proveedor ya está registrado", 409)
    return proveedor


def _tiene_historial(proveedor_id: int) -> bool:
    """Impide borrar un proveedor con historial que MySQL no dejaría eliminar."""
    consultas = (
        select(OrdenCompra.id).where(OrdenCompra.proveedor_id == proveedor_id).limit(1),
        select(Cotizacion.id).where(Cotizacion.proveedor_id == proveedor_id).limit(1),
        select(LoteMaterial.id).where(LoteMaterial.proveedor_id == proveedor_id).limit(1),
    )
    return any(db.session.scalar(consulta) is not None for consulta in consultas)


def desactivar(id: int, usuario_id, ip=None) -> None:
    proveedor = obtener(id)
    modo = "LOGICO"
    if _tiene_historial(proveedor.id):
        proveedor.estatus = "INACTIVO"
        proveedor.eliminado_en = ahora_utc()
        db.session.execute(
            update(ProveedorMaterial)
            .where(ProveedorMaterial.proveedor_id == proveedor.id)
            .values(activo=False)
        )
    else:
        db.session.execute(
            delete(ProveedorMaterial).where(
                ProveedorMaterial.proveedor_id == proveedor.id
            )
        )
        db.session.delete(proveedor)
        modo = "FISICO"
    bitacora_service.registrar_bitacora(
        usuario_id,
        "PROVEEDOR_DESACTIVADO",
        "proveedor",
        proveedor.id,
        {"modo": modo, "nombre_comercial": proveedor.nombre_comercial},
        ip,
    )
    db.session.commit()


def _serializar_material(fila: ProveedorMaterial) -> dict:
    material = fila.material
    return {
        "id": fila.id,
        "proveedor_id": fila.proveedor_id,
        "material_id": fila.material_id,
        "material_codigo": material.codigo if material else None,
        "material_nombre": material.nombre if material else None,
        "unidad_compra": material.unidad_compra if material else None,
        "precio_compra": dinero(fila.precio_compra),
        "minimo_compra": material_texto(fila.minimo_compra),
        "plazo_dias": fila.plazo_dias,
        "es_principal": fila.es_principal,
        "vigencia_hasta": fila.vigencia_hasta.isoformat() if fila.vigencia_hasta else None,
        "activo": fila.activo,
    }


def serializar_material(fila: ProveedorMaterial) -> dict:
    return _serializar_material(fila)


def listar_materiales(proveedor_id: int):
    obtener(proveedor_id)
    filas = db.session.execute(
        select(ProveedorMaterial)
        .join(Material, Material.id == ProveedorMaterial.material_id)
        .where(ProveedorMaterial.proveedor_id == proveedor_id)
        .order_by(Material.codigo, ProveedorMaterial.id)
    ).scalars()
    return [_serializar_material(fila) for fila in filas]


def _obtener_material(proveedor_id: int, id: int) -> ProveedorMaterial:
    fila = db.session.get(ProveedorMaterial, id)
    if fila is None or fila.proveedor_id != proveedor_id:
        raise ApiError("MATERIAL_PROVEEDOR_NO_ENCONTRADO", "Material del proveedor no encontrado", 404)
    return fila


def _fijar_principal(fila: ProveedorMaterial) -> None:
    if not fila.es_principal:
        return
    db.session.execute(
        update(ProveedorMaterial)
        .where(
            ProveedorMaterial.material_id == fila.material_id,
            ProveedorMaterial.id != fila.id,
            ProveedorMaterial.es_principal.is_(True),
        )
        .values(es_principal=False)
    )


def agregar_material(proveedor_id: int, datos, usuario_id) -> ProveedorMaterial:
    proveedor = obtener(proveedor_id)
    if proveedor.estatus == "INACTIVO" or proveedor.eliminado_en is not None:
        raise ApiError("PROVEEDOR_INACTIVO", "El proveedor está inactivo", 409)
    material = db.session.get(Material, datos["material_id"])
    if material is None or material.eliminado_en is not None:
        raise ApiError("MATERIAL_NO_ENCONTRADO", "Material no encontrado", 404)
    fila = ProveedorMaterial(
        proveedor_id=proveedor_id,
        material_id=datos["material_id"],
        precio_compra=datos["precio_compra"],
        minimo_compra=datos["minimo_compra"],
        plazo_dias=datos["plazo_dias"],
        es_principal=datos.get("es_principal", False),
        vigencia_hasta=datos.get("vigencia_hasta"),
        activo=datos.get("activo", True),
    )
    db.session.add(fila)
    db.session.flush()
    _fijar_principal(fila)
    bitacora_service.registrar_bitacora(
        usuario_id,
        "PROVEEDOR_MATERIAL_AGREGADO",
        "proveedor_material",
        fila.id,
        {
            "proveedor_id": proveedor_id,
            "material_id": fila.material_id,
            "precio_compra": dinero(fila.precio_compra),
        },
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("MATERIAL_PROVEEDOR_DUPLICADO", "El material ya está asignado al proveedor", 409)
    return fila


def actualizar_material(proveedor_id: int, id: int, datos, usuario_id) -> ProveedorMaterial:
    fila = _obtener_material(proveedor_id, id)
    cambios = {}
    for campo in (
        "material_id",
        "precio_compra",
        "minimo_compra",
        "plazo_dias",
        "es_principal",
        "vigencia_hasta",
        "activo",
    ):
        if campo not in datos:
            continue
        anterior = getattr(fila, campo)
        if str(anterior) != str(datos[campo]):
            cambios[campo] = {"anterior": str(anterior), "nuevo": str(datos[campo])}
        setattr(fila, campo, datos[campo])
    if "material_id" in datos:
        material = db.session.get(Material, datos["material_id"])
        if material is None or material.eliminado_en is not None:
            db.session.rollback()
            raise ApiError("MATERIAL_NO_ENCONTRADO", "Material no encontrado", 404)
    _fijar_principal(fila)
    bitacora_service.registrar_bitacora(
        usuario_id, "PROVEEDOR_MATERIAL_ACTUALIZADO", "proveedor_material", id, cambios
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("MATERIAL_PROVEEDOR_DUPLICADO", "El material ya está asignado al proveedor", 409)
    return fila


def eliminar_material(proveedor_id: int, id: int, usuario_id) -> None:
    fila = _obtener_material(proveedor_id, id)
    fila.activo = False
    bitacora_service.registrar_bitacora(
        usuario_id,
        "PROVEEDOR_MATERIAL_ELIMINADO",
        "proveedor_material",
        id,
        {"proveedor_id": proveedor_id, "material_id": fila.material_id},
    )
    db.session.commit()


def advertencias_cobertura(proveedor_id=None) -> list:
    """Advierte sobre materiales sin principal y críticos sin alterno."""
    hoy = date.today()
    condiciones_relacion = [
        ProveedorMaterial.activo.is_(True),
        Proveedor.eliminado_en.is_(None),
        or_(
            ProveedorMaterial.vigencia_hasta.is_(None),
            ProveedorMaterial.vigencia_hasta >= hoy,
        ),
    ]
    condiciones_material = [Material.activo.is_(True)]
    if proveedor_id is not None:
        condiciones_material.append(
            Material.id.in_(
                select(ProveedorMaterial.material_id).where(
                    ProveedorMaterial.proveedor_id == proveedor_id,
                    ProveedorMaterial.activo.is_(True),
                )
            )
        )
    materiales = db.session.execute(
        select(Material).where(*condiciones_material).order_by(Material.codigo)
    ).scalars()
    relaciones = db.session.execute(
        select(ProveedorMaterial, Proveedor)
        .join(Proveedor, Proveedor.id == ProveedorMaterial.proveedor_id)
        .where(*condiciones_relacion)
    ).all()
    principales = defaultdict(int)
    activos = defaultdict(int)
    nombres = {}
    for fila, _proveedor in relaciones:
        activos[fila.material_id] += 1
        if fila.es_principal:
            principales[fila.material_id] += 1
    for material in materiales:
        nombres[material.id] = material.codigo
        activos[material.id] += 0
        principales[material.id] += 0

    advertencias = []
    for material_id, codigo in nombres.items():
        if principales[material_id] == 0:
            advertencias.append(f"El material {codigo} no tiene proveedor principal")
        if codigo in MATERIALES_CRITICOS and activos[material_id] < 2:
            advertencias.append(f"El material crítico {codigo} requiere un proveedor alterno")
    return advertencias


def _abrir_o_reabrir(tipo, titulo, detalle, proveedor_id, clave_unica) -> None:
    alerta = alertas_service.abrir(
        tipo,
        "INFORMATIVA",
        titulo,
        detalle,
        "proveedor",
        proveedor_id,
        rol_destino="ADMIN",
        clave_unica=clave_unica,
        accion_sugerida="Revisar proveedor",
    )
    if alerta is not None and alerta.estado != "ABIERTA":
        alerta.estado = "ABIERTA"
        alerta.atendida_por = None
        alerta.atendida_en = None


def evaluacion(persistir: bool = False) -> dict:
    """Calcula entregas a tiempo y aceptación por proveedor.

    Por defecto es de solo lectura: el GET expone el estatus derivado sin mutar
    el padrón. El proceso programado llama con ``persistir=True`` para ajustar
    estatus y abrir alertas.
    """
    umbral = configuracion_service.valor_decimal(
        "proveedor_minimo_a_tiempo_pct", Decimal("80")
    )
    proveedores = db.session.execute(
        select(Proveedor)
        .where(Proveedor.eliminado_en.is_(None))
        .order_by(Proveedor.nombre_comercial, Proveedor.id)
    ).scalars().all()

    ultima_entrega = {}
    for recepcion, orden in db.session.execute(
        select(Recepcion, OrdenCompra).join(
            OrdenCompra, OrdenCompra.id == Recepcion.orden_compra_id
        )
    ).all():
        fecha = recepcion.fecha
        if hasattr(fecha, "date"):
            fecha = fecha.date()
        clave = (orden.proveedor_id, orden.id)
        anterior = ultima_entrega.get(clave)
        if anterior is None or fecha > anterior[0]:
            ultima_entrega[clave] = (fecha, orden.fecha_prometida)

    entregas = defaultdict(lambda: {"recibidas": set(), "evaluadas": 0, "a_tiempo": 0})
    for (proveedor_id, _orden_id), (fecha, prometida) in ultima_entrega.items():
        grupo = entregas[proveedor_id]
        grupo["recibidas"].add(_orden_id)
        if prometida is not None:
            grupo["evaluadas"] += 1
            if fecha <= prometida:
                grupo["a_tiempo"] += 1

    aceptacion = {}
    for proveedor_id, medido, aceptado in db.session.execute(
        select(
            OrdenCompra.proveedor_id,
            func.coalesce(func.sum(RecepcionLinea.cantidad_base_medida), 0),
            func.coalesce(func.sum(RecepcionLinea.cantidad_base_aceptada), 0),
        )
        .join(Recepcion, Recepcion.orden_compra_id == OrdenCompra.id)
        .join(RecepcionLinea, RecepcionLinea.recepcion_id == Recepcion.id)
        .group_by(OrdenCompra.proveedor_id)
    ).all():
        aceptacion[proveedor_id] = (medido, aceptado)

    avisos_globales = advertencias_cobertura()
    items = []
    cambio = False
    for proveedor in proveedores:
        grupo = entregas[proveedor.id]
        medido, aceptado = aceptacion.get(proveedor.id, (Decimal("0"), Decimal("0")))
        recibidas = len(grupo["recibidas"])
        a_tiempo = _porcentaje(grupo["a_tiempo"], recibidas)
        acept = _porcentaje(aceptado, medido)
        estatus = proveedor.estatus
        if estatus != "INACTIVO":
            if a_tiempo < umbral:
                estatus = "EN_REVISION"
                if persistir:
                    if proveedor.estatus != "EN_REVISION":
                        proveedor.estatus = "EN_REVISION"
                        cambio = True
                    _abrir_o_reabrir(
                        "PROVEEDOR_EN_REVISION",
                        "Proveedor por debajo del porcentaje mínimo de entregas a tiempo",
                        f"{proveedor.nombre_comercial} tiene {a_tiempo}% de entregas a tiempo.",
                        proveedor.id,
                        f"PROVEEDOR_EN_REVISION:{proveedor.id}",
                    )
            elif estatus == "EN_REVISION":
                estatus = "ACTIVO"
                if persistir:
                    proveedor.estatus = "ACTIVO"
                    cambio = True
                    alerta = db.session.execute(
                        select(Alerta).where(
                            Alerta.clave_unica == f"PROVEEDOR_EN_REVISION:{proveedor.id}"
                        )
                    ).scalars().first()
                    if alerta is not None and alerta.estado == "ABIERTA":
                        alerta.estado = "RESUELTA_AUTO"
                        alerta.atendida_en = ahora_utc()
        items.append(
            {
                "proveedor_id": proveedor.id,
                "razon_social": proveedor.razon_social,
                "nombre_comercial": proveedor.nombre_comercial,
                "estatus": estatus,
                "ordenes_recibidas": recibidas,
                "ordenes_evaluadas": grupo["evaluadas"],
                "entregas_a_tiempo": grupo["a_tiempo"],
                "porcentaje_a_tiempo": str(a_tiempo),
                "cantidad_medida": material_texto(medido),
                "cantidad_aceptada": material_texto(aceptado),
                "porcentaje_aceptacion": str(acept),
                "advertencias": advertencias_cobertura(proveedor.id),
            }
        )
    if cambio:
        db.session.commit()

    return {
        "items": items,
        "advertencias": avisos_globales,
        "umbral_a_tiempo_pct": str(umbral),
    }


__all__ = [
    "actualizar",
    "actualizar_material",
    "advertencias_cobertura",
    "agregar_material",
    "crear",
    "desactivar",
    "eliminar_material",
    "evaluacion",
    "listar",
    "listar_materiales",
    "obtener",
    "serializar_material",
]
