"""
EcoFiver — Sistema Multiagente IA
Entry point principal. FastAPI + Telegram + Scheduler.
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

# ── Carga de configuración (SIEMPRE PRIMERO, antes de cualquier import interno)
# En Fly.io: DATA_DIR=/data (volumen persistente)  |  Local: directorio de la app
_env_base = Path(os.getenv("DATA_DIR", "")) if os.getenv("DATA_DIR") else Path(__file__).parent
_ENV_PATH = _env_base / ".env"
if _ENV_PATH.exists():
    # IMPORTANTE: un valor VACÍO en .env NO debe pisar un secret real ya presente
    # en el entorno (ej: fly secrets). Solo overrideamos con valores no vacíos.
    from dotenv import dotenv_values as _dotenv_values
    for _k, _v in _dotenv_values(str(_ENV_PATH)).items():
        if _v is not None and _v.strip() != "":
            os.environ[_k] = _v
        elif _k not in os.environ:
            os.environ[_k] = _v or ""
else:
    load_dotenv(override=False)  # carga variables de entorno del sistema si existen
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, HTMLResponse
from pydantic import BaseModel

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Importaciones internas ──────────────────────────────────────────────────
from channels.whatsapp import router as wa_router
from channels.meta_leads import router as meta_leads_router
from channels.telegram_bot import start_telegram
from scheduler.cron import start_scheduler, stop_scheduler
from orchestrator.router import route_message
from admin_panel import router as admin_router
from dashboard import router as dashboard_router
from agent_panel import router as agent_panel_router
from tools.audit_log import leer_ultimas, leer_por_session

# ── Auto-configuración de canales Meta (FB Page + IG) ──────────────────────
async def _autoconfigurar_meta():
    """
    Detecta automáticamente META_PAGE_ID y META_IG_USER_ID usando el
    META_PAGE_ACCESS_TOKEN ya configurado. Escribe los IDs en /data/.env.
    No requiere intervención del usuario.
    """
    token = os.getenv("META_PAGE_ACCESS_TOKEN", "")
    if not token:
        logger.info("[AutoConfig] META_PAGE_ACCESS_TOKEN no configurado — saltando Meta setup")
        return

    page_id_ok = bool(os.getenv("META_PAGE_ID", ""))
    ig_id_ok   = bool(os.getenv("META_IG_USER_ID", ""))

    if page_id_ok and ig_id_ok:
        logger.info("[AutoConfig] META_PAGE_ID e META_IG_USER_ID ya configurados")
        return

    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            # Obtener lista de páginas administradas
            r = await c.get(
                "https://graph.facebook.com/v19.0/me/accounts",
                params={"access_token": token, "fields": "id,name,instagram_business_account"},
            )
            if r.status_code != 200:
                logger.warning(f"[AutoConfig] Meta /me/accounts error {r.status_code}: {r.text[:200]}")
                return

            data  = r.json()
            pages = data.get("data", [])

            if not pages:
                # Token de usuario personal, no de página — intentar con /me
                r2 = await c.get(
                    "https://graph.facebook.com/v19.0/me",
                    params={"access_token": token, "fields": "id,name"},
                )
                me = r2.json()
                logger.info(f"[AutoConfig] Token personal detectado: {me.get('name', '?')}")
                # No podemos publicar en página con token de usuario — loguear sin error
                return

        # Tomar la primera página
        pagina  = pages[0]
        page_id = pagina.get("id", "")
        ig_data = pagina.get("instagram_business_account", {})
        ig_id   = ig_data.get("id", "") if ig_data else ""

        if not ig_id and len(pages) > 0:
            # Buscar IG account con query explícita
            async with httpx.AsyncClient(timeout=15) as c:
                r3 = await c.get(
                    f"https://graph.facebook.com/v19.0/{page_id}",
                    params={
                        "access_token": token,
                        "fields":       "instagram_business_account{id,username}",
                    },
                )
                if r3.status_code == 200:
                    ig_obj = r3.json().get("instagram_business_account", {})
                    ig_id  = ig_obj.get("id", "") if ig_obj else ""

        # Escribir en /data/.env para persistencia
        nuevas_vars = {}
        if page_id and not page_id_ok:
            os.environ["META_PAGE_ID"] = page_id
            nuevas_vars["META_PAGE_ID"] = page_id
            logger.info(f"[AutoConfig] META_PAGE_ID detectado: {page_id} ({pagina.get('name', '')})")

        if ig_id and not ig_id_ok:
            os.environ["META_IG_USER_ID"] = ig_id
            nuevas_vars["META_IG_USER_ID"] = ig_id
            logger.info(f"[AutoConfig] META_IG_USER_ID detectado: {ig_id}")

        if nuevas_vars and _ENV_PATH.exists():
            _actualizar_env_file(nuevas_vars)

    except Exception as e:
        logger.warning(f"[AutoConfig] Error configurando Meta: {e}")


def _actualizar_env_file(nuevas_vars: dict):
    """Agrega o actualiza variables en /data/.env sin borrar las existentes."""
    try:
        contenido = ""
        if _ENV_PATH.exists():
            with open(_ENV_PATH, "r", encoding="utf-8") as f:
                contenido = f.read()

        for key, val in nuevas_vars.items():
            # Si ya existe la clave, reemplazar; si no, agregar al final
            import re as _re
            if _re.search(rf"^{key}=", contenido, _re.MULTILINE):
                contenido = _re.sub(rf"^{key}=.*$", f"{key}={val}", contenido, flags=_re.MULTILINE)
            else:
                contenido = contenido.rstrip("\n") + f"\n{key}={val}\n"

        with open(_ENV_PATH, "w", encoding="utf-8") as f:
            f.write(contenido)
        logger.info(f"[AutoConfig] .env actualizado con: {list(nuevas_vars.keys())}")
    except Exception as e:
        logger.warning(f"[AutoConfig] No se pudo actualizar .env: {e}")


# ── Bootstrap: crea /data/.env desde fly secrets si aún no existe ──────────
def _bootstrap_config():
    """
    Primera vez en Fly.io: si el volumen está vacío pero se pasaron secrets
    via 'fly secrets set', los escribe en el .env persistente para que el
    panel de admin los pueda leer y editar desde ahí en adelante.
    """
    if _ENV_PATH.exists():
        return
    try:
        _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        vars_to_save = [
            "AI_PROVIDER",
            "GROK_API_KEY", "XAI_API_KEY", "GROK_MODEL",
            "GEMINI_API_KEY", "GEMINI_MODEL",
            "ANTHROPIC_API_KEY", "CLAUDE_MODEL",
            "OPENAI_API_KEY", "OPENAI_MODEL",
            "CRM_BASE_URL", "CRM_API_KEY",
            "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID_RODRIGO",
            "WA_TOKEN", "WA_PHONE_ID", "WA_VERIFY_TOKEN",
            "META_PAGE_ACCESS_TOKEN", "META_APP_SECRET",
            "META_PAGE_ID", "META_IG_USER_ID",
            "GOOGLE_SERVICE_ACCOUNT_JSON", "DRIVE_GALLERY_FOLDER_ID",
            "NOTIFICATION_NUMBER",
            "BASE_URL", "PORT", "ADMIN_PASSWORD",
        ]
        # Agregar AI_PROVIDER=grok por defecto si hay GROK_API_KEY
        if os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY"):
            if not os.getenv("AI_PROVIDER"):
                os.environ["AI_PROVIDER"] = "grok"
        with open(_ENV_PATH, "w") as f:
            for key in vars_to_save:
                val = os.getenv(key, "")
                if val:
                    f.write(f"{key}={val}\n")
            # Default provider: grok si hay key
            if not os.getenv("AI_PROVIDER"):
                if os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY"):
                    f.write("AI_PROVIDER=grok\n")
        logger.info(f"[Config] .env inicializado en {_ENV_PATH}")
    except Exception as e:
        logger.warning(f"[Config] No se pudo crear .env en {_ENV_PATH.parent}: {e}")


# ── Lifespan (startup / shutdown) ──────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Iniciando EcoFiver IA — Sistema Multiagente")

    # Bootstrap config persistente (primera vez en Fly.io)
    _bootstrap_config()

    # Auto-configurar canales Meta (Page ID + IG User ID) desde token existente
    await _autoconfigurar_meta()

    # Iniciar scheduler de tareas programadas
    start_scheduler()
    logger.info("⏰ Scheduler iniciado")

    # Iniciar bot de Telegram en background
    asyncio.create_task(start_telegram())
    logger.info("📱 Bot Telegram iniciado en background")

    # Iniciar polling de email en background (si hay credenciales configuradas)
    try:
        from channels.email_channel import iniciar_polling_email
        asyncio.create_task(iniciar_polling_email())
        logger.info("📧 Polling de email iniciado en background")
    except Exception as e:
        logger.warning(f"Canal email no iniciado: {e}")

    yield

    # Shutdown
    stop_scheduler()
    logger.info("Sistema EcoFiver IA apagado correctamente.")


# ── App FastAPI ────────────────────────────────────────────────────────────
app = FastAPI(
    title="EcoFiver — Sistema IA",
    description=(
        "Sistema multiagente con 16 agentes IA para "
        "EcoFiver. WhatsApp + Instagram + Web + Telegram."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

# CORS — necesario para el widget embebido en la landing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Routers externos ───────────────────────────────────────────────────────
app.include_router(wa_router)
app.include_router(meta_leads_router)
app.include_router(admin_router)
app.include_router(dashboard_router)
app.include_router(agent_panel_router)


# ── Modelos Pydantic ───────────────────────────────────────────────────────
class WebChatRequest(BaseModel):
    session_id: str
    message: str


class WebChatResponse(BaseModel):
    reply: str
    agent: str


# ── Endpoint: Widget web ───────────────────────────────────────────────────
@app.post("/chat/web", response_model=WebChatResponse)
async def web_chat(body: WebChatRequest):
    """
    Endpoint del widget de chat embebido en la landing page.
    Recibe mensajes del visitante y devuelve respuesta de Valentina
    (o el agente al que haya sido derivado).
    """
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Mensaje vacío")

    result = await route_message(
        canal="web",
        session_id=body.session_id,
        mensaje=body.message.strip(),
        msg_type="text",
    )
    return WebChatResponse(
        reply=result["reply"],
        agent=result["agent"],
    )


# ── Lead generation endpoints ────────────────────────────────────────────
@app.post("/leadgen/scraping/trigger")
async def trigger_scraping():
    """Dispara manualmente un ciclo de scraping orgánico."""
    try:
        from tools.lead_scraper import ejecutar_ciclo_scraping
        resumen = await ejecutar_ciclo_scraping()
        return {"status": "ok", "resumen": resumen}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/leadgen/content/publish")
async def trigger_content():
    """Dispara manualmente la publicación de contenido del día."""
    try:
        from tools.content_poster import generar_contenido, publicar_facebook
        contenido = await generar_contenido()
        if not contenido:
            return {"status": "error", "detail": "No se pudo generar contenido"}
        ok = await publicar_facebook(contenido["texto_fb"])
        return {"status": "ok", "publicado": ok, "preview": contenido["texto_fb"][:200]}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/leadgen/status")
async def leadgen_status():
    """Estado del sistema de generación de leads."""
    import os
    return {
        "canales_activos": {
            "whatsapp":   bool(os.getenv("WA_TOKEN")),
            "telegram":   bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "instagram":  bool(os.getenv("META_PAGE_ACCESS_TOKEN")),
            "email":      bool(os.getenv("EMAIL_USER") and os.getenv("EMAIL_PASSWORD")),
            "facebook_posts": bool(os.getenv("META_PAGE_ACCESS_TOKEN") and os.getenv("META_PAGE_ID")),
        },
        "scraping": {
            "mercadolibre": True,
            "olx":          True,
            "clasificados": True,
        },
        "ultimo_scraping": _ultimo_scraping_resumen(),
        "scheduler": "activo",
    }


def _ultimo_scraping_resumen():
    try:
        from tools.lead_scraper import get_ultimo_resumen
        return get_ultimo_resumen()
    except Exception:
        return {}


# ── Audit log endpoints ───────────────────────────────────────────────────
@app.get("/audit/log")
async def audit_log_recientes(n: int = 50):
    """Últimas N interacciones de todos los agentes (default 50)."""
    return {"entries": leer_ultimas(n), "total": n}


@app.get("/audit/session/{session_id}")
async def audit_log_session(session_id: str, n: int = 100):
    """Historial de auditoría de una sesión específica."""
    return {"session_id": session_id, "entries": leer_por_session(session_id, n)}


# ── Servir archivos del widget ────────────────────────────────────────────
WIDGET_DIR = os.path.join(os.path.dirname(__file__), "web_widget")


@app.get("/web_widget/chat.js")
async def serve_widget_js():
    path = os.path.join(WIDGET_DIR, "chat.js")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="chat.js no encontrado")
    return FileResponse(path, media_type="application/javascript")


@app.get("/web_widget/chat.css")
async def serve_widget_css():
    path = os.path.join(WIDGET_DIR, "chat.css")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="chat.css no encontrado")
    return FileResponse(path, media_type="text/css")


# ── Página de inicio ──────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EcoFiver — Sistema IA</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #f0f7f3;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }
    .card {
      background: white;
      border-radius: 16px;
      box-shadow: 0 4px 24px rgba(26,92,56,0.12);
      padding: 48px 40px;
      max-width: 560px;
      width: 100%;
      text-align: center;
    }
    .logo { font-size: 52px; margin-bottom: 16px; }
    h1 { color: #1A5C38; font-size: 22px; font-weight: 700; margin-bottom: 6px; }
    .sub { color: #666; font-size: 14px; margin-bottom: 32px; }
    .badge {
      display: inline-block;
      background: #e8f5ee;
      color: #1A5C38;
      border-radius: 20px;
      padding: 6px 16px;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 32px;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 32px;
      text-align: left;
    }
    .item {
      background: #f8faf8;
      border-radius: 10px;
      padding: 14px;
      border-left: 3px solid #1A5C38;
    }
    .item-icon { font-size: 20px; margin-bottom: 4px; }
    .item-label { font-size: 11px; color: #999; text-transform: uppercase; letter-spacing: .5px; }
    .item-value { font-size: 14px; color: #222; font-weight: 600; margin-top: 2px; }
    .endpoints { text-align: left; margin-bottom: 28px; }
    .endpoints h3 { font-size: 12px; color: #999; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 10px; }
    .ep {
      display: flex; align-items: center; gap: 10px;
      padding: 8px 0; border-bottom: 1px solid #f0f0f0; font-size: 13px;
    }
    .ep:last-child { border-bottom: none; }
    .method {
      font-size: 10px; font-weight: 700; padding: 2px 7px;
      border-radius: 4px; flex-shrink: 0;
    }
    .get  { background: #e3f2fd; color: #1565c0; }
    .post { background: #e8f5e9; color: #2e7d32; }
    .ep-path { color: #333; font-family: monospace; }
    .ep-desc { color: #888; font-size: 12px; margin-left: auto; }
    .btn {
      display: inline-block;
      background: #1A5C38;
      color: white;
      text-decoration: none;
      padding: 11px 28px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      transition: background .2s;
    }
    .btn:hover { background: #145030; }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🌿</div>
    <h1>EcoFiver</h1>
    <p class="sub">Sistema Multiagente IA — v1.0.0</p>
    <span class="badge">✅ Sistema operativo</span>

    <div class="grid">
      <div class="item">
        <div class="item-icon">🤖</div>
        <div class="item-label">Agentes activos</div>
        <div class="item-value">16 agentes IA</div>
      </div>
      <div class="item">
        <div class="item-icon">🏊</div>
        <div class="item-label">Catálogo</div>
        <div class="item-value">16 modelos piscinas</div>
      </div>
      <div class="item">
        <div class="item-icon">🏠</div>
        <div class="item-label">Módulos NCE</div>
        <div class="item-value">6m² a 72m²</div>
      </div>
      <div class="item">
        <div class="item-icon">💳</div>
        <div class="item-label">Financiación</div>
        <div class="item-value">Hasta 120 cuotas</div>
      </div>
    </div>

    <div class="endpoints">
      <h3>Endpoints disponibles</h3>
      <div class="ep">
        <span class="method post">POST</span>
        <span class="ep-path">/chat/web</span>
        <span class="ep-desc">Widget chat</span>
      </div>
      <div class="ep">
        <span class="method post">POST</span>
        <span class="ep-path">/webhook/whatsapp</span>
        <span class="ep-desc">Meta Business</span>
      </div>
      <div class="ep">
        <span class="method post">POST</span>
        <span class="ep-path">/webhook/meta</span>
        <span class="ep-desc">Lead Ads + Instagram</span>
      </div>
      <div class="ep">
        <span class="method get">GET</span>
        <span class="ep-path">/web_widget/chat.js</span>
        <span class="ep-desc">Widget embebible</span>
      </div>
      <div class="ep">
        <span class="method get">GET</span>
        <span class="ep-path">/health</span>
        <span class="ep-desc">Health check</span>
      </div>
      <div class="ep">
        <span class="method get">GET</span>
        <span class="ep-path">/widget-snippet</span>
        <span class="ep-desc">HTML para landing</span>
      </div>
    </div>

    <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
      <a href="/dashboard" class="btn">📊 Dashboard</a>
      <a href="/panel" class="btn" style="background:#2e7d32">💬 Comandar Agentes</a>
      <a href="/admin" class="btn" style="background:#444">⚙️ Configurar APIs</a>
    </div>
  </div>
</body>
</html>
"""


