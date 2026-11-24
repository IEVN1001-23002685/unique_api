"""Carga idempotente de datos semilla de UNIQUE.

Uso:
    python -m scripts.seed
    python scripts/seed.py
"""

import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from argon2 import PasswordHasher

from app import create_app
from app.extensions import db
from app.models import (
    CausaMerma,
    CategoriaMaterial,
    CategoriaProducto,
    Color,
    Configuracion,
    Descuento,
    DisenoBordado,
    EmpaqueRegla,
    InventarioMaterial,
    Material,
    Producto,
    Receta,
    RecetaBordado,
    RecetaLinea,
    Rol,
    StockVariante,
    Talla,
    TarifaEnvio,
    Usuario,
    VarianteProducto,
)

logger = logging.getLogger(__name__)

PENDIENTE_CONFIRMACION = "PROPUESTA: pendiente de confirmar"

ROLES = ("CLIENTE", "OPERATIVO", "ADMIN")

COLORES = (
    ("BL", "Blanco", "#FFFFFF", True),
    ("NG", "Negro", "#000000", True),
    ("GR", "Gris", "#808080", True),
    ("NA", "No aplica", "#000000", False),
)

TALLAS = (("CH", "Chica", 1), ("MD", "Mediana", 2), ("GD", "Grande", 3), ("UN", "Única", 4))

CATEGORIAS_PRODUCTO = (
    ("Sudadera", "SD", True),
    ("Playera", "PL", True),
    ("Pantalón", "PN", True),
    ("Gorro", "GO", False),
    ("Bolsa de tela", "BO", False),
)

CATEGORIAS_MATERIAL = (
    "Tela",
    "Hilo",
    "Estabilizador",
    "Avío",
    "Etiqueta",
    "Empaque",
)

CAUSAS_MERMA = (
    ("Defecto de tela", "MATERIAL", "CORTE"),
    ("Rechazo en recepción", "AMBOS", "RECEPCION"),
    ("Error de corte", "MATERIAL", "CORTE"),
    ("Error de tejido", "MATERIAL", "TEJIDO"),
    ("Defecto de bordado", "AMBOS", "BORDADO"),
    ("Error de confección", "AMBOS", "CONFECCION"),
    ("Defecto de acabado", "PRODUCTO", "ACABADOS"),
    ("Daño en almacén", "AMBOS", "ALMACEN"),
    ("Daño en envío", "PRODUCTO", "ENTREGA"),
    ("Devolución de cliente dañada", "PRODUCTO", "DEVOLUCION"),
    ("Encogimiento o desgaste", "MATERIAL", "ALMACEN"),
    ("Sobrante inservible", "MATERIAL", "ALMACEN"),
    ("Otro", "AMBOS", "ALMACEN"),
)

DISEÑOS = (
    ("DIS-001", "Sudadera 22 × 15 cm", "22", "15"),
    ("DIS-002", "Playera 22 × 15 cm", "22", "15"),
    ("DIS-003", "Pantalón tubo 55 × 15 cm", "55", "15"),
    ("DIS-004", "Pantalón bolsillo 5 × 5 cm", "5", "5"),
    ("DIS-005", "Gorro 5 × 5 cm", "5", "5"),
    ("DIS-006", "Bolsa 20 × 20 cm", "20", "20"),
)

CONFIGURACION = (
    ("iva_pct", "16", "IVA incluido en precios", False),
    ("margen_objetivo_pct", "55", "Margen objetivo para precio sugerido", False),
    ("merma_meta_pct", "5", "Meta de merma y umbral de alerta", False),
    ("proveedor_minimo_a_tiempo_pct", "80", "Porcentaje mínimo de entregas a tiempo", False),
    ("dias_devolucion", "15", "Ventana de cambios y devoluciones", True),
    ("max_intentos_entrega", "2", "Intentos fallidos antes de alerta crítica", True),
    ("dias_produccion_estandar", "5", "Fecha estimada de pedidos bajo pedido", True),
    ("max_piezas_por_linea", "10", "Máximo de piezas por línea de carrito", True),
    ("saldo_inicial_cuenta_simulada", "5000.00", "Saldo inicial de cuenta simulada", True),
    ("envio_gratis_desde", "0", "Monto mínimo para envío gratis; 0 desactiva el beneficio", False),
    ("horas_max_recibido", "2", "Horas máximas en recibido antes de alerta", False),
    ("horas_max_confirmado", "24", "Horas máximas en confirmado antes de alerta", False),
    ("dias_max_en_produccion", "7", "Días máximos en producción antes de alerta", False),
    ("horas_max_en_preparacion", "24", "Horas máximas en preparación antes de alerta", False),
    ("horas_max_listo_envio", "24", "Horas máximas en listo para envío antes de alerta", False),
    ("horas_max_en_reparto", "24", "Horas máximas en reparto antes de alerta", False),
    ("horas_alerta_devolucion", "48", "Horas para alertar devolución sin atender", False),
    ("dias_carrito_abandonado", "7", "Días para marcar carrito como abandonado", False),
    ("intentos_login_max", "5", "Intentos de inicio de sesión permitidos", False),
    ("bloqueo_login_min", "15", "Minutos de bloqueo tras agotar los intentos", False),
    ("vigencia_recuperacion_min", "30", "Vigencia del enlace de recuperación en minutos", False),
)

