"""Casos de uso de productos, variantes, imágenes y activación (M10)."""

import io
import os
import secrets
from datetime import datetime, timezone

from flask import current_app
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    CategoriaProducto,
    CarritoLinea,
    Color,
    DevolucionLinea,
    Merma,
    MovimientoProducto,
    OrdenProduccionLinea,
    Producto,
    ProductoImagen,
    Receta,
    RecetaBordado,
    RecetaLinea,
    StockVariante,
    Talla,
    VarianteProducto,
    VentaLinea,
)
from app.services import receta_service
from app.services.bitacora_service import registrar_bitacora
from app.services.configuracion_service import valor_entero
from app.utils.errores import ApiError

TALLAS_CON_TALLA = ("CH", "MD", "GD")
TALLAS_UNICA = ("UN",)
EXTENSIONES = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "WEBP": ("webp", "image/webp"),
}
TAMANO_MAXIMO = 2 * 1024 * 1024


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _obtener_producto(producto_id: int) -> Producto:
    producto = db.session.get(Producto, producto_id)
    if producto is None or producto.eliminado_en is not None:
        raise ApiError("PRODUCTO_NO_ENCONTRADO", "Producto no encontrado", 404)
    return producto


def _catalogos(categoria_id: int, colores=None, tallas=None):
    categoria = db.session.get(CategoriaProducto, categoria_id)
    if categoria is None or not categoria.activa:
        raise ApiError("CATEGORIA_NO_DISPONIBLE", "Categoría de producto no disponible", 422)

    colores_disponibles = db.session.execute(
        select(Color).where(Color.es_comercial.is_(True)).order_by(Color.codigo)
    ).scalars().all()
    por_codigo = {color.codigo: color for color in colores_disponibles}
    if colores is None:
        colores_elegidos = list(colores_disponibles)
    else:
        codigos = {str(codigo).upper() for codigo in colores}
        desconocidos = codigos - set(por_codigo)
        if desconocidos:
            raise ApiError(
                "COLOR_NO_DISPONIBLE",
                "Solo se permiten colores comerciales BL, NG y GR",
                422,
                sorted(desconocidos),
            )
        colores_elegidos = [por_codigo[codigo] for codigo in sorted(codigos)]
    if not colores_elegidos:
        raise ApiError("COLOR_REQUERIDO", "Se requiere al menos un color comercial", 422)

    codigos_talla = TALLAS_CON_TALLA if categoria.usa_tallas else TALLAS_UNICA
    tallas_disponibles = db.session.execute(
        select(Talla).where(Talla.codigo.in_(codigos_talla)).order_by(Talla.orden)
    ).scalars().all()
    por_codigo_talla = {talla.codigo: talla for talla in tallas_disponibles}
    if tallas is None:
        tallas_elegidas = list(tallas_disponibles)
    else:
        codigos = {str(codigo).upper() for codigo in tallas}
        desconocidos = codigos - set(por_codigo_talla)
        if desconocidos:
            raise ApiError(
                "TALLA_NO_DISPONIBLE", "Talla no válida para la categoría", 422, sorted(desconocidos)
            )
        tallas_elegidas = [por_codigo_talla[codigo] for codigo in codigos]
    if not tallas_elegidas:
        raise ApiError("TALLA_REQUERIDA", "Se requiere al menos una talla", 422)

    return categoria, tallas_elegidas, colores_elegidos


def _generar_codigo_base(categoria: CategoriaProducto) -> str:
    fila = db.session.execute(
        select(CategoriaProducto).where(CategoriaProducto.id == categoria.id).with_for_update()
    ).scalars().first()
    total = db.session.scalar(
        select(func.count()).select_from(Producto).where(Producto.categoria_id == fila.id)
    ) or 0
    consecutivo = 1 if total == 0 else total + 1
    while True:
        candidato = fila.prefijo_sku if consecutivo == 1 else f"{fila.prefijo_sku}{consecutivo}"
        if len(candidato) > 4:
            raise ApiError(
                "CODIGO_SKU_AGOTADO", "No hay códigos base disponibles para la categoría", 409
            )
        usado = db.session.scalar(
            select(func.count()).select_from(Producto).where(Producto.codigo_sku == candidato)
        )
        if not usado:
            return candidato
        consecutivo += 1


def _verificar_skus(skus) -> None:
    if not skus:
        return
    existentes = db.session.execute(
        select(VarianteProducto.sku).where(VarianteProducto.sku.in_(skus))
    ).scalars().all()
    if existentes:
        raise ApiError("SKU_DUPLICADO", "Ya existen variantes con ese SKU", 409, sorted(existentes))


