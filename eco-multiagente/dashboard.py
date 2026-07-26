"""
Dashboard de Control — EcoFiver IA
Ruta base: /dashboard
Contraseña: ADMIN_PASSWORD del .env (default: ecomodulos2026)
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv, dotenv_values, set_key

logger = logging.getLogger(__name__)
router = APIRouter()

# Ruta del .env: usa DATA_DIR si está definida (Fly.io volume), si no usa el directorio de la app
_env_base     = Path(os.getenv("DATA_DIR", "")) if os.getenv("DATA_DIR") else Path(__file__).parent
ENV_PATH      = _env_base / ".env"

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ecomodulos2026")

# ── Helpers ────────────────────────────────────────────────────────────────

def read_env() -> dict:
    if ENV_PATH.exists():
        return dict(dotenv_values(ENV_PATH))
    return {}

def save_env(values: dict):
    """Guarda variables en el .env. Crea el directorio si no existe."""
    try:
        ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"[dashboard] No se pudo crear directorio {ENV_PATH.parent}: {e}")
    if not ENV_PATH.exists():
        ENV_PATH.write_text("")
    for k, v in values.items():
        if v is not None:
            set_key(str(ENV_PATH), k, v)
    load_dotenv(str(ENV_PATH), override=True)

# ── Definición completa de los 15 agentes ─────────────────────────────────

AGENTS_META = [
    {
        "id": "maximo",
        "nombre": "Máximo",
        "rol": "CEO / Director Operativo",
        "modelo": "gemini-2.5-pro",
        "reporta_a": None,
        "supervisa": ["aurora", "renata", "bruno", "ezequiel", "daniela", "sebastian"],
        "canal": "interno",
        "descripcion": "Agente de mayor jerarquía. Toma decisiones autónomas, reporta a Rodrigo a las 08:00 AM por Telegram.",
        "funciones": [
            "Reporte diario 08:00 AM a Rodrigo vía Telegram",
            "Activar/pausar campañas Meta Ads",
            "Reasignar leads entre vendedores IA",
            "Activar protocolo urgencia cupos fabricación",
            "Autorizar refinanciación hasta 2 cuotas vencidas",
            "Activar Daniela ante reclamos",
            "Ordenar contenido a Renata",
            "Coordinar instalaciones con Bruno",
            "Emitir contratos y recibos automáticamente",
        ],
        "escala_a": "Rodrigo (dueño)",
        "color": "#1A5C38",
        "emoji": "👑",
    },
    {
        "id": "aurora",
        "nombre": "Aurora",
        "rol": "Gerente Comercial",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "maximo",
        "supervisa": ["tomas"],
        "canal": "interno",
        "descripcion": "Supervisa todo el rendimiento comercial. Revisa pipeline 2x/día y detecta cuellos de botella.",
        "funciones": [
            "Revisión pipeline 08:30 y 18:00 hs",
            "Supervisar agenda videollamadas (máx 2/franja, Lun-Vie 11:30-18:00)",
            "Actualizar scripts ante objeciones recurrentes",
            "Reasignar leads entre vendedores IA",
            "Control tasa conversión (mínimo 15% contado, 10% financiado)",
            "Reporte matutino y vespertino a Máximo",
        ],
        "escala_a": "Máximo",
        "color": "#2E7D32",
        "emoji": "📊",
    },
    {
        "id": "tomas",
        "nombre": "Tomás",
        "rol": "Supervisor de Ventas",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "aurora",
        "supervisa": ["valentina", "camila", "mateo", "nicolas", "luciano"],
        "canal": "interno",
        "descripcion": "Ojos en tiempo real del equipo de ventas. Supervisa cada conversación activa y activa alertas.",
        "funciones": [
            "Alerta leads sin respuesta >2hs",
            "Alerta conversación estancada >4hs",
            "Alerta lead caliente sin cierre >24hs",
            "Corrección vendedor IA fuera de script",
            "Análisis 3 leads caídos seguidos",
            "Reconfirmar videollamadas 2hs antes",
            "Clasificación leads: Caliente / Tibio / Frío",
            "Manejo de objeciones: Lo pienso / Está caro / No tengo banco / Lo hablo con mi pareja",
        ],
        "escala_a": "Aurora",
        "color": "#388E3C",
        "emoji": "👁️",
    },
    {
        "id": "valentina",
        "nombre": "Valentina",
        "rol": "Asesora Comercial General",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "tomas",
        "supervisa": [],
        "canal": "whatsapp + web",
        "descripcion": "Primer contacto con el cliente. Califica y deriva al especialista correcto.",
        "funciones": [
            "Atender WhatsApp, Instagram y chat web",
            "Detectar necesidad: piscina vs módulo",
            "Detectar forma de pago: contado vs financiado",
            "Derivar a especialista correcto",
            "Frase antifraude en contado",
            "Dar link WA si prefiere salir del chat web",
        ],
        "escala_a": "Tomás",
        "color": "#43A047",
        "emoji": "💬",
    },
    {
        "id": "camila",
        "nombre": "Camila",
        "rol": "Especialista Piscinas Contado",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "tomas",
        "supervisa": [],
        "canal": "whatsapp",
        "descripcion": "Cierra ventas de piscinas al contado y coordina instalación.",
        "funciones": [
            "Catálogo 16 modelos con precios contado",
            "Calcular flete por localidad ($3.000/km, Miniportante $2.000/km)",
            "Informar kit completo incluido",
            "Urgencia: cupos de quincena de fabricación",
            "Coordinar fecha de instalación",
            "Frase antifraude: pago en domicilio, obra terminada",
        ],
        "escala_a": "Tomás",
        "color": "#00897B",
        "emoji": "🏊",
    },
    {
        "id": "mateo",
        "nombre": "Mateo",
        "rol": "Especialista Módulos Financiados",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "tomas",
        "supervisa": [],
        "canal": "whatsapp",
        "descripcion": "Califica y lleva a videollamada de admisión para módulo financiado.",
        "funciones": [
            "Módulos 6m² a 72m²",
            "Planes 12/18/24/36/120 cuotas sin banco",
            "Calificación suave: terreno, plazos, cuota cómoda",
            "Argumentos por perfil: glamping, home office, pareja joven",
            "Cierre hacia videollamada de admisión",
            "Beneficio NCE: bien mueble, ahorro 60% energía",
        ],
        "escala_a": "Tomás",
        "color": "#0288D1",
        "emoji": "🏠",
    },
    {
        "id": "nicolas",
        "nombre": "Nicolás",
        "rol": "Especialista Piscinas Financiadas",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "tomas",
        "supervisa": [],
        "canal": "whatsapp",
        "descripcion": "Califica y lleva a videollamada para piscina financiada.",
        "funciones": [
            "Catálogo 16 modelos con planes de cuotas",
            "Simulación de cuotas en tiempo real",
            "Urgencia: cupos de fabricación por quincena",
            "Financiación directa sin banco ni scoring",
            "Cierre hacia videollamada de admisión",
        ],
        "escala_a": "Tomás",
        "color": "#0277BD",
        "emoji": "💧",
    },
    {
        "id": "luciano",
        "nombre": "Luciano",
        "rol": "Especialista Módulos Contado + Combos",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "tomas",
        "supervisa": [],
        "canal": "whatsapp",
        "descripcion": "Cierra módulos al contado y gestiona combos módulo+piscina.",
        "funciones": [
            "Módulos contado 6m² a 72m²",
            "Combos módulo+piscina (25% descuento, solo financiado)",
            "Argumento material NCE (resina náutica, bien mueble)",
            "Flete desde Zárate por localidad",
            "Framing supervisora para aumentar autoridad",
            "Deriva combos a Mateo para financiación",
        ],
        "escala_a": "Tomás",
        "color": "#5C6BC0",
        "emoji": "🏡",
    },
    {
        "id": "renata",
        "nombre": "Renata",
        "rol": "Marketing, Contenido y Web",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "maximo",
        "supervisa": [],
        "canal": "interno + cloudflare",
        "descripcion": "Produce contenido visual (Ecopost), gestiona Meta Ads y mantiene la landing page.",
        "funciones": [
            "Generar flyers 1080x1080 y stories 9:16 con Gemini Imagen 3",
            "Subir contenido a Google Drive (organizado por carpetas)",
            "Gestionar 4 campañas Meta Ads activas",
            "Pausar/escalar campañas según performance",
            "Actualizar precios en la landing page",
            "Monitorear chat Valentina en web",
            "Reporte semanal: alcance, CTR, leads por campaña",
            "Procesar fotos enviadas por Rodrigo como base de flyers",
        ],
        "escala_a": "Máximo",
        "color": "#E91E63",
        "emoji": "🎨",
    },
    {
        "id": "bruno",
        "nombre": "Bruno",
        "rol": "Operaciones y Logística",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "maximo",
        "supervisa": [],
        "canal": "interno",
        "descripcion": "Gestiona fletes, stock, cupos de fabricación y agenda de instalaciones.",
        "funciones": [
            "Calcular fletes ($3.000/km general, $2.000/km Miniportante)",
            "Verificar stock antes de confirmar entregas",
            "Coordinar agenda de instalaciones",
            "Gestionar cupos de fabricación por quincena",
            "Alertar a Máximo cuando stock está bajo",
            "Confirmar fechas en financiados",
        ],
        "escala_a": "Máximo",
        "color": "#FF6F00",
        "emoji": "🚛",
    },
    {
        "id": "ezequiel",
        "nombre": "Ezequiel",
        "rol": "Administrador General",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "maximo",
        "supervisa": ["ignacio", "elena"],
        "canal": "interno",
        "descripcion": "Control de cartera, generación de contratos PDF y supervisión de cobros.",
        "funciones": [
            "Control cartera activa: cuotas y vencimientos",
            "Generar contratos PDF (módulos y piscinas financiadas)",
            "Emitir recibos de pago en PDF",
            "Supervisar cobros de Ignacio",
            "Supervisar reportes de Elena",
            "Alertar cuando morosidad supera 15% de cartera",
            "Reporte semanal a Máximo",
        ],
        "escala_a": "Máximo",
        "color": "#795548",
        "emoji": "📋",
    },
    {
        "id": "ignacio",
        "nombre": "Ignacio",
        "rol": "Cobrador",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "ezequiel",
        "supervisa": [],
        "canal": "whatsapp",
        "descripcion": "Recupera cuotas vencidas manteniendo la relación con el cliente.",
        "funciones": [
            "Día 1-3: recordatorio cordial automático",
            "Día 4-7: consulta de situación",
            "Día 8-15: propuesta refinanciación (con autorización Máximo)",
            "Día 16+: escalar a Ezequiel y Máximo",
            "Reporte diario a Ezequiel",
        ],
        "escala_a": "Ezequiel",
        "color": "#E53935",
        "emoji": "💳",
    },
    {
        "id": "elena",
        "nombre": "Elena",
        "rol": "Finanzas y CRM",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "ezequiel",
        "supervisa": [],
        "canal": "interno",
        "descripcion": "Simula cuotas, sincroniza con CRM y genera reportes financieros.",
        "funciones": [
            "Simulación de cuotas en tiempo real (todos los planes)",
            "Sincronización leads y ventas con CRM",
            "Reportes de pipeline",
            "Proyección de ingresos mensuales",
            "Actualización de precios (con autorización Rodrigo)",
            "Reporte semanal a Ezequiel",
        ],
        "escala_a": "Ezequiel",
        "color": "#1565C0",
        "emoji": "💰",
    },
    {
        "id": "daniela",
        "nombre": "Daniela",
        "rol": "RRPP y Gestión de Crisis",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "maximo",
        "supervisa": [],
        "canal": "whatsapp",
        "descripcion": "Atiende reclamos en menos de 30 minutos. Nunca admite culpa institucional.",
        "funciones": [
            "Respuesta en <30 min ante activación de Máximo",
            "Escucha empática sin validar el reclamo como error",
            "Contextualizar con factores externos reales",
            "Ofrecer acción concreta siempre",
            "Convertir queja en fidelización",
            "Escalar a Máximo: abogado, INAES, redes, potencial mediático",
        ],
        "escala_a": "Máximo",
        "color": "#6A1B9A",
        "emoji": "🤝",
    },
    {
        "id": "sebastian",
        "nombre": "Sebastián",
        "rol": "Postventa y Soporte Técnico",
        "modelo": "gemini-2.0-flash",
        "reporta_a": "maximo",
        "supervisa": [],
        "canal": "whatsapp",
        "descripcion": "Atiende consultas post-instalación, guía mantenimiento y gestiona garantías.",
        "funciones": [
            "Guía mantenimiento piscinas: pH 7.2-7.6, cloro, filtro, skimmer",
            "Guía mantenimiento módulos: pintura, juntas, sellados",
            "Gestión de garantías: registrar, evaluar, coordinar visita",
            "Detectar problemas recurrentes para mejora de producto",
            "Reporte a Máximo sobre fallas repetidas",
        ],
        "escala_a": "Máximo",
        "color": "#00695C",
        "emoji": "🔧",
    },
]

AGENTS_BY_ID = {a["id"]: a for a in AGENTS_META}

# ── HTML del dashboard ─────────────────────────────────────────────────────

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Dashboard — EcoFiver IA</title>
  <style>
    :root {
      --verde: #1A5C38; --verde2: #2E7D32; --verde-claro: #e8f5e9;
      --bg: #f0f4f0; --sidebar-w: 240px; --header-h: 56px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: var(--bg); color: #222; }

    /* ── Sidebar ── */
    #sidebar {
      position: fixed; top: 0; left: 0; width: var(--sidebar-w);
      height: 100vh; background: #0f3d24; display: flex;
      flex-direction: column; z-index: 100; overflow-y: auto;
    }
    .sidebar-logo {
      padding: 18px 20px; border-bottom: 1px solid rgba(255,255,255,.1);
    }
    .sidebar-logo h1 { color: #fff; font-size: 14px; font-weight: 700; line-height: 1.3; }
    .sidebar-logo p  { color: rgba(255,255,255,.5); font-size: 11px; margin-top: 2px; }
    .nav-section { padding: 12px 0 4px; }
    .nav-label {
      padding: 4px 16px; font-size: 10px; font-weight: 700;
      color: rgba(255,255,255,.35); text-transform: uppercase; letter-spacing: .8px;
    }
    .nav-item {
      display: flex; align-items: center; gap: 10px;
      padding: 9px 16px; color: rgba(255,255,255,.7); font-size: 13px;
      cursor: pointer; transition: all .15s; border-left: 3px solid transparent;
      text-decoration: none;
    }
    .nav-item:hover { background: rgba(255,255,255,.07); color: #fff; }
    .nav-item.active {
      background: rgba(255,255,255,.12); color: #fff;
      border-left-color: #4CAF50;
    }
    .nav-item .icon { font-size: 16px; width: 20px; text-align: center; }
    .nav-badge {
      margin-left: auto; background: #4CAF50; color: #fff;
      border-radius: 10px; padding: 1px 7px; font-size: 10px; font-weight: 700;
    }

    /* ── Header ── */
    #header {
      position: fixed; top: 0; left: var(--sidebar-w); right: 0;
      height: var(--header-h); background: #fff;
      border-bottom: 1px solid #e0e0e0; display: flex; align-items: center;
      padding: 0 24px; gap: 12px; z-index: 99;
    }
    #header h2 { font-size: 16px; font-weight: 700; color: #222; flex: 1; }
    .header-badge {
      background: var(--verde-claro); color: var(--verde);
      border-radius: 20px; padding: 4px 12px; font-size: 12px; font-weight: 600;
    }
    #clock { font-size: 12px; color: #888; }

    /* ── Main ── */
    #main {
      margin-left: var(--sidebar-w); margin-top: var(--header-h);
      padding: 24px; min-height: calc(100vh - var(--header-h));
    }

    /* ── Cards grid ── */
    .grid-4 { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-bottom: 24px; }
    .grid-3 { display: grid; grid-template-columns: repeat(3,1fr); gap: 16px; }
    .grid-2 { display: grid; grid-template-columns: repeat(2,1fr); gap: 16px; }
    .card {
      background: #fff; border-radius: 12px;
      box-shadow: 0 1px 6px rgba(0,0,0,.07); overflow: hidden;
    }
    .card-header {
      padding: 14px 18px; border-bottom: 1px solid #f0f0f0;
      display: flex; align-items: center; gap: 10px;
    }
    .card-header h3 { font-size: 14px; font-weight: 700; color: #333; }
    .card-body { padding: 18px; }

    /* ── Stat cards ── */
    .stat-card {
      background: #fff; border-radius: 12px; padding: 18px 20px;
      box-shadow: 0 1px 6px rgba(0,0,0,.07);
      border-left: 4px solid var(--verde);
    }
    .stat-card .stat-label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: .5px; }
    .stat-card .stat-value { font-size: 28px; font-weight: 800; color: #222; margin: 4px 0; }
    .stat-card .stat-sub   { font-size: 12px; color: #666; }

    /* ── Agent cards ── */
    .agent-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
    .agent-card {
      background: #fff; border-radius: 12px;
      box-shadow: 0 1px 6px rgba(0,0,0,.07);
      overflow: hidden; cursor: pointer; transition: transform .15s, box-shadow .15s;
    }
    .agent-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,.12); }
    .agent-card-top {
      padding: 16px 18px 12px; display: flex; align-items: flex-start; gap: 12px;
    }
    .agent-emoji { font-size: 28px; flex-shrink: 0; }
    .agent-name  { font-size: 15px; font-weight: 700; }
    .agent-rol   { font-size: 11px; color: #888; margin-top: 1px; }
    .agent-model { font-size: 10px; border-radius: 4px; padding: 2px 7px; margin-top: 6px;
                   display: inline-block; font-weight: 600; }
    .model-pro   { background: #fff3e0; color: #e65100; }
    .model-flash { background: #e3f2fd; color: #1565c0; }
    .agent-card-mid {
      padding: 0 18px 10px; font-size: 12px; color: #555; line-height: 1.5;
    }
    .agent-card-bot {
      padding: 10px 18px 14px; border-top: 1px solid #f5f5f5;
      display: flex; gap: 8px; flex-wrap: wrap;
    }
    .chip {
      background: #f0f4f0; color: var(--verde); border-radius: 20px;
      padding: 3px 10px; font-size: 11px; font-weight: 600;
    }
    .chip.canal { background: #e8f5e9; }

    /* ── Agent detail modal ── */
    #modal-overlay {
      position: fixed; inset: 0; background: rgba(0,0,0,.5);
      z-index: 200; display: none; align-items: center; justify-content: center;
    }
    #modal-overlay.open { display: flex; }
    #modal {
      background: #fff; border-radius: 16px; width: 720px; max-width: 95vw;
      max-height: 90vh; overflow-y: auto; padding: 0;
    }
    .modal-header {
      padding: 20px 24px; border-bottom: 1px solid #eee;
      display: flex; align-items: center; gap: 12px; position: sticky;
      top: 0; background: #fff; z-index: 1;
    }
    .modal-header h2 { font-size: 18px; font-weight: 700; flex: 1; }
    .modal-close {
      background: none; border: none; font-size: 22px; cursor: pointer; color: #888;
    }
    .modal-body { padding: 24px; }
    .modal-section { margin-bottom: 24px; }
    .modal-section h4 {
      font-size: 11px; font-weight: 700; color: #888; text-transform: uppercase;
      letter-spacing: .6px; margin-bottom: 10px;
    }
    .func-list { list-style: none; }
    .func-list li {
      padding: 6px 0; border-bottom: 1px solid #f5f5f5; font-size: 13px;
      display: flex; align-items: flex-start; gap: 8px;
    }
    .func-list li::before { content: "▸"; color: var(--verde); flex-shrink: 0; margin-top: 1px; }
    .hierarchy-pill {
      display: inline-flex; align-items: center; gap: 6px; background: var(--verde-claro);
      color: var(--verde); border-radius: 20px; padding: 5px 12px; font-size: 12px; font-weight: 600;
    }
    .prompt-box {
      background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 8px;
      padding: 12px; font-size: 12px; font-family: monospace; line-height: 1.6;
      max-height: 300px; overflow-y: auto; white-space: pre-wrap; word-break: break-word;
    }
    .btn { padding: 9px 18px; border-radius: 8px; font-size: 13px; font-weight: 600;
           cursor: pointer; border: none; transition: all .15s; }
    .btn-primary { background: var(--verde); color: #fff; }
    .btn-primary:hover { background: #145030; }
    .btn-outline { background: #fff; color: var(--verde); border: 1.5px solid var(--verde); }
    .btn-outline:hover { background: var(--verde-claro); }
    .btn-danger { background: #fff; color: #e53935; border: 1.5px solid #e53935; }
    .btn-danger:hover { background: #ffebee; }

    /* ── Config forms ── */
    .config-section { margin-bottom: 28px; }
    .config-title {
      font-size: 13px; font-weight: 700; color: var(--verde);
      border-bottom: 2px solid var(--verde-claro); padding-bottom: 8px; margin-bottom: 14px;
    }
    .field { margin-bottom: 14px; }
    .field label {
      display: block; font-size: 11px; font-weight: 700; color: #666;
      text-transform: uppercase; letter-spacing: .5px; margin-bottom: 5px;
    }
    .field input, .field textarea, .field select {
      width: 100%; border: 1.5px solid #dde; border-radius: 8px;
      padding: 9px 12px; font-size: 13px; outline: none; transition: border .2s;
      background: #fafafa; font-family: inherit;
    }
    .field input:focus, .field textarea:focus, .field select:focus {
      border-color: var(--verde); background: #fff;
    }
    .field textarea { resize: vertical; font-family: monospace; font-size: 12px; }
    .field .hint { font-size: 11px; color: #999; margin-top: 4px; }
    .field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .status-ok   { color: #2e7d32; font-weight: 600; font-size: 12px; }
    .status-err  { color: #c62828; font-weight: 600; font-size: 12px; }
    .test-result {
      margin-top: 8px; padding: 8px 12px; border-radius: 6px; font-size: 12px; display: none;
    }
    .test-result.ok  { background: #e8f5e9; color: #2e7d32; }
    .test-result.err { background: #ffebee; color: #c62828; }

    /* ── Scheduler ── */
    .sched-row {
      display: flex; align-items: center; gap: 12px; padding: 12px 0;
      border-bottom: 1px solid #f0f0f0; font-size: 13px;
    }
    .sched-time { font-weight: 700; color: var(--verde); min-width: 140px; font-size: 12px; font-family: monospace; }
    .sched-name { flex: 1; }
    .sched-badge {
      background: #e8f5e9; color: #2e7d32; border-radius: 20px;
      padding: 2px 10px; font-size: 11px; font-weight: 600;
    }

    /* ── Catálogo ── */
    .tabla { width: 100%; border-collapse: collapse; font-size: 13px; }
    .tabla th {
      background: #f5f5f5; padding: 10px 12px; text-align: left;
      font-size: 11px; font-weight: 700; text-transform: uppercase; color: #666;
      border-bottom: 1px solid #e0e0e0;
    }
    .tabla td { padding: 10px 12px; border-bottom: 1px solid #f5f5f5; }
    .tabla tr:last-child td { border-bottom: none; }
    .tabla input {
      border: 1px solid #dde; border-radius: 6px; padding: 5px 8px;
      font-size: 13px; width: 100%; background: #fafafa;
    }
    .tabla input:focus { outline: none; border-color: var(--verde); background: #fff; }

    /* ── Toast ── */
    #toast {
      position: fixed; bottom: 24px; right: 24px; background: #333; color: #fff;
      padding: 12px 20px; border-radius: 8px; font-size: 13px; font-weight: 600;
      z-index: 999; opacity: 0; transition: opacity .3s; pointer-events: none;
    }
    #toast.show { opacity: 1; }

    /* ── Command cards ── */
    .cmd-card { background:#f8faf8; border:1px solid #e8f0e8; border-radius:12px; padding:16px; }
    .cmd-title { font-size:14px; font-weight:700; color:#222; margin-bottom:6px; }
    .cmd-desc  { font-size:12px; color:#777; line-height:1.5; margin-bottom:12px; min-height:48px; }
    .cmd-result { margin-top:10px; font-size:12px; line-height:1.5; display:none;
                  border-radius:8px; padding:8px 12px; white-space:pre-wrap; }
    .cmd-result.ok  { background:#e8f5e9; color:#2e7d32; display:block; }
    .cmd-result.err { background:#ffebee; color:#c62828; display:block; }
    .cmd-result.run { background:#fff8e1; color:#f57f17; display:block; }
    /* ── Canal status ── */
    .canal-item { display:flex; align-items:center; gap:10px; background:#f8faf8;
                  border:1px solid #eee; border-radius:10px; padding:12px 14px; }
    .canal-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
    .canal-on  { background:#43a047; box-shadow:0 0 6px #43a047; }
    .canal-off { background:#bbb; }
    .canal-name { font-size:13px; font-weight:700; color:#333; }
    .canal-state { font-size:11px; margin-top:1px; }

    /* ── Bars ── */
    .bar-row { display:flex; align-items:center; gap:10px; padding:6px 0; font-size:13px; }
    .bar-label { min-width:130px; color:#555; text-transform:capitalize; }
    .bar-track { flex:1; background:#f0f0f0; border-radius:6px; height:18px; overflow:hidden; }
    .bar-fill { height:100%; background:var(--verde); border-radius:6px; transition:width .4s; }
    .bar-val { min-width:36px; text-align:right; font-weight:700; color:#333; }

    /* ── Misc ── */
    .page { display: none; }
    .page.active { display: block; }
    .sep { height: 1px; background: #f0f0f0; margin: 24px 0; }
    .tag-verde { background: var(--verde-claro); color: var(--verde); border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 700; }
    .empty { text-align: center; padding: 40px; color: #bbb; font-size: 14px; }

    @media(max-width:768px) {
      #sidebar { display: none; }
      #header, #main { left: 0; margin-left: 0; }
      .grid-4, .grid-3 { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>

<!-- ── SIDEBAR ─────────────────────────────────────── -->
<nav id="sidebar">
  <div class="sidebar-logo">
    <h1>🌿 EcoFiver IA</h1>
    <p>Panel de control</p>
  </div>

  <div class="nav-section">
    <div class="nav-label">General</div>
    <a class="nav-item active" data-page="overview" href="#">
      <span class="icon">📊</span> Resumen
    </a>
    <a class="nav-item" data-page="comando" href="#">
      <span class="icon">🎛️</span> Centro de Comando
    </a>
    <a class="nav-item" data-page="ecopost" href="#">
      <span class="icon">🎨</span> Ecopost — Contenido
    </a>
    <a class="nav-item" data-page="galeria" href="#">
      <span class="icon">🖼️</span> Galería de Activos
    </a>
    <a class="nav-item" data-page="mercadolibre" href="#">
      <span class="icon">🛒</span> MercadoLibre
    </a>
    <a class="nav-item" data-page="conocimiento" href="#">
      <span class="icon">🧠</span> Base de Conocimiento
    </a>
    <a class="nav-item" href="/panel">
      <span class="icon">💬</span> Comandar Agentes
    </a>
    <a class="nav-item" data-page="agents" href="#">
      <span class="icon">🤖</span> Agentes
      <span class="nav-badge">15</span>
    </a>
    <a class="nav-item" data-page="hierarchy" href="#">
      <span class="icon">🗂️</span> Jerarquía
    </a>
  </div>

  <div class="nav-section">
    <div class="nav-label">Sistema</div>
    <a class="nav-item" data-page="config" href="#">
      <span class="icon">⚙️</span> Configuración
    </a>
    <a class="nav-item" data-page="scheduler" href="#">
      <span class="icon">⏰</span> Scheduler
    </a>
    <a class="nav-item" data-page="catalogo" href="#">
      <span class="icon">🏊</span> Catálogo
    </a>
  </div>

  <div class="nav-section">
    <div class="nav-label">Herramientas</div>
    <a class="nav-item" data-page="cuotas" href="#">
      <span class="icon">💰</span> Simulador Cuotas
    </a>
    <a class="nav-item" data-page="flete" href="#">
      <span class="icon">🚛</span> Calculador Flete
    </a>
    <a class="nav-item" data-page="webhook" href="#">
      <span class="icon">💬</span> WhatsApp / Webhook
    </a>
  </div>

  <div style="margin-top:auto;padding:16px;border-top:1px solid rgba(255,255,255,.1)">
    <a href="/" style="color:rgba(255,255,255,.5);font-size:12px;text-decoration:none">← Volver al inicio</a>
  </div>
</nav>

<!-- ── HEADER ──────────────────────────────────────── -->
<header id="header">
  <h2 id="page-title">Resumen del sistema</h2>
  <span class="header-badge">✅ Sistema operativo</span>
  <span id="clock"></span>
</header>

<!-- ── MAIN CONTENT ────────────────────────────────── -->
<main id="main">

  <!-- OVERVIEW -->
  <div id="page-overview" class="page active">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
      <span style="font-size:12px;color:#888">Números reales del negocio (CRM en vivo)</span>
      <span id="kpi-ts" style="font-size:11px;color:#aaa;font-family:monospace"></span>
      <button class="btn btn-outline" style="margin-left:auto;font-size:12px;padding:6px 14px" onclick="loadKpis()">🔄 Actualizar</button>
    </div>

    <!-- Fila: HOY -->
    <div class="grid-4" style="margin-bottom:16px">
      <div class="stat-card">
        <div class="stat-label">Leads nuevos hoy</div>
        <div class="stat-value" id="kpi-leads-hoy">—</div>
        <div class="stat-sub">Captados en el día</div>
      </div>
      <div class="stat-card" style="border-left-color:#2e7d32">
        <div class="stat-label">Cierres hoy</div>
        <div class="stat-value" id="kpi-cierres-hoy">—</div>
        <div class="stat-sub">Ventas confirmadas</div>
      </div>
      <div class="stat-card" style="border-left-color:#1565C0">
        <div class="stat-label">Facturación hoy</div>
        <div class="stat-value" id="kpi-monto-hoy" style="font-size:22px">—</div>
        <div class="stat-sub">Monto cerrado</div>
      </div>
      <div class="stat-card" style="border-left-color:#C62828">
        <div class="stat-label">Leads sin responder</div>
        <div class="stat-value" id="kpi-sin-resp">—</div>
        <div class="stat-sub">Esperan +2hs</div>
      </div>
    </div>

    <!-- Fila: pipeline -->
    <div class="grid-4" style="margin-bottom:24px">
      <div class="stat-card" style="border-left-color:#E65100">
        <div class="stat-label">Total de leads</div>
        <div class="stat-value" id="kpi-total-leads">—</div>
        <div class="stat-sub">En el CRM</div>
      </div>
      <div class="stat-card" style="border-left-color:#D84315">
        <div class="stat-label">Leads calientes</div>
        <div class="stat-value" id="kpi-calientes">—</div>
        <div class="stat-sub">Calificados / agendados</div>
      </div>
      <div class="stat-card" style="border-left-color:#6A1B9A">
        <div class="stat-label">Videollamadas próximas</div>
        <div class="stat-value" id="kpi-videollamadas">—</div>
        <div class="stat-sub">Próximas 48hs</div>
      </div>
      <div class="stat-card" style="border-left-color:#b71c1c">
        <div class="stat-label">Cuotas vencidas</div>
        <div class="stat-value" id="kpi-cuotas-venc">—</div>
        <div class="stat-sub" id="kpi-monto-venc">Monto: —</div>
      </div>
    </div>

    <div class="card">
      <div class="card-header"><span>🔻</span><h3>Embudo comercial (CRM en vivo)</h3></div>
      <div class="card-body"><div id="funnel-estados"><div class="empty">Cargando…</div></div></div>
    </div>

    <div style="margin-top:24px" class="card">
      <div class="card-header"><span>📅</span><h3>Agenda — próximas videollamadas</h3></div>
      <div class="card-body"><div id="agenda-list"><div class="empty">Cargando…</div></div></div>
    </div>

    <div style="margin-top:24px" class="grid-2">
      <div class="card">
        <div class="card-header"><span>🤖</span><h3>Equipo IA por área</h3></div>
        <div class="card-body"><div id="team-summary"></div></div>
      </div>
      <div class="card">
        <div class="card-header"><span>⏰</span><h3>Tareas automáticas</h3></div>
        <div class="card-body">
          <div class="sched-row"><span class="sched-time">08:00</span><span>Reporte Máximo → Rodrigo (Telegram)</span></div>
          <div class="sched-row"><span class="sched-time">Cada 4hs</span><span>Scraping orgánico (MLA + OLX)</span></div>
          <div class="sched-row"><span class="sched-time">10 / 19</span><span>Renata — publicación FB + IG</span></div>
          <div class="sched-row"><span class="sched-time">Cada 2hs</span><span>Check leads sin respuesta → Tomás</span></div>
          <div class="sched-row" style="border:none"><span class="sched-time">20:00</span><span>Cobros Ignacio — cuotas vencidas</span></div>
        </div>
      </div>
    </div>
  </div>

  <!-- CENTRO DE COMANDO -->
  <div id="page-comando" class="page">
    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span>🛰️</span><h3>Máquina autónoma de leads — canales activos</h3></div>
      <div class="card-body">
        <div id="canales-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px">
          <div class="empty">Cargando estado…</div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span>⚡</span><h3>Acciones manuales del sistema</h3></div>
      <div class="card-body">
        <p style="font-size:13px;color:#666;margin-bottom:16px">
          El sistema ejecuta esto solo, automáticamente. Estos botones te dejan dispararlo ahora mismo sin esperar al horario programado.
        </p>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px">
          <div class="cmd-card">
            <div class="cmd-title">🔍 Buscar leads ahora</div>
            <div class="cmd-desc">Rastrea MercadoLibre, OLX y clasificados en busca de interesados reales.</div>
            <button class="btn btn-primary" onclick="ejecutarComando('scraping', this)">Ejecutar scraping</button>
            <div class="cmd-result" id="res-scraping"></div>
          </div>
          <div class="cmd-card">
            <div class="cmd-title">📣 Publicar contenido</div>
            <div class="cmd-desc">Renata genera y publica un post en Facebook e Instagram según la temporada.</div>
            <button class="btn btn-primary" onclick="ejecutarComando('contenido', this)">Publicar ahora</button>
            <div class="cmd-result" id="res-contenido"></div>
          </div>
          <div class="cmd-card">
            <div class="cmd-title">📧 Procesar emails</div>
            <div class="cmd-desc">Lee la casilla y responde consultas entrantes por email automáticamente.</div>
            <button class="btn btn-primary" onclick="ejecutarComando('emails', this)">Revisar casilla</button>
            <div class="cmd-result" id="res-emails"></div>
          </div>
          <div class="cmd-card">
            <div class="cmd-title">👋 Contactar leads nuevos</div>
            <div class="cmd-desc">Envía el primer mensaje a los leads que aún no fueron contactados.</div>
            <button class="btn btn-primary" onclick="ejecutarComando('leads_nuevos', this)">Contactar ahora</button>
            <div class="cmd-result" id="res-leads_nuevos"></div>
          </div>
          <div class="cmd-card">
            <div class="cmd-title">🔥 Reactivar leads fríos</div>
            <div class="cmd-desc">Reescribe y reenvía un mensaje cálido a leads que se enfriaron, para recuperarlos.</div>
            <button class="btn btn-primary" onclick="ejecutarComando('reactivar_frios', this)">Reactivar ahora</button>
            <div class="cmd-result" id="res-reactivar_frios"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span>🔥</span><h3>Leads que requieren acción</h3>
        <button class="btn btn-outline" style="margin-left:auto;font-size:12px" onclick="cargarLeadsAccion()">🔄 Actualizar</button>
      </div>
      <div class="card-body">
        <p style="font-size:13px;color:#666;margin-bottom:12px">
          Leads sin respuesta hace +2hs — son los que estás por perder. Contactalos cuanto antes.
        </p>
        <div id="leads-accion"><div class="empty">Cargando…</div></div>
      </div>
    </div>

    <div class="card">
      <div class="card-header"><span>💬</span><h3>Dar órdenes a los agentes</h3></div>
      <div class="card-body">
        <p style="font-size:13px;color:#666;margin-bottom:14px">
          Para conversar con cada agente, darle instrucciones, editar su comportamiento o ver su historial, entrá al panel operativo.
        </p>
        <a href="/panel" class="btn btn-primary" style="text-decoration:none">💬 Abrir panel de agentes →</a>
      </div>
    </div>
  </div>

  <!-- ECOPOST -->
  <div id="page-ecopost" class="page">
    <div class="grid-2" style="align-items:start">
      <!-- Paso 1: crear -->
      <div class="card">
        <div class="card-header"><span>✨</span><h3>1 · Crear contenido</h3></div>
        <div class="card-body">
          <div class="field">
            <label>¿Qué querés promocionar?</label>
            <select id="eco-producto">
              <option value="piscina">🏊 Piscinas de fibra</option>
              <option value="modulo">🏠 Módulos habitables</option>
              <option value="combo">🎁 Combo módulo + piscina</option>
            </select>
          </div>
          <div class="field">
            <label>Formato</label>
            <select id="eco-tipo">
              <option value="flyer">📷 Post cuadrado (feed)</option>
              <option value="story">📱 Story vertical (9:16)</option>
            </select>
          </div>
          <div class="field">
            <label>Tono</label>
            <select id="eco-tono">
              <option value="cálido y aspiracional">Cálido y aspiracional</option>
              <option value="urgente y promocional">Urgente / promoción</option>
              <option value="informativo y de confianza">Informativo / confianza</option>
              <option value="divertido y fresco">Divertido y fresco</option>
            </select>
          </div>
          <div class="field">
            <label>¿Algo puntual que quieras decir? (opcional)</label>
            <textarea id="eco-desc" rows="3" placeholder="Ej: promo de verano, financiación en 36 cuotas, modelo nuevo de 6x3..." style="font-family:inherit"></textarea>
          </div>
          <div class="field">
            <label style="display:flex;align-items:center;gap:8px;text-transform:none;font-weight:600">
              <input type="checkbox" id="eco-con-imagen" checked style="width:auto"> Generar también una imagen con IA
            </label>
          </div>
          <button class="btn btn-primary" style="width:100%;padding:12px;font-size:15px" onclick="ecoGenerar(this)">✨ Generar contenido con IA</button>
          <div style="text-align:center;margin:10px 0;color:#aaa;font-size:12px">— o —</div>
          <button class="btn btn-outline" style="width:100%;padding:11px;font-size:14px" onclick="ecoEmpezarManual()">✍️ Armar yo mismo (subir foto/video + mi texto)</button>
        </div>
      </div>

      <!-- Paso 2: revisar y publicar -->
      <div class="card">
        <div class="card-header"><span>👀</span><h3>2 · Revisar y publicar</h3></div>
        <div class="card-body">
          <div id="eco-preview-empty" class="empty" style="padding:30px">
            Generá contenido a la izquierda y va a aparecer acá para revisarlo antes de publicar.
          </div>
          <div id="eco-preview" style="display:none">
            <div id="eco-img-wrap" style="margin-bottom:12px;text-align:center">
              <img id="eco-img" style="max-width:100%;border-radius:10px;border:1px solid #eee;display:none" />
              <video id="eco-video" controls style="max-width:100%;border-radius:10px;border:1px solid #eee;display:none"></video>
            </div>
            <div id="eco-img-msg" style="font-size:12px;margin-bottom:12px"></div>

            <label style="display:block;font-size:11px;font-weight:700;color:#666;text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px">Texto del posteo (editable)</label>
            <textarea id="eco-caption" rows="7" style="width:100%;border:1.5px solid #dde;border-radius:8px;padding:10px;font-size:13px;font-family:inherit;line-height:1.5"></textarea>

            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
              <label class="btn btn-outline" style="font-size:12px;cursor:pointer">
                📁 Subir foto o video
                <input type="file" id="eco-upload" accept="image/*,video/*" style="display:none" onchange="ecoSubirFoto(event)">
              </label>
              <button class="btn btn-outline" style="font-size:12px" onclick="ecoDescargar()">📥 Descargar archivo</button>
            </div>

            <div class="sep"></div>
            <label style="display:block;font-size:11px;font-weight:700;color:#666;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Publicar en</label>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <button class="btn btn-primary" onclick="ecoPublicar('facebook', this)">📘 Facebook</button>
              <button class="btn btn-primary" style="background:#C13584" onclick="ecoPublicar('instagram', this)">📸 Instagram</button>
              <button class="btn btn-primary" style="background:#444" onclick="ecoPublicar('ambos', this)">🚀 Ambos</button>
            </div>
            <div class="cmd-result" id="eco-pub-result"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:20px">
      <div class="card-header"><span>📚</span><h3>Historial y calendario completo</h3></div>
      <div class="card-body">
        <p style="font-size:13px;color:#666;margin-bottom:12px">
          Renata también publica sola dos veces por día. Para ver el historial completo, el calendario de contenido y el flujo de aprobación, usá el módulo Ecopost del CRM.
        </p>
        <a href="https://eco-crm-dawn-fog-5476.fly.dev/ecopost" target="_blank" class="btn btn-outline" style="text-decoration:none">📚 Abrir Ecopost del CRM →</a>
      </div>
    </div>
  </div>

  <!-- GALERÍA DE ACTIVOS -->
  <div id="page-galeria" class="page">

    <!-- Fila superior: subir + generar con IA -->
    <div class="grid-2" style="align-items:start;margin-bottom:20px">

      <!-- Subir imágenes propias -->
      <div class="card">
        <div class="card-header"><span>📁</span><h3>Subir imágenes</h3></div>
        <div class="card-body">
          <div id="gal-drop-zone" style="border:2px dashed #c5e0d0;border-radius:12px;padding:30px;text-align:center;cursor:pointer;background:#f8fdf9;transition:background .2s"
               onclick="document.getElementById('gal-file-input').click()"
               ondragover="event.preventDefault();this.style.background='#e8f5e9'"
               ondragleave="this.style.background='#f8fdf9'"
               ondrop="galDrop(event)">
            <div style="font-size:36px;margin-bottom:8px">🖼️</div>
            <div style="font-size:14px;color:#555;font-weight:600">Arrastrá imágenes acá o hacé clic para seleccionar</div>
            <div style="font-size:12px;color:#999;margin-top:4px">JPG, PNG, WEBP — máx 5 MB por imagen</div>
          </div>
          <input type="file" id="gal-file-input" accept="image/*" multiple style="display:none" onchange="galSubirArchivos(event.target.files)">

          <!-- Etiquetas para la imagen subida -->
          <div id="gal-upload-meta" style="display:none;margin-top:14px">
            <div class="field">
              <label>Nombre (opcional)</label>
              <input id="gal-nombre" placeholder="Ej: Piscina 6x3 verano 2026">
            </div>
            <div class="field">
              <label>Etiquetas (seleccioná las que aplican)</label>
              <div id="gal-etiq-upload" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:4px"></div>
            </div>
            <div class="field">
              <label>Descripción breve</label>
              <input id="gal-descripcion" placeholder="Ej: foto de obra piscina GRP 6x3">
            </div>
            <button class="btn btn-primary" style="width:100%" onclick="galConfirmarSubida(this)">💾 Guardar en galería</button>
            <div class="cmd-result" id="gal-upload-result"></div>
          </div>
        </div>
      </div>

      <!-- Generar con IA (Ecopost/Gemini) -->
      <div class="card">
        <div class="card-header"><span>✨</span><h3>Generar imagen con IA</h3></div>
        <div class="card-body">
          <div class="field">
            <label>Producto</label>
            <select id="gal-ia-producto">
              <option value="piscina">🏊 Piscinas de fibra</option>
              <option value="modulo">🏠 Módulos habitables</option>
              <option value="combo">🎁 Combo módulo + piscina</option>
            </select>
          </div>
          <div class="field">
            <label>Formato</label>
            <select id="gal-ia-tipo">
              <option value="flyer">📷 Cuadrado 1:1 (feed)</option>
              <option value="story">📱 Vertical 9:16 (story)</option>
            </select>
          </div>
          <div class="field">
            <label>Descripción de la imagen</label>
            <textarea id="gal-ia-desc" rows="3" placeholder="Ej: familia disfrutando de una piscina de fibra en un jardín verde, atardecer, colores cálidos" style="font-family:inherit"></textarea>
          </div>
          <div class="field">
            <label>Etiquetas</label>
            <div id="gal-etiq-ia" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:4px"></div>
          </div>
          <button class="btn btn-primary" style="width:100%;padding:12px" onclick="galGenerarIA(this)">✨ Generar con Gemini/Ecopost</button>

          <!-- Preview de imagen IA generada -->
          <div id="gal-ia-preview" style="display:none;margin-top:14px;text-align:center">
            <img id="gal-ia-img" style="max-width:100%;border-radius:10px;border:1px solid #eee">
            <div style="display:flex;gap:8px;margin-top:10px;justify-content:center">
              <button class="btn btn-primary" style="font-size:13px" onclick="galGuardarIA(this)">💾 Guardar en galería</button>
              <button class="btn btn-outline" style="font-size:13px" onclick="galDescargaIA()">📥 Descargar</button>
            </div>
            <div class="cmd-result" id="gal-ia-result"></div>
          </div>
          <div class="cmd-result" id="gal-ia-gen-result"></div>
        </div>
      </div>
    </div>

    <!-- Sync Google Drive -->
    <div class="card" style="margin-bottom:20px;border-left:4px solid #4285F4">
      <div class="card-header"><span>☁️</span><h3>Sincronizar desde Google Drive</h3>
        <span id="gal-drive-badge" style="margin-left:8px;font-size:12px;color:#888">Verificando…</span>
        <button class="btn btn-outline" style="font-size:12px;margin-left:auto" onclick="galVerificarDrive()">🔍 Verificar conexión</button>
      </div>
      <div class="card-body">
        <p style="font-size:13px;color:#555;margin-bottom:12px;line-height:1.6">
          Organizá tus imágenes en Google Drive con subcarpetas por categoría
          (<b>modulos/</b>, <b>piscinas/</b>, <b>combo/</b>, <b>contado/</b>, <b>financiado/</b>, <b>familia/</b>, <b>obra/</b>, <b>general/</b>)
          y el sistema las importa automáticamente a la galería con las etiquetas correctas.
        </p>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          <button class="btn btn-primary" style="background:#4285F4" onclick="galSyncDrive(this)">☁️ Sincronizar ahora desde Drive</button>
          <div id="gal-drive-folder" style="font-size:12px;color:#666"></div>
        </div>
        <div class="cmd-result" id="gal-drive-result"></div>
      </div>
    </div>

    <!-- Galería de imágenes -->
    <div class="card" style="margin-bottom:20px">
      <div class="card-header">
        <span>🖼️</span><h3>Imágenes en la galería</h3>
        <button class="btn btn-outline" style="font-size:12px;margin-left:auto" onclick="galCargar()">🔄 Actualizar</button>
      </div>
      <div class="card-body">
        <!-- Filtros -->
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px" id="gal-filtros"></div>
        <!-- Grid -->
        <div id="gal-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:14px">
          <div class="empty" style="grid-column:1/-1">Cargando galería…</div>
        </div>
      </div>
    </div>

    <!-- Biblioteca de copies -->
    <div class="card">
      <div class="card-header"><span>✍️</span><h3>Biblioteca de copies</h3>
        <button class="btn btn-primary" style="font-size:12px;margin-left:auto" onclick="galNuevoCopy()">+ Nuevo copy</button>
      </div>
      <div class="card-body">
        <!-- Filtros copies -->
        <div class="field-row" style="margin-bottom:14px">
          <div class="field">
            <label>Filtrar por producto</label>
            <select id="gal-copy-producto" onchange="galCargarCopies()">
              <option value="">Todos</option>
              <option value="modulos">Módulos</option>
              <option value="piscinas">Piscinas</option>
              <option value="combo">Combo</option>
              <option value="general">General</option>
            </select>
          </div>
          <div class="field">
            <label>Objetivo</label>
            <select id="gal-copy-objetivo" onchange="galCargarCopies()">
              <option value="">Todos</option>
              <option value="captar">Captar leads</option>
              <option value="cerrar">Cerrar venta</option>
              <option value="nutrir">Nutrir</option>
              <option value="financiacion">Financiación</option>
              <option value="general">General</option>
            </select>
          </div>
        </div>

        <!-- Editor inline de copy -->
        <div id="gal-copy-editor" style="display:none;background:#f8fdf9;border:1.5px solid #c5e0d0;border-radius:10px;padding:16px;margin-bottom:16px">
          <input type="hidden" id="gal-copy-id">
          <div class="field-row">
            <div class="field">
              <label>Producto</label>
              <select id="gal-copy-ed-producto">
                <option value="modulos">Módulos</option>
                <option value="piscinas">Piscinas</option>
                <option value="combo">Combo</option>
                <option value="general">General</option>
              </select>
            </div>
            <div class="field">
              <label>Objetivo</label>
              <select id="gal-copy-ed-objetivo">
                <option value="captar">Captar leads</option>
                <option value="cerrar">Cerrar venta</option>
                <option value="nutrir">Nutrir</option>
                <option value="financiacion">Financiación</option>
                <option value="general">General</option>
              </select>
            </div>
          </div>
          <div class="field">
            <label>Texto del copy</label>
            <textarea id="gal-copy-ed-texto" rows="5" style="width:100%;font-family:inherit;border:1.5px solid #dde;border-radius:8px;padding:10px;font-size:13px;line-height:1.5"></textarea>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-primary" onclick="galGuardarCopy(this)">💾 Guardar copy</button>
            <button class="btn btn-outline" onclick="galCerrarEditorCopy()">Cancelar</button>
            <div class="cmd-result" id="gal-copy-ed-result" style="flex:1"></div>
          </div>
        </div>

        <!-- Lista de copies -->
        <div id="gal-copies-lista"><div class="empty">Cargando copies…</div></div>
      </div>
    </div>
  </div>

  <!-- MERCADOLIBRE -->
  <div id="page-mercadolibre" class="page">
    <!-- Estado de conexión -->
    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span>🛒</span><h3>Conexión con MercadoLibre</h3>
        <span id="ml-status-badge" style="margin-left:auto" class="header-badge">…</span>
      </div>
      <div class="card-body" id="ml-conexion"><div class="empty">Cargando estado…</div></div>
    </div>

    <!-- Métricas (cuando está conectado) -->
    <div id="ml-metricas-wrap" style="display:none">
      <div class="grid-4" style="margin-bottom:20px">
        <div class="stat-card"><div class="stat-label">Publicaciones activas</div><div class="stat-value" id="ml-activas">—</div><div class="stat-sub">En línea</div></div>
        <div class="stat-card" style="border-left-color:#999"><div class="stat-label">Pausadas</div><div class="stat-value" id="ml-pausadas">—</div><div class="stat-sub">Fuera de línea</div></div>
        <div class="stat-card" style="border-left-color:#2e7d32"><div class="stat-label">Ventas pagadas</div><div class="stat-value" id="ml-ventas">—</div><div class="stat-sub" id="ml-monto">—</div></div>
        <div class="stat-card" style="border-left-color:#E65100"><div class="stat-label">Preguntas sin responder</div><div class="stat-value" id="ml-preguntas">—</div><div class="stat-sub">Pendientes</div></div>
      </div>
    </div>

    <!-- Gestión de publicaciones -->
    <div id="ml-gestion-wrap" style="display:none">
      <div class="card" style="margin-bottom:20px">
        <div class="card-header"><span>📦</span><h3>Mis publicaciones</h3>
          <select id="ml-filtro-estado" style="margin-left:auto;padding:6px 12px;border:1.5px solid #dde;border-radius:8px;font-size:13px" onchange="mlCargarPublicaciones()">
            <option value="active">Activas</option>
            <option value="paused">Pausadas</option>
          </select>
          <button class="btn btn-outline" style="font-size:12px;margin-left:8px" onclick="mlCargarPublicaciones()">🔄 Actualizar</button>
        </div>
        <div class="card-body" style="overflow-x:auto"><div id="ml-lista"><div class="empty">Cargando…</div></div></div>
      </div>

      <!-- Crear publicación -->
      <div class="card">
        <div class="card-header"><span>➕</span><h3>Crear nueva publicación</h3></div>
        <div class="card-body">
          <div class="field-row">
            <div class="field"><label>Título (máx 60)</label><input id="ml-new-title" maxlength="60" placeholder="Piscina de fibra 6x3 con instalación"></div>
            <div class="field"><label>Precio (ARS)</label><input id="ml-new-price" type="number" placeholder="3900000"></div>
          </div>
          <div class="field-row">
            <div class="field"><label>Stock disponible</label><input id="ml-new-stock" type="number" value="1"></div>
            <div class="field"><label>Tipo de publicación</label>
              <select id="ml-new-listing">
                <option value="gold_special">Clásica</option>
                <option value="gold_pro">Premium</option>
                <option value="free">Gratuita</option>
              </select>
            </div>
          </div>
          <div class="field"><label>Fotos (URLs públicas, una por línea)</label><textarea id="ml-new-pics" rows="2" placeholder="https://...jpg" style="font-family:inherit"></textarea></div>
          <div class="field"><label>Descripción</label><textarea id="ml-new-desc" rows="4" placeholder="Detalle del producto..." style="font-family:inherit"></textarea></div>
          <div class="field"><label>Categoría (se autodetecta del título si lo dejás vacío)</label><input id="ml-new-cat" placeholder="MLA1500"></div>
          <button class="btn btn-primary" onclick="mlCrear(this)">➕ Publicar en MercadoLibre</button>
          <div class="cmd-result" id="ml-crear-result"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- BASE DE CONOCIMIENTO -->
  <div id="page-conocimiento" class="page">
    <!-- Estilo global -->
    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span>✍️</span><h3>Estilo de respuesta (afecta a TODOS los agentes)</h3></div>
      <div class="card-body">
        <p style="font-size:13px;color:#666;margin-bottom:10px">
          Acá controlás el largo, tono y formato de TODAS las respuestas. Si te resultan largas o genéricas, ajustá esto.
        </p>
        <textarea id="kb-estilo" rows="7" style="width:100%;border:1.5px solid #dde;border-radius:8px;padding:12px;font-size:13px;font-family:monospace;line-height:1.6"></textarea>
        <div style="display:flex;gap:10px;margin-top:10px;align-items:center">
          <button class="btn btn-primary" onclick="kbGuardarEstilo(this)">💾 Guardar estilo</button>
          <button class="btn btn-outline" onclick="kbResetEstilo()">↩ Restaurar recomendado</button>
          <span id="kb-estilo-msg" style="font-size:13px;color:#666"></span>
        </div>
      </div>
    </div>

    <!-- Documentos de conocimiento -->
    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span>📚</span><h3>Documentos de conocimiento</h3>
        <button class="btn btn-primary" style="margin-left:auto;font-size:12px" onclick="kbNuevoDoc()">➕ Nuevo documento</button>
      </div>
      <div class="card-body">
        <p style="font-size:13px;color:#666;margin-bottom:14px">
          Cada documento es conocimiento real que los agentes usan como verdad al responder (políticas, argumentos, datos técnicos, FAQs...). Asigná a qué agentes aplica.
        </p>
        <div id="kb-lista"><div class="empty">Cargando…</div></div>
      </div>
    </div>

    <!-- Editor de documento -->
    <div class="card" id="kb-editor" style="display:none;margin-bottom:20px;border:2px solid var(--verde)">
      <div class="card-header"><span>📝</span><h3 id="kb-editor-titulo">Nuevo documento</h3></div>
      <div class="card-body">
        <input type="hidden" id="kb-doc-id">
        <div class="field"><label>Título</label><input id="kb-doc-titulo" placeholder="Ej: Política de pago en domicilio"></div>
        <div class="field">
          <label>Contenido (el conocimiento que el agente debe saber)</label>
          <textarea id="kb-doc-contenido" rows="8" style="font-family:inherit" placeholder="Escribí o importá el conocimiento..."></textarea>
        </div>
        <div class="field">
          <label>Importar desde archivo (.txt, .md, .csv)</label>
          <input type="file" id="kb-doc-file" accept=".txt,.md,.csv,.text,text/*" onchange="kbImportarArchivo(event)">
          <div class="hint">El texto del archivo se carga en el contenido de arriba.</div>
        </div>
        <div class="field">
          <label>¿A qué agentes aplica?</label>
          <div style="margin-bottom:8px">
            <label style="font-weight:600;font-size:13px;text-transform:none"><input type="checkbox" id="kb-ag-todos" onchange="kbToggleTodos()" style="width:auto"> Todos los agentes</label>
          </div>
          <div id="kb-agentes-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px"></div>
        </div>
        <div class="field">
          <label style="text-transform:none;font-weight:600"><input type="checkbox" id="kb-doc-activo" checked style="width:auto"> Activo (lo usan los agentes)</label>
        </div>
        <div style="display:flex;gap:10px;align-items:center">
          <button class="btn btn-primary" onclick="kbGuardarDoc(this)">💾 Guardar documento</button>
          <button class="btn btn-outline" onclick="document.getElementById('kb-editor').style.display='none'">Cancelar</button>
          <span id="kb-doc-msg" style="font-size:13px;color:#666"></span>
        </div>
      </div>
    </div>

    <!-- Atajos a otros conocimientos -->
    <div class="card">
      <div class="card-header"><span>🔗</span><h3>Otros conocimientos editables</h3></div>
      <div class="card-body" style="display:flex;gap:12px;flex-wrap:wrap">
        <a class="btn btn-outline" style="text-decoration:none" href="#" onclick="document.querySelector('.nav-item[data-page=catalogo]').click();return false">🏊 Catálogo y precios</a>
        <a class="btn btn-outline" style="text-decoration:none" href="/panel" target="_blank">💬 Prompt de cada agente (en Comandar Agentes → pestaña Prompt)</a>
      </div>
    </div>
  </div>

  <!-- AGENTS -->
  <div id="page-agents" class="page">
    <div style="margin-bottom:20px;display:flex;gap:10px;flex-wrap:wrap">
      <input type="text" id="agent-search" placeholder="Buscar agente..." style="padding:8px 14px;border:1.5px solid #dde;border-radius:8px;font-size:13px;outline:none;flex:1;max-width:300px">
      <select id="agent-filter" style="padding:8px 14px;border:1.5px solid #dde;border-radius:8px;font-size:13px;outline:none">
        <option value="">Todos los canales</option>
        <option value="whatsapp">WhatsApp</option>
        <option value="interno">Interno</option>
        <option value="web">Web</option>
      </select>
    </div>
    <div class="agent-grid" id="agents-grid"></div>
  </div>

  <!-- HIERARCHY -->
  <div id="page-hierarchy" class="page">
    <div class="card">
      <div class="card-header"><span>🗂️</span><h3>Jerarquía del equipo IA</h3></div>
      <div class="card-body" id="hierarchy-tree" style="overflow-x:auto;padding:8px 0"></div>
    </div>
  </div>

  <!-- CONFIG -->
  <div id="page-config" class="page">
    <form id="config-form">
      <div class="grid-2">
        <!-- col izquierda -->
        <div>
          <div class="card" style="margin-bottom:16px">
            <div class="card-header"><span>🤖</span><h3>Google Gemini IA</h3></div>
            <div class="card-body">
              <div class="field">
                <label>GEMINI_API_KEY <span id="dot-gemini"></span></label>
                <input type="password" name="GEMINI_API_KEY" id="cfg-gemini" placeholder="AIza...">
                <div class="hint">aistudio.google.com → Get API Key → Create API Key</div>
              </div>
              <button type="button" class="btn btn-outline" onclick="testIntegration('gemini')">▶ Probar Gemini</button>
              <div class="test-result" id="tr-gemini"></div>
            </div>
          </div>

          <div class="card" style="margin-bottom:16px">
            <div class="card-header"><span>🗄️</span><h3>CRM (Fly.io)</h3></div>
            <div class="card-body">
              <div class="field-row">
                <div class="field">
                  <label>CRM_BASE_URL <span id="dot-crm"></span></label>
                  <input type="text" name="CRM_BASE_URL" id="cfg-crm-url" placeholder="https://eco-crm-dawn-fog-5476.fly.dev">
                </div>
                <div class="field">
                  <label>CRM_API_KEY</label>
                  <input type="password" name="CRM_API_KEY" id="cfg-crm-key" placeholder="eco-crm-api-key...">
                </div>
              </div>
              <button type="button" class="btn btn-outline" onclick="testIntegration('crm')">▶ Probar CRM</button>
              <div class="test-result" id="tr-crm"></div>
            </div>
          </div>

          <div class="card" style="margin-bottom:16px">
            <div class="card-header"><span>📱</span><h3>Telegram</h3></div>
            <div class="card-body">
              <div class="field-row">
                <div class="field">
                  <label>BOT_TOKEN <span id="dot-tg"></span></label>
                  <input type="password" name="TELEGRAM_BOT_TOKEN" id="cfg-tg-token" placeholder="1234567890:AAF...">
                  <div class="hint">@BotFather → /newbot</div>
                </div>
                <div class="field">
                  <label>CHAT_ID_RODRIGO</label>
                  <input type="text" name="TELEGRAM_CHAT_ID_RODRIGO" id="cfg-tg-id" placeholder="123456789">
                  <div class="hint">@userinfobot</div>
                </div>
              </div>
              <button type="button" class="btn btn-outline" onclick="testIntegration('telegram')">▶ Probar Telegram</button>
              <div class="test-result" id="tr-telegram"></div>
            </div>
          </div>
        </div>

        <!-- col derecha -->
        <div>
          <div class="card" style="margin-bottom:16px">
            <div class="card-header"><span>💬</span><h3>WhatsApp Business</h3></div>
            <div class="card-body">
              <div class="field-row">
                <div class="field">
                  <label>WA_TOKEN <span id="dot-wa"></span></label>
                  <input type="password" name="WA_TOKEN" id="cfg-wa-token" placeholder="EAABm0...">
                  <div class="hint">Meta Business → API Setup</div>
                </div>
                <div class="field">
                  <label>WA_PHONE_ID</label>
                  <input type="text" name="WA_PHONE_ID" id="cfg-wa-phone" placeholder="123456789012345">
                </div>
              </div>
              <div class="field">
                <label>WA_VERIFY_TOKEN</label>
                <input type="text" name="WA_VERIFY_TOKEN" id="cfg-wa-verify" placeholder="eco_modules_verify_2026">
                <div class="hint">Copiá este mismo valor en Meta Business al configurar el webhook</div>
              </div>
              <button type="button" class="btn btn-outline" onclick="testIntegration('whatsapp')">▶ Probar WhatsApp</button>
              <div class="test-result" id="tr-whatsapp"></div>
            </div>
          </div>

          <div class="card" style="margin-bottom:16px">
            <div class="card-header"><span>☁️</span><h3>Cloudflare (Ecopost)</h3></div>
            <div class="card-body">
              <div class="field">
                <label>CLOUDFLARE_WORKER_URL <span id="dot-cf"></span></label>
                <input type="text" name="CLOUDFLARE_WORKER_URL" id="cfg-cf-url" placeholder="https://eco-agentes.growersb.workers.dev">
              </div>
              <div class="field">
                <label>GOOGLE_DRIVE_FOLDER_ID</label>
                <input type="text" name="GOOGLE_DRIVE_FOLDER_ID" id="cfg-drive" placeholder="1tXwe5E9M7R31Q8X-...">
              </div>
              <button type="button" class="btn btn-outline" onclick="testIntegration('cloudflare')">▶ Probar Cloudflare</button>
              <div class="test-result" id="tr-cloudflare"></div>
            </div>
          </div>

          <div class="card" style="margin-bottom:16px">
            <div class="card-header"><span>🌐</span><h3>Web y Seguridad</h3></div>
            <div class="card-body">
              <div class="field-row">
                <div class="field">
                  <label>BASE_URL</label>
                  <input type="text" name="BASE_URL" id="cfg-base-url" placeholder="https://eco-multiagente.fly.dev">
                </div>
                <div class="field">
                  <label>PORT</label>
                  <input type="text" name="PORT" id="cfg-port" placeholder="8080">
                </div>
              </div>
              <div class="field">
                <label>ADMIN_PASSWORD (nueva contraseña — dejá vacío para no cambiar)</label>
                <input type="password" name="ADMIN_PASSWORD" id="cfg-admin-pw" placeholder="••••••••">
              </div>
            </div>
          </div>
        </div>
      </div>

      <div style="display:flex;gap:12px;align-items:center;padding:4px 0">
        <button type="button" class="btn btn-primary" onclick="saveConfig()" style="font-size:15px;padding:12px 32px">
          💾 Guardar toda la configuración
        </button>
        <span id="save-msg" style="font-size:13px;color:#666"></span>
      </div>
    </form>
  </div>

  <!-- SCHEDULER -->
  <div id="page-scheduler" class="page">
    <div class="card">
      <div class="card-header"><span>⏰</span><h3>Tareas programadas (Zona horaria: Argentina GMT-3)</h3></div>
      <div class="card-body">
        <div class="sched-row">
          <span class="sched-time">Diario 08:00 AM</span>
          <span class="sched-name">Reporte diario Máximo → Rodrigo (Telegram)</span>
          <span class="sched-badge">Activo</span>
        </div>
        <div class="sched-row">
          <span class="sched-time">Diario 09:00 AM</span>
          <span class="sched-name">Aurora — reporte matutino pipeline</span>
          <span class="sched-badge">Activo</span>
        </div>
        <div class="sched-row">
          <span class="sched-time">Cada 2 hs (8-22)</span>
          <span class="sched-name">Check leads sin respuesta → alerta Tomás</span>
          <span class="sched-badge">Activo</span>
        </div>
        <div class="sched-row">
          <span class="sched-time">Diario 18:00 PM</span>
          <span class="sched-name">Aurora — reporte vespertino + check cuotas</span>
          <span class="sched-badge">Activo</span>
        </div>
        <div class="sched-row">
          <span class="sched-time">Diario 20:00 PM</span>
          <span class="sched-name">Ignacio — revisión cuotas vencidas + cobros automáticos</span>
          <span class="sched-badge">Activo</span>
        </div>
        <div class="sched-row" style="border:none">
          <span class="sched-time">Lunes 09:00 AM</span>
          <span class="sched-name">Elena — reporte semanal + Renata — calendario de contenido</span>
          <span class="sched-badge">Activo</span>
        </div>
      </div>
    </div>

    <div style="margin-top:20px" class="card">
      <div class="card-header"><span>⚡</span><h3>Escala de cobro automático (Ignacio)</h3></div>
      <div class="card-body">
        <div class="sched-row"><span class="sched-time" style="color:#43a047">Día 1-3</span><span>Recordatorio cordial automático por WhatsApp</span></div>
        <div class="sched-row"><span class="sched-time" style="color:#fb8c00">Día 4-7</span><span>Consulta de situación — contacto directo</span></div>
        <div class="sched-row"><span class="sched-time" style="color:#e53935">Día 8-15</span><span>Propuesta refinanciación (requiere autorización Máximo)</span></div>
        <div class="sched-row" style="border:none"><span class="sched-time" style="color:#b71c1c">Día 16+</span><span>Escalada a Ezequiel y Máximo — decisión manual</span></div>
      </div>
    </div>
  </div>

  <!-- CATÁLOGO -->
  <div id="page-catalogo" class="page">
    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span>🏊</span><h3>Piscinas de fibra de vidrio — 16 modelos</h3></div>
      <div class="card-body" style="overflow-x:auto">
        <table class="tabla" id="tabla-piscinas"></table>
      </div>
    </div>
    <div class="card" style="margin-bottom:20px">
      <div class="card-header"><span>🏠</span><h3>Módulos NCE — configuración</h3></div>
      <div class="card-body" id="modulos-config"></div>
    </div>
    <div class="card">
      <div class="card-header"><span>💳</span><h3>Planes de financiación</h3></div>
      <div class="card-body" id="planes-config"></div>
    </div>
    <div style="margin-top:16px;display:flex;gap:12px">
      <button class="btn btn-primary" onclick="saveCatalogo()">💾 Guardar catálogo</button>
      <span id="cat-msg" style="font-size:13px;color:#666;align-self:center"></span>
    </div>
  </div>

  <!-- SIMULADOR CUOTAS -->
  <div id="page-cuotas" class="page">
    <div class="card" style="max-width:560px">
      <div class="card-header"><span>💰</span><h3>Simulador de cuotas</h3></div>
      <div class="card-body">
        <div class="field">
          <label>Precio del producto ($)</label>
          <input type="number" id="sim-precio" placeholder="3900000" value="3900000">
        </div>
        <div class="field">
          <label>Planes a mostrar</label>
          <select id="sim-planes" multiple style="height:120px">
            <option value="12" selected>12 cuotas</option>
            <option value="18" selected>18 cuotas</option>
            <option value="24" selected>24 cuotas</option>
            <option value="36" selected>36 cuotas</option>
            <option value="60">60 cuotas</option>
            <option value="120">120 cuotas</option>
          </select>
          <div class="hint">Ctrl+Click para seleccionar varios</div>
        </div>
        <div class="field">
          <label>Tipo de producto</label>
          <select id="sim-tipo">
            <option value="piscina">Piscina</option>
            <option value="modulo">Módulo</option>
          </select>
        </div>
        <button class="btn btn-primary" onclick="simularCuotas()">▶ Simular</button>
        <div id="sim-result" style="margin-top:16px;background:#f8faf8;border-radius:8px;padding:14px;font-size:13px;display:none;white-space:pre-line;line-height:1.7;font-family:monospace"></div>
      </div>
    </div>
  </div>

  <!-- CALCULADOR FLETE -->
  <div id="page-flete" class="page">
    <div class="card" style="max-width:560px">
      <div class="card-header"><span>🚛</span><h3>Calculador de flete desde Zárate</h3></div>
      <div class="card-body">
        <div class="field">
          <label>Localidad destino</label>
          <input type="text" id="flete-loc" placeholder="Mar del Plata, Córdoba, Rosario...">
        </div>
        <div class="field">
          <label>Tipo de producto</label>
          <select id="flete-tipo">
            <option value="general" id="opt-flete-general">General</option>
            <option value="miniportante" id="opt-flete-mini">Miniportante</option>
          </select>
        </div>
        <button class="btn btn-primary" onclick="calcFlete()">▶ Calcular</button>
        <div id="flete-result" style="margin-top:16px;background:#f8faf8;border-radius:8px;padding:14px;font-size:13px;display:none;line-height:1.7"></div>
      </div>
    </div>
  </div>

  <!-- WEBHOOK INFO -->
  <div id="page-webhook" class="page">
    <div class="grid-2">
      <div class="card">
        <div class="card-header"><span>💬</span><h3>Configuración webhook WhatsApp</h3></div>
        <div class="card-body">
          <div style="margin-bottom:16px">
            <div class="hint" style="margin-bottom:6px;font-weight:700;color:#333">URL del webhook (copiar en Meta Business):</div>
            <div style="background:#f8f9fa;border-radius:8px;padding:10px 14px;font-size:13px;font-family:monospace;word-break:break-all" id="webhook-url">—</div>
            <button class="btn btn-outline" style="margin-top:8px;font-size:12px" onclick="copyWebhook()">📋 Copiar URL</button>
          </div>
          <div>
            <div class="hint" style="margin-bottom:6px;font-weight:700;color:#333">Token de verificación:</div>
            <div style="background:#f8f9fa;border-radius:8px;padding:10px 14px;font-size:13px;font-family:monospace" id="webhook-token">eco_modules_verify_2026</div>
          </div>
          <div class="sep"></div>
          <div class="hint" style="line-height:1.7">
            <b>Pasos en Meta Business:</b><br>
            1. Ir a WhatsApp → Configuración → Webhooks<br>
            2. Pegar la URL de arriba<br>
            3. Pegar el token de verificación<br>
            4. Hacer click en <b>Verificar y guardar</b><br>
            5. Suscribir al campo: <b>messages</b>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span>🧩</span><h3>Snippet para la landing page</h3></div>
        <div class="card-body">
          <div class="hint" style="margin-bottom:8px">Pegá este código antes del <code>&lt;/body&gt;</code> en tu landing:</div>
          <div style="background:#1e1e1e;color:#a6e22e;border-radius:8px;padding:14px;font-size:12px;font-family:monospace;white-space:pre;overflow-x:auto;line-height:1.6" id="snippet-box">Cargando...</div>
          <button class="btn btn-outline" style="margin-top:10px;font-size:12px" onclick="copySnippet()">📋 Copiar snippet</button>
        </div>
      </div>
    </div>
  </div>

</main>

<!-- ── MODAL AGENTE ─────────────────────────────────── -->
<div id="modal-overlay" onclick="closeModal(event)">
  <div id="modal">
    <div class="modal-header">
      <span id="modal-emoji" style="font-size:32px"></span>
      <h2 id="modal-title"></h2>
      <button class="modal-close" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body" id="modal-body"></div>
  </div>
</div>

<!-- ── TOAST ────────────────────────────────────────── -->
<div id="toast"></div>

<script>
// ── DATOS ────────────────────────────────────────────
const AGENTS = __AGENTS_JSON__;
const CATALOGO = __CATALOGO_JSON__;
const ENV = __ENV_JSON__;

// ── NAVEGACIÓN ───────────────────────────────────────
const pageMap = {
  overview:  'Resumen del sistema',
  comando:   'Centro de Comando',
  ecopost:   'Ecopost — Estudio de contenido',
  galeria:   'Galería de Activos — Imágenes y Copies',
  mercadolibre: 'MercadoLibre — Gestión de publicaciones',
  conocimiento: 'Base de Conocimiento de los agentes',
  agents:    'Agentes IA — 15 agentes',
  hierarchy: 'Jerarquía del equipo',
  config:    'Configuración general',
  scheduler: 'Tareas programadas',
  catalogo:  'Catálogo de productos',
  cuotas:    'Simulador de cuotas',
  flete:     'Calculador de flete',
  webhook:   'WhatsApp / Webhook',
};

document.querySelectorAll('.nav-item[data-page]').forEach(el => {
  el.addEventListener('click', e => {
    e.preventDefault();
    const page = el.dataset.page;
    document.querySelectorAll('.nav-item').forEach(x => x.classList.remove('active'));
    el.classList.add('active');
    document.querySelectorAll('.page').forEach(x => x.classList.remove('active'));
    document.getElementById('page-' + page).classList.add('active');
    document.getElementById('page-title').textContent = pageMap[page] || page;
    if (page === 'mercadolibre' && typeof mlCargarEstado === 'function') mlCargarEstado();
    if (page === 'overview' && typeof loadKpis === 'function') loadKpis();
    if (page === 'conocimiento' && typeof kbCargar === 'function') kbCargar();
    if (page === 'comando' && typeof cargarLeadsAccion === 'function') cargarLeadsAccion();
    if (page === 'galeria' && typeof galCargar === 'function') galCargar();
  });
});

function navigateTo(page) {
  const el = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (el) el.click();
}

// ── RELOJ ────────────────────────────────────────────
function updateClock() {
  document.getElementById('clock').textContent =
    new Date().toLocaleString('es-AR', {
      timeZone:'America/Argentina/Buenos_Aires',
      weekday:'short', hour:'2-digit', minute:'2-digit'
    });
}
updateClock(); setInterval(updateClock, 30000);

// ── OVERVIEW ─────────────────────────────────────────
function buildTeamSummary() {
  const areas = {
    'Dirección': ['maximo'],
    'Comercial': ['aurora','tomas'],
    'Ventas': ['valentina','camila','mateo','nicolas','luciano'],
    'Marketing': ['renata'],
    'Operaciones': ['bruno'],
    'Administración': ['ezequiel','ignacio','elena'],
    'RRPP / Postventa': ['daniela','sebastian'],
  };
  let html = '';
  for (const [area, ids] of Object.entries(areas)) {
    const agents = ids.map(id => AGENTS.find(a => a.id === id)).filter(Boolean);
    html += `<div style="display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid #f5f5f5">
      <span style="font-size:11px;font-weight:700;color:#888;min-width:120px;text-transform:uppercase">${area}</span>
      <span style="font-size:13px">${agents.map(a => `${a.emoji} ${a.nombre}`).join(' · ')}</span>
    </div>`;
  }
  document.getElementById('team-summary').innerHTML = html;
}

function buildEndpoints() {
  const eps = [
    {method:'POST', path:'/chat/web', desc:'Widget chat web'},
    {method:'POST', path:'/webhook/whatsapp', desc:'Mensajes WhatsApp'},
    {method:'GET',  path:'/webhook/whatsapp', desc:'Verificación Meta'},
    {method:'POST', path:'/send/whatsapp', desc:'Envío proactivo'},
    {method:'GET',  path:'/health', desc:'Health check'},
    {method:'GET',  path:'/web_widget/chat.js', desc:'Widget embebible'},
    {method:'GET',  path:'/widget-snippet', desc:'Snippet landing'},
    {method:'GET',  path:'/dashboard', desc:'Este panel'},
  ];
  document.getElementById('endpoints-list').innerHTML = eps.map(e =>
    `<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:#f8faf8;border-radius:8px">
      <span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;background:${e.method==='POST'?'#e8f5e9':'#e3f2fd'};color:${e.method==='POST'?'#2e7d32':'#1565c0'}">${e.method}</span>
      <code style="font-size:12px;color:#333">${e.path}</code>
      <span style="font-size:11px;color:#888;margin-left:auto">${e.desc}</span>
    </div>`
  ).join('');
}

// ── AGENTES ──────────────────────────────────────────
function buildAgentsGrid(filtered) {
  const list = filtered || AGENTS;
  document.getElementById('agents-grid').innerHTML = list.map(a => `
    <div class="agent-card" onclick="openAgent('${a.id}')" style="border-top:4px solid ${a.color}">
      <div class="agent-card-top">
        <div class="agent-emoji">${a.emoji}</div>
        <div>
          <div class="agent-name">${a.nombre}</div>
          <div class="agent-rol">${a.rol}</div>
          <span class="agent-model ${a.modelo.includes('pro') ? 'model-pro' : 'model-flash'}">${a.modelo}</span>
        </div>
      </div>
      <div class="agent-card-mid">${a.descripcion}</div>
      <div class="agent-card-bot">
        <span class="chip canal">📡 ${a.canal}</span>
        ${a.reporta_a ? `<span class="chip">↑ ${AGENTS.find(x=>x.id===a.reporta_a)?.nombre||a.reporta_a}</span>` : '<span class="chip">👑 Dirección</span>'}
        <span class="chip">${a.funciones.length} funciones</span>
      </div>
    </div>
  `).join('');
}

document.getElementById('agent-search').addEventListener('input', filterAgents);
document.getElementById('agent-filter').addEventListener('change', filterAgents);

function filterAgents() {
  const q = document.getElementById('agent-search').value.toLowerCase();
  const canal = document.getElementById('agent-filter').value;
  const filtered = AGENTS.filter(a =>
    (a.nombre.toLowerCase().includes(q) || a.rol.toLowerCase().includes(q) || a.descripcion.toLowerCase().includes(q)) &&
    (!canal || a.canal.includes(canal))
  );
  buildAgentsGrid(filtered);
}

// ── MODAL AGENTE ─────────────────────────────────────
function openAgent(id) {
  const a = AGENTS.find(x => x.id === id);
  if (!a) return;
  document.getElementById('modal-emoji').textContent = a.emoji;
  document.getElementById('modal-title').textContent = `${a.nombre} — ${a.rol}`;

  const supervisa = a.supervisa.map(sid => {
    const ag = AGENTS.find(x => x.id === sid);
    return ag ? `<span class="hierarchy-pill">${ag.emoji} ${ag.nombre}</span>` : '';
  }).join(' ');

  document.getElementById('modal-body').innerHTML = `
    <div class="modal-section">
      <h4>Descripción</h4>
      <p style="font-size:13px;line-height:1.6;color:#444">${a.descripcion}</p>
    </div>
    <div class="modal-section" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">
      <div>
        <h4>Modelo</h4>
        <span class="agent-model ${a.modelo.includes('pro')?'model-pro':'model-flash'}" style="font-size:12px">${a.modelo}</span>
      </div>
      <div>
        <h4>Canal</h4>
        <span class="tag-verde">📡 ${a.canal}</span>
      </div>
      <div>
        <h4>Reporta a</h4>
        ${a.reporta_a ? `<span class="hierarchy-pill" style="font-size:12px">${AGENTS.find(x=>x.id===a.reporta_a)?.emoji||''} ${AGENTS.find(x=>x.id===a.reporta_a)?.nombre||a.reporta_a}</span>` : '<span style="font-size:13px">👑 Solo a Rodrigo</span>'}
      </div>
    </div>
    ${a.supervisa.length ? `
    <div class="modal-section">
      <h4>Supervisa a</h4>
      <div style="display:flex;gap:8px;flex-wrap:wrap">${supervisa}</div>
    </div>` : ''}
    <div class="modal-section">
      <h4>Funciones activas (${a.funciones.length})</h4>
      <ul class="func-list">${a.funciones.map(f => `<li>${f}</li>`).join('')}</ul>
    </div>
    <div class="modal-section">
      <h4>Escala a</h4>
      <p style="font-size:13px;color:#444">${a.escala_a}</p>
    </div>
  `;
  document.getElementById('modal-overlay').classList.add('open');
}

function closeModal(e) {
  if (!e || e.target === document.getElementById('modal-overlay')) {
    document.getElementById('modal-overlay').classList.remove('open');
  }
}

// ── JERARQUÍA ─────────────────────────────────────────
function buildHierarchy() {
  const CSS = `
    .htree{display:flex;flex-direction:column;align-items:center;gap:0}
    .hlevel{display:flex;gap:16px;justify-content:center;flex-wrap:wrap}
    .hnode{background:#fff;border-radius:10px;padding:10px 14px;text-align:center;
           min-width:110px;box-shadow:0 1px 6px rgba(0,0,0,.1);position:relative;
           border-top:3px solid var(--verde)}
    .hnode .he{font-size:20px}
    .hnode .hn{font-size:11px;font-weight:700;margin-top:3px}
    .hnode .hr{font-size:10px;color:#888;margin-top:1px}
    .hconnector{width:1px;height:20px;background:#ccc;margin:0 auto}
    .hrow{display:flex;gap:2px;align-items:flex-start;justify-content:center}
  `;

  const node = (a) => `
    <div class="hnode" style="border-top-color:${a.color}" onclick="openAgent('${a.id}');event.stopPropagation()">
      <div class="he">${a.emoji}</div>
      <div class="hn">${a.nombre}</div>
      <div class="hr">${a.rol.split(' ').slice(0,3).join(' ')}</div>
    </div>`;

  const html = `
    <style>${CSS}</style>
    <div class="htree">
      <div class="hlevel">${node(AGENTS.find(a=>a.id==='maximo'))}</div>
      <div class="hconnector"></div>
      <div class="hlevel">
        ${['aurora','renata','bruno','ezequiel','daniela','sebastian'].map(id=>node(AGENTS.find(a=>a.id===id))).join('')}
      </div>
      <div style="display:flex;gap:80px;justify-content:center;margin:0">
        <div style="display:flex;flex-direction:column;align-items:center">
          <div class="hconnector"></div>
          ${node(AGENTS.find(a=>a.id==='tomas'))}
          <div class="hconnector"></div>
          <div class="hlevel">
            ${['valentina','camila','mateo','nicolas','luciano'].map(id=>node(AGENTS.find(a=>a.id===id))).join('')}
          </div>
        </div>
        <div style="display:flex;flex-direction:column;align-items:center">
          <div class="hconnector"></div>
          ${node(AGENTS.find(a=>a.id==='ezequiel'))}
          <div class="hconnector"></div>
          <div class="hlevel">
            ${['ignacio','elena'].map(id=>node(AGENTS.find(a=>a.id===id))).join('')}
          </div>
        </div>
      </div>
    </div>`;
  document.getElementById('hierarchy-tree').innerHTML = html;
}

// ── CONFIG ────────────────────────────────────────────
function loadConfig() {
  const fieldMap = {
    'GEMINI_API_KEY': 'cfg-gemini',
    'CRM_BASE_URL': 'cfg-crm-url',
    'CRM_API_KEY': 'cfg-crm-key',
    'TELEGRAM_BOT_TOKEN': 'cfg-tg-token',
    'TELEGRAM_CHAT_ID_RODRIGO': 'cfg-tg-id',
    'WA_TOKEN': 'cfg-wa-token',
    'WA_PHONE_ID': 'cfg-wa-phone',
    'WA_VERIFY_TOKEN': 'cfg-wa-verify',
    'CLOUDFLARE_WORKER_URL': 'cfg-cf-url',
    'GOOGLE_DRIVE_FOLDER_ID': 'cfg-drive',
    'BASE_URL': 'cfg-base-url',
    'PORT': 'cfg-port',
  };
  const dots = {'GEMINI_API_KEY':'dot-gemini','CRM_BASE_URL':'dot-crm',
                 'TELEGRAM_BOT_TOKEN':'dot-tg','WA_TOKEN':'dot-wa',
                 'CLOUDFLARE_WORKER_URL':'dot-cf'};
  for (const [k, elemId] of Object.entries(fieldMap)) {
    const el = document.getElementById(elemId);
    if (el && ENV[k]) el.value = ENV[k];
  }
  for (const [k, dotId] of Object.entries(dots)) {
    const dot = document.getElementById(dotId);
    if (dot) dot.innerHTML = ENV[k]
      ? '<span style="color:#43a047;font-size:10px">●</span>'
      : '<span style="color:#e53935;font-size:10px">●</span>';
  }
  // Webhook URL
  const base = ENV['BASE_URL'] || window.location.origin;
  document.getElementById('webhook-url').textContent = base + '/webhook/whatsapp';
  document.getElementById('webhook-token').textContent = ENV['WA_VERIFY_TOKEN'] || 'eco_modules_verify_2026';
  // Snippet
  const snippet = `<!-- EcoFiver — Widget Chat -->
<script>
  window.ECO_CHAT_URL = '${base}/chat/web';
  window.ECO_WIDGET_BASE = '${base}';
<\/script>
<script src="${base}/web_widget/chat.js" defer><\/script>`;
  document.getElementById('snippet-box').textContent = snippet;
}

async function saveConfig() {
  const fields = ['GEMINI_API_KEY','CRM_BASE_URL','CRM_API_KEY',
    'TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID_RODRIGO','WA_TOKEN','WA_PHONE_ID',
    'WA_VERIFY_TOKEN','CLOUDFLARE_WORKER_URL','GOOGLE_DRIVE_FOLDER_ID','BASE_URL','PORT','ADMIN_PASSWORD'];
  const fieldMap = {
    'GEMINI_API_KEY':'cfg-gemini','CRM_BASE_URL':'cfg-crm-url','CRM_API_KEY':'cfg-crm-key',
    'TELEGRAM_BOT_TOKEN':'cfg-tg-token','TELEGRAM_CHAT_ID_RODRIGO':'cfg-tg-id',
    'WA_TOKEN':'cfg-wa-token','WA_PHONE_ID':'cfg-wa-phone','WA_VERIFY_TOKEN':'cfg-wa-verify',
    'CLOUDFLARE_WORKER_URL':'cfg-cf-url','GOOGLE_DRIVE_FOLDER_ID':'cfg-drive',
    'BASE_URL':'cfg-base-url','PORT':'cfg-port','ADMIN_PASSWORD':'cfg-admin-pw',
  };
  const data = {password: sessionStorage.getItem('eco_admin_pw') || ''};
  for (const k of fields) {
    const el = document.getElementById(fieldMap[k]);
    if (el && el.value.trim()) data[k] = el.value.trim();
  }
  const msg = document.getElementById('save-msg');
  msg.textContent = 'Guardando...';
  try {
    const r = await fetch('/dashboard/save-config', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(data)
    });
    const d = await r.json();
    msg.textContent = d.ok ? '✅ Guardado correctamente' : '❌ ' + d.message;
    if (d.ok) showToast('✅ Configuración guardada');
  } catch(e) { msg.textContent = '❌ Error: ' + e.message; }
}

async function testIntegration(service) {
  const fieldMap = {
    'GEMINI_API_KEY':'cfg-gemini','CRM_BASE_URL':'cfg-crm-url','CRM_API_KEY':'cfg-crm-key',
    'TELEGRAM_BOT_TOKEN':'cfg-tg-token','WA_TOKEN':'cfg-wa-token',
    'CLOUDFLARE_WORKER_URL':'cfg-cf-url',
  };
  const payload = {password: sessionStorage.getItem('eco_admin_pw') || ''};
  for (const [k, eid] of Object.entries(fieldMap)) {
    const el = document.getElementById(eid);
    if (el) payload[k] = el.value;
  }
  const resultEl = document.getElementById('tr-' + service);
  resultEl.style.display = 'none';
  try {
    const r = await fetch('/dashboard/test/' + service, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    resultEl.textContent = (d.ok ? '✅ ' : '❌ ') + d.message;
    resultEl.className = 'test-result ' + (d.ok ? 'ok' : 'err');
    resultEl.style.display = 'block';
  } catch(e) {
    resultEl.textContent = '❌ Error: ' + e.message;
    resultEl.className = 'test-result err';
    resultEl.style.display = 'block';
  }
}

// ── CATÁLOGO ─────────────────────────────────────────
function buildCatalogo() {
  // Piscinas
  let rows = `<thead><tr><th>#</th><th>Modelo</th><th>Medida</th><th>Precio ($)</th></tr></thead><tbody>`;
  CATALOGO.piscinas.forEach((p,i) => {
    rows += `<tr>
      <td>${p.id}</td>
      <td><input value="${p.modelo}" data-field="modelo" data-idx="${i}"></td>
      <td><input value="${p.medida}" data-field="medida" data-idx="${i}"></td>
      <td><input type="number" value="${p.precio}" data-field="precio" data-idx="${i}" style="max-width:140px"></td>
    </tr>`;
  });
  rows += '</tbody>';
  document.getElementById('tabla-piscinas').innerHTML = rows;

  // Actualizar labels del calculador de flete con tarifas del catálogo
  const optG = document.getElementById('opt-flete-general');
  const optM = document.getElementById('opt-flete-mini');
  if (optG) optG.textContent = `General ($${CATALOGO.flete_por_km.toLocaleString('es-AR')}/km)`;
  if (optM) optM.textContent = `Miniportante ($${CATALOGO.flete_miniportante_por_km.toLocaleString('es-AR')}/km)`;

  // Módulos
  document.getElementById('modulos-config').innerHTML = `
    <div class="field-row">
      <div class="field">
        <label>Superficies disponibles (m²)</label>
        <input type="text" id="mod-m2" value="${CATALOGO.modulos_m2.join(', ')}">
        <div class="hint">Separados por coma</div>
      </div>
      <div class="field">
        <label>Flete por km (general)</label>
        <input type="number" id="flete-km" value="${CATALOGO.flete_por_km}">
      </div>
    </div>
    <div class="field-row">
      <div class="field">
        <label>Flete Miniportante por km</label>
        <input type="number" id="flete-km-mini" value="${CATALOGO.flete_miniportante_por_km}">
      </div>
      <div class="field">
        <label>Descuento combo módulo+piscina (%)</label>
        <input type="number" id="combo-desc" value="${CATALOGO.combo_descuento_pct}">
      </div>
    </div>`;

  // Planes — solo muestra las cuotas disponibles (los factores de ingreso son fijos por tipo)
  const factorInfo = `
    <div style="background:#f0f7f3;border-radius:8px;padding:10px 14px;font-size:12px;color:#555;margin-bottom:12px;line-height:1.7">
      <b>Factores de ingreso (fijos):</b><br>
      Módulos: ingreso = 2 × cuota mensual del plan<br>
      Piscinas: ingreso = 1,5 × cuota mensual del plan
    </div>`;
  let planes = factorInfo + '<div class="field-row">';
  let i = 0;
  const planKeys = Object.keys(CATALOGO.planes_financiacion);
  for (const key of planKeys) {
    planes += `<div class="field">
      <label>Plan ${key} cuotas</label>
      <input type="number" id="plan-${key}" value="${CATALOGO.planes_financiacion[key].cuotas}" readonly style="background:#f8f8f8;color:#888">
    </div>`;
    i++;
    if (i % 2 === 0 && i < planKeys.length) planes += '</div><div class="field-row">';
  }
  planes += '</div>';
  document.getElementById('planes-config').innerHTML = planes;
}

async function saveCatalogo() {
  // Leer tabla piscinas
  const piscinas = [...document.querySelectorAll('#tabla-piscinas tbody tr')].map((tr, idx) => ({
    id: idx + 1,
    modelo: tr.querySelector('[data-field=modelo]').value,
    medida:  tr.querySelector('[data-field=medida]').value,
    precio:  parseFloat(tr.querySelector('[data-field=precio]').value),
  }));
  const modulos_m2 = document.getElementById('mod-m2').value.split(',').map(x => parseInt(x.trim())).filter(Boolean);
  const planes = {};
  for (const key of Object.keys(CATALOGO.planes_financiacion)) {
    planes[key] = { cuotas: parseInt(key) };
  }
  const payload = {
    password: sessionStorage.getItem('eco_admin_pw') || '',
    piscinas, modulos_m2,
    flete_por_km: parseInt(document.getElementById('flete-km').value),
    flete_miniportante_por_km: parseInt(document.getElementById('flete-km-mini').value),
    combo_descuento_pct: parseInt(document.getElementById('combo-desc').value),
    planes_financiacion: planes,
  };
  const msg = document.getElementById('cat-msg');
  msg.textContent = 'Guardando...';
  try {
    const r = await fetch('/dashboard/save-catalogo', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    msg.textContent = d.ok ? '✅ Catálogo guardado' : '❌ ' + d.message;
    if (d.ok) showToast('✅ Catálogo actualizado');
  } catch(e) { msg.textContent = '❌ ' + e.message; }
}

// ── SIMULADOR CUOTAS ─────────────────────────────────
function simularCuotas() {
  const precio = parseFloat(document.getElementById('sim-precio').value) || 0;
  const sel    = [...document.getElementById('sim-planes').selectedOptions].map(o => o.value);
  const tipo   = document.getElementById('sim-tipo').value;
  if (!precio || sel.length === 0) { showToast('Ingresá precio y seleccioná al menos un plan'); return; }
  const factor = tipo === 'modulo' ? 2.0 : 1.5;
  let lines = [`💰 Opciones de financiación para $${precio.toLocaleString('es-AR')}:\n`];
  for (const key of sel) {
    const plan = CATALOGO.planes_financiacion[key];
    if (!plan) continue;
    const n      = plan.cuotas;
    const ingreso = Math.round(factor * precio / (n + factor));
    const cuota   = Math.round(precio / (n + factor));
    lines.push(`  • ${n} cuotas:  Ingreso $${ingreso.toLocaleString('es-AR')} + $${cuota.toLocaleString('es-AR')}/mes`);
  }
  lines.push('\n📋 Financiación directa — sin banco, sin scoring externo.');
  lines.push('✅ Precio final cerrado. Sin sorpresas.');
  const el = document.getElementById('sim-result');
  el.textContent = lines.join('\n');
  el.style.display = 'block';
}

// ── CALCULADOR FLETE ─────────────────────────────────
async function calcFlete() {
  const loc = document.getElementById('flete-loc').value.trim();
  const tipo = document.getElementById('flete-tipo').value;
  if (!loc) { showToast('Ingresá una localidad'); return; }
  const r = await fetch(`/dashboard/flete?localidad=${encodeURIComponent(loc)}&producto=${tipo}`);
  const d = await r.json();
  const el = document.getElementById('flete-result');
  if (d.monto_aproximado) {
    el.innerHTML = `<b>${d.texto_formateado}</b>`;
  } else {
    el.innerHTML = `<span style="color:#888">${d.nota}</span>`;
  }
  el.style.display = 'block';
}

// ── WEBHOOK / SNIPPET ─────────────────────────────────
function copyWebhook() {
  const text = document.getElementById('webhook-url').textContent;
  navigator.clipboard.writeText(text).then(() => showToast('URL copiada al portapapeles'));
}
function copySnippet() {
  const text = document.getElementById('snippet-box').textContent;
  navigator.clipboard.writeText(text).then(() => showToast('Snippet copiado'));
}

// ── TOAST ────────────────────────────────────────────
function showToast(msg, duration=2500) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), duration);
}

// ── KPIs EN VIVO ─────────────────────────────────────
const DASH_PW = sessionStorage.getItem('eco_admin_pw') || '';
const fmtMonto = n => '$' + (Number(n)||0).toLocaleString('es-AR');

async function loadKpis() {
  try {
    const r = await fetch('/dashboard/api/kpis', { headers:{'X-Dashboard-Password':DASH_PW} });
    if (!r.ok) return;
    const d = await r.json();

    document.getElementById('kpi-ts').textContent = '· actualizado ' + (d.ts||'');
    document.getElementById('kpi-leads-hoy').textContent   = d.hoy.leads_nuevos ?? 0;
    document.getElementById('kpi-cierres-hoy').textContent = d.hoy.cierres ?? 0;
    document.getElementById('kpi-monto-hoy').textContent   = fmtMonto(d.hoy.monto_total);
    document.getElementById('kpi-sin-resp').textContent    = d.leads.sin_respuesta ?? 0;
    document.getElementById('kpi-total-leads').textContent = d.leads.total ?? 0;
    document.getElementById('kpi-calientes').textContent   = d.leads.calientes ?? 0;
    document.getElementById('kpi-videollamadas').textContent = d.agenda.videollamadas_proximas ?? 0;
    document.getElementById('kpi-cuotas-venc').textContent = d.cobranzas.cuotas_vencidas ?? 0;
    document.getElementById('kpi-monto-venc').textContent  = 'Monto: ' + fmtMonto(d.cobranzas.monto_vencido);

    renderBars('funnel-estados', d.leads.funnel, true);

    // Agenda
    const ag = document.getElementById('agenda-list');
    if (d.agenda.detalle && d.agenda.detalle.length) {
      ag.innerHTML = d.agenda.detalle.map(v =>
        `<div class="sched-row"><span class="sched-time">${(v.fecha||'').replace('T',' ').slice(0,16)}</span>
         <span class="sched-name">${escHtmlD(v.lead)}</span>
         <span class="sched-badge">${escHtmlD(v.tipo)}</span></div>`).join('');
    } else {
      ag.innerHTML = '<div class="empty">No hay videollamadas agendadas en las próximas 48hs.</div>';
    }

    renderCanales(d.canales);
  } catch(e) { /* CRM puede estar caído; no romper */ }
}

function escHtmlD(t){return String(t==null?'':t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function renderBars(elId, obj, keepOrder) {
  const el = document.getElementById(elId);
  if (!el) return;
  let entries = Object.entries(obj||{});
  if (!keepOrder) entries = entries.sort((a,b)=>b[1]-a[1]);
  if (!entries.length) { el.innerHTML = '<div class="empty">Sin datos.</div>'; return; }
  const max = Math.max(...entries.map(e=>e[1]), 1);
  el.innerHTML = entries.map(([k,v]) =>
    `<div class="bar-row">
       <span class="bar-label" style="text-transform:none">${escHtmlD(k)}</span>
       <span class="bar-track"><span class="bar-fill" style="width:${Math.max(2,Math.round(v/max*100))}%"></span></span>
       <span class="bar-val">${v}</span>
     </div>`).join('');
}

function renderCanales(canales) {
  const el = document.getElementById('canales-grid');
  if (!el) return;
  const meta = {
    whatsapp:{n:'WhatsApp',e:'💬'}, telegram:{n:'Telegram',e:'📱'},
    instagram:{n:'Instagram',e:'📸'}, facebook_posts:{n:'Facebook',e:'👍'},
    email:{n:'Email',e:'📧'}, scraping:{n:'Scraping web',e:'🔍'},
  };
  el.innerHTML = Object.entries(canales||{}).map(([k,on]) => {
    const m = meta[k] || {n:k,e:'•'};
    return `<div class="canal-item">
      <span class="canal-dot ${on?'canal-on':'canal-off'}"></span>
      <div><div class="canal-name">${m.e} ${m.n}</div>
      <div class="canal-state" style="color:${on?'#43a047':'#999'}">${on?'Activo':'Inactivo'}</div></div>
    </div>`;
  }).join('');
}

// ── LEADS QUE REQUIEREN ACCIÓN ───────────────────────
async function cargarLeadsAccion() {
  const cont = document.getElementById('leads-accion');
  if (!cont) return;
  cont.innerHTML = '<div class="empty">Cargando…</div>';
  try {
    const r = await fetch('/dashboard/api/leads-accion', { headers:{'X-Dashboard-Password':DASH_PW} });
    const d = await r.json();
    const leads = d.sin_respuesta || [];
    if (!leads.length) { cont.innerHTML = '<div class="empty">✅ No hay leads sin responder. Todo al día.</div>'; return; }
    let html = `<div style="font-size:12px;color:#888;margin-bottom:8px">${d.total_sin_respuesta} sin responder · ${d.videollamadas_proximas} videollamadas próximas</div>`;
    html += '<table class="tabla"><thead><tr><th>Lead</th><th>Producto</th><th>Canal</th><th>Atiende</th><th>Espera</th></tr></thead><tbody>';
    for (const l of leads) {
      html += `<tr>
        <td><b>${escHtmlD(l.nombre)}</b>${l.telefono?`<br><span style="font-size:11px;color:#888">${escHtmlD(l.telefono)}</span>`:''}</td>
        <td>${escHtmlD(l.producto||'-')}</td>
        <td>${escHtmlD(l.canal||'-')}</td>
        <td>${escHtmlD(l.agente||'-')}</td>
        <td style="color:#c62828;font-weight:700">${escHtmlD(String(l.horas||'?'))}h</td>
      </tr>`;
    }
    html += '</tbody></table>';
    html += '<button class="btn btn-primary" style="margin-top:12px" onclick="ejecutarComando(\'leads_nuevos\', this)">👋 Contactar a todos ahora</button>';
    cont.innerHTML = html;
  } catch(e) { cont.innerHTML = `<div class="empty">Error: ${e.message}</div>`; }
}

// ── COMANDOS DEL SISTEMA ─────────────────────────────
async function ejecutarComando(accion, btn) {
  const res = document.getElementById('res-' + accion);
  const orig = btn.textContent;
  btn.disabled = true; btn.textContent = 'Ejecutando…';
  res.className = 'cmd-result run'; res.textContent = '⏳ Procesando, puede tardar unos segundos…';
  try {
    const r = await fetch('/dashboard/api/comando/' + accion, {
      method:'POST', headers:{'X-Dashboard-Password':DASH_PW}
    });
    const d = await r.json();
    if (d.ok) {
      res.className = 'cmd-result ok';
      res.textContent = '✅ ' + resumenComando(accion, d);
    } else {
      res.className = 'cmd-result err';
      res.textContent = '❌ ' + (d.error || 'Error desconocido');
    }
  } catch(e) {
    res.className = 'cmd-result err'; res.textContent = '❌ ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = orig;
  }
}

function resumenComando(accion, d) {
  if (accion === 'scraping' && d.resumen)
    return `Encontrados: ${d.resumen.encontrados||0} · Nuevos: ${d.resumen.nuevos||0} · Contactados: ${d.resumen.contactados||0}`;
  if (accion === 'contenido')
    return `Post (${d.tipo||'?'}/${d.foco||'?'}) — FB: ${d.facebook?'✓':'✗'} · IG: ${d.instagram?'✓':'✗'}\n${d.preview||''}`;
  if (accion === 'emails')
    return `Emails procesados: ${d.procesados||0}`;
  if (accion === 'leads_nuevos')
    return 'Leads nuevos contactados.';
  if (accion === 'reactivar_frios')
    return d.detalle || 'Leads fríos reactivados.';
  return 'Listo.';
}

// ── ECOPOST STUDIO ───────────────────────────────────
let ecoMediaB64 = null;    // base64 sin prefijo del archivo actual, o null
let ecoMediaKind = 'image'; // 'image' | 'video'

function ecoShowMedia(b64, kind, mime) {
  ecoMediaB64 = b64; ecoMediaKind = kind;
  const img = document.getElementById('eco-img');
  const vid = document.getElementById('eco-video');
  const wrap = document.getElementById('eco-img-wrap');
  if (!b64) { wrap.style.display = 'none'; img.style.display='none'; vid.style.display='none'; return; }
  wrap.style.display = 'block';
  const dataUrl = 'data:' + (mime || (kind==='video'?'video/mp4':'image/png')) + ';base64,' + b64;
  if (kind === 'video') {
    vid.src = dataUrl; vid.style.display = 'inline-block'; img.style.display = 'none';
  } else {
    img.src = dataUrl; img.style.display = 'inline-block'; vid.style.display = 'none';
  }
}

function ecoAbrirPreview() {
  document.getElementById('eco-preview-empty').style.display = 'none';
  document.getElementById('eco-preview').style.display = 'block';
}

function ecoEmpezarManual() {
  ecoAbrirPreview();
  document.getElementById('eco-caption').value = '';
  ecoShowMedia(null);
  const m = document.getElementById('eco-img-msg');
  m.style.color = '#666';
  m.textContent = '✍️ Modo manual: escribí tu texto y subí tu foto o video abajo.';
  document.getElementById('eco-pub-result').className = 'cmd-result';
  document.getElementById('eco-pub-result').textContent = '';
}

async function ecoGenerar(btn) {
  const producto = document.getElementById('eco-producto').value;
  const tipo     = document.getElementById('eco-tipo').value;
  const tono     = document.getElementById('eco-tono').value;
  const desc     = document.getElementById('eco-desc').value.trim();
  const conImg   = document.getElementById('eco-con-imagen').checked;
  const orig = btn.textContent;
  btn.disabled = true; btn.textContent = '⏳ Generando…';
  try {
    const r = await fetch('/dashboard/api/ecopost/generar', {
      method:'POST', headers:{'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
      body: JSON.stringify({producto, tipo, tono, descripcion:desc, con_imagen:conImg})
    });
    const d = await r.json();
    if (!d.ok) { showToast('❌ ' + (d.error||'Error')); return; }

    ecoAbrirPreview();
    document.getElementById('eco-caption').value = d.caption || d.copy || '';

    const imgMsg = document.getElementById('eco-img-msg');
    if (d.image_base64) {
      ecoShowMedia(d.image_base64, 'image', 'image/png');
      imgMsg.textContent = '';
    } else {
      ecoShowMedia(null);
      imgMsg.style.color = '#e65100';
      imgMsg.textContent = d.image_error
        ? ('🖼️ ' + d.image_error + ' Podés subir tu propia foto o video abajo.')
        : (conImg ? '🖼️ No se pudo generar imagen. Subí tu propia foto o video abajo.' : '');
    }
    document.getElementById('eco-pub-result').className = 'cmd-result';
    document.getElementById('eco-pub-result').textContent = '';
  } catch(e) {
    showToast('❌ ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = orig;
  }
}

function ecoSubirFoto(ev) {
  const file = ev.target.files[0];
  if (!file) return;
  const esVideo = file.type.startsWith('video');
  if (file.size > 60 * 1024 * 1024) { showToast('El archivo supera 60MB, probá uno más liviano'); return; }
  const reader = new FileReader();
  reader.onload = () => {
    const b64 = reader.result.split(',')[1];
    ecoAbrirPreview();
    ecoShowMedia(b64, esVideo ? 'video' : 'image', file.type);
    const m = document.getElementById('eco-img-msg');
    m.textContent = esVideo ? '✅ Video cargado.' : '✅ Foto cargada.';
    m.style.color = '#2e7d32';
  };
  reader.readAsDataURL(file);
}

function ecoDescargar() {
  if (!ecoMediaB64) { showToast('No hay archivo para descargar'); return; }
  const ext = ecoMediaKind === 'video' ? 'mp4' : 'png';
  const mime = ecoMediaKind === 'video' ? 'video/mp4' : 'image/png';
  const a = document.createElement('a');
  a.href = 'data:' + mime + ';base64,' + ecoMediaB64;
  a.download = 'ecopost.' + ext;
  a.click();
}

async function ecoPublicar(canal, btn) {
  const caption = document.getElementById('eco-caption').value.trim();
  const res = document.getElementById('eco-pub-result');
  if (canal !== 'facebook' && !ecoMediaB64) {
    res.className = 'cmd-result err'; res.textContent = '❌ Instagram necesita una foto o video. Generá o subí uno.';
    return;
  }
  if (!caption && !ecoMediaB64) {
    res.className = 'cmd-result err'; res.textContent = '❌ Escribí un texto o subí un archivo antes de publicar.';
    return;
  }
  const orig = btn.textContent;
  btn.disabled = true; btn.textContent = '⏳…';
  res.className = 'cmd-result run'; res.textContent = '⏳ Publicando' + (ecoMediaKind==='video'?' (el video puede tardar)…':'…');
  try {
    const r = await fetch('/dashboard/api/ecopost/publicar', {
      method:'POST', headers:{'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
      body: JSON.stringify({canal, caption, media_base64: ecoMediaB64, media_kind: ecoMediaKind})
    });
    const d = await r.json();
    const rr = d.resultados || {};
    let parts = [];
    if ('facebook' in rr)  parts.push('Facebook: ' + (rr.facebook ? '✓ publicado' : '✗ error'));
    if ('instagram' in rr) parts.push('Instagram: ' + (rr.instagram ? '✓ publicado' : ('✗ ' + (rr.instagram_error||'error'))));
    res.className = 'cmd-result ' + (d.ok ? 'ok' : 'err');
    res.textContent = (d.ok ? '✅ ' : '❌ ') + (parts.join(' · ') || (d.error||'Sin resultado'));
  } catch(e) {
    res.className = 'cmd-result err'; res.textContent = '❌ ' + e.message;
  } finally {
    btn.disabled = false; btn.textContent = orig;
  }
}

// ── MERCADOLIBRE ─────────────────────────────────────
const ML_CALLBACK = window.location.origin + '/dashboard/ml/callback';

async function mlCargarEstado() {
  const cont = document.getElementById('ml-conexion');
  const badge = document.getElementById('ml-status-badge');
  cont.innerHTML = '<div class="empty">Cargando estado…</div>';
  try {
    const r = await fetch('/dashboard/api/ml/estado', { headers:{'X-Dashboard-Password':DASH_PW} });
    const d = await r.json();

    if (d.conectado) {
      badge.textContent = '✅ Conectado'; badge.style.background='#e8f5e9'; badge.style.color='#2e7d32';
      const cta = d.cuenta || {};
      cont.innerHTML = `<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
        <div style="font-size:14px"><b>Cuenta:</b> ${escHtmlD(cta.nickname||'—')} ·
        <b>Ventas históricas:</b> ${cta.ventas_total||0} · <b>Reputación:</b> ${escHtmlD(cta.reputacion||'—')}</div>
        <a href="${d.auth_url||'#'}" class="btn btn-outline" style="margin-left:auto;font-size:12px;text-decoration:none">🔄 Reconectar</a>
      </div>`;
      document.getElementById('ml-metricas-wrap').style.display = 'block';
      document.getElementById('ml-gestion-wrap').style.display = 'block';
      const m = d.metricas || {};
      document.getElementById('ml-activas').textContent  = m.activas ?? 0;
      document.getElementById('ml-pausadas').textContent = m.pausadas ?? 0;
      document.getElementById('ml-ventas').textContent   = m.ventas_pagadas ?? 0;
      document.getElementById('ml-monto').textContent    = fmtMonto(m.monto_ventas||0);
      document.getElementById('ml-preguntas').textContent= m.preguntas_sin_responder ?? 0;
      mlCargarPublicaciones();
      return;
    }

    document.getElementById('ml-metricas-wrap').style.display = 'none';
    document.getElementById('ml-gestion-wrap').style.display = 'none';

    if (d.configurado) {
      badge.textContent = '🔌 Falta conectar'; badge.style.background='#fff8e1'; badge.style.color='#f57f17';
      cont.innerHTML = `<p style="font-size:14px;color:#444;margin-bottom:14px">
        Las credenciales están cargadas. Ahora autorizá el acceso a tu cuenta de MercadoLibre:</p>
        <a href="${d.auth_url}" class="btn btn-primary" style="text-decoration:none;font-size:15px;padding:12px 28px">🔗 Conectar mi cuenta de MercadoLibre</a>
        <p style="font-size:12px;color:#999;margin-top:12px">Se abre MercadoLibre, das permiso y volvés acá automáticamente.</p>
        <div class="sep"></div>${mlFormConfig(d)}`;
    } else {
      badge.textContent = '⚙️ Sin configurar'; badge.style.background='#ffebee'; badge.style.color='#c62828';
      cont.innerHTML = `<p style="font-size:14px;color:#444;margin-bottom:8px">
        Para operar en MercadoLibre necesitás crear una aplicación (gratis) en
        <a href="https://developers.mercadolibre.com.ar/devcenter" target="_blank" style="color:#1A5C38">developers.mercadolibre.com.ar</a>
        y pegar acá tus credenciales.</p>
        <div style="background:#f0f7f3;border-radius:8px;padding:12px;font-size:13px;color:#555;margin-bottom:16px;line-height:1.7">
        <b>Importante:</b> en tu app de MercadoLibre, configurá esta <b>Redirect URI</b> exactamente:<br>
        <code style="background:#fff;padding:3px 8px;border-radius:4px;display:inline-block;margin-top:4px">${ML_CALLBACK}</code></div>
        ${mlFormConfig(d)}`;
    }
  } catch(e) {
    cont.innerHTML = `<div class="empty">Error: ${e.message}</div>`;
  }
}

function mlFormConfig(d) {
  return `<div class="field-row">
      <div class="field"><label>App ID (client_id)</label><input id="ml-cfg-appid" value="${escHtmlD(d.app_id||'')}" placeholder="1234567890123456"></div>
      <div class="field"><label>Secret Key (client_secret)</label><input id="ml-cfg-secret" type="password" placeholder="••••••••••••"></div>
    </div>
    <div class="field"><label>Redirect URI</label><input id="ml-cfg-redirect" value="${escHtmlD(d.redirect_uri||ML_CALLBACK)}"></div>
    <button class="btn btn-primary" onclick="mlGuardarConfig(this)">💾 Guardar credenciales</button>
    <span id="ml-cfg-msg" style="font-size:13px;color:#666;margin-left:10px"></span>`;
}

async function mlGuardarConfig(btn) {
  const msg = document.getElementById('ml-cfg-msg');
  msg.textContent = 'Guardando…';
  const body = { password: DASH_PW,
    ML_APP_ID: document.getElementById('ml-cfg-appid').value.trim(),
    ML_REDIRECT_URI: document.getElementById('ml-cfg-redirect').value.trim() };
  const sec = document.getElementById('ml-cfg-secret').value.trim();
  if (sec) body.ML_SECRET = sec;
  try {
    const r = await fetch('/dashboard/api/ml/config', {
      method:'POST', headers:{'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
      body: JSON.stringify(body)
    });
    const d = await r.json();
    msg.textContent = d.ok ? '✅ Guardado' : ('❌ ' + (d.error||''));
    if (d.ok) setTimeout(mlCargarEstado, 800);
  } catch(e) { msg.textContent = '❌ ' + e.message; }
}

async function mlCargarPublicaciones() {
  const cont = document.getElementById('ml-lista');
  const estado = document.getElementById('ml-filtro-estado').value;
  cont.innerHTML = '<div class="empty">Cargando publicaciones…</div>';
  try {
    const r = await fetch('/dashboard/api/ml/publicaciones?status=' + estado, { headers:{'X-Dashboard-Password':DASH_PW} });
    const d = await r.json();
    const items = d.items || [];
    if (!items.length) { cont.innerHTML = '<div class="empty">No hay publicaciones ' + (estado==='active'?'activas':'pausadas') + '.</div>'; return; }
    let html = '<table class="tabla"><thead><tr><th></th><th>Título</th><th>Precio</th><th>Stock</th><th>Vendidos</th><th>Acciones</th></tr></thead><tbody>';
    for (const it of items) {
      html += `<tr>
        <td>${it.thumbnail?`<img src="${it.thumbnail}" style="width:40px;height:40px;object-fit:cover;border-radius:6px">`:''}</td>
        <td><a href="${it.permalink}" target="_blank" style="color:#1A5C38">${escHtmlD((it.titulo||'').slice(0,50))}</a></td>
        <td><input type="number" value="${it.precio||0}" style="width:110px" id="mlp-${it.id}"></td>
        <td><input type="number" value="${it.stock||0}" style="width:70px" id="mls-${it.id}"></td>
        <td>${it.vendidos||0}</td>
        <td style="white-space:nowrap">
          <button class="btn btn-ghost" style="font-size:11px;padding:5px 9px" onclick="mlGuardarItem('${it.id}',this)">💾</button>
          ${estado==='active'
            ? `<button class="btn btn-ghost" style="font-size:11px;padding:5px 9px" onclick="mlEstado('${it.id}','paused',this)">⏸ Pausar</button>`
            : `<button class="btn btn-ghost" style="font-size:11px;padding:5px 9px" onclick="mlEstado('${it.id}','active',this)">▶ Activar</button>`}
        </td></tr>`;
    }
    html += '</tbody></table>';
    cont.innerHTML = html;
  } catch(e) { cont.innerHTML = `<div class="empty">Error: ${e.message}</div>`; }
}

async function mlGuardarItem(id, btn) {
  const price = document.getElementById('mlp-'+id).value;
  const stock = document.getElementById('mls-'+id).value;
  btn.disabled = true; const o = btn.textContent; btn.textContent = '…';
  try {
    const r = await fetch('/dashboard/api/ml/item/'+id+'/actualizar', {
      method:'POST', headers:{'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
      body: JSON.stringify({price, stock})
    });
    const d = await r.json();
    showToast(d.ok ? '✅ Actualizado' : '❌ ' + (d.res?.message||'error'));
  } catch(e) { showToast('❌ ' + e.message); }
  finally { btn.disabled=false; btn.textContent=o; }
}

async function mlEstado(id, estado, btn) {
  btn.disabled = true; const o = btn.textContent; btn.textContent = '…';
  try {
    const r = await fetch('/dashboard/api/ml/item/'+id+'/estado', {
      method:'POST', headers:{'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
      body: JSON.stringify({estado})
    });
    const d = await r.json();
    if (d.ok) { showToast('✅ Listo'); mlCargarPublicaciones(); }
    else { showToast('❌ ' + (d.res?.message||'error')); btn.disabled=false; btn.textContent=o; }
  } catch(e) { showToast('❌ ' + e.message); btn.disabled=false; btn.textContent=o; }
}

async function mlCrear(btn) {
  const res = document.getElementById('ml-crear-result');
  const body = {
    title: document.getElementById('ml-new-title').value.trim(),
    price: parseFloat(document.getElementById('ml-new-price').value||'0'),
    available_quantity: parseInt(document.getElementById('ml-new-stock').value||'1'),
    listing_type_id: document.getElementById('ml-new-listing').value,
    pictures: document.getElementById('ml-new-pics').value.split('\n').map(s=>s.trim()).filter(Boolean),
    description: document.getElementById('ml-new-desc').value.trim(),
    category_id: document.getElementById('ml-new-cat').value.trim(),
  };
  if (!body.title || !body.price) { res.className='cmd-result err'; res.textContent='❌ Completá título y precio'; return; }
  btn.disabled = true; const o = btn.textContent; btn.textContent = '⏳ Publicando…';
  res.className='cmd-result run'; res.textContent='⏳ Creando publicación…';
  try {
    const r = await fetch('/dashboard/api/ml/crear', {
      method:'POST', headers:{'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
      body: JSON.stringify(body)
    });
    const d = await r.json();
    if (d.ok) { res.className='cmd-result ok'; res.textContent='✅ Publicado: ' + (d.res.permalink||d.res.id); mlCargarPublicaciones(); }
    else { res.className='cmd-result err'; res.textContent='❌ ' + (d.res?.message || JSON.stringify(d.res).slice(0,200)); }
  } catch(e) { res.className='cmd-result err'; res.textContent='❌ ' + e.message; }
  finally { btn.disabled=false; btn.textContent=o; }
}

// ── GALERÍA DE ACTIVOS ────────────────────────────────
const GAL_ETIQ_TODAS = ['modulos','piscinas','combo','contado','financiado','familia','obra','instalacion','exterior','interior','verano','invierno','historia','general'];
const GAL_ETIQ_LABELS = {
  modulos:'Módulos', piscinas:'Piscinas', combo:'Combo', contado:'Contado',
  financiado:'Financiado', familia:'Familia', obra:'Obra', instalacion:'Instalación',
  exterior:'Exterior', interior:'Interior', verano:'Verano', invierno:'Invierno',
  historia:'Historia', general:'General'
};
let galPendingFiles = [];   // FileList pendiente de subir
let galIaB64 = null;        // base64 de imagen IA generada (sin prefijo)
let galIaMime = 'image/png';
let galFiltroActivo = null; // etiqueta actualmente filtrada

function _galEtiqSelector(containerId, seleccionadas = []) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = GAL_ETIQ_TODAS.map(t =>
    `<label style="display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:500;background:${seleccionadas.includes(t)?'#1A5C38':'#eef'};color:${seleccionadas.includes(t)?'#fff':'#333'};border-radius:20px;padding:3px 10px;cursor:pointer;transition:all .15s">
      <input type="checkbox" class="gal-etiq-cb" value="${t}" style="display:none" ${seleccionadas.includes(t)?'checked':''}
        onchange="this.parentElement.style.background=this.checked?'#1A5C38':'#eef';this.parentElement.style.color=this.checked?'#fff':'#333'">
      ${GAL_ETIQ_LABELS[t]}
    </label>`
  ).join('');
}

function _galEtiqSeleccionadas(containerId) {
  return [...document.querySelectorAll(`#${containerId} .gal-etiq-cb:checked`)].map(c => c.value);
}

function galDrop(event) {
  event.preventDefault();
  document.getElementById('gal-drop-zone').style.background = '#f8fdf9';
  galSubirArchivos(event.dataTransfer.files);
}

function galSubirArchivos(files) {
  if (!files || files.length === 0) return;
  galPendingFiles = [...files];
  document.getElementById('gal-upload-meta').style.display = 'block';
  _galEtiqSelector('gal-etiq-upload', []);
  const dropZone = document.getElementById('gal-drop-zone');
  dropZone.innerHTML = `<div style="font-size:36px">✅</div><div style="font-size:14px;color:#1A5C38;font-weight:600">${files.length} imagen${files.length>1?'es':''} lista${files.length>1?'s':''} — completá los datos abajo</div>`;
}

async function galConfirmarSubida(btn) {
  if (!galPendingFiles.length) return;
  const res = document.getElementById('gal-upload-result');
  res.className = 'cmd-result run'; res.textContent = '⏳ Subiendo…';
  btn.disabled = true; const o = btn.textContent; btn.textContent = '⏳ Guardando…';
  const etiquetas = _galEtiqSeleccionadas('gal-etiq-upload');
  const nombre = document.getElementById('gal-nombre').value.trim();
  const descripcion = document.getElementById('gal-descripcion').value.trim();
  let ok = 0;
  for (const file of galPendingFiles) {
    try {
      const b64 = await new Promise((resolve, reject) => {
        const fr = new FileReader();
        fr.onload = () => resolve(fr.result.split(',')[1]);
        fr.onerror = reject;
        fr.readAsDataURL(file);
      });
      const r = await fetch('/dashboard/api/galeria/upload', {
        method: 'POST',
        headers: {'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
        body: JSON.stringify({b64, nombre: nombre || file.name, descripcion, etiquetas, mime: file.type})
      });
      const d = await r.json();
      if (d.ok) ok++;
    } catch(e) { console.error(e); }
  }
  galPendingFiles = [];
  res.className = 'cmd-result ok'; res.textContent = `✅ ${ok} imagen${ok!==1?'es':''} guardada${ok!==1?'s':''}`;
  btn.disabled = false; btn.textContent = o;
  document.getElementById('gal-upload-meta').style.display = 'none';
  document.getElementById('gal-drop-zone').innerHTML = '<div style="font-size:36px;margin-bottom:8px">🖼️</div><div style="font-size:14px;color:#555;font-weight:600">Arrastrá imágenes acá o hacé clic para seleccionar</div><div style="font-size:12px;color:#999;margin-top:4px">JPG, PNG, WEBP — máx 5 MB por imagen</div>';
  galCargar();
}

async function galGenerarIA(btn) {
  const res = document.getElementById('gal-ia-gen-result');
  res.className = 'cmd-result run'; res.textContent = '⏳ Generando imagen con IA…';
  btn.disabled = true; const o = btn.textContent; btn.textContent = '⏳ Generando…';
  galIaB64 = null;
  document.getElementById('gal-ia-preview').style.display = 'none';
  try {
    const r = await fetch('/dashboard/api/galeria/generar-imagen', {
      method: 'POST',
      headers: {'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
      body: JSON.stringify({
        producto: document.getElementById('gal-ia-producto').value,
        tipo: document.getElementById('gal-ia-tipo').value,
        descripcion: document.getElementById('gal-ia-desc').value.trim()
      })
    });
    const d = await r.json();
    if (d.ok && d.b64) {
      galIaB64 = d.b64;
      galIaMime = d.mime || 'image/png';
      document.getElementById('gal-ia-img').src = 'data:' + galIaMime + ';base64,' + galIaB64;
      document.getElementById('gal-ia-preview').style.display = 'block';
      _galEtiqSelector('gal-etiq-ia', [document.getElementById('gal-ia-producto').value === 'modulo' ? 'modulos' : document.getElementById('gal-ia-producto').value]);
      res.className = 'cmd-result ok'; res.textContent = '✅ Imagen generada — guardala en la galería';
    } else {
      res.className = 'cmd-result err'; res.textContent = '❌ ' + (d.error || 'No se pudo generar');
    }
  } catch(e) { res.className = 'cmd-result err'; res.textContent = '❌ ' + e.message; }
  finally { btn.disabled = false; btn.textContent = o; }
}

async function galGuardarIA(btn) {
  if (!galIaB64) return;
  const res = document.getElementById('gal-ia-result');
  res.className = 'cmd-result run'; res.textContent = '⏳ Guardando…';
  btn.disabled = true; const o = btn.textContent; btn.textContent = '⏳';
  const etiquetas = _galEtiqSeleccionadas('gal-etiq-ia');
  try {
    const r = await fetch('/dashboard/api/galeria/upload', {
      method: 'POST',
      headers: {'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
      body: JSON.stringify({b64: galIaB64, nombre: '', descripcion: document.getElementById('gal-ia-desc').value.trim(), etiquetas, mime: galIaMime, origen: 'ia'})
    });
    const d = await r.json();
    res.className = d.ok ? 'cmd-result ok' : 'cmd-result err';
    res.textContent = d.ok ? '✅ Guardada en galería' : ('❌ ' + (d.error||''));
    if (d.ok) galCargar();
  } catch(e) { res.className = 'cmd-result err'; res.textContent = '❌ ' + e.message; }
  finally { btn.disabled = false; btn.textContent = o; }
}

function galDescargaIA() {
  if (!galIaB64) return;
  const a = document.createElement('a');
  a.href = 'data:' + galIaMime + ';base64,' + galIaB64;
  a.download = 'imagen_ia_' + Date.now() + '.png';
  a.click();
}

async function galCargar() {
  const grid = document.getElementById('gal-grid');
  grid.innerHTML = '<div class="empty" style="grid-column:1/-1">Cargando…</div>';
  _galEtiqSelector('gal-etiq-upload', []);
  _galEtiqSelector('gal-etiq-ia', []);
  // render filtros
  const filtros = document.getElementById('gal-filtros');
  filtros.innerHTML = ['<button class="btn ' + (galFiltroActivo===null?'btn-primary':'btn-outline') + '" style="font-size:12px" onclick="galFiltrar(null)">Todas</button>',
    ...GAL_ETIQ_TODAS.map(t =>
      `<button class="btn ${galFiltroActivo===t?'btn-primary':'btn-outline'}" style="font-size:12px" onclick="galFiltrar('${t}')">${GAL_ETIQ_LABELS[t]}</button>`)
  ].join('');
  try {
    const url = galFiltroActivo ? `/dashboard/api/galeria/imagenes?etiqueta=${galFiltroActivo}` : '/dashboard/api/galeria/imagenes';
    const r = await fetch(url, { headers:{'X-Dashboard-Password':DASH_PW} });
    const d = await r.json();
    const imgs = d.imagenes || [];
    if (!imgs.length) { grid.innerHTML = '<div class="empty" style="grid-column:1/-1">No hay imágenes todavía. ¡Subí la primera!</div>'; return; }
    grid.innerHTML = imgs.map(img => {
      const etiq = (img.etiquetas||[]).map(t => `<span style="background:#e8f5e9;color:#1A5C38;font-size:10px;padding:2px 6px;border-radius:10px">${GAL_ETIQ_LABELS[t]||t}</span>`).join('');
      const origen = img.origen === 'ia' ? '<span style="background:#e8eaf6;color:#3949ab;font-size:10px;padding:2px 6px;border-radius:10px">✨ IA</span>' : '';
      return `<div style="border:1.5px solid #eee;border-radius:10px;overflow:hidden;background:#fff;position:relative;cursor:pointer" title="${escHtmlD(img.nombre||'')}">
        <img src="/dashboard/api/galeria/imagen/${img.id}/thumb" loading="lazy"
             style="width:100%;aspect-ratio:1;object-fit:cover;display:block"
             onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22160%22 height=%22160%22><rect fill=%22%23eee%22 width=%22160%22 height=%22160%22/><text x=%2250%25%22 y=%2250%25%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 font-size=%2230%22>🖼️</text></svg>'">
        <div style="padding:7px">
          <div style="font-size:11px;color:#444;font-weight:600;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escHtmlD((img.nombre||'Sin nombre').slice(0,30))}</div>
          <div style="display:flex;flex-wrap:wrap;gap:3px;margin-bottom:5px">${origen}${etiq}</div>
          <div style="display:flex;gap:4px">
            <button class="btn btn-ghost" style="font-size:10px;padding:3px 7px;flex:1" onclick="galUsarEnEcopost('${img.id}')">Usar en post</button>
            <button class="btn btn-danger" style="font-size:10px;padding:3px 7px" onclick="galEliminarImg('${img.id}',this)" title="Eliminar">🗑</button>
          </div>
        </div>
      </div>`;
    }).join('');
  } catch(e) { grid.innerHTML = `<div class="empty" style="grid-column:1/-1">Error: ${e.message}</div>`; }
  galCargarCopies();
}

function galFiltrar(etiqueta) {
  galFiltroActivo = etiqueta;
  galCargar();
}

async function galEliminarImg(id, btn) {
  if (!confirm('¿Eliminar esta imagen de la galería?')) return;
  btn.disabled = true;
  try {
    const r = await fetch('/dashboard/api/galeria/imagen/' + id + '/borrar', {
      method:'POST', headers:{'X-Dashboard-Password':DASH_PW}
    });
    const d = await r.json();
    if (d.ok) { showToast('✅ Imagen eliminada'); galCargar(); }
    else { showToast('❌ ' + (d.error||'')); btn.disabled = false; }
  } catch(e) { showToast('❌ ' + e.message); btn.disabled = false; }
}

function galUsarEnEcopost(imgId) {
  // Navega a ecopost y marca la imagen como "archivo seleccionado"
  navigateTo('ecopost');
  showToast('Cargando imagen desde galería…');
  fetch('/dashboard/api/galeria/imagen/' + imgId + '/thumb', { headers:{'X-Dashboard-Password':DASH_PW} })
    .then(r => r.blob())
    .then(blob => {
      const reader = new FileReader();
      reader.onload = () => {
        const b64 = reader.result.split(',')[1];
        const mime = blob.type || 'image/jpeg';
        ecoShowMedia(b64, 'image', mime);
        ecoAbrirPreview();
        ecoMediaB64 = b64; ecoMediaKind = 'image';
        showToast('✅ Imagen lista en Ecopost');
      };
      reader.readAsDataURL(blob);
    })
    .catch(e => showToast('❌ ' + e.message));
}

// ── Drive sync ───────────────────────────────────────
async function galVerificarDrive() {
  const badge = document.getElementById('gal-drive-badge');
  badge.textContent = 'Verificando…';
  try {
    const r = await fetch('/dashboard/api/galeria/drive/verificar', { headers:{'X-Dashboard-Password':DASH_PW} });
    const d = await r.json();
    if (d.ok) {
      badge.textContent = '✅ Conectado';
      badge.style.color = '#2e7d32';
      document.getElementById('gal-drive-folder').textContent = '📁 Carpeta: ' + d.folder_name;
    } else {
      badge.textContent = '❌ Sin credenciales';
      badge.style.color = '#c62828';
      document.getElementById('gal-drive-folder').textContent = d.error || '';
    }
  } catch(e) {
    badge.textContent = '❌ Error';
    badge.style.color = '#c62828';
  }
}

async function galSyncDrive(btn) {
  const res = document.getElementById('gal-drive-result');
  res.className = 'cmd-result run';
  res.textContent = '⏳ Sincronizando con Google Drive…';
  btn.disabled = true; const o = btn.textContent; btn.textContent = '⏳ Sincronizando…';
  try {
    const r = await fetch('/dashboard/api/galeria/drive/sync', {
      method: 'POST', headers:{'X-Dashboard-Password':DASH_PW}
    });
    const d = await r.json();
    if (d.ok) {
      res.className = 'cmd-result ok';
      res.textContent = `✅ Sync completo — ${d.nuevas} imagen${d.nuevas!==1?'es':''} nueva${d.nuevas!==1?'s':''}, ${d.saltadas} ya existían${d.errores?' — ⚠️ '+d.errores+' errores':''}`;
      if (d.nuevas > 0) galCargar();
    } else {
      res.className = 'cmd-result err';
      res.textContent = '❌ ' + (d.error || 'Error de sync');
    }
  } catch(e) { res.className = 'cmd-result err'; res.textContent = '❌ ' + e.message; }
  finally { btn.disabled = false; btn.textContent = o; }
}

// ── Copies de la biblioteca ───────────────────────────
async function galCargarCopies() {
  const cont = document.getElementById('gal-copies-lista');
  if (!cont) return;
  cont.innerHTML = '<div class="empty">Cargando…</div>';
  const prod = document.getElementById('gal-copy-producto').value;
  const obj  = document.getElementById('gal-copy-objetivo').value;
  let url = '/dashboard/api/galeria/copies?';
  if (prod) url += 'producto=' + prod + '&';
  if (obj) url += 'objetivo=' + obj;
  try {
    const r = await fetch(url, { headers:{'X-Dashboard-Password':DASH_PW} });
    const d = await r.json();
    const copies = d.copies || [];
    if (!copies.length) { cont.innerHTML = '<div class="empty">No hay copies todavía. Creá el primero con "+ Nuevo copy".</div>'; return; }
    cont.innerHTML = copies.map(c => `
      <div style="border:1.5px solid #eee;border-radius:10px;padding:14px;margin-bottom:10px;background:#fafafa">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
          <span style="background:#e8f5e9;color:#1A5C38;font-size:11px;padding:2px 8px;border-radius:10px">${c.producto||'—'}</span>
          <span style="background:#e3f2fd;color:#1565c0;font-size:11px;padding:2px 8px;border-radius:10px">${c.objetivo||'—'}</span>
          <span style="margin-left:auto;font-size:11px;color:#aaa">${c.fecha||''}</span>
          <button class="btn btn-ghost" style="font-size:11px;padding:4px 8px" onclick="galEditarCopy('${c.id}')">✏️ Editar</button>
          <button class="btn btn-danger" style="font-size:11px;padding:4px 8px" onclick="galEliminarCopy('${c.id}',this)">🗑</button>
        </div>
        <div style="font-size:13px;color:#333;line-height:1.6;white-space:pre-wrap">${escHtmlD(c.texto)}</div>
      </div>`).join('');
  } catch(e) { cont.innerHTML = `<div class="empty">Error: ${e.message}</div>`; }
}

function galNuevoCopy() {
  document.getElementById('gal-copy-id').value = '';
  document.getElementById('gal-copy-ed-texto').value = '';
  document.getElementById('gal-copy-ed-producto').value = 'piscinas';
  document.getElementById('gal-copy-ed-objetivo').value = 'captar';
  document.getElementById('gal-copy-ed-result').textContent = '';
  document.getElementById('gal-copy-editor').style.display = 'block';
  document.getElementById('gal-copy-ed-texto').focus();
}

function galEditarCopy(id) {
  // Busca el copy del DOM actual y lo carga en el editor
  galCargarCopyParaEdicion(id);
}

async function galCargarCopyParaEdicion(id) {
  try {
    const r = await fetch('/dashboard/api/galeria/copies', { headers:{'X-Dashboard-Password':DASH_PW} });
    const d = await r.json();
    const c = (d.copies||[]).find(x => x.id === id);
    if (!c) return;
    document.getElementById('gal-copy-id').value = c.id;
    document.getElementById('gal-copy-ed-texto').value = c.texto || '';
    document.getElementById('gal-copy-ed-producto').value = c.producto || 'general';
    document.getElementById('gal-copy-ed-objetivo').value = c.objetivo || 'general';
    document.getElementById('gal-copy-ed-result').textContent = '';
    document.getElementById('gal-copy-editor').style.display = 'block';
    document.getElementById('gal-copy-ed-texto').focus();
  } catch(e) { showToast('❌ ' + e.message); }
}

async function galGuardarCopy(btn) {
  const texto  = document.getElementById('gal-copy-ed-texto').value.trim();
  const prod   = document.getElementById('gal-copy-ed-producto').value;
  const obj    = document.getElementById('gal-copy-ed-objetivo').value;
  const copyId = document.getElementById('gal-copy-id').value.trim();
  const res    = document.getElementById('gal-copy-ed-result');
  if (!texto) { res.className='cmd-result err'; res.textContent='❌ Escribí el texto del copy'; return; }
  btn.disabled = true; const o = btn.textContent; btn.textContent = '⏳';
  res.className = 'cmd-result run'; res.textContent = 'Guardando…';
  try {
    const r = await fetch('/dashboard/api/galeria/copy', {
      method:'POST',
      headers:{'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
      body: JSON.stringify({texto, producto:prod, objetivo:obj, copy_id: copyId||null})
    });
    const d = await r.json();
    if (d.ok) {
      res.className = 'cmd-result ok'; res.textContent = '✅ Guardado';
      setTimeout(() => { galCerrarEditorCopy(); galCargarCopies(); }, 600);
    } else { res.className='cmd-result err'; res.textContent='❌ '+(d.error||''); }
  } catch(e) { res.className='cmd-result err'; res.textContent='❌ '+e.message; }
  finally { btn.disabled=false; btn.textContent=o; }
}

function galCerrarEditorCopy() {
  document.getElementById('gal-copy-editor').style.display = 'none';
}

async function galEliminarCopy(id, btn) {
  if (!confirm('¿Eliminar este copy?')) return;
  btn.disabled = true;
  try {
    const r = await fetch('/dashboard/api/galeria/copy/' + id + '/borrar', {
      method:'POST', headers:{'X-Dashboard-Password':DASH_PW}
    });
    const d = await r.json();
    if (d.ok) { showToast('✅ Copy eliminado'); galCargarCopies(); }
    else { showToast('❌ ' + (d.error||'')); btn.disabled=false; }
  } catch(e) { showToast('❌ ' + e.message); btn.disabled=false; }
}

// ── BASE DE CONOCIMIENTO ─────────────────────────────
let KB_DATA = {estilo:'', docs:[]};

async function kbCargar() {
  try {
    const r = await fetch('/dashboard/api/kb', { headers:{'X-Dashboard-Password':DASH_PW} });
    KB_DATA = await r.json();
    document.getElementById('kb-estilo').value = KB_DATA.estilo || '';
    kbRenderLista();
  } catch(e) { document.getElementById('kb-lista').innerHTML = '<div class="empty">Error: '+e.message+'</div>'; }
}

function kbRenderLista() {
  const cont = document.getElementById('kb-lista');
  const docs = KB_DATA.docs || [];
  if (!docs.length) { cont.innerHTML = '<div class="empty">No hay documentos todavía. Creá el primero con "Nuevo documento".</div>'; return; }
  cont.innerHTML = docs.map(d => {
    const ag = (d.agentes||[]).includes('*') ? 'Todos los agentes' : (d.agentes||[]).join(', ');
    const estado = d.activo ? '<span style="color:#2e7d32;font-weight:700">● Activo</span>' : '<span style="color:#bbb">○ Inactivo</span>';
    return `<div style="border:1px solid #eee;border-radius:10px;padding:14px;margin-bottom:10px;background:#fafafa">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <b style="font-size:14px">${escHtmlD(d.titulo)}</b>
        ${estado}
        <span style="font-size:11px;color:#888">👥 ${escHtmlD(ag)}</span>
        <span style="margin-left:auto;display:flex;gap:6px">
          <button class="btn btn-ghost" style="font-size:11px;padding:5px 10px" onclick="kbEditar('${d.id}')">✏️ Editar</button>
          <button class="btn btn-danger" style="font-size:11px;padding:5px 10px" onclick="kbBorrar('${d.id}')">🗑</button>
        </span>
      </div>
      <div style="font-size:12px;color:#666;margin-top:6px;white-space:pre-wrap;max-height:60px;overflow:hidden">${escHtmlD((d.contenido||'').slice(0,220))}${(d.contenido||'').length>220?'…':''}</div>
    </div>`;
  }).join('');
}

function kbRenderAgentesCheckboxes(seleccionados) {
  const grid = document.getElementById('kb-agentes-grid');
  const sel = seleccionados || [];
  grid.innerHTML = AGENTS.map(a =>
    `<label style="font-size:12px;text-transform:none;font-weight:500;display:flex;align-items:center;gap:5px">
      <input type="checkbox" class="kb-ag" value="${a.id}" style="width:auto" ${sel.includes(a.id)?'checked':''}> ${a.emoji} ${a.nombre}
    </label>`).join('');
}

function kbToggleTodos() {
  const todos = document.getElementById('kb-ag-todos').checked;
  document.getElementById('kb-agentes-grid').style.opacity = todos ? '.4' : '1';
  document.querySelectorAll('.kb-ag').forEach(c => c.disabled = todos);
}

function kbNuevoDoc() {
  document.getElementById('kb-editor').style.display = 'block';
  document.getElementById('kb-editor-titulo').textContent = 'Nuevo documento';
  document.getElementById('kb-doc-id').value = '';
  document.getElementById('kb-doc-titulo').value = '';
  document.getElementById('kb-doc-contenido').value = '';
  document.getElementById('kb-doc-activo').checked = true;
  document.getElementById('kb-ag-todos').checked = true;
  kbRenderAgentesCheckboxes([]);
  kbToggleTodos();
  document.getElementById('kb-doc-msg').textContent = '';
  document.getElementById('kb-editor').scrollIntoView({behavior:'smooth', block:'nearest'});
}

function kbEditar(id) {
  const d = (KB_DATA.docs||[]).find(x => x.id === id);
  if (!d) return;
  document.getElementById('kb-editor').style.display = 'block';
  document.getElementById('kb-editor-titulo').textContent = 'Editar documento';
  document.getElementById('kb-doc-id').value = d.id;
  document.getElementById('kb-doc-titulo').value = d.titulo || '';
  document.getElementById('kb-doc-contenido').value = d.contenido || '';
  document.getElementById('kb-doc-activo').checked = !!d.activo;
  const todos = (d.agentes||[]).includes('*');
  document.getElementById('kb-ag-todos').checked = todos;
  kbRenderAgentesCheckboxes(todos ? [] : (d.agentes||[]));
  kbToggleTodos();
  document.getElementById('kb-doc-msg').textContent = '';
  document.getElementById('kb-editor').scrollIntoView({behavior:'smooth', block:'nearest'});
}

function kbImportarArchivo(ev) {
  const file = ev.target.files[0];
  if (!file) return;
  if (file.size > 2*1024*1024) { showToast('Archivo muy grande (máx 2MB de texto)'); return; }
  const reader = new FileReader();
  reader.onload = () => {
    document.getElementById('kb-doc-contenido').value = reader.result;
    if (!document.getElementById('kb-doc-titulo').value)
      document.getElementById('kb-doc-titulo').value = file.name.replace(/\.[^.]+$/, '');
    showToast('✅ Archivo importado al contenido');
  };
  reader.readAsText(file);
}

async function kbGuardarDoc(btn) {
  const todos = document.getElementById('kb-ag-todos').checked;
  const agentes = todos ? ['*'] : [...document.querySelectorAll('.kb-ag:checked')].map(c => c.value);
  if (!todos && !agentes.length) { document.getElementById('kb-doc-msg').textContent = '❌ Elegí al menos un agente'; return; }
  const doc = {
    id: document.getElementById('kb-doc-id').value || undefined,
    titulo: document.getElementById('kb-doc-titulo').value.trim(),
    contenido: document.getElementById('kb-doc-contenido').value.trim(),
    agentes, activo: document.getElementById('kb-doc-activo').checked,
  };
  if (!doc.titulo || !doc.contenido) { document.getElementById('kb-doc-msg').textContent = '❌ Completá título y contenido'; return; }
  btn.disabled = true;
  try {
    const r = await fetch('/dashboard/api/kb/doc', {
      method:'POST', headers:{'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
      body: JSON.stringify(doc)
    });
    const d = await r.json();
    if (d.ok) { showToast('✅ Documento guardado'); document.getElementById('kb-editor').style.display='none'; kbCargar(); }
    else document.getElementById('kb-doc-msg').textContent = '❌ Error al guardar';
  } catch(e) { document.getElementById('kb-doc-msg').textContent = '❌ ' + e.message; }
  finally { btn.disabled = false; }
}

async function kbBorrar(id) {
  if (!confirm('¿Borrar este documento de conocimiento?')) return;
  await fetch('/dashboard/api/kb/doc/'+id+'/borrar', { method:'POST', headers:{'X-Dashboard-Password':DASH_PW} });
  showToast('Documento borrado'); kbCargar();
}

async function kbGuardarEstilo(btn) {
  const msg = document.getElementById('kb-estilo-msg');
  msg.textContent = 'Guardando…'; btn.disabled = true;
  try {
    const r = await fetch('/dashboard/api/kb/estilo', {
      method:'POST', headers:{'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
      body: JSON.stringify({estilo: document.getElementById('kb-estilo').value})
    });
    const d = await r.json();
    msg.textContent = d.ok ? '✅ Guardado — afecta las próximas respuestas' : '❌ Error';
  } catch(e) { msg.textContent = '❌ ' + e.message; }
  finally { btn.disabled = false; }
}

async function kbResetEstilo() {
  const r = await fetch('/dashboard/api/kb/estilo', {
    method:'POST', headers:{'Content-Type':'application/json','X-Dashboard-Password':DASH_PW},
    body: JSON.stringify({reset:true})
  });
  const d = await r.json();
  if (d.estilo) { document.getElementById('kb-estilo').value = d.estilo; showToast('✅ Estilo restaurado'); }
}

// ── INIT ─────────────────────────────────────────────
buildTeamSummary();
buildAgentsGrid();
buildHierarchy();
buildCatalogo();
loadConfig();
loadKpis();
setInterval(loadKpis, 60000);  // auto-refresh cada 60s
</script>
</body>
</html>"""


