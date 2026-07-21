"""
notificaciones.py — Helpers para crear notificaciones internas.
Importado por cualquier módulo que necesite generar alertas.
"""
import json
from sqlalchemy.orm import Session
from database.models import Notificacion, Usuario


def _get_todos_usuarios(db: Session) -> list:
    """Retorna todos los usuarios activos."""
    return db.query(Usuario).filter(Usuario.activo == True).all()


def crear_notificacion(
    db: Session,
    usuario_id: int,
    titulo: str,
    mensaje: str,
    tipo: str = "INFO",
    referencia_id: int = None,
    referencia_tipo: str = None,
):
    """Inserta una notificación para un usuario. No hace commit."""
    db.add(Notificacion(
        usuario_id=usuario_id,
        titulo=titulo,
        mensaje=mensaje,
        tipo=tipo,
        referencia_id=referencia_id,
        referencia_tipo=referencia_tipo,
        leida=False,
    ))


def notificar_todos(
    db: Session,
    titulo: str,
    mensaje: str,
    tipo: str = "INFO",
    referencia_id: int = None,
    referencia_tipo: str = None,
    url: str = "/",
):
    """Genera la misma notificación in-app para todos los usuarios activos
    y envía Web Push a todos los dispositivos suscritos."""
    for u in _get_todos_usuarios(db):
        crear_notificacion(db, u.id, titulo, mensaje, tipo, referencia_id, referencia_tipo)

    # Web Push (importación lazy para evitar circularidad)
    try:
        from routers.push import notificar_push_todos
        notificar_push_todos(db, titulo, mensaje, url)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[PUSH] No se pudo enviar push: {e}")


def notificar_nueva_venta(
    db: Session,
    tipo_venta: str,          # "CONTADO" | "FINANCIADA"
    cliente_nombre: str,
    producto: str,
    modelo: str,
    monto: float,
    vendedor_id: int = None,
    supervisor_id: int = None,
    referencia_id: int = None,
):
    """Notifica a TODOS los usuarios activos sobre una nueva venta."""
    tipo_label = "Contado" if tipo_venta == "CONTADO" else "Financiada"
    monto_fmt = f"${monto:,.0f}".replace(",", ".")
    titulo = f"💰 Nueva Venta {tipo_label} — {cliente_nombre}"
    mensaje = (
        f"Se registró una nueva venta {tipo_label.lower()}.\n"
        f"Cliente: {cliente_nombre}\n"
        f"Producto: {producto} {modelo}\n"
        f"Monto: {monto_fmt}"
    )
    notificar_todos(
        db, titulo, mensaje,
        tipo="VENTA",
        referencia_id=referencia_id,
        referencia_tipo=f"venta_{tipo_venta.lower()}",
    )


def notificar_videollamada(
    db: Session,
    accion: str,              # "NUEVA" | "REALIZADA" | "NO_SE_PRESENTO" | "REPROGRAMAR" | "CERRO"
    cliente_nombre: str,
    producto: str = "",
    fecha_hora: str = "",
    asesor_nombre: str = "",
    referencia_id: int = None,
):
    """Notifica a TODOS los usuarios activos sobre una videollamada."""
    emojis = {
        "NUEVA":          "📹",
        "REALIZADA":      "✅",
        "NO_SE_PRESENTO": "❌",
        "REPROGRAMAR":    "🔄",
        "CERRO":          "🏆",
    }
    acciones_label = {
        "NUEVA":          "Nueva videollamada agendada",
        "REALIZADA":      "Videollamada realizada",
        "NO_SE_PRESENTO": "Cliente no se presentó",
        "REPROGRAMAR":    "Videollamada a reprogramar",
        "CERRO":          "¡Cierre en videollamada!",
    }
    emoji = emojis.get(accion, "📹")
    label = acciones_label.get(accion, "Videollamada actualizada")

    titulo = f"{emoji} {label} — {cliente_nombre}"
    partes = [f"Cliente: {cliente_nombre}"]
    if producto:
        partes.append(f"Producto: {producto}")
    if fecha_hora:
        partes.append(f"Fecha/hora: {fecha_hora}")
    if asesor_nombre:
        partes.append(f"Asesor: {asesor_nombre}")
    mensaje = "\n".join(partes)

    notificar_todos(
        db, titulo, mensaje,
        tipo="VIDEOLLAMADA",
        referencia_id=referencia_id,
        referencia_tipo="videollamada",
    )