def _crear_variantes(
    producto,
    tallas,
    colores,
    usuario_id,
    stock_minimo: int,
    cantidad_reposicion: int,
):
    skus = [
        f"{producto.codigo_sku}-{talla.codigo}-{color.codigo}"
        for talla in tallas
        for color in colores
    ]
    _verificar_skus(skus)

    existentes = {
        (fila[0], fila[1], fila[2])
        for fila in db.session.execute(
            select(
                VarianteProducto.producto_id,
                VarianteProducto.talla_id,
                VarianteProducto.color_id,
            ).where(VarianteProducto.producto_id == producto.id)
        ).all()
    }
    creadas = []
    for talla in tallas:
        receta = db.session.execute(
            select(Receta).where(
                Receta.producto_id == producto.id, Receta.talla_id == talla.id
            )
        ).scalars().first()
        if receta is None:
            if not db.session.scalar(
                select(func.count()).select_from(Receta).where(
                    Receta.producto_id == producto.id,
                    Receta.talla_id == talla.id,
                    Receta.estado == "BORRADOR",
                )
            ):
                receta_service.crear_borrador(producto.id, talla.id, usuario_id)
        for color in colores:
            clave = (producto.id, talla.id, color.id)
            if clave in existentes:
                continue
            variante = VarianteProducto(
                producto_id=producto.id,
                talla_id=talla.id,
                color_id=color.id,
                sku=f"{producto.codigo_sku}-{talla.codigo}-{color.codigo}",
                activa=False,
            )
            db.session.add(variante)
            db.session.flush()
            db.session.add(
                StockVariante(
                    variante_id=variante.id,
                    existencia=0,
                    reservado=0,
                    stock_minimo=stock_minimo,
                    cantidad_reposicion=cantidad_reposicion,
                )
            )
            creadas.append(variante.id)
    return creadas


def _imagenes(producto_id: int) -> list:
    filas = db.session.execute(
        select(ProductoImagen, Color)
        .outerjoin(Color, Color.id == ProductoImagen.color_id)
        .where(ProductoImagen.producto_id == producto_id)
        .order_by(ProductoImagen.orden, ProductoImagen.id)
    ).all()
    return [
        {
            "id": imagen.id,
            "color": color.codigo if color else None,
            "url": imagen.url,
            "orden": imagen.orden,
        }
        for imagen, color in filas
    ]


def _variantes(producto_id: int) -> list:
    filas = db.session.execute(
        select(VarianteProducto, StockVariante, Talla, Color)
        .join(StockVariante, StockVariante.variante_id == VarianteProducto.id)
        .join(Talla, Talla.id == VarianteProducto.talla_id)
        .join(Color, Color.id == VarianteProducto.color_id)
        .where(VarianteProducto.producto_id == producto_id)
        .order_by(Talla.orden, Color.codigo)
    ).all()
    return [
        {
            "id": variante.id,
            "sku": variante.sku,
            "talla": talla.codigo,
            "color": color.codigo,
            "activa": variante.activa,
            "existencia": stock.existencia,
            "reservado": stock.reservado,
            "disponible": stock.existencia - stock.reservado,
            "stock_minimo": stock.stock_minimo,
            "cantidad_reposicion": stock.cantidad_reposicion,
        }
        for variante, stock, talla, color in filas
    ]


def _recetas(producto_id: int) -> list:
    filas = db.session.execute(
        select(Receta, Talla)
        .join(Talla, Talla.id == Receta.talla_id)
        .where(Receta.producto_id == producto_id)
        .order_by(Talla.orden, Receta.version.desc())
    ).all()
    return [
        {
            "id": receta.id,
            "talla": talla.codigo,
            "version": receta.version,
            "estado": receta.estado,
            "activada_en": receta.activada_en,
        }
        for receta, talla in filas
    ]


def _financiero(producto) -> dict:
    recetas = db.session.execute(
        select(Receta).where(
            Receta.producto_id == producto.id, Receta.estado == "VIGENTE"
        )
    ).scalars().all()
    if not recetas:
        return {"costo_estandar": None, "margen_real": None}
    costos = [receta_service.desglose_costos(receta)["costo_estandar"] for receta in recetas]
    costo = max(costos)
    return {
        "costo_estandar": costo,
        "margen_real": receta_service.margen_real(producto.precio_venta, costo),
    }