MATERIALES = (
    ("TEL-FEL", "Felpa", "Tela", "M2", "Rollo 20 kg, 1.80 x 36 m = 64.80 m2", "64.80", "89.1975", "15", True),
    ("TEL-JER", "Jersey peinado", "Tela", "M2", "Rollo 20 kg, 1.80 x 76 m = 136.80 m2", "136.80", "25.7310", "15", True),
    ("TEL-RIB", "Tejido acanalado (rib)", "Tela", "M2", "Rollo 12 kg, 1.40 x 30 m = 42.00 m2", "42.00", "50.2857", "20", True),
    ("TEL-LON", "Loneta", "Tela", "M2", "Rollo de 1.50 x 50.00 m = 75.00 m2", "75.00", "76.5333", "10", True),
    ("HIL-EST", "Estambre acrílico", "Hilo", "M", "Cono de 1,000 g = 2,100 m", "2100", "0.247619", "5", True),
    ("HIL-COS", "Hilo de costura 40/2", "Hilo", "M", "Cono de 5,000 yd = 4,572 m", "4572", "0.012741", "10", False),
    ("HIL-BOR-001", "Hilo de bordado 120D/2 blanco", "Hilo", "M", "Cono de 5,000 m", "5000", "0.010600", "0", False),
    ("HIL-BOR-002", "Hilo de bordado 120D/2 negro", "Hilo", "M", "Cono de 5,000 m", "5000", "0.010600", "0", False),
    ("HIL-BOR-003", "Hilo de bordado 120D/2 gris", "Hilo", "M", "Cono de 5,000 m", "5000", "0.010600", "0", False),
    ("EST-HOJ", "Estabilizador de corte, hoja de 25 x 30 cm", "Estabilizador", "PZA", "Paquete de 100 piezas", "100", "5.0000", "0", False),
    ("EST-ROL", "Estabilizador de corte, rollo de 30.5 cm", "Estabilizador", "M", "Rollo de 22.86 m", "22.86", "21.9593", "0", False),
    ("AVI-COR", "Cordón redondo de poliéster, 120 cm", "Avío", "PZA", "Paquete de 2 piezas", "2", "32.7750", "0", False),
    ("AVI-OJI", "Ojillos metálicos de 8 mm con contra", "Avío", "PZA", "Millar de piezas", "1000", "0.4200", "0", False),
    ("ETQ-MAR", "Etiqueta de marca", "Etiqueta", "PZA", "Paquete de 500 piezas", "500", "0.6500", "0", False),
    ("ETQ-TAL-CH", "Etiqueta de talla CH", "Etiqueta", "PZA", "Paquete de 500 piezas", "500", "0.6500", "0", False),
    ("ETQ-TAL-MD", "Etiqueta de talla MD", "Etiqueta", "PZA", "Paquete de 500 piezas", "500", "0.6500", "0", False),
    ("ETQ-TAL-GD", "Etiqueta de talla GD", "Etiqueta", "PZA", "Paquete de 500 piezas", "500", "0.6500", "0", False),
    ("ETQ-COM-SD", "Etiqueta de composición y cuidado Sudadera", "Etiqueta", "PZA", "Paquete de 500 piezas", "500", "0.6500", "0", False),
    ("ETQ-COM-PL", "Etiqueta de composición y cuidado Playera", "Etiqueta", "PZA", "Paquete de 500 piezas", "500", "0.6500", "0", False),
    ("ETQ-COM-PN", "Etiqueta de composición y cuidado Pantalón", "Etiqueta", "PZA", "Paquete de 500 piezas", "500", "0.6500", "0", False),
    ("ETQ-COM-GO", "Etiqueta de composición y cuidado Gorro", "Etiqueta", "PZA", "Paquete de 500 piezas", "500", "0.6500", "0", False),
    ("ETQ-COM-BO", "Etiqueta de composición y cuidado Bolsa", "Etiqueta", "PZA", "Paquete de 500 piezas", "500", "0.6500", "0", False),
    ("EMP-BOL", "Bolsa individual kraft mediana", "Empaque", "PZA", "Lote de 200 piezas", "200", "12.0000", "0", False),
    ("EMP-PAP", "Papel protector", "Empaque", "PZA", "Lote de 200 piezas", "200", "2.5000", "0", False),
    ("EMP-TAR", "Tarjeta personalizada con QR", "Empaque", "PZA", "Lote de 200 piezas", "200", "5.0000", "0", False),
    ("EMP-ETE", "Etiqueta de envío", "Empaque", "PZA", "Por cotizar; factor provisional", "1", "0.0000", "0", False),
)