# ── Política de Privacidad (requerida por Meta para modo Live) ────────────
@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    return """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Política de Privacidad — EcoFiver</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           max-width: 800px; margin: 0 auto; padding: 40px 24px; color: #222; line-height: 1.7; }
    h1 { color: #1A5C38; margin-bottom: 8px; }
    h2 { color: #1A5C38; margin-top: 32px; font-size: 18px; }
    p, li { color: #444; font-size: 15px; }
    ul { padding-left: 20px; }
    .updated { color: #888; font-size: 13px; margin-bottom: 32px; }
    a { color: #1A5C38; }
  </style>
</head>
<body>
  <h1>🌿 Política de Privacidad</h1>
  <p class="updated">Última actualización: mayo de 2026</p>

  <p><strong>EcoFiver</strong> ("nosotros") opera un sistema de atención al cliente
  mediante WhatsApp Business API. Esta política explica cómo recopilamos, usamos y protegemos
  tu información personal.</p>

  <h2>1. Información que recopilamos</h2>
  <ul>
    <li>Número de teléfono de WhatsApp</li>
    <li>Mensajes de texto, audio e imágenes que nos envíes</li>
    <li>Nombre de perfil de WhatsApp (si está disponible)</li>
    <li>Datos de consultas sobre productos y servicios</li>
  </ul>

  <h2>2. Cómo usamos tu información</h2>
  <ul>
    <li>Responder consultas sobre nuestros productos y servicios</li>
    <li>Gestionar presupuestos, pedidos y seguimiento post-venta</li>
    <li>Mejorar la calidad de nuestro servicio al cliente</li>
    <li>Enviar información relevante sobre nuestros productos (solo si lo solicitaste)</li>
  </ul>

  <h2>3. Compartición de datos</h2>
  <p>No vendemos ni compartimos tu información personal con terceros, excepto cuando sea
  requerido por ley o necesario para prestar el servicio (por ejemplo, proveedores de tecnología
  como Meta/WhatsApp Business API y servicios de IA para procesar consultas).</p>

  <h2>4. Retención de datos</h2>
  <p>Conservamos los datos de conversación durante 12 meses para poder brindar seguimiento
  adecuado. Podés solicitar la eliminación de tus datos en cualquier momento.</p>

  <h2>5. Tus derechos</h2>
  <ul>
    <li>Acceder a la información que tenemos sobre vos</li>
    <li>Solicitar la corrección o eliminación de tus datos</li>
    <li>Dejar de recibir mensajes en cualquier momento (respondiendo "STOP")</li>
  </ul>

  <h2>6. Seguridad</h2>
  <p>Implementamos medidas de seguridad técnicas y organizativas para proteger tu información
  contra acceso no autorizado, pérdida o alteración.</p>

  <h2>7. Contacto</h2>
  <p>Para consultas sobre privacidad o para ejercer tus derechos, contactanos por WhatsApp
  o por correo electrónico. Respondemos en un plazo máximo de 48 horas hábiles.</p>

  <h2>8. Cambios a esta política</h2>
  <p>Podemos actualizar esta política periódicamente. Te notificaremos sobre cambios
  significativos a través de nuestros canales de comunicación habituales.</p>

  <hr style="margin-top:40px;border:none;border-top:1px solid #eee">
  <p style="font-size:13px;color:#888;text-align:center">
    &copy; 2026 EcoFiver — Todos los derechos reservados
  </p>
</body>
</html>"""


# ── Health check ──────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Health check para Replit / Fly.io."""
    return {
        "status": "ok",
        "sistema": "EcoFiver IA",
        "agentes": 16,
        "version": "1.0.0",
    }


# ── Snippet de embebido (para copiar en la landing) ───────────────────────
@app.get("/widget-snippet", response_class=PlainTextResponse)
async def widget_snippet():
    base_url = os.getenv("BASE_URL", "https://TU-URL.replit.app")
    snippet = f"""<!-- EcoFiver — Widget de Chat -->
<script>
  window.ECO_CHAT_URL = '{base_url}/chat/web';
  window.ECO_WIDGET_BASE = '{base_url}';
</script>
<script src="{base_url}/web_widget/chat.js" defer></script>
<!-- Fin Widget -->"""
    return snippet


# ── Entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=False,
        log_level="info",
    )
