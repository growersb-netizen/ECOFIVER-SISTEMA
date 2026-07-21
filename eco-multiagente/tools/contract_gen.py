"""
Generador de contratos PDF con ReportLab.
Dos templates: módulos financiados y piscinas financiadas.
"""

import io
import logging
from datetime import datetime, date
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

logger = logging.getLogger(__name__)

# Colores corporativos
COLOR_VERDE = colors.HexColor("#1A5C38")
COLOR_VERDE_CLARO = colors.HexColor("#E8F5EE")
COLOR_GRIS = colors.HexColor("#666666")


def _numero_contrato(tipo: str) -> str:
    """Genera número de contrato autoincrementado basado en timestamp."""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    prefijo = "MOD" if tipo == "modulos" else "PIS"
    return f"{prefijo}-{ts}"


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="Titulo",
        fontSize=18,
        textColor=COLOR_VERDE,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="Subtitulo",
        fontSize=11,
        textColor=COLOR_GRIS,
        alignment=TA_CENTER,
        fontName="Helvetica",
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="Seccion",
        fontSize=10,
        textColor=COLOR_VERDE,
        fontName="Helvetica-Bold",
        spaceBefore=10,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        name="Cuerpo",
        fontSize=9,
        textColor=colors.black,
        fontName="Helvetica",
        alignment=TA_JUSTIFY,
        leading=14,
    ))
    styles.add(ParagraphStyle(
        name="Firma",
        fontSize=9,
        textColor=COLOR_GRIS,
        fontName="Helvetica",
        alignment=TA_CENTER,
    ))
    return styles


def _header(styles, numero_contrato: str, tipo: str) -> list:
    tipo_label = "MÓDULO NCE" if tipo == "modulos" else "PISCINA DE FIBRA DE VIDRIO"
    elementos = [
        Paragraph("ECO MÓDULOS & PISCINAS", styles["Titulo"]),
        Paragraph("Cooperativa de Trabajo — Zárate, Buenos Aires", styles["Subtitulo"]),
        HRFlowable(width="100%", thickness=2, color=COLOR_VERDE),
        Spacer(1, 8),
        Paragraph(
            f"CONTRATO DE FINANCIACIÓN — {tipo_label}",
            styles["Titulo"],
        ),
        Paragraph(f"N° {numero_contrato}", styles["Subtitulo"]),
        Spacer(1, 12),
    ]
    return elementos


def _tabla_datos(titulo: str, filas: list, styles) -> list:
    """Genera una tabla de datos con estilo corporativo."""
    data = [[f[0], f[1]] for f in filas]
    tabla = Table(data, colWidths=[5 * cm, 12 * cm])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), COLOR_VERDE_CLARO),
        ("TEXTCOLOR", (0, 0), (0, -1), COLOR_VERDE),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [Paragraph(titulo, styles["Seccion"]), tabla, Spacer(1, 8)]


def _clausulas(tipo: str, styles) -> list:
    producto = "módulo NCE" if tipo == "modulos" else "piscina de fibra de vidrio"
    texto = f"""
    <b>CLÁUSULAS Y CONDICIONES:</b><br/><br/>
    1. La cooperativa ECO MÓDULOS & PISCINAS se compromete a entregar el {producto}
    especificado en las condiciones acordadas y en el plazo estimado indicado en este contrato.<br/><br/>
    2. El adquirente abonará el ingreso inicial al momento de la firma del presente contrato,
    y las cuotas mensuales en las fechas pactadas, sin necesidad de recibo previo.<br/><br/>
    3. El incumplimiento de más de 2 (dos) cuotas consecutivas habilitará a la cooperativa
    a iniciar el proceso de recupero del bien, previo aviso fehaciente al adquirente.<br/><br/>
    4. El {producto} será instalado en el domicilio indicado por el adquirente.
    El pago se realiza en el domicilio, obra terminada y funcionando.<br/><br/>
    5. La cooperativa otorga garantía sobre defectos de fabricación según las condiciones
    vigentes al momento de la entrega.<br/><br/>
    6. El presente contrato se regirá por las leyes de la República Argentina y
    la normativa aplicable a cooperativas de trabajo.<br/>
    """
    return [
        Paragraph(texto, styles["Cuerpo"]),
        Spacer(1, 16),
    ]


