"""Cálculo de costo estándar, edición y activación de recetas (M11)."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import (
    CategoriaMaterial,
    Color,
    DisenoBordado,
    DisenoBordadoHilo,
    EmpaqueRegla,
    InventarioMaterial,
    LoteMaterial,
    Material,
    OrdenMaterial,
    OrdenProduccion,
    Producto,
    Receta,
    RecetaBordado,
    RecetaLinea,
    Talla,
    VarianteProducto,
)
from app.services import configuracion_service
from app.services.bitacora_service import registrar_bitacora
from app.utils.errores import ApiError

ESTADOS_ORDEN_ABIERTOS = ("PLANEADA", "LISTA", "EN_PROCESO", "EN_REVISION")


def _d(valor) -> Decimal:
    return Decimal(str(valor)) if valor is not None else Decimal("0")


def _q(valor, lugares="0.000001") -> Decimal:
    return _d(valor).quantize(Decimal(lugares), rounding=ROUND_HALF_UP)


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def receta_para_variante(variante_id: int) -> Receta | None:
    variante = db.session.get(VarianteProducto, variante_id)
    if variante is None:
        return None
    return db.session.execute(
        select(Receta)
        .where(
            Receta.producto_id == variante.producto_id,
            Receta.talla_id == variante.talla_id,
            Receta.estado != "ARCHIVADA",
        )
        .order_by(
            case((Receta.estado == "VIGENTE", 0), else_=1),
            Receta.version.desc(),
        )
        .limit(1)
    ).scalars().first()


def calcular_costo(receta: Receta) -> Decimal:
    lineas = db.session.execute(
        select(RecetaLinea)
        .options(selectinload(RecetaLinea.material))
        .where(RecetaLinea.receta_id == receta.id)
    ).scalars().all()
    materiales = sum(
        (_d(linea.cantidad_bruta) * _d(linea.material.costo_estandar_base)) for linea in lineas
    )
    total = (
        materiales
        + _d(receta.mano_obra)
        + _d(receta.costo_bordado)
        + _d(receta.costos_indirectos)
    )
    return total.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def costo_estandar_unitario(variante_id: int) -> Decimal:
    receta = receta_para_variante(variante_id)
    if receta is None:
        return Decimal("0.000000")
    return calcular_costo(receta)


def iva_factor() -> Decimal:
    return Decimal("1") + configuracion_service.valor_decimal("iva_pct", 16) / Decimal("100")


def precio_sugerido(costo, margen=None, iva=None) -> Decimal:
    margen = (
        configuracion_service.valor_decimal("margen_objetivo_pct", 55) / Decimal("100")
        if margen is None
        else _d(margen)
    )
    iva = iva_factor() if iva is None else _d(iva)
    if margen >= 1:
        raise ApiError("CONFIGURACION_INVALIDA", "El margen objetivo debe ser menor a 100 %", 422)
    return _q(_d(costo) / (Decimal("1") - margen) * iva, "0.01")


def margen_real(precio, costo, iva=None) -> Decimal:
    iva = iva_factor() if iva is None else _d(iva)
    sin_iva = _d(precio) / iva
    if sin_iva <= 0:
        return Decimal("0.000000")
    return _q((sin_iva - _d(costo)) / sin_iva)


def cantidad_bruta(cantidad_neta, factor_consumo, merma_pct) -> Decimal:
    tasa = Decimal("1") - _d(merma_pct) / Decimal("100")
    if tasa <= 0:
        raise ApiError("MERMA_INVALIDA", "La merma debe ser menor a 100 %", 422)
    return _q(_d(cantidad_neta) * _d(factor_consumo) / tasa, "0.0001")


def _costo_hilo_bordado(receta_id: int) -> Decimal:
    total = Decimal("0")
    aplicaciones = db.session.execute(
        select(RecetaBordado).where(RecetaBordado.receta_id == receta_id)
    ).scalars().all()
    for aplicacion in aplicaciones:
        diseno = db.session.get(DisenoBordado, aplicacion.diseno_id)
        if diseno is None or diseno.estado != "DIGITALIZADO":
            continue
        hilos = db.session.execute(
            select(DisenoBordadoHilo, Material)
            .join(Material, Material.id == DisenoBordadoHilo.material_id)
            .where(DisenoBordadoHilo.diseno_id == diseno.id)
        ).all()
        for hilo, material in hilos:
            total += (
                _d(hilo.metros_por_aplicacion)
                * int(aplicacion.aplicaciones)
                * _d(material.costo_estandar_base)
            )
    return total


def _costo_empaque() -> Decimal:
    reglas = db.session.execute(
        select(EmpaqueRegla, Material)
        .join(Material, Material.id == EmpaqueRegla.material_id)
        .where(EmpaqueRegla.base == "POR_PRENDA", EmpaqueRegla.activo.is_(True))
    ).all()
    return sum(
        (_d(regla.cantidad) * _d(material.costo_estandar_base)) for regla, material in reglas
    )


def desglose_costos(receta) -> dict:
    lineas = db.session.execute(
        select(RecetaLinea)
        .options(selectinload(RecetaLinea.material))
        .where(RecetaLinea.receta_id == receta.id)
    ).scalars().all()
    materia_prima = sum(
        (_d(linea.cantidad_bruta) * _d(linea.material.costo_estandar_base)) for linea in lineas
    )
    hilo = _costo_hilo_bordado(receta.id)
    empaque = _costo_empaque()
    mano_obra = _d(receta.mano_obra)
    bordado = _d(receta.costo_bordado)
    indirectos = _d(receta.costos_indirectos)
    total = materia_prima + hilo + empaque + mano_obra + bordado + indirectos
    return {
        "costo_materia_prima": _q(materia_prima + hilo),
        "costo_hilo_bordado": _q(hilo),
        "costo_empaque": _q(empaque),
        "mano_obra": _q(mano_obra, "0.01"),
        "costo_bordado": _q(bordado, "0.01"),
        "costos_indirectos": _q(indirectos, "0.01"),
        "costo_estandar": _q(total),
        "precio_sugerido": _q(precio_sugerido(total), "0.01"),
    }


def _obtener_receta(receta_id: int) -> Receta:
    receta = db.session.get(Receta, receta_id)
    if receta is None:
        raise ApiError("RECETA_NO_ENCONTRADA", "Receta no encontrada", 404)
    return receta


def _validar_editable(receta) -> None:
    if receta.estado != "BORRADOR":
        raise ApiError(
            "RECETA_NO_EDITABLE",
            "Una receta vigente o archivada no se edita; cópiela a un borrador nuevo",
            422,
        )


def _siguiente_version(producto_id: int, talla_id: int) -> int:
    ultima = db.session.scalar(
        select(func.max(Receta.version)).where(
            Receta.producto_id == producto_id, Receta.talla_id == talla_id
        )
    )
    return int(ultima or 0) + 1


def crear_borrador(producto_id: int, talla_id: int, usuario_id: int) -> Receta:
    if db.session.scalar(
        select(func.count()).select_from(Receta).where(
            Receta.producto_id == producto_id,
            Receta.talla_id == talla_id,
            Receta.estado == "BORRADOR",
        )
    ):
        raise ApiError("BORRADOR_EXISTENTE", "Ya existe un borrador para esa talla", 409)
    receta = Receta(
        producto_id=producto_id,
        talla_id=talla_id,
        version=_siguiente_version(producto_id, talla_id),
        estado="BORRADOR",
        mano_obra=Decimal("0.00"),
        costo_bordado=Decimal("0.00"),
        costos_indirectos=Decimal("0.00"),
        creada_por=usuario_id,
    )
    db.session.add(receta)
    db.session.flush()
    return receta


def _lineas(receta_id: int, incluir_costos: bool) -> list:
    filas = db.session.execute(
        select(RecetaLinea)
        .options(selectinload(RecetaLinea.material))
        .where(RecetaLinea.receta_id == receta_id)
        .order_by(RecetaLinea.id)
    ).scalars().all()
    respuesta = []
    for linea in filas:
        item = {
            "id": linea.id,
            "material_id": linea.material_id,
            "material_codigo": linea.material.codigo,
            "material_nombre": linea.material.nombre,
            "unidad_base": linea.material.unidad_base,
            "cantidad_neta": linea.cantidad_neta,
            "factor_consumo": linea.factor_consumo,
            "merma_pct": linea.merma_pct,
            "cantidad_bruta": linea.cantidad_bruta,
            "nota": linea.nota,
        }
        if incluir_costos:
            item["costo_unitario_base"] = linea.material.costo_estandar_base
            item["costo_linea"] = _q(
                _d(linea.cantidad_bruta) * _d(linea.material.costo_estandar_base)
            )
        respuesta.append(item)
    return respuesta


def _bordados(receta_id: int) -> list:
    filas = db.session.execute(
        select(RecetaBordado, DisenoBordado)
        .join(DisenoBordado, DisenoBordado.id == RecetaBordado.diseno_id)
        .where(RecetaBordado.receta_id == receta_id)
        .order_by(RecetaBordado.id)
    ).all()
    return [
        {
            "id": bordado.id,
            "diseno_id": bordado.diseno_id,
            "diseno_codigo": diseno.codigo,
            "diseno_nombre": diseno.nombre,
            "estado_diseno": diseno.estado,
            "aplicaciones": bordado.aplicaciones,
            "ubicacion": bordado.ubicacion,
        }
        for bordado, diseno in filas
    ]


def _detalle(receta, incluir_costos: bool = True, detalle: bool = False) -> dict:
    producto = db.session.get(Producto, receta.producto_id)
    talla = db.session.get(Talla, receta.talla_id)
    item = {
        "id": receta.id,
        "producto_id": receta.producto_id,
        "producto": producto.nombre if producto else None,
        "categoria": producto.categoria.nombre if producto else None,
        "talla_id": receta.talla_id,
        "talla": talla.codigo if talla else None,
        "version": receta.version,
        "estado": receta.estado,
        "creada_por": receta.creada_por,
        "activada_en": receta.activada_en,
        "actualizado_en": receta.actualizado_en,
        "nota": receta.nota,
    }
    if incluir_costos:
        precios = db.session.execute(
            select(Producto.precio_venta).where(Producto.id == receta.producto_id)
        ).scalars().first()
        desglose = desglose_costos(receta)
        item.update(desglose)
        item["precio_venta"] = precios
        item["margen_real"] = margen_real(precios, desglose["costo_estandar"])
    if detalle:
        item["lineas"] = _lineas(receta.id, incluir_costos)
        item["bordados"] = _bordados(receta.id)
    return item


def listar(filtros=None, incluir_costos: bool = True) -> list:
    filtros = filtros or {}
    consulta = select(Receta).join(Producto, Producto.id == Receta.producto_id)
    if filtros.get("producto_id"):
        consulta = consulta.where(Receta.producto_id == int(filtros["producto_id"]))
    if filtros.get("talla_id"):
        consulta = consulta.where(Receta.talla_id == int(filtros["talla_id"]))
    if filtros.get("estado"):
        consulta = consulta.where(Receta.estado == filtros["estado"])
    if filtros.get("q"):
        consulta = consulta.where(Producto.nombre.like(f"%{filtros['q']}%"))
    recetas = db.session.execute(
        consulta.order_by(Producto.nombre, Receta.talla_id, Receta.version.desc())
    ).scalars().all()
    return [_detalle(receta, incluir_costos) for receta in recetas]


def obtener(receta_id: int, incluir_costos: bool = True) -> dict:
    return _detalle(_obtener_receta(receta_id), incluir_costos, detalle=True)


def crear(datos: dict, usuario_id: int) -> dict:
    try:
        receta = crear_borrador(datos["producto_id"], datos["talla_id"], usuario_id)
        for campo in ("mano_obra", "costo_bordado", "costos_indirectos", "nota"):
            if campo in datos:
                setattr(receta, campo, datos[campo])
        registrar_bitacora(
            usuario_id,
            "RECETA_CREADA",
            "receta",
            receta.id,
            {"producto_id": receta.producto_id, "talla_id": receta.talla_id},
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return obtener(receta.id)


def actualizar(receta_id: int, datos: dict, usuario_id: int) -> dict:
    try:
        receta = _obtener_receta(receta_id)
        _validar_editable(receta)
        cambios = {}
        for campo in ("mano_obra", "costo_bordado", "costos_indirectos", "nota"):
            if campo in datos and getattr(receta, campo) != datos[campo]:
                cambios[campo] = str(getattr(receta, campo))
                setattr(receta, campo, datos[campo])
        registrar_bitacora(usuario_id, "RECETA_ACTUALIZADA", "receta", receta_id, cambios)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return obtener(receta_id)


def agregar_linea(receta_id: int, datos: dict, usuario_id: int) -> dict:
    try:
        receta = _obtener_receta(receta_id)
        _validar_editable(receta)
        if datos.get("diseno_id") is not None:
            diseno = db.session.get(DisenoBordado, datos["diseno_id"])
            if diseno is None or not diseno.activo:
                raise ApiError("DISENO_NO_DISPONIBLE", "Diseño de bordado no disponible", 422)
            bordado = db.session.execute(
                select(RecetaBordado).where(
                    RecetaBordado.receta_id == receta_id,
                    RecetaBordado.diseno_id == diseno.id,
                )
            ).scalars().first()
            if bordado is None:
                bordado = RecetaBordado(
                    receta_id=receta_id, diseno_id=diseno.id, aplicaciones=1
                )
                db.session.add(bordado)
            bordado.aplicaciones = int(datos.get("aplicaciones") or bordado.aplicaciones)
            bordado.ubicacion = datos.get("ubicacion", bordado.ubicacion)
            registrar_bitacora(
                usuario_id,
                "RECETA_BORDADO_ACTUALIZADO",
                "receta",
                receta_id,
                {"diseno_id": diseno.id, "aplicaciones": bordado.aplicaciones},
            )
        else:
            material = db.session.get(Material, datos["material_id"])
            if material is None or not material.activo:
                raise ApiError("MATERIAL_NO_DISPONIBLE", "Material no disponible", 422)
            merma = (
                material.merma_estandar_pct
                if datos.get("merma_pct") is None
                else datos["merma_pct"]
            )
            bruta = cantidad_bruta(
                datos["cantidad_neta"], datos.get("factor_consumo", 1), merma
            )
            linea = db.session.execute(
                select(RecetaLinea).where(
                    RecetaLinea.receta_id == receta_id,
                    RecetaLinea.material_id == material.id,
                )
            ).scalars().first()
            if linea is None:
                linea = RecetaLinea(receta_id=receta_id, material_id=material.id)
                db.session.add(linea)
            linea.cantidad_neta = datos["cantidad_neta"]
            linea.factor_consumo = datos.get("factor_consumo", 1)
            linea.merma_pct = merma
            linea.cantidad_bruta = bruta
            linea.nota = datos.get("nota")
            registrar_bitacora(
                usuario_id,
                "RECETA_LINEA_ACTUALIZADA",
                "receta",
                receta_id,
                {"material_id": material.id, "cantidad_bruta": str(bruta)},
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return obtener(receta_id)


def _lineas_calculadas(lineas) -> list:
    resultado = []
    color_na = db.session.execute(
        select(Color.id).where(Color.codigo == "NA")
    ).scalars().first()
    for linea in lineas or []:
        if linea.get("diseno_id") is not None:
            diseno = db.session.get(DisenoBordado, linea["diseno_id"])
            if diseno is None or not diseno.activo:
                raise ApiError("DISENO_NO_DISPONIBLE", "Diseño de bordado no disponible", 422)
            aplicaciones = int(linea.get("aplicaciones") or 1)
            if diseno.estado == "DIGITALIZADO":
                hilos = db.session.execute(
                    select(DisenoBordadoHilo, Material)
                    .join(Material, Material.id == DisenoBordadoHilo.material_id)
                    .where(DisenoBordadoHilo.diseno_id == diseno.id)
                ).all()
                for hilo, material in hilos:
                    bruta = _q(_d(hilo.metros_por_aplicacion) * aplicaciones, "0.0001")
                    resultado.append(
                        {
                            "material_id": material.id,
                            "material_codigo": material.codigo,
                            "cantidad_neta": bruta,
                            "factor_consumo": Decimal("1.000"),
                            "merma_pct": Decimal("0.00"),
                            "cantidad_bruta": bruta,
                            "costo_unitario_base": material.costo_estandar_base,
                            "por_color": material.por_color,
                        }
                    )
            continue
        material = db.session.get(Material, linea["material_id"])
        if material is None or not material.activo:
            raise ApiError("MATERIAL_NO_DISPONIBLE", "Material no disponible", 422)
        merma = (
            material.merma_estandar_pct
            if linea.get("merma_pct") is None
            else linea["merma_pct"]
        )
        neta = _d(linea.get("cantidad_neta") or 0)
        factor = _d(linea.get("factor_consumo") or 1)
        bruta = cantidad_bruta(neta, factor, merma)
        resultado.append(
            {
                "material_id": material.id,
                "material_codigo": material.codigo,
                "cantidad_neta": neta,
                "factor_consumo": factor,
                "merma_pct": _d(merma),
                "cantidad_bruta": bruta,
                "costo_unitario_base": material.costo_estandar_base,
                "por_color": material.por_color,
            }
        )
    return resultado


def _disponible_material(material_id: int, color_id: int) -> Decimal:
    fisico = db.session.scalar(
        select(func.coalesce(func.sum(LoteMaterial.cantidad_base_disponible), 0))
        .join(InventarioMaterial, InventarioMaterial.id == LoteMaterial.inventario_material_id)
        .where(
            InventarioMaterial.material_id == material_id,
            InventarioMaterial.color_id == color_id,
        )
    ) or 0
    reservado = db.session.scalar(
        select(func.coalesce(func.sum(OrdenMaterial.cantidad_reservada - OrdenMaterial.cantidad_consumida), 0))
        .join(OrdenProduccion, OrdenProduccion.id == OrdenMaterial.orden_id)
        .where(
            OrdenMaterial.inventario_material_id.in_(
                select(InventarioMaterial.id).where(
                    InventarioMaterial.material_id == material_id,
                    InventarioMaterial.color_id == color_id,
                )
            ),
            OrdenProduccion.estado.in_(ESTADOS_ORDEN_ABIERTOS),
        )
    ) or 0
    return max(Decimal("0"), _d(fisico) - _d(reservado))


def _capacidad(producto_id: int, talla_id: int, lineas_calculadas) -> int:
    variantes = db.session.execute(
        select(VarianteProducto).where(
            VarianteProducto.producto_id == producto_id,
            VarianteProducto.talla_id == talla_id,
            VarianteProducto.activa.is_(True),
        )
    ).scalars().all()
    if not variantes:
        return 0
    color_na = db.session.execute(select(Color.id).where(Color.codigo == "NA")).scalars().first()
    if color_na is None:
        return 0
    capacidades = []
    for variante in variantes:
        capacidad = None
        for linea in lineas_calculadas:
            color_id = variante.color_id if linea["por_color"] else color_na
            bruta = _d(linea["cantidad_bruta"])
            if bruta <= 0:
                continue
            unidades = int(_disponible_material(linea["material_id"], color_id) // bruta)
            capacidad = unidades if capacidad is None else min(capacidad, unidades)
        capacidades.append(capacidad or 0)
    return min(capacidades)


def previsualizar(datos: dict, usuario_id: int) -> dict:
    lineas = _lineas_calculadas(datos.get("lineas"))
    mp = sum(
        (_d(linea["cantidad_bruta"]) * _d(linea["costo_unitario_base"])) for linea in lineas
    )
    empaque = _costo_empaque()
    mano_obra = _d(datos.get("mano_obra"))
    bordado = _d(datos.get("costo_bordado"))
    indirectos = _d(datos.get("costos_indirectos"))
    total = mp + empaque + mano_obra + bordado + indirectos
    return {
        "producto_id": datos["producto_id"],
        "talla_id": datos["talla_id"],
        "costo_materia_prima": _q(mp),
        "costo_empaque": _q(empaque),
        "mano_obra": _q(mano_obra, "0.01"),
        "costo_bordado": _q(bordado, "0.01"),
        "costos_indirectos": _q(indirectos, "0.01"),
        "costo_estandar": _q(total),
        "precio_sugerido": _q(precio_sugerido(total), "0.01"),
        "margen_real": margen_real(datos.get("precio_venta"), total)
        if datos.get("precio_venta")
        else None,
        "capacidad": _capacidad(datos["producto_id"], datos["talla_id"], lineas),
        "lineas": [
            {
                "material_id": linea["material_id"],
                "material_codigo": linea["material_codigo"],
                "cantidad_neta": linea["cantidad_neta"],
                "factor_consumo": linea["factor_consumo"],
                "merma_pct": linea["merma_pct"],
                "cantidad_bruta": linea["cantidad_bruta"],
                "costo_linea": _q(
                    _d(linea["cantidad_bruta"]) * _d(linea["costo_unitario_base"])
                ),
            }
            for linea in lineas
        ],
    }


def copiar(receta_id: int, datos: dict, usuario_id: int) -> dict:
    try:
        origen = _obtener_receta(receta_id)
        producto_id = int(datos.get("producto_id") or origen.producto_id)
        talla_id = int(datos.get("talla_id") or origen.talla_id)
        destino = crear_borrador(producto_id, talla_id, usuario_id)
        destino.origen_receta_id = origen.id
        for campo in ("mano_obra", "costo_bordado", "costos_indirectos"):
            setattr(destino, campo, getattr(origen, campo))
        destino.nota = datos.get("nota", origen.nota)
        for linea in db.session.execute(
            select(RecetaLinea).where(RecetaLinea.receta_id == origen.id)
        ).scalars().all():
            db.session.add(
                RecetaLinea(
                    receta_id=destino.id,
                    material_id=linea.material_id,
                    cantidad_neta=linea.cantidad_neta,
                    factor_consumo=linea.factor_consumo,
                    merma_pct=linea.merma_pct,
                    cantidad_bruta=linea.cantidad_bruta,
                    nota=linea.nota,
                )
            )
        for bordado in db.session.execute(
            select(RecetaBordado).where(RecetaBordado.receta_id == origen.id)
        ).scalars().all():
            db.session.add(
                RecetaBordado(
                    receta_id=destino.id,
                    diseno_id=bordado.diseno_id,
                    aplicaciones=bordado.aplicaciones,
                    ubicacion=bordado.ubicacion,
                )
            )
        registrar_bitacora(
            usuario_id,
            "RECETA_COPIADA",
            "receta",
            destino.id,
            {"origen_receta_id": origen.id, "producto_id": producto_id, "talla_id": talla_id},
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return obtener(destino.id)


def activar(receta_id: int, usuario_id: int, ip=None) -> dict:
    try:
        receta = _obtener_receta(receta_id)
        if receta.estado == "VIGENTE":
            raise ApiError("RECETA_YA_VIGENTE", "La receta ya está vigente", 409)
        if receta.estado != "BORRADOR":
            raise ApiError("RECETA_NO_ACTIVABLE", "La receta no puede activarse", 422)

        filas = db.session.execute(
            select(RecetaLinea, Material, CategoriaMaterial)
            .join(Material, Material.id == RecetaLinea.material_id)
            .join(CategoriaMaterial, CategoriaMaterial.id == Material.categoria_material_id)
            .where(RecetaLinea.receta_id == receta_id)
        ).all()
        codigos = {material.codigo for _, material, _ in filas}
        mermas = [_d(linea.merma_pct) for linea, _, _ in filas]
        if not any(
            categoria.nombre.upper() == "TELA" or material.codigo == "HIL-EST"
            for _, material, categoria in filas
        ):
            raise ApiError(
                "RECETA_SIN_TELA", "Se requiere una línea de tela o hilo de tejido", 422
            )
        if "HIL-COS" not in codigos:
            raise ApiError("RECETA_SIN_HILO_COSTURA", "Se requiere HIL-COS", 422)
        if any(merma >= 100 for merma in mermas):
            raise ApiError("MERMA_INVALIDA", "La merma debe ser menor a 100 %", 422)

        producto = db.session.get(Producto, receta.producto_id)
        talla = db.session.get(Talla, receta.talla_id)
        prefijo = producto.categoria.prefijo_sku
        etiquetas = {"ETQ-MAR", f"ETQ-COM-{prefijo}"}
        if talla.codigo != "UN":
            etiquetas.add(f"ETQ-TAL-{talla.codigo}")
        faltantes = sorted(etiquetas - codigos)
        if faltantes:
            raise ApiError(
                "ETIQUETAS_INCOMPLETAS", "Faltan etiquetas obligatorias", 422, faltantes
            )

        anteriores = db.session.execute(
            select(Receta)
            .where(
                Receta.producto_id == receta.producto_id,
                Receta.talla_id == receta.talla_id,
                Receta.estado == "VIGENTE",
            )
            .with_for_update()
        ).scalars().all()
        for anterior in anteriores:
            anterior.estado = "ARCHIVADA"
        receta.estado = "VIGENTE"
        receta.activada_en = _ahora()
        registrar_bitacora(
            usuario_id,
            "RECETA_ACTIVADA",
            "receta",
            receta_id,
            {"version": receta.version, "archivadas": [item.id for item in anteriores]},
            ip,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return obtener(receta_id)


def costeo() -> list:
    recetas = db.session.execute(
        select(Receta)
        .join(Producto, Producto.id == Receta.producto_id)
        .where(Receta.estado == "VIGENTE")
        .order_by(Producto.nombre, Receta.talla_id)
    ).scalars().all()
    filas = []
    for receta in recetas:
        desglose = desglose_costos(receta)
        producto = db.session.get(Producto, receta.producto_id)
        talla = db.session.get(Talla, receta.talla_id)
        filas.append(
            {
                "producto_id": producto.id,
                "producto": producto.nombre,
                "talla_id": talla.id,
                "talla": talla.codigo,
                "receta_id": receta.id,
                **desglose,
                "precio_venta": producto.precio_venta,
            }
        )
    mayor_costo = {}
    for fila in filas:
        actual = mayor_costo.get(fila["producto_id"])
        if actual is None or fila["costo_estandar"] > actual:
            mayor_costo[fila["producto_id"]] = fila["costo_estandar"]
    for fila in filas:
        sugerido = precio_sugerido(mayor_costo[fila["producto_id"]])
        fila["precio_sugerido"] = sugerido
        fila["margen_real"] = margen_real(fila["precio_venta"], fila["costo_estandar"])
    return filas
