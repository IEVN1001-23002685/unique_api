"""Biblioteca de diseños de bordado y sus hilos por aplicación (M11)."""

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import CategoriaMaterial, DisenoBordado, DisenoBordadoHilo, Material
from app.services.bitacora_service import registrar_bitacora
from app.utils.errores import ApiError


def _obtener(diseno_id: int) -> DisenoBordado:
    diseno = db.session.get(DisenoBordado, diseno_id)
    if diseno is None:
        raise ApiError("DISENO_NO_ENCONTRADO", "Diseño de bordado no encontrado", 404)
    return diseno


def _hilos(diseno_id: int) -> list:
    filas = db.session.execute(
        select(DisenoBordadoHilo, Material)
        .join(Material, Material.id == DisenoBordadoHilo.material_id)
        .where(DisenoBordadoHilo.diseno_id == diseno_id)
        .order_by(Material.codigo)
    ).all()
    return [
        {
            "material_id": hilo.material_id,
            "material_codigo": material.codigo,
            "material_nombre": material.nombre,
            "metros_por_aplicacion": hilo.metros_por_aplicacion,
        }
        for hilo, material in filas
    ]


def _detalle(diseno) -> dict:
    return {
        "id": diseno.id,
        "codigo": diseno.codigo,
        "nombre": diseno.nombre,
        "ancho_cm": diseno.ancho_cm,
        "alto_cm": diseno.alto_cm,
        "estado": diseno.estado,
        "notas": diseno.notas,
        "activo": diseno.activo,
        "hilos": _hilos(diseno.id),
    }


def _validar_hilos(hilos) -> dict:
    if hilos is None:
        return {}
    materiales = {}
    for hilo in hilos:
        material_id = int(hilo["material_id"])
        if material_id in materiales:
            raise ApiError(
                "HILO_DUPLICADO", "El material de hilo está repetido en el diseño", 400
            )
        material = db.session.execute(
            select(Material)
            .join(CategoriaMaterial, CategoriaMaterial.id == Material.categoria_material_id)
            .where(
                Material.id == material_id,
                Material.activo.is_(True),
                func.upper(CategoriaMaterial.nombre) == "HILO",
            )
        ).scalars().first()
        if material is None:
            raise ApiError(
                "HILO_NO_DISPONIBLE", "El material debe ser un hilo activo del catálogo", 422
            )
        metros = hilo["metros_por_aplicacion"]
        if metros is None:
            raise ApiError("METROS_REQUERIDOS", "Se requieren metros por aplicación", 400)
        materiales[material_id] = metros
    return materiales


def _reemplazar_hilos(diseno_id: int, materiales: dict) -> None:
    db.session.execute(
        delete(DisenoBordadoHilo).where(DisenoBordadoHilo.diseno_id == diseno_id)
    )
    for material_id, metros in materiales.items():
        db.session.add(
            DisenoBordadoHilo(
                diseno_id=diseno_id,
                material_id=material_id,
                metros_por_aplicacion=metros,
            )
        )


def listar(filtros=None) -> list:
    filtros = filtros or {}
    consulta = select(DisenoBordado)
    if filtros.get("activo") is not None:
        consulta = consulta.where(DisenoBordado.activo.is_(bool(filtros["activo"])))
    if filtros.get("estado"):
        consulta = consulta.where(DisenoBordado.estado == filtros["estado"])
    disenos = db.session.execute(consulta.order_by(DisenoBordado.codigo)).scalars().all()
    return [_detalle(diseno) for diseno in disenos]


def obtener(diseno_id: int) -> dict:
    return _detalle(_obtener(diseno_id))


def crear(datos: dict, usuario_id: int, ip=None) -> dict:
    try:
        if db.session.scalar(
            select(func.count()).select_from(DisenoBordado).where(DisenoBordado.codigo == datos["codigo"])
        ):
            raise ApiError("DISENO_DUPLICADO", "Ya existe un diseño con ese código", 409)
        hilos = _validar_hilos(datos.get("hilos"))
        diseno = DisenoBordado(
            codigo=datos["codigo"],
            nombre=datos["nombre"],
            ancho_cm=datos["ancho_cm"],
            alto_cm=datos["alto_cm"],
            notas=datos.get("notas"),
            activo=datos.get("activo", True),
            estado="DIGITALIZADO" if hilos else "PENDIENTE",
        )
        db.session.add(diseno)
        db.session.flush()
        if hilos:
            _reemplazar_hilos(diseno.id, hilos)
        registrar_bitacora(
            usuario_id,
            "DISENO_CREADO",
            "diseno_bordado",
            diseno.id,
            {"codigo": diseno.codigo, "estado": diseno.estado},
            ip,
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("DISENO_DUPLICADO", "Ya existe un diseño con ese código", 409)
    except Exception:
        db.session.rollback()
        raise
    return _detalle(diseno)


def actualizar(diseno_id: int, datos: dict, usuario_id: int, ip=None) -> dict:
    try:
        diseno = _obtener(diseno_id)
        cambios = {}
        for campo in ("nombre", "ancho_cm", "alto_cm", "notas", "activo", "codigo"):
            if campo in datos and getattr(diseno, campo) != datos[campo]:
                cambios[campo] = str(getattr(diseno, campo))
                setattr(diseno, campo, datos[campo])
        if "hilos" in datos:
            hilos = _validar_hilos(datos["hilos"])
            _reemplazar_hilos(diseno_id, hilos)
            if hilos:
                diseno.estado = "DIGITALIZADO"
                cambios["estado"] = "DIGITALIZADO"
        elif "estado" in datos:
            estado = datos["estado"]
            if estado == "DIGITALIZADO" and not _hilos(diseno_id):
                raise ApiError(
                    "DISENO_SIN_HILOS", "Se requieren hilos para digitalizar el diseño", 422
                )
            diseno.estado = estado
            cambios["estado"] = estado
        registrar_bitacora(
            usuario_id, "DISENO_ACTUALIZADO", "diseno_bordado", diseno_id, cambios, ip
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiError("DISENO_DUPLICADO", "Ya existe un diseño con ese código", 409)
    except Exception:
        db.session.rollback()
        raise
    return _detalle(diseno)


def desactivar(diseno_id: int, usuario_id: int, ip=None) -> None:
    try:
        diseno = _obtener(diseno_id)
        diseno.activo = False
        registrar_bitacora(
            usuario_id,
            "DISENO_DESACTIVADO",
            "diseno_bordado",
            diseno_id,
            {"codigo": diseno.codigo},
            ip,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