def _firmas(styles) -> list:
    fecha = date.today().strftime("%d/%m/%Y")
    data = [
        ["", ""],
        ["________________________", "________________________"],
        ["Firma del Adquirente", "Firma Cooperativa / Sello"],
        [f"Aclaración:", "Eco Módulos & Piscinas"],
        [f"DNI:", f"Zárate, {fecha}"],
    ]
    tabla = Table(data, colWidths=[8.5 * cm, 8.5 * cm])
    tabla.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TEXTCOLOR", (0, 1), (-1, 1), COLOR_GRIS),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [
        HRFlowable(width="100%", thickness=1, color=colors.lightgrey),
        Spacer(1, 20),
        Paragraph("FIRMAS", styles["Seccion"]),
        tabla,
    ]


async def generar_contrato(tipo: str, datos: dict) -> bytes:
    """
    Genera un contrato PDF y retorna los bytes.

    Args:
        tipo: "modulos" o "piscinas"
        datos: dict con los campos del contrato

    Returns:
        bytes del PDF generado
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Contrato Eco Módulos & Piscinas",
    )
    styles = _build_styles()
    numero = _numero_contrato(tipo)
    elementos = []

    # Header
    elementos.extend(_header(styles, numero, tipo))

    # Datos del cliente
    elementos.extend(_tabla_datos(
        "DATOS DEL ADQUIRENTE",
        [
            ("Nombre y Apellido:", datos.get("nombre_cliente", "")),
            ("DNI:", datos.get("dni", "")),
            ("Domicilio:", datos.get("domicilio", "")),
            ("Teléfono / WhatsApp:", datos.get("telefono", "")),
        ],
        styles,
    ))

    # Datos del producto
    if tipo == "modulos":
        filas_producto = [
            ("Producto:", "Módulo NCE"),
            ("Superficie:", datos.get("producto", "")),
            ("Descripción:", "Entrega Obra Blanca — interior blanqueado, instalaciones listas"),
        ]
    else:
        filas_producto = [
            ("Producto:", "Piscina de Fibra de Vidrio"),
            ("Modelo:", datos.get("producto", "")),
            ("Medidas:", datos.get("medida", "")),
            ("Kit incluye:", "Bomba, filtro, cañerías, skimmer, hidrojets, luces LED"),
        ]

    elementos.extend(_tabla_datos("PRODUCTO ADQUIRIDO", filas_producto, styles))

    # Condiciones económicas
    elementos.extend(_tabla_datos(
        "CONDICIONES ECONÓMICAS",
        [
            ("Precio Total:", f"${float(datos.get('precio_total', 0)):,.0f}"),
            ("Ingreso Inicial:", f"${float(datos.get('ingreso_inicial', 0)):,.0f}"),
            ("Plan de cuotas:", f"{datos.get('plan', '')} cuotas mensuales"),
            ("Monto por cuota:", f"${float(datos.get('monto_cuota', 0)):,.0f}/mes"),
            ("Fecha 1° cuota:", datos.get("fecha_primer_cuota", "")),
            ("Entrega estimada:", datos.get("fecha_entrega_estimada", "")),
            ("Vendedor asignado:", datos.get("vendedor_asignado", "")),
            ("N° de Contrato:", numero),
        ],
        styles,
    ))

    # Cláusulas
    elementos.extend(_clausulas(tipo, styles))

    # Firmas
    elementos.extend(_firmas(styles))

    try:
        doc.build(elementos)
        buffer.seek(0)
        return buffer.read()
    except Exception as e:
        logger.error(f"[contract_gen] Error generando PDF: {e}")
        raise