REGLAS_EMPAQUE = (
    ("EMP-BOL", "POR_PRENDA", "1"),
    ("EMP-PAP", "POR_PRENDA", "1"),
    ("EMP-TAR", "POR_PEDIDO", "1"),
    ("EMP-ETE", "POR_PEDIDO", "1"),
)

DISEÑOS_POR_PRODUCTO = {
    "SD": "DIS-001",
    "PL": "DIS-002",
    "PN": "DIS-003",
    "GO": "DIS-005",
    "BO": "DIS-006",
}

RECETAS = (
    ("SD", "CH", (("TEL-FEL", "0.9386"), ("TEL-RIB", "0.1048"), ("HIL-COS", "13.950"), ("EST-HOJ", "1"))),
    ("SD", "MD", (("TEL-FEL", "1.0184"), ("TEL-RIB", "0.1137"), ("HIL-COS", "14.540"), ("EST-HOJ", "1"))),
    ("SD", "GD", (("TEL-FEL", "1.1029"), ("TEL-RIB", "0.1231"), ("HIL-COS", "15.140"), ("EST-HOJ", "1"))),
    ("PL", "CH", (("TEL-JER", "0.7778"), ("TEL-RIB", "0.0872"), ("HIL-COS", "11.450"), ("EST-HOJ", "1"))),
    ("PL", "MD", (("TEL-JER", "0.9600"), ("TEL-RIB", "0.0946"), ("HIL-COS", "11.930"), ("EST-HOJ", "1"))),
    ("PL", "GD", (("TEL-JER", "1.0396"), ("TEL-RIB", "0.1025"), ("HIL-COS", "12.420"), ("EST-HOJ", "1"))),
    ("PN", "CH", (("TEL-FEL", "1.0364"), ("HIL-COS", "17.200"), ("EST-ROL", "0.610"), ("EST-HOJ", "0.25"), ("AVI-COR", "1"), ("AVI-OJI", "2"))),
    ("PN", "MD", (("TEL-FEL", "1.1245"), ("HIL-COS", "17.920"), ("EST-ROL", "0.610"), ("EST-HOJ", "0.25"), ("AVI-COR", "1"), ("AVI-OJI", "2"))),
    ("PN", "GD", (("TEL-FEL", "1.2178"), ("HIL-COS", "18.660"), ("EST-ROL", "0.610"), ("EST-HOJ", "0.25"), ("AVI-COR", "1"), ("AVI-OJI", "2"))),
    ("GO", "UN", (("HIL-EST", "130.000"), ("HIL-COS", "4.000"), ("EST-HOJ", "0.25"))),
    ("BO", "UN", (("TEL-LON", "0.3410"), ("HIL-COS", "11.650"), ("EST-HOJ", "1"))),
)

USUARIOS_INICIALES = (
    ("ADMIN_EMAIL", "ADMIN_PASSWORD", "ADMIN", "Administrador"),
    ("OPERATIVO_EMAIL", "OPERATIVO_PASSWORD", "OPERATIVO", "Operativo"),
)


def _decimal(valor):
    return Decimal(str(valor))