def _detalle(producto) -> dict:
    return {
        "id": producto.id,
        "codigo_sku": producto.codigo_sku,
        "nombre": producto.nombre,
        "descripcion": producto.descripcion,
        "composicion_textil": producto.composicion_textil,
        "guia_medidas": producto.guia_medidas,
        "precio_venta": producto.precio_venta,
        "permite_bajo_pedido": producto.permite_bajo_pedido,
        "activo": producto.activo,
        "eliminado_en": producto.eliminado_en,
        "categoria": producto.categoria.nombre,
        "categoria_id": producto.categoria_id,
        "variantes": _variantes(producto.id),
        "imagenes": _imagenes(producto.id),
        "recetas": _recetas(producto.id),
        **_financiero(producto),
    }


def crear_producto(datos: dict, usuario_id: int, ip=None) -> dict:
    try:
        categoria, tallas, colores = _catalogos(
            datos["categoria_id"], datos.get("colores"), datos.get("tallas")
        )
        codigo = _generar_codigo_base(categoria)
        producto = Producto(
            categoria_id=categoria.id,
            codigo_sku=codigo,
            nombre=datos["nombre"],
            descripcion=datos["descripcion"],
            composicion_textil=datos["composicion_textil"],
            guia_medidas=datos["guia_medidas"],
            precio_venta=datos["precio_venta"],
            permite_bajo_pedido=datos.get("permite_bajo_pedido", False),
            activo=False,
        )
        db.session.add(producto)
        db.session.flush()
        creadas = _crear_variantes(
            producto,
            tallas,
            colores,
            usuario_id,
            datos.get(
                "stock_minimo", valor_entero("stock_minimo_variante", 5)
            ),
            datos.get(
                "cantidad_reposicion", valor_entero("cantidad_reposicion_variante", 20)
            ),
        )
        registrar_bitacora(
            usuario_id,
            "PRODUCTO_CREADO",
            "producto",
            producto.id,
            {"codigo_sku": codigo, "variantes": len(creadas)},
            ip,
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("SKU_DUPLICADO", "El SKU generado ya existe", 409)
    except Exception:
        db.session.rollback()
        raise
    return _detalle(producto)


def listar(filtros=None) -> list:
    filtros = filtros or {}
    consulta = select(Producto).where(Producto.eliminado_en.is_(None))
    if filtros.get("categoria"):
        valor = str(filtros["categoria"]).upper()
        consulta = consulta.join(
            CategoriaProducto, CategoriaProducto.id == Producto.categoria_id
        ).where(
            (CategoriaProducto.prefijo_sku == valor)
            | (func.upper(CategoriaProducto.nombre) == valor)
        )
    if filtros.get("activo") is not None:
        consulta = consulta.where(Producto.activo.is_(bool(filtros["activo"])))
    if filtros.get("q"):
        patron = f"%{filtros['q']}%"
        consulta = consulta.where(
            Producto.nombre.like(patron) | Producto.codigo_sku.like(patron)
        )
    productos = db.session.execute(consulta.order_by(Producto.nombre)).scalars().all()
    respuesta = []
    for producto in productos:
        detalle = _detalle(producto)
        detalle["numero_variantes"] = len(detalle["variantes"])
        detalle.pop("variantes")
        detalle.pop("imagenes")
        detalle.pop("recetas")
        respuesta.append(detalle)
    return respuesta


def obtener(producto_id: int) -> dict:
    return _detalle(_obtener_producto(producto_id))


def actualizar(producto_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    try:
        producto = _obtener_producto(producto_id)
        cambios = {}
        campos = (
            "nombre",
            "descripcion",
            "composicion_textil",
            "guia_medidas",
            "precio_venta",
            "permite_bajo_pedido",
        )
        for campo in campos:
            if campo in datos:
                anterior = getattr(producto, campo)
                nuevo = datos[campo]
                if anterior != nuevo:
                    cambios[campo] = {"anterior": str(anterior), "nuevo": str(nuevo)}
                    setattr(producto, campo, nuevo)
        if "precio_venta" in cambios:
            registrar_bitacora(
                usuario_id,
                "PRECIO_ACTUALIZADO",
                "producto",
                producto.id,
                cambios["precio_venta"],
                ip,
            )
        cambios.pop("precio_venta", None)
        if cambios:
            registrar_bitacora(
                usuario_id, "PRODUCTO_ACTUALIZADO", "producto", producto.id, cambios, ip
            )
        if "colores" in datos or "tallas" in datos:
            actuales = db.session.execute(
                select(VarianteProducto).where(VarianteProducto.producto_id == producto_id)
            ).scalars().all()
            tallas_actuales = sorted({variante.talla.codigo for variante in actuales})
            colores_actuales = sorted({variante.color.codigo for variante in actuales})
            categoria, tallas, colores = _catalogos(
                producto.categoria_id,
                datos.get("colores", colores_actuales),
                datos.get("tallas", tallas_actuales),
            )
            creadas = _crear_variantes(
                producto,
                tallas,
                colores,
                usuario_id,
                valor_entero("stock_minimo_variante", 5),
                valor_entero("cantidad_reposicion_variante", 20),
            )
            registrar_bitacora(
                usuario_id,
                "VARIANTES_AGREGADAS",
                "producto",
                producto.id,
                {"variantes": creadas},
                ip,
            )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("SKU_DUPLICADO", "El SKU generado ya existe", 409)
    except Exception:
        db.session.rollback()
        raise
    return _detalle(producto)


def _tiene_historial(producto_id: int) -> bool:
    variantes = select(VarianteProducto.id).where(VarianteProducto.producto_id == producto_id)
    if db.session.scalar(
        select(func.count()).select_from(VentaLinea).where(VentaLinea.variante_id.in_(variantes))
    ):
        return True
    for modelo in (MovimientoProducto, Merma, OrdenProduccionLinea, CarritoLinea):
        if db.session.scalar(
            select(func.count()).select_from(modelo).where(modelo.variante_id.in_(variantes))
        ):
            return True
    if db.session.scalar(
        select(func.count())
        .select_from(DevolucionLinea)
        .join(VentaLinea, VentaLinea.id == DevolucionLinea.venta_linea_id)
        .where(VentaLinea.variante_id.in_(variantes))
    ) or db.session.scalar(
        select(func.count())
        .select_from(DevolucionLinea)
        .where(DevolucionLinea.variante_cambio_id.in_(variantes))
    ):
        return True
    if db.session.scalar(
        select(func.count()).select_from(Receta).where(
            Receta.producto_id == producto_id, Receta.estado != "BORRADOR"
        )
    ):
        return True
    return False


def _borrar_sin_historial(producto) -> None:
    variantes = select(VarianteProducto.id).where(VarianteProducto.producto_id == producto.id)
    recetas = select(Receta.id).where(Receta.producto_id == producto.id)
    db.session.execute(delete(RecetaBordado).where(RecetaBordado.receta_id.in_(recetas)))
    db.session.execute(delete(RecetaLinea).where(RecetaLinea.receta_id.in_(recetas)))
    db.session.execute(delete(Receta).where(Receta.producto_id == producto.id))
    db.session.execute(delete(ProductoImagen).where(ProductoImagen.producto_id == producto.id))
    db.session.execute(delete(StockVariante).where(StockVariante.variante_id.in_(variantes)))
    db.session.execute(delete(VarianteProducto).where(VarianteProducto.producto_id == producto.id))
    db.session.delete(producto)


def desactivar(producto_id: int, usuario_id: int, ip=None) -> None:
    try:
        producto = _obtener_producto(producto_id)
        if _tiene_historial(producto_id):
            producto.activo = False
            producto.eliminado_en = _ahora()
            for variante in db.session.execute(
                select(VarianteProducto).where(VarianteProducto.producto_id == producto_id)
            ).scalars():
                variante.activa = False
            accion = "PRODUCTO_DESACTIVADO"
        else:
            _borrar_sin_historial(producto)
            accion = "PRODUCTO_ELIMINADO"
        registrar_bitacora(
            usuario_id, accion, "producto", producto_id, {"codigo_sku": producto.codigo_sku}, ip
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def _guardar_archivo(archivo) -> tuple:
    datos = archivo.read(TAMANO_MAXIMO + 1)
    if len(datos) > TAMANO_MAXIMO:
        raise ApiError("ARCHIVO_GRANDE", "La imagen no puede superar 2 MB", 400)
    if not datos:
        raise ApiError("ARCHIVO_VACIO", "El archivo de imagen está vacío", 400)

    mime = (archivo.mimetype or "").lower()
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        raise ApiError("IMAGEN_NO_VALIDA", "No se pudo verificar la imagen", 422)
    try:
        with Image.open(io.BytesIO(datos)) as imagen:
            formato = imagen.format
            imagen.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise ApiError("IMAGEN_NO_VALIDA", "El archivo no es una imagen válida", 422)
    permitido = EXTENSIONES.get(formato)
    if permitido is None or mime != permitido[1]:
        raise ApiError("IMAGEN_NO_VALIDA", "Formato o MIME de imagen no permitido", 422)

    directorio = current_app.config.get("UPLOAD_FOLDER") or "/var/lib/unique/uploads"
    nombre = f"{secrets.token_hex(16)}.{permitido[0]}"
    try:
        os.makedirs(directorio, exist_ok=True)
        with open(os.path.join(directorio, nombre), "xb") as destino:
            destino.write(datos)
    except OSError:
        raise ApiError("ERROR_ALMACENAMIENTO", "No se pudo guardar la imagen", 500)
    return nombre, f"/uploads/{nombre}"


def agregar_imagen(producto_id: int, archivo, usuario_id: int, ip=None, datos=None) -> dict:
    datos = datos or {}
    nombre = None
    try:
        producto = _obtener_producto(producto_id)
        color_id = None
        if datos.get("color"):
            color = db.session.execute(
                select(Color).where(func.upper(Color.codigo) == str(datos["color"]).upper())
            ).scalars().first()
            if color is None:
                raise ApiError("COLOR_NO_ENCONTRADO", "Color no encontrado", 404)
            color_id = color.id
        nombre, url = _guardar_archivo(archivo)
        imagen = ProductoImagen(
            producto_id=producto.id,
            color_id=color_id,
            url=url,
            orden=int(datos.get("orden") or 0),
        )
        db.session.add(imagen)
        db.session.flush()
        registrar_bitacora(
            usuario_id,
            "IMAGEN_AGREGADA",
            "producto",
            producto_id,
            {"archivo": nombre, "color_id": color_id},
            ip,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        if nombre:
            directorio = current_app.config.get("UPLOAD_FOLDER") or "/var/lib/unique/uploads"
            try:
                os.remove(os.path.join(directorio, nombre))
            except OSError:
                pass
        raise
    return {
        "id": imagen.id,
        "color": datos.get("color") and str(datos["color"]).upper(),
        "url": imagen.url,
        "orden": imagen.orden,
    }


def actualizar_variante(variante_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    try:
        variante = db.session.get(VarianteProducto, variante_id)
        if variante is None:
            raise ApiError("VARIANTE_NO_ENCONTRADA", "Variante no encontrada", 404)
        anterior = variante.activa
        variante.activa = bool(datos["activa"])
        registrar_bitacora(
            usuario_id,
            "VARIANTE_ACTUALIZADA",
            "variante_producto",
            variante_id,
            {"activa": {"anterior": anterior, "nuevo": variante.activa}},
            ip,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    for item in _variantes(variante.producto_id):
        if item["id"] == variante.id:
            return item
    return {}


def activar(producto_id: int, usuario_id: int, ip=None) -> dict:
    try:
        producto = _obtener_producto(producto_id)
        if producto.activo:
            raise ApiError("PRODUCTO_YA_ACTIVO", "El producto ya está activo", 409)
        if not db.session.scalar(
            select(func.count()).select_from(ProductoImagen).where(
                ProductoImagen.producto_id == producto_id
            )
        ):
            raise ApiError("IMAGEN_REQUERIDA", "Se requiere al menos una imagen", 422)
        tallas = db.session.execute(
            select(Talla)
            .join(VarianteProducto, VarianteProducto.talla_id == Talla.id)
            .where(VarianteProducto.producto_id == producto_id)
            .distinct()
        ).scalars().all()
        faltantes = []
        for talla in tallas:
            vigente = db.session.scalar(
                select(func.count()).select_from(Receta).where(
                    Receta.producto_id == producto_id,
                    Receta.talla_id == talla.id,
                    Receta.estado == "VIGENTE",
                )
            )
            if not vigente:
                faltantes.append(talla.codigo)
        if faltantes:
            raise ApiError(
                "RECETA_NO_VIGENTE",
                "Todas las tallas deben tener receta vigente",
                422,
                faltantes,
            )
        producto.activo = True
        for variante in db.session.execute(
            select(VarianteProducto).where(VarianteProducto.producto_id == producto_id)
        ).scalars():
            variante.activa = True
        registrar_bitacora(
            usuario_id, "PRODUCTO_ACTIVADO", "producto", producto_id, {}, ip
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return _detalle(producto)
