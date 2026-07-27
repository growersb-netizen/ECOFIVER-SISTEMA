"""
Motor de generación de contratos y recibos — EcoFiver CRM.

Renderiza los templates HTML reales (templates/documentos/*.html, placeholders
{{campo}}) con Jinja2 y los convierte a PDF con Playwright (Chromium headless),
igual al flujo manual que se usaba antes fuera del CRM.
"""
import logging
import tempfile
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

log = logging.getLogger(__name__)

TEMPLATES_DOCUMENTOS = Path("templates/documentos")

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DOCUMENTOS)),
    autoescape=select_autoescape(["html"]),
)

# Campos que ya vienen armados como HTML (no se deben escapar)
_CAMPOS_HTML_CRUDO = {
    "firma_productor_block", "op_data_blocks", "tabla_filas", "nota_final",
}


def _preparar_contexto(context: dict) -> dict:
    """Marca como Markup (seguro/sin escapar) los campos de HTML crudo, y
    convierte todo lo demás a string vacío si viene None (nunca 'None' en el doc)."""
    out = {}
    for k, v in context.items():
        if v is None:
            v = ""
        if k in _CAMPOS_HTML_CRUDO:
            out[k] = Markup(v) if v else Markup("")
        else:
            out[k] = v
    return out


def render_html(template_name: str, context: dict) -> str:
    """Renderiza un template de documentos/ con el contexto dado."""
    template = _env.get_template(template_name)
    return template.render(**_preparar_contexto(context))


async def html_to_pdf(html: str, out_path: Path) -> Path:
    """
    Convierte HTML a PDF con Playwright, siguiendo las reglas aprendidas del
    flujo manual: viewport fijo en 794px antes del PDF, print_background=True,
    y alto calculado dinámicamente con scrollHeight (cada documento tiene
    largo distinto según cuántos campos opcionales tenga).
    """
    from playwright.async_api import async_playwright

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp_html_path = f.name

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(device_scale_factor=2, viewport={"width": 794, "height": 800})
            await page.goto(f"file:///{tmp_html_path}")
            await page.wait_for_timeout(300)
            height = await page.evaluate("document.body.scrollHeight")
            await page.set_viewport_size({"width": 794, "height": height})
            await page.pdf(
                path=str(out_path),
                print_background=True,
                width="794px",
                height=f"{height}px",
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
            await browser.close()
    finally:
        Path(tmp_html_path).unlink(missing_ok=True)

    return out_path


def monto_en_letras(monto: float) -> str:
    """Convierte un monto a texto en pesos argentinos (ej: 'Ciento cincuenta mil pesos')."""
    try:
        from num2words import num2words
        entero = int(round(monto))
        texto = num2words(entero, lang="es")
        return f"{texto.capitalize()} pesos"
    except Exception as e:
        log.warning(f"[documentos] monto_en_letras falló: {e}")
        return ""


def split_nombre_apellido(cliente_nombre: str) -> tuple[str, str]:
    """
    Convención usada en el CRM: cliente_nombre = "Apellido, Nombre".
    Si no hay coma, hace un split best-effort por el último espacio.
    """
    cliente_nombre = (cliente_nombre or "").strip()
    if not cliente_nombre:
        return "", ""
    if "," in cliente_nombre:
        apellido, nombre = cliente_nombre.split(",", 1)
        return nombre.strip(), apellido.strip()
    partes = cliente_nombre.rsplit(" ", 1)
    if len(partes) == 2:
        return partes[0].strip(), partes[1].strip()
    return cliente_nombre, ""