def _obtener(modelo, **filtros):
    return db.session.query(modelo).filter_by(**filtros).one()


def _insertar_si_falta(modelo, filtros, valores, contadores, clave):
    instancia = db.session.query(modelo).filter_by(**filtros).first()
    if instancia is not None:
        return instancia, False
    instancia = modelo(**filtros, **valores)
    db.session.add(instancia)
    db.session.flush()
    contadores[clave] += 1
    return instancia, True


def _sembrar_roles(contadores):
    for codigo in ROLES:
        _insertar_si_falta(
            Rol,
            {"codigo": codigo},
            {"nombre": codigo.title()},
            contadores,
            "roles",
        )


def _sembrar_catalogos(contadores):
    colores = {}
    for codigo, nombre, hex_color, es_comercial in COLORES:
        color, _ = _insertar_si_falta(
            Color,
            {"codigo": codigo},
            {"nombre": nombre, "hex": hex_color, "es_comercial": es_comercial},
            contadores,
            "colores",
        )
        colores[codigo] = color

    tallas = {}
    for codigo, nombre, orden in TALLAS:
        talla, _ = _insertar_si_falta(
            Talla,
            {"codigo": codigo},
            {"nombre": nombre, "orden": orden},
            contadores,
            "tallas",
        )
        tallas[codigo] = talla

    categorias_producto = {}
    for nombre, prefijo, usa_tallas in CATEGORIAS_PRODUCTO:
        categoria, _ = _insertar_si_falta(
            CategoriaProducto,
            {"prefijo_sku": prefijo},
            {"nombre": nombre, "usa_tallas": usa_tallas, "activa": True},
            contadores,
            "categorias_producto",
        )
        categorias_producto[prefijo] = categoria

    categorias_material = {}
    for nombre in CATEGORIAS_MATERIAL:
        categoria, _ = _insertar_si_falta(
            CategoriaMaterial,
            {"nombre": nombre},
            {"descripcion": nombre},
            contadores,
            "categorias_material",
        )
        categorias_material[nombre] = categoria

    for nombre, aplica_a, etapa in CAUSAS_MERMA:
        _insertar_si_falta(
            CausaMerma,
            {"nombre": nombre},
            {"aplica_a": aplica_a, "etapa_sugerida": etapa, "activa": True},
            contadores,
            "causas_merma",
        )

    disenos = {}
    for codigo, nombre, ancho, alto in DISEÑOS:
        diseno, _ = _insertar_si_falta(
            DisenoBordado,
            {"codigo": codigo},
            {
                "nombre": nombre,
                "ancho_cm": _decimal(ancho),
                "alto_cm": _decimal(alto),
                "estado": "PENDIENTE",
                "activo": True,
            },
            contadores,
            "disenos",
        )
        disenos[codigo] = diseno

    return colores, tallas, categorias_producto, categorias_material, disenos


def _sembrar_configuracion(contadores):
    for clave, valor, descripcion, es_propuesta in CONFIGURACION:
        texto = f"{PENDIENTE_CONFIRMACION} - {descripcion}" if es_propuesta else descripcion
        _insertar_si_falta(
            Configuracion,
            {"clave": clave},
            {"valor": valor, "descripcion": texto},
            contadores,
            "configuracion",
        )


def _sembrar_tarifa_y_descuento(contadores):
    _insertar_si_falta(
        TarifaEnvio,
        {"nombre": "Local León", "cp_inicio": "37000", "cp_fin": "37999"},
        {
            "costo": _decimal("200.00"),
            "dias_estimados": 2,
            "activa": True,
        },
        contadores,
        "tarifas_envio",
    )
    logger.warning(
        "Tarifa Local León: costo 200.00 y 2 dias son valores de referencia pendientes de confirmar."
    )

    _insertar_si_falta(
        Descuento,
        {"codigo": "PRIMERA_COMPRA"},
        {
            "nombre": "Primera compra",
            "tipo": "PORCENTAJE",
            "valor": _decimal("10"),
            "aplicacion": "AUTOMATICO",
            "solo_primera_compra": True,
            "vigente_desde": datetime.now(timezone.utc).date(),
            "usos_por_cliente": 1,
            "usos_actuales": 0,
            "activo": True,
        },
        contadores,
        "descuentos",
    )