# ── Login page ─────────────────────────────────────────────────────────────

DASHBOARD_LOGIN = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Dashboard — EcoFiver IA</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#f0f7f3;min-height:100vh;display:flex;align-items:center;
         justify-content:center;padding:24px}
    .card{background:white;border-radius:16px;box-shadow:0 4px 24px rgba(26,92,56,.12);
          padding:44px 40px;max-width:400px;width:100%;text-align:center}
    .icon{font-size:52px;margin-bottom:16px}
    h1{color:#1A5C38;font-size:22px;font-weight:800;margin-bottom:6px}
    p{color:#888;font-size:13px;margin-bottom:28px}
    .field{margin-bottom:14px;text-align:left}
    .field label{display:block;font-size:11px;font-weight:700;color:#666;
                  text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px}
    input{width:100%;border:1.5px solid #dde;border-radius:8px;padding:11px 14px;
          font-size:14px;outline:none;transition:border .2s}
    input:focus{border-color:#1A5C38}
    button{width:100%;background:#1A5C38;color:white;border:none;border-radius:8px;
           padding:13px;font-size:15px;font-weight:700;cursor:pointer;transition:background .2s;margin-top:6px}
    button:hover{background:#145030}
    .err{background:#ffebee;color:#c62828;border-radius:8px;padding:10px;
         font-size:13px;margin-bottom:14px;display:none;text-align:left}
    .hint{font-size:12px;color:#aaa;margin-top:20px}
  </style>
</head>
<body>
<div class="card">
  <div class="icon">🌿</div>
  <h1>EcoFiver IA</h1>
  <p>Dashboard de control — ingresá tu contraseña</p>
  <div class="err" id="err">Contraseña incorrecta. Intentá de nuevo.</div>
  <form id="f">
    <div class="field">
      <label>Contraseña</label>
      <input type="password" id="pw" placeholder="••••••••••••" autofocus autocomplete="current-password">
    </div>
    <button type="submit">Ingresar al dashboard →</button>
  </form>
  <p class="hint">Contraseña por defecto: <code>ecomodulos2026</code></p>
</div>
<script>
document.getElementById('f').onsubmit = async function(e) {
  e.preventDefault();
  const pw = document.getElementById('pw').value;
  const r  = await fetch('/dashboard/check', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({password: pw})
  });
  const d = await r.json();
  if (d.ok) {
    sessionStorage.setItem('eco_admin_pw', pw);
    window.location.href = '/dashboard/home';
  } else {
    document.getElementById('err').style.display = 'block';
    document.getElementById('pw').value = '';
    document.getElementById('pw').focus();
  }
};
</script>
</body>
</html>"""


# ── Rutas ──────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_login():
    return DASHBOARD_LOGIN


@router.post("/dashboard/check")
async def dashboard_check(request: Request):
    from auth import check_password
    body = await request.json()
    # Dashboard accesible para Rodrigo y Renzo
    return JSONResponse({"ok": check_password(body.get("password", ""))})


@router.get("/dashboard/home", response_class=HTMLResponse)
async def dashboard_home():
    from agents.catalogo import CATALOGO
    env = read_env()

    html = DASHBOARD_HTML \
        .replace("__AGENTS_JSON__", json.dumps(AGENTS_META, ensure_ascii=False)) \
        .replace("__CATALOGO_JSON__", json.dumps(CATALOGO, ensure_ascii=False)) \
        .replace("__ENV_JSON__", json.dumps({
            k: ("***" if any(s in k for s in ["KEY","TOKEN","PASSWORD","SECRET"]) and v else v)
            for k, v in env.items()
        }, ensure_ascii=False))
    return html


@router.post("/dashboard/save-config")
async def dashboard_save_config(request: Request):
    from auth import is_admin
    body = await request.json()
    if not is_admin(body.get("password", "")):
        return JSONResponse({"ok": False, "message": "Solo Rodrigo puede cambiar la configuración"})
    campos = ["GEMINI_API_KEY","CRM_BASE_URL","CRM_API_KEY","TELEGRAM_BOT_TOKEN",
              "TELEGRAM_CHAT_ID_RODRIGO","WA_TOKEN","WA_PHONE_ID","WA_VERIFY_TOKEN",
              "CLOUDFLARE_WORKER_URL","GOOGLE_DRIVE_FOLDER_ID","BASE_URL","PORT","ADMIN_PASSWORD"]
    values = {k: body[k] for k in campos if body.get(k)}
    save_env(values)
    return JSONResponse({"ok": True, "message": "Guardado correctamente"})


@router.post("/dashboard/save-catalogo")
async def dashboard_save_catalogo(request: Request):
    from auth import is_admin
    body = await request.json()
    if not is_admin(body.get("password", "")):
        return JSONResponse({"ok": False, "message": "Solo Rodrigo puede modificar el catálogo"})
    catalogo_path = Path(__file__).parent / "agents" / "catalogo.py"
    catalogo = {
        "piscinas": body.get("piscinas", []),
        "modulos_m2": body.get("modulos_m2", []),
        "flete_por_km": body.get("flete_por_km", 3000),
        "flete_miniportante_por_km": body.get("flete_miniportante_por_km", 2000),
        "ciudad_origen": "Zarate",
        "combo_descuento_pct": body.get("combo_descuento_pct", 25),
        "combo_solo_financiacion": True,
        "planes_financiacion": {
            k: {"cuotas": int(k)}
            for k in body.get("planes_financiacion", {}).keys()
        },
        "factor_ingreso_modulos":  2.0,
        "factor_ingreso_piscinas": 1.5,
    }
    content = f'"""\nCatálogo oficial de productos EcoFiver.\nEste archivo es importado por TODOS los agentes.\n"""\n\nCATALOGO = {json.dumps(catalogo, ensure_ascii=False, indent=2)}\n'
    catalogo_path.write_text(content, encoding="utf-8")
    return JSONResponse({"ok": True, "message": "Catálogo guardado"})


@router.post("/dashboard/test/{servicio}")
async def dashboard_test(servicio: str, request: Request):
    from auth import check_password
    body = await request.json()
    if not check_password(body.get("password", "")):
        return JSONResponse({"ok": False, "message": "Contraseña incorrecta"})
    try:
        if servicio == "gemini":
            from google import genai
            client = genai.Client(api_key=body.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY",""))
            r = client.models.generate_content(model="gemini-2.0-flash", contents="Respondé solo: OK")
            return JSONResponse({"ok": True, "message": f"Gemini responde: {r.text.strip()[:60]}"})
        elif servicio == "crm":
            import httpx
            url = body.get("CRM_BASE_URL") or os.getenv("CRM_BASE_URL","")
            key = body.get("CRM_API_KEY") or os.getenv("CRM_API_KEY","")
            if not url: return JSONResponse({"ok": False, "message": "CRM_BASE_URL no configurada"})
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(f"{url}/api/health", headers={"Authorization": f"Bearer {key}"})
            return JSONResponse({"ok": r.status_code < 400, "message": f"CRM respondió con status {r.status_code}"})
        elif servicio == "telegram":
            import httpx
            token = body.get("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN","")
            if not token: return JSONResponse({"ok": False, "message": "Token no configurado"})
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get(f"https://api.telegram.org/bot{token}/getMe")
            d = r.json()
            if d.get("ok"):
                return JSONResponse({"ok": True, "message": f"Bot: @{d['result'].get('username')} ({d['result'].get('first_name')})"})
            return JSONResponse({"ok": False, "message": d.get("description","Error")})
        elif servicio == "whatsapp":
            import httpx
            token = body.get("WA_TOKEN") or os.getenv("WA_TOKEN","")
            if not token: return JSONResponse({"ok": False, "message": "WA_TOKEN no configurado"})
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.get("https://graph.facebook.com/v19.0/me", headers={"Authorization": f"Bearer {token}"})
            d = r.json()
            if "id" in d: return JSONResponse({"ok": True, "message": f"Token válido. Cuenta: {d.get('name', d.get('id'))}"})
            return JSONResponse({"ok": False, "message": d.get("error",{}).get("message","Token inválido")})
        elif servicio == "cloudflare":
            import httpx
            url = body.get("CLOUDFLARE_WORKER_URL") or os.getenv("CLOUDFLARE_WORKER_URL","")
            if not url: return JSONResponse({"ok": False, "message": "URL no configurada"})
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(f"{url}/health")
            return JSONResponse({"ok": r.status_code < 400, "message": f"Worker respondió {r.status_code}"})
        return JSONResponse({"ok": False, "message": f"Servicio '{servicio}' desconocido"})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)})


@router.get("/dashboard/flete")
async def dashboard_flete(localidad: str, producto: str = "general"):
    from tools.flete_calc import calcular_flete
    return JSONResponse(calcular_flete(localidad, producto))


# ── KPIs en vivo (números reales del negocio desde el CRM) ─────────────────

@router.get("/dashboard/api/kpis")
async def dashboard_kpis(request: Request):
    """Agrega en una sola llamada todos los números reales del negocio."""
    from auth import check_password
    if not check_password(request.headers.get("X-Dashboard-Password", "")):
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    import asyncio
    from tools import crm_client

    async def _safe(coro, default):
        try:
            return await coro
        except Exception as e:
            logger.warning(f"[KPIs] {e}")
            return default

    (ventas_hoy, pipeline, cuotas_venc,
     videollamadas, leads_sin_resp) = await asyncio.gather(
        _safe(crm_client.get_ventas_hoy(), {}),
        _safe(crm_client.get_pipeline_stats(), {}),
        _safe(crm_client.get_cuotas_vencidas(0), []),
        _safe(crm_client.get_videollamadas_proximas(48), []),
        _safe(crm_client.get_leads_sin_respuesta(2), []),
    )

    p = pipeline or {}

    # Monto de cuotas vencidas (si el endpoint lista cuotas con monto)
    monto_vencido = 0
    for c in (cuotas_venc or []):
        try:
            monto_vencido += float(c.get("monto", 0) or 0)
        except Exception:
            pass

    # Embudo real construido desde el pipeline del CRM
    funnel = {
        "Leads recibidos":  p.get("leads_recibidos", 0),
        "Desde la web":     p.get("leads_web", 0),
        "Calificados":      p.get("leads_calificados", 0),
        "Videollamadas":    p.get("videollamadas", 0),
        "Cierres contado":  p.get("cierres_contado", 0),
    }

    canales_activos = {
        "whatsapp":       bool(os.getenv("WA_TOKEN")),
        "telegram":       bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        "instagram":      bool(os.getenv("META_PAGE_ACCESS_TOKEN") and os.getenv("META_IG_USER_ID")),
        "facebook_posts": bool(os.getenv("META_PAGE_ACCESS_TOKEN") and os.getenv("META_PAGE_ID")),
        "email":          bool(os.getenv("EMAIL_USER") and os.getenv("EMAIL_PASSWORD")),
        "scraping":       True,
    }

    cuotas_vencidas_n = p.get("cuotas_vencidas", len(cuotas_venc or []))

    return JSONResponse({
        "ts": datetime.now().strftime("%H:%M:%S"),
        "hoy": {
            "cierres":      ventas_hoy.get("cierres", 0),
            "monto_total":  ventas_hoy.get("monto_total", 0),
            "leads_nuevos": ventas_hoy.get("leads_nuevos", p.get("leads_hoy", 0)),
        },
        "pipeline": {
            "leads_recibidos":   p.get("leads_recibidos", 0),
            "leads_web":         p.get("leads_web", 0),
            "leads_calificados": p.get("leads_calificados", 0),
            "cierres_contado":   p.get("cierres_contado", 0),
            "monto_contado":     p.get("monto_contado", 0),
            "videollamadas":     p.get("videollamadas", 0),
            "cuotas_cobradas":   p.get("cuotas_cobradas", 0),
            "monto_cuotas":      p.get("monto_cuotas", 0),
        },
        "leads": {
            "total":         p.get("leads_recibidos", 0),
            "calientes":     p.get("leads_calificados", 0),
            "sin_respuesta": len(leads_sin_resp or []),
            "funnel":        funnel,
        },
        "cobranzas": {
            "cuotas_vencidas": cuotas_vencidas_n,
            "monto_vencido":   monto_vencido,
        },
        "agenda": {
            "videollamadas_proximas": len(videollamadas or []),
            "detalle": [
                {
                    "lead":  v.get("nombre") or v.get("lead_id") or "?",
                    "fecha": v.get("fecha_hora", ""),
                    "tipo":  v.get("tipo", "videollamada"),
                }
                for v in (videollamadas or [])[:8]
            ],
        },
        "canales": canales_activos,
    })


# ── Leads que requieren acción (para el widget del dashboard) ──────────────

@router.get("/dashboard/api/leads-accion")
async def dashboard_leads_accion(request: Request):
    """Leads sin respuesta + videollamadas próximas — lista accionable."""
    from auth import check_password
    if not check_password(request.headers.get("X-Dashboard-Password", "")):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    import asyncio
    from tools import crm_client

    async def _safe(coro, default):
        try:
            return await coro
        except Exception:
            return default

    sin_resp, videollamadas = await asyncio.gather(
        _safe(crm_client.get_leads_sin_respuesta(2), []),
        _safe(crm_client.get_videollamadas_proximas(48), []),
    )
    leads = []
    for l in (sin_resp or [])[:25]:
        leads.append({
            "nombre":   l.get("nombre", "Sin nombre"),
            "telefono": l.get("telefono", ""),
            "canal":    l.get("canal_origen", ""),
            "agente":   l.get("agente_asignado", ""),
            "horas":    l.get("horas_sin_respuesta", ""),
            "producto": l.get("producto_interes", ""),
            "estado":   l.get("estado", ""),
        })
    return JSONResponse({
        "sin_respuesta": leads,
        "total_sin_respuesta": len(sin_resp or []),
        "videollamadas_proximas": len(videollamadas or []),
    })


# ── Centro de Comando: disparar acciones del sistema autónomo ──────────────

@router.post("/dashboard/api/comando/{accion}")
async def dashboard_comando(accion: str, request: Request):
    """Dispara manualmente una acción de la máquina autónoma de leads."""
    from auth import check_password
    if not check_password(request.headers.get("X-Dashboard-Password", "")):
        return JSONResponse({"ok": False, "error": "no autorizado"}, status_code=401)
    try:
        if accion == "scraping":
            from tools.lead_scraper import ejecutar_ciclo_scraping
            resumen = await ejecutar_ciclo_scraping()
            return JSONResponse({"ok": True, "accion": accion, "resumen": resumen})

        elif accion == "contenido":
            from tools.content_poster import generar_contenido, publicar_facebook, publicar_instagram_texto
            contenido = await generar_contenido()
            if not contenido:
                return JSONResponse({"ok": False, "error": "No se pudo generar contenido"})
            fb_ok = await publicar_facebook(contenido["texto_fb"])
            ig_ok = await publicar_instagram_texto(contenido["texto_ig"])
            return JSONResponse({
                "ok": True, "accion": accion,
                "facebook": fb_ok, "instagram": ig_ok,
                "tipo": contenido.get("tipo"), "foco": contenido.get("foco"),
                "preview": contenido["texto_fb"][:280],
            })

        elif accion == "emails":
            from channels.email_channel import procesar_ciclo_email_unico
            n = await procesar_ciclo_email_unico()
            return JSONResponse({"ok": True, "accion": accion, "procesados": n})

        elif accion == "leads_nuevos":
            # Contactar leads nuevos sin contactar (mismo flujo que el cron)
            from scheduler.cron import tarea_contacto_leads_nuevos
            await tarea_contacto_leads_nuevos()
            return JSONResponse({"ok": True, "accion": accion})

        elif accion == "reactivar_frios":
            from tools.crm_actions import _reactivar_leads_frios
            resultado = await _reactivar_leads_frios({"dias": 30, "limite": 15})
            return JSONResponse({"ok": True, "accion": accion, "detalle": resultado})

        return JSONResponse({"ok": False, "error": f"acción '{accion}' desconocida"})
    except Exception as e:
        logger.error(f"[Comando] {accion} falló: {e}")
        return JSONResponse({"ok": False, "error": str(e)})


# ── Ecopost Studio: generar y publicar contenido de marketing ──────────────

_ECOPOST_FOCOS = {
    "piscina": "piscinas de fibra de vidrio",
    "modulo":  "módulos habitables NCE (viviendas, oficinas, glamping)",
    "combo":   "combo módulo + piscina con descuento",
}


@router.post("/dashboard/api/ecopost/generar")
async def ecopost_generar(request: Request):
    """Genera copy (siempre) e imagen (best-effort) para un post de marketing."""
    from auth import check_password
    if not check_password(request.headers.get("X-Dashboard-Password", "")):
        return JSONResponse({"ok": False, "error": "no autorizado"}, status_code=401)

    body        = await request.json()
    producto    = (body.get("producto") or "piscina").lower()
    tipo        = (body.get("tipo") or "flyer").lower()       # flyer | story
    descripcion = (body.get("descripcion") or "").strip()
    tono        = (body.get("tono") or "cálido y aspiracional").strip()
    con_imagen  = body.get("con_imagen", True)

    foco = _ECOPOST_FOCOS.get(producto, "productos de EcoFiver")

    # ── Copy con Renata (cadena de IA con fallback, confiable) ──────────────
    copy_text, hashtags = "", ""
    try:
        from agents.renata import get_agent
        renata = get_agent()
        prompt = (
            f"Generá el texto para un posteo de redes sociales de EcoFiver "
            f"(empresa argentina de Zárate). Producto: {foco}. "
            f"{'Indicación extra: ' + descripcion if descripcion else ''} "
            f"Formato: {'story vertical' if tipo == 'story' else 'posteo de feed'}. "
            f"Tono: {tono}, en castellano argentino (de vos). "
            f"Incluí un gancho inicial, 2-3 líneas de beneficio y un llamado a la acción "
            f"(escribir por WhatsApp/DM). Sin markdown. "
            f"Al final, en una línea aparte, 6-8 hashtags relevantes para Argentina."
        )
        contenido = await renata.respond(prompt)
        lines = (contenido or "").strip().split("\n")
        for i, line in enumerate(lines):
            if line.strip().startswith("#") or line.count("#") >= 3:
                hashtags = line.strip()
                copy_text = "\n".join(lines[:i]).strip()
                break
        if not copy_text:
            copy_text = (contenido or "").strip()
    except Exception as e:
        logger.warning(f"[Ecopost] copy falló: {e}")
        copy_text = ""

    # ── Imagen (best-effort: free tier limitado) ────────────────────────────
    image_b64, image_error = None, None
    if con_imagen:
        try:
            from tools.cloudflare_client import generar_imagen_gemini
            prompt_img = descripcion or f"{foco}, escena real y atractiva"
            img_bytes = await generar_imagen_gemini(prompt_img, tipo)
            import base64 as _b64
            image_b64 = _b64.b64encode(img_bytes).decode("utf-8")
        except Exception as e:
            image_error = str(e)

    return JSONResponse({
        "ok": True,
        "copy": copy_text,
        "hashtags": hashtags,
        "caption": (copy_text + ("\n\n" + hashtags if hashtags else "")).strip(),
        "image_base64": image_b64,
        "image_error": image_error,
    })


@router.post("/dashboard/api/ecopost/publicar")
async def ecopost_publicar(request: Request):
    """Publica el contenido en Facebook y/o Instagram."""
    from auth import check_password
    if not check_password(request.headers.get("X-Dashboard-Password", "")):
        return JSONResponse({"ok": False, "error": "no autorizado"}, status_code=401)

    body       = await request.json()
    canal      = (body.get("canal") or "facebook").lower()   # facebook | instagram | ambos
    caption    = (body.get("caption") or "").strip()
    media_b64  = body.get("media_base64") or body.get("image_base64")
    media_kind = (body.get("media_kind") or "image").lower()  # image | video

    if not caption and not media_b64:
        return JSONResponse({"ok": False, "error": "No hay nada para publicar"})

    media_bytes = None
    if media_b64:
        try:
            import base64 as _b64
            media_bytes = _b64.b64decode(media_b64)
        except Exception:
            return JSONResponse({"ok": False, "error": "Archivo inválido"})

    es_video = media_kind == "video"
    from tools import content_poster
    resultados = {}

    if canal in ("facebook", "ambos"):
        if media_bytes and es_video:
            resultados["facebook"] = await content_poster.publicar_facebook_video(media_bytes, caption)
        elif media_bytes:
            resultados["facebook"] = await content_poster.publicar_facebook_foto(media_bytes, caption)
        else:
            resultados["facebook"] = await content_poster.publicar_facebook(caption)

    if canal in ("instagram", "ambos"):
        if media_bytes and es_video:
            resultados["instagram"] = await content_poster.publicar_instagram_video(media_bytes, caption)
        elif media_bytes:
            resultados["instagram"] = await content_poster.publicar_instagram_foto(media_bytes, caption)
        else:
            resultados["instagram"] = False
            resultados["instagram_error"] = "Instagram requiere una imagen o video"

    ok_any = any(v is True for v in resultados.values())
    return JSONResponse({"ok": ok_any, "resultados": resultados})


# ── MercadoLibre ────────────────────────────────────────────────────────────

def _ml_auth(request: Request) -> bool:
    from auth import check_password
    return check_password(request.headers.get("X-Dashboard-Password", ""))


@router.get("/dashboard/api/ml/estado")
async def ml_estado(request: Request):
    if not _ml_auth(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    from tools import mercadolibre_client as ml
    estado = {
        "configurado": ml.esta_configurado(),
        "conectado":   ml.esta_conectado(),
        "redirect_uri": os.getenv("ML_REDIRECT_URI", ""),
        "app_id":       os.getenv("ML_APP_ID", ""),
    }
    if ml.esta_conectado():
        estado["cuenta"]   = await ml.info_cuenta()
        estado["metricas"] = await ml.metricas()
    if ml.esta_configurado():
        estado["auth_url"] = ml.url_autorizacion()
    return JSONResponse(estado)


@router.post("/dashboard/api/ml/config")
async def ml_config(request: Request):
    from auth import is_admin
    body = await request.json()
    if not is_admin(body.get("password", "") or request.headers.get("X-Dashboard-Password", "")):
        return JSONResponse({"ok": False, "error": "no autorizado"}, status_code=401)
    vals = {}
    for k in ("ML_APP_ID", "ML_SECRET", "ML_REDIRECT_URI"):
        if body.get(k):
            vals[k] = body[k].strip()
    if vals:
        save_env(vals)
    return JSONResponse({"ok": True})


@router.get("/dashboard/ml/callback", response_class=HTMLResponse)
async def ml_callback(code: str = "", error: str = ""):
    """ML redirige acá tras autorizar. Intercambia el code por tokens."""
    from tools import mercadolibre_client as ml
    if error:
        msg, ok = f"Autorización cancelada: {error}", False
    elif not code:
        msg, ok = "No se recibió código de autorización.", False
    else:
        res = await ml.intercambiar_codigo(code)
        ok  = res.get("ok", False)
        msg = "✅ ¡Cuenta de MercadoLibre conectada!" if ok else f"❌ {res.get('error','Error')}"
    color = "#2e7d32" if ok else "#c62828"
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">
<title>MercadoLibre — Conexión</title>
<style>body{{font-family:-apple-system,Segoe UI,sans-serif;background:#f0f7f3;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0}}
.c{{background:#fff;padding:40px;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.1);text-align:center;max-width:420px}}
h1{{color:{color};font-size:20px}}a{{display:inline-block;margin-top:20px;background:#1A5C38;color:#fff;
text-decoration:none;padding:11px 24px;border-radius:8px;font-weight:600}}</style></head>
<body><div class="c"><h1>{msg}</h1>
<p style="color:#666;font-size:14px">Ya podés volver al panel y gestionar tus publicaciones.</p>
<a href="/dashboard/home">← Volver al dashboard</a></div></body></html>"""


@router.get("/dashboard/api/ml/publicaciones")
async def ml_publicaciones(request: Request, status: str = "active"):
    if not _ml_auth(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    from tools import mercadolibre_client as ml
    return JSONResponse({"items": await ml.listar_publicaciones(status=status)})


@router.post("/dashboard/api/ml/item/{item_id}/estado")
async def ml_item_estado(item_id: str, request: Request):
    if not _ml_auth(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    body = await request.json()
    from tools import mercadolibre_client as ml
    res = await ml.cambiar_estado(item_id, body.get("estado", "paused"))
    return JSONResponse({"ok": "id" in res or res.get("status_code", 0) == 200, "res": res})


@router.post("/dashboard/api/ml/item/{item_id}/actualizar")
async def ml_item_actualizar(item_id: str, request: Request):
    if not _ml_auth(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    body = await request.json()
    from tools import mercadolibre_client as ml
    cambios = {}
    if body.get("price") is not None:  cambios["price"] = float(body["price"])
    if body.get("stock") is not None:  cambios["available_quantity"] = int(body["stock"])
    if body.get("title"):              cambios["title"] = body["title"]
    res = await ml.actualizar_publicacion(item_id, cambios)
    return JSONResponse({"ok": "id" in res, "res": res})


@router.post("/dashboard/api/ml/crear")
async def ml_crear(request: Request):
    if not _ml_auth(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    body = await request.json()
    from tools import mercadolibre_client as ml
    # Autocompletar categoría si no vino
    if not body.get("category_id") and body.get("title"):
        sug = await ml.sugerir_categoria(body["title"])
        if sug.get("category_id"):
            body["category_id"] = sug["category_id"]
    res = await ml.crear_publicacion(body)
    return JSONResponse({"ok": "id" in res, "res": res})


@router.get("/dashboard/api/ml/sugerir-categoria")
async def ml_sugerir_categoria(request: Request, titulo: str = ""):
    if not _ml_auth(request):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    from tools import mercadolibre_client as ml
    return JSONResponse(await ml.sugerir_categoria(titulo))


# ── Base de Conocimiento de los agentes ─────────────────────────────────────

@router.get("/dashboard/api/kb")
async def kb_listar(request: Request):
    from auth import check_password
    if not check_password(request.headers.get("X-Dashboard-Password", "")):
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    from tools import knowledge_base as kb
    return JSONResponse(kb.listar())


@router.post("/dashboard/api/kb/estilo")
async def kb_set_estilo(request: Request):
    from auth import check_password
    if not check_password(request.headers.get("X-Dashboard-Password", "")):
        return JSONResponse({"ok": False}, status_code=401)
    body = await request.json()
    from tools import knowledge_base as kb
    if body.get("reset"):
        return JSONResponse({"ok": True, "estilo": kb.restaurar_estilo_default()})
    kb.set_estilo(body.get("estilo", ""))
    return JSONResponse({"ok": True})


@router.post("/dashboard/api/kb/doc")
async def kb_guardar_doc(request: Request):
    from auth import check_password
    if not check_password(request.headers.get("X-Dashboard-Password", "")):
        return JSONResponse({"ok": False}, status_code=401)
    body = await request.json()
    from tools import knowledge_base as kb
    nuevo = kb.guardar_doc(body)
    return JSONResponse({"ok": True, "doc": nuevo})


@router.post("/dashboard/api/kb/doc/{doc_id}/borrar")
async def kb_borrar_doc(doc_id: str, request: Request):
    from auth import check_password
    if not check_password(request.headers.get("X-Dashboard-Password", "")):
        return JSONResponse({"ok": False}, status_code=401)
    from tools import knowledge_base as kb
    return JSONResponse({"ok": kb.borrar_doc(doc_id)})


# ── Galería de Activos ────────────────────────────────────────────────────────

def _gal_auth(request: Request) -> bool:
    from auth import check_password
    return check_password(request.headers.get("X-Dashboard-Password", ""))


@router.post("/dashboard/api/galeria/upload")
async def galeria_upload(request: Request):
    if not _gal_auth(request):
        return JSONResponse({"ok": False, "error": "no autorizado"}, status_code=401)
    body = await request.json()
    b64  = body.get("b64", "")
    if not b64:
        return JSONResponse({"ok": False, "error": "sin imagen"})
    from tools.asset_library import guardar_imagen, guardar_imagen_ia
    try:
        if body.get("origen") == "ia":
            meta = guardar_imagen_ia(b64, body.get("descripcion", ""), body.get("etiquetas", []), body.get("mime", "image/png"))
        else:
            meta = guardar_imagen(b64, body.get("nombre", ""), body.get("etiquetas", []), body.get("descripcion", ""), body.get("mime", "image/jpeg"))
        return JSONResponse({"ok": True, "id": meta["id"]})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@router.get("/dashboard/api/galeria/imagenes")
async def galeria_listar(request: Request, etiqueta: str = ""):
    if not _gal_auth(request):
        return JSONResponse({"ok": False}, status_code=401)
    from tools.asset_library import listar_imagenes
    etiquetas = [etiqueta] if etiqueta else None
    imgs = listar_imagenes(etiquetas=etiquetas, solo_activas=True)
    # Excluimos el contenido binario de la lista — el cliente los pide por ID
    for img in imgs:
        img.pop("b64", None)
    return JSONResponse({"ok": True, "imagenes": imgs})


@router.get("/dashboard/api/galeria/imagen/{asset_id}/thumb")
async def galeria_thumb(asset_id: str, request: Request):
    """Devuelve la imagen como response de bytes (para <img src=>)."""
    if not _gal_auth(request):
        return JSONResponse({"ok": False}, status_code=401)
    from tools.asset_library import leer_imagen_b64
    import base64
    resultado = leer_imagen_b64(asset_id)
    if not resultado:
        return JSONResponse({"ok": False, "error": "no encontrada"}, status_code=404)
    b64, mime = resultado
    from fastapi.responses import Response
    return Response(content=base64.b64decode(b64), media_type=mime)


@router.post("/dashboard/api/galeria/imagen/{asset_id}/borrar")
async def galeria_borrar_imagen(asset_id: str, request: Request):
    if not _gal_auth(request):
        return JSONResponse({"ok": False}, status_code=401)
    from tools.asset_library import eliminar_imagen
    return JSONResponse({"ok": eliminar_imagen(asset_id)})


@router.post("/dashboard/api/galeria/generar-imagen")
async def galeria_generar_imagen(request: Request):
    """Genera imagen con Gemini/Cloudflare Worker sin guardarla (el usuario decide)."""
    if not _gal_auth(request):
        return JSONResponse({"ok": False, "error": "no autorizado"}, status_code=401)
    body     = await request.json()
    producto = (body.get("producto") or "piscina").lower()
    tipo     = (body.get("tipo") or "flyer").lower()
    desc     = (body.get("descripcion") or "").strip()

    _focos = {
        "piscina": "piscina de fibra de vidrio, jardín, agua turquesa, familia argentina",
        "modulo":  "módulo habitable moderno NCE, exterior prolijo, iluminación natural",
        "combo":   "combo módulo habitable con piscina de fibra, estética aspiracional",
    }
    foco = _focos.get(producto, _focos["piscina"])
    prompt = f"{foco}. {desc}".strip(". ") if desc else foco

    try:
        from tools.cloudflare_client import generar_imagen, generar_imagen_gemini
        import base64
        try:
            img_bytes = await generar_imagen(prompt, tipo)
        except Exception:
            img_bytes = await generar_imagen_gemini(prompt, tipo)

        b64  = base64.b64encode(img_bytes).decode()
        mime = "image/png"
        return JSONResponse({"ok": True, "b64": b64, "mime": mime})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


@router.get("/dashboard/api/galeria/copies")
async def galeria_listar_copies(request: Request, producto: str = "", objetivo: str = ""):
    if not _gal_auth(request):
        return JSONResponse({"ok": False}, status_code=401)
    from tools.asset_library import listar_copies
    copies = listar_copies(producto=producto or None, objetivo=objetivo or None)
    return JSONResponse({"ok": True, "copies": copies})


@router.post("/dashboard/api/galeria/copy")
async def galeria_guardar_copy(request: Request):
    if not _gal_auth(request):
        return JSONResponse({"ok": False}, status_code=401)
    body = await request.json()
    texto   = (body.get("texto") or "").strip()
    producto = (body.get("producto") or "general").strip()
    objetivo = (body.get("objetivo") or "general").strip()
    copy_id  = body.get("copy_id") or None
    if not texto:
        return JSONResponse({"ok": False, "error": "texto vacío"})
    from tools.asset_library import guardar_copy
    nuevo = guardar_copy(texto, producto, objetivo, copy_id=copy_id)
    return JSONResponse({"ok": True, "copy": nuevo})


@router.post("/dashboard/api/galeria/copy/{copy_id}/borrar")
async def galeria_borrar_copy(copy_id: str, request: Request):
    if not _gal_auth(request):
        return JSONResponse({"ok": False}, status_code=401)
    from tools.asset_library import eliminar_copy
    return JSONResponse({"ok": eliminar_copy(copy_id)})


@router.get("/dashboard/api/galeria/drive/verificar")
async def galeria_drive_verificar(request: Request):
    if not _gal_auth(request):
        return JSONResponse({"ok": False}, status_code=401)
    from tools.drive_sync import verificar_conexion_drive
    return JSONResponse(await verificar_conexion_drive())


@router.post("/dashboard/api/galeria/drive/sync")
async def galeria_drive_sync(request: Request):
    if not _gal_auth(request):
        return JSONResponse({"ok": False}, status_code=401)
    from tools.drive_sync import sincronizar_drive
    try:
        resultado = await sincronizar_drive()
        return JSONResponse(resultado)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})