def _sembrar_materiales(categorias_material, contadores):
    materiales = {}
    for (
        codigo,
        nombre,
        categoria,
        unidad_base,
        unidad_compra,
        factor,
        costo,
        merma,
        por_color,
    ) in MATERIALES:
        material, _ = _insertar_si_falta(
            Material,
            {"codigo": codigo},
            {
                "categoria_material_id": categorias_material[categoria].id,
                "nombre": nombre,
                "unidad_base": unidad_base,
                "unidad_compra": unidad_compra,
                "factor_compra_base": _decimal(factor),
                "costo_estandar_base": _decimal(costo),
                "merma_estandar_pct": _decimal(merma),
                "por_color": por_color,
                "activo": True,
            },
            contadores,
            "materiales",
        )
        materiales[codigo] = material
    return materiales


def _sembrar_inventario_material(materiales, colores, contadores):
    for material in materiales.values():
        ids_colores = ("BL", "NG", "GR") if material.por_color else ("NA",)
        for codigo_color in ids_colores:
            _insertar_si_falta(
                InventarioMaterial,
                {"material_id": material.id, "color_id": colores[codigo_color].id},
                {"stock_minimo": _decimal("0"), "stock_seguridad": _decimal("0"), "activo": True},
                contadores,
                "inventario_material",
            )


def _sembrar_productos(categorias_producto, tallas, colores, contadores):
    productos = {}
    for nombre, prefijo, usa_tallas in CATEGORIAS_PRODUCTO:
        producto, _ = _insertar_si_falta(
            Producto,
            {"codigo_sku": prefijo},
            {
                "categoria_id": categorias_producto[prefijo].id,
                "nombre": nombre,
                "descripcion": "",
                "composicion_textil": "",
                "guia_medidas": "",
                "precio_venta": _decimal("0.00"),
                "permite_bajo_pedido": True,
                "activo": False,
            },
            contadores,
            "productos",
        )
        productos[prefijo] = producto

        codigos_talla = ("CH", "MD", "GD") if usa_tallas else ("UN",)
        for codigo_talla in codigos_talla:
            for codigo_color in ("BL", "NG", "GR"):
                sku = f"{prefijo}-{codigo_talla}-{codigo_color}"
                variante, _ = _insertar_si_falta(
                    VarianteProducto,
                    {"sku": sku},
                    {
                        "producto_id": producto.id,
                        "talla_id": tallas[codigo_talla].id,
                        "color_id": colores[codigo_color].id,
                        "activa": False,
                    },
                    contadores,
                    "variantes",
                )
                _insertar_si_falta(
                    StockVariante,
                    {"variante_id": variante.id},
                    {
                        "existencia": 0,
                        "reservado": 0,
                        "stock_minimo": 5,
                        "cantidad_reposicion": 20,
                    },
                    contadores,
                    "stock_variantes",
                )

    logger.warning(
        "Productos y variantes sembrados como inactivos, sin precio y con existencia 0; "
        "stock minimo 5 y reposicion 20 son propuestos por confirmar."
    )
    return productos


def _cantidad_bruta(cantidad_neta, merma_pct):
    tasa = Decimal("1") - _decimal(merma_pct) / Decimal("100")
    return (_decimal(cantidad_neta) / tasa).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def _lineas_etiqueta(prefijo, codigo_talla):
    codigos = ["ETQ-MAR"]
    if codigo_talla != "UN":
        codigos.append(f"ETQ-TAL-{codigo_talla}")
    codigos.append(f"ETQ-COM-{prefijo}")
    return tuple((codigo, "1") for codigo in codigos)


def _creador_de_recetas():
    if Receta.__table__.c.creada_por.nullable:
        return None
    administrador = (
        db.session.query(Usuario)
        .join(Rol, Usuario.rol_id == Rol.id)
        .filter(Rol.codigo == "ADMIN")
        .first()
    )
    if administrador is None:
        raise RuntimeError(
            "Receta.creada_por no admite NULL en el modelo actual; defina ADMIN_EMAIL "
            "y ADMIN_PASSWORD o permita NULL en esa columna antes de cargar las recetas semilla."
        )
    logger.warning(
        "Receta.creada_por no admite NULL en el modelo actual; se asigna el administrador inicial."
    )
    return administrador.id


def _sembrar_recetas(productos, tallas, materiales, disenos, contadores):
    for prefijo, codigo_talla, consumos in RECETAS:
        filtros = {
            "producto_id": productos[prefijo].id,
            "talla_id": tallas[codigo_talla].id,
            "version": 1,
        }
        valores = {
            "estado": "BORRADOR",
            "mano_obra": _decimal("0"),
            "costo_bordado": _decimal("0"),
            "costos_indirectos": _decimal("0"),
        }
        if db.session.query(Receta).filter_by(**filtros).first() is None:
            valores["creada_por"] = _creador_de_recetas()
        receta, _ = _insertar_si_falta(
            Receta, filtros, valores, contadores, "recetas"
        )

        lineas = tuple(consumos) + _lineas_etiqueta(prefijo, codigo_talla)
        for codigo_material, cantidad_neta in lineas:
            material = materiales[codigo_material]
            merma = _decimal(material.merma_estandar_pct)
            _insertar_si_falta(
                RecetaLinea,
                {"receta_id": receta.id, "material_id": material.id},
                {
                    "cantidad_neta": _decimal(cantidad_neta),
                    "factor_consumo": _decimal("1.000"),
                    "merma_pct": merma,
                    "cantidad_bruta": _cantidad_bruta(cantidad_neta, merma),
                },
                contadores,
                "recetas_lineas",
            )

        diseno = disenos[DISEÑOS_POR_PRODUCTO[prefijo]]
        _insertar_si_falta(
            RecetaBordado,
            {"receta_id": receta.id, "diseno_id": diseno.id},
            {"aplicaciones": 1},
            contadores,
            "recetas_bordado",
        )

    logger.warning(
        "Las 11 recetas semilla quedan en BORRADOR; el consumo de Playera CH tiene una "
        "nota de patron pendiente y no debe activarse sin verificacion. El hilo de bordado "
        "no se registra en metros mientras el diseno este PENDIENTE."
    )


def _sembrar_reglas_empaque(materiales, contadores):
    for codigo, base, cantidad in REGLAS_EMPAQUE:
        material = materiales[codigo]
        _insertar_si_falta(
            EmpaqueRegla,
            {"material_id": material.id, "base": base},
            {"cantidad": _decimal(cantidad), "activa": True},
            contadores,
            "reglas_empaque",
        )


def _sembrar_usuarios(contadores):
    hasher = PasswordHasher()
    for variable_correo, variable_clave, codigo_rol, nombre in USUARIOS_INICIALES:
        correo = (os.getenv(variable_correo) or "").strip().lower()
        clave = os.getenv(variable_clave) or ""
        if not correo or not clave:
            logger.warning(
                "Se omite la cuenta %s: defina %s y %s para crearla.",
                codigo_rol,
                variable_correo,
                variable_clave,
            )
            continue
        if db.session.query(Usuario).filter_by(correo=correo).first() is not None:
            logger.info("La cuenta con correo registrado ya existe; no se modifica.")
            continue
        rol = _obtener(Rol, codigo=codigo_rol)
        db.session.add(
            Usuario(
                rol_id=rol.id,
                nombre=nombre,
                apellidos="UNIQUE",
                correo=correo,
                telefono="",
                password_hash=hasher.hash(clave),
                estado_cuenta="ACTIVA",
                acepta_promociones=False,
            )
        )
        db.session.flush()
        contadores["usuarios"] += 1
        logger.info("Se creo una cuenta inicial con rol %s.", codigo_rol)


def seed():
    """Carga o completa los datos semilla sin sobrescribir los existentes."""
    contadores = Counter()
    try:
        _sembrar_roles(contadores)
        colores, tallas, categorias_producto, categorias_material, disenos = _sembrar_catalogos(
            contadores
        )
        _sembrar_configuracion(contadores)
        _sembrar_tarifa_y_descuento(contadores)
        materiales = _sembrar_materiales(categorias_material, contadores)
        _sembrar_inventario_material(materiales, colores, contadores)
        productos = _sembrar_productos(categorias_producto, tallas, colores, contadores)
        _sembrar_usuarios(contadores)
        _sembrar_recetas(productos, tallas, materiales, disenos, contadores)
        _sembrar_reglas_empaque(materiales, contadores)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("La siembra fallo; se revirtio la transaccion completa.")
        raise

    logger.info("Siembra completada. Registros insertados: %s", dict(contadores))
    return dict(contadores)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = create_app()
    with app.app_context():
        seed()


if __name__ == "__main__":
    main()
