"""
Panel de configuración del sistema EcoFiver IA.
Soporta Gemini, Claude (Anthropic) y OpenAI con toggle de proveedor activo.
"""
import os
import logging
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv, dotenv_values, set_key

logger = logging.getLogger(__name__)
router = APIRouter()

# Ruta del .env: usa DATA_DIR si está definida (Fly.io volume), si no usa el directorio de la app
_env_base = Path(os.getenv("DATA_DIR", "")) if os.getenv("DATA_DIR") else Path(__file__).parent
ENV_PATH  = _env_base / ".env"

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ecomodulos2026")


def read_env() -> dict:
    if ENV_PATH.exists():
        return dict(dotenv_values(ENV_PATH))
    return {}


def save_env(values: dict):
    """Guarda variables en el .env. Crea el directorio si no existe."""
    try:
        ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"[admin] No se pudo crear directorio {ENV_PATH.parent}: {e}")
    if not ENV_PATH.exists():
        ENV_PATH.write_text("")
    for key, value in values.items():
        if value is not None:
            set_key(str(ENV_PATH), key, value)
    load_dotenv(str(ENV_PATH), override=True)
    # Resetear cache de providers para reflejar cambios en runtime
    try:
        from providers.factory import reset_provider_cache
        reset_provider_cache()
    except Exception:
        pass


def _dot(key, env):
    return '<span class="dot-ok">●</span>' if env.get(key) else '<span class="dot-empty">●</span>'


def render_panel(env: dict, msg: str = "", msg_type: str = "ok") -> str:
    def val(k): return env.get(k, "") or ""

    active_provider = val("AI_PROVIDER") or ("openrouter" if val("OPENROUTER_API_KEY") else "grok" if val("GROK_API_KEY") or val("XAI_API_KEY") else "gemini")
    msg_html = ""
    if msg:
        color = "#2e7d32" if msg_type == "ok" else "#c62828"
        bg    = "#e8f5e9" if msg_type == "ok" else "#ffebee"
        msg_html = f'<div class="msg" style="background:{bg};color:{color}">{msg}</div>'

    def provider_tab(pid, label, emoji):
        active = "active" if active_provider == pid else ""
        return f'<button type="button" class="ptab {active}" onclick="selectProvider(\'{pid}\')" data-p="{pid}">{emoji} {label}</button>'

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Config — EcoFiver IA</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          background:#f0f7f3;min-height:100vh;padding:24px}}
    .header{{background:#1A5C38;color:white;border-radius:12px;
             padding:20px 28px;margin-bottom:24px;display:flex;align-items:center;gap:12px}}
    .header h1{{font-size:18px;font-weight:700}}
    .header p{{font-size:13px;opacity:.8;margin-top:2px}}
    .card{{background:white;border-radius:12px;
           box-shadow:0 2px 12px rgba(0,0,0,.07);margin-bottom:20px;overflow:hidden}}
    .card-header{{background:#f8faf8;border-bottom:1px solid #eee;
                  padding:14px 20px;display:flex;align-items:center;gap:10px}}
    .card-header h2{{font-size:14px;font-weight:700;color:#1A5C38}}
    .card-body{{padding:20px}}
    .row{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}}
    .row.one{{grid-template-columns:1fr}}
    .field label{{display:block;font-size:11px;font-weight:700;color:#666;
                  text-transform:uppercase;letter-spacing:.5px;margin-bottom:5px}}
    .field input,.field select{{width:100%;border:1.5px solid #dde;border-radius:8px;
                  padding:9px 12px;font-size:13px;outline:none;
                  transition:border .2s;background:#fafafa;font-family:monospace}}
    .field input:focus,.field select:focus{{border-color:#1A5C38;background:white}}
    .field .hint{{font-size:11px;color:#999;margin-top:4px}}
    .test-btn{{display:inline-flex;align-items:center;gap:6px;
               background:#f0f7f3;border:1.5px solid #1A5C38;color:#1A5C38;
               border-radius:6px;padding:5px 12px;font-size:12px;font-weight:600;
               cursor:pointer;margin-top:8px;transition:all .2s}}
    .test-btn:hover{{background:#1A5C38;color:white}}
    .test-result{{margin-top:6px;font-size:12px;padding:6px 10px;
                  border-radius:6px;display:none}}
    .msg{{padding:12px 16px;border-radius:8px;margin-bottom:20px;font-size:14px;font-weight:600}}
    .save-bar{{position:sticky;bottom:0;background:white;border-top:1px solid #eee;
               padding:16px 0;display:flex;gap:12px;align-items:center}}
    .btn-save{{background:#1A5C38;color:white;border:none;border-radius:8px;
               padding:12px 32px;font-size:14px;font-weight:700;cursor:pointer}}
    .btn-save:hover{{background:#145030}}
    .btn-back{{background:white;color:#1A5C38;border:1.5px solid #1A5C38;
               border-radius:8px;padding:11px 20px;font-size:14px;font-weight:600;
               cursor:pointer;text-decoration:none;display:inline-block}}
    .dot-ok{{color:#43a047;font-size:10px}}
    .dot-empty{{color:#e53935;font-size:10px}}

    /* Provider toggle */
    .provider-toggle{{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}}
    .ptab{{flex:1;min-width:140px;padding:14px 10px;border-radius:10px;
           border:2px solid #dde;background:white;cursor:pointer;
           font-size:14px;font-weight:600;color:#666;transition:all .2s;text-align:center}}
    .ptab:hover{{border-color:#1A5C38;color:#1A5C38}}
    .ptab.active{{border-color:#1A5C38;background:#1A5C38;color:white}}
    .ptab.has-key{{border-color:#43a047}}
    .ptab.active.has-key{{background:#1A5C38;border-color:#1A5C38}}
    .provider-section{{display:none}}
    .provider-section.active{{display:block}}
    .active-badge{{display:inline-block;background:#e8f5e9;color:#2e7d32;
                   border-radius:20px;padding:3px 10px;font-size:11px;font-weight:700;
                   margin-left:8px}}

    @media(max-width:600px){{.row{{grid-template-columns:1fr}}}}
  </style>
</head>
<body>

<div class="header">
  <span style="font-size:28px">⚙️</span>
  <div>
    <h1>Panel de Configuración — EcoFiver IA</h1>
    <p>Configurá todas las integraciones. Los cambios se aplican inmediatamente.</p>
  </div>
</div>

{msg_html}

<form method="POST" action="/admin/save" id="configForm">
  <input type="hidden" name="admin_password" id="admin_password" value="">
  <input type="hidden" name="AI_PROVIDER" id="ai_provider_input" value="{active_provider}">

  <!-- ── PROVEEDOR DE IA ── -->
  <div class="card">
    <div class="card-header">
      <span>🤖</span>
      <div><h2>Proveedor de Inteligencia Artificial</h2></div>
    </div>
    <div class="card-body">
      <p style="font-size:13px;color:#666;margin-bottom:16px">
        Seleccioná el proveedor activo. Podés guardar keys de los tres y cambiar con un click.
        El que esté marcado en verde es el que usan los agentes ahora mismo.
      </p>

      <div class="provider-toggle">
        {provider_tab("openrouter", "OpenRouter ⭐", "🌐")}
        {provider_tab("grok", "Grok (xAI)", "🔵")}
        {provider_tab("gemini", "Google Gemini", "🟢")}
        {provider_tab("claude", "Claude (Anthropic)", "🟣")}
        {provider_tab("openai", "OpenAI (GPT)", "⚫")}
      </div>

      <!-- OpenRouter -->
      <div class="provider-section {'active' if active_provider == 'openrouter' else ''}" id="section-openrouter">
        <div class="row one">
          <div class="field">
            <label>OPENROUTER_API_KEY {_dot('OPENROUTER_API_KEY', env)}</label>
            <input type="password" name="OPENROUTER_API_KEY"
                   value="{val('OPENROUTER_API_KEY')}" placeholder="sk-or-v1-...">
            <div class="hint">
              <a href="https://openrouter.ai/keys" target="_blank">openrouter.ai/keys</a>
              → Acceso a GPT, Claude, Llama, Gemini y más con una sola key
            </div>
          </div>
        </div>
        <div class="row one">
          <div class="field">
            <label>Modelo OpenRouter</label>
            <select name="OPENROUTER_MODEL">
              <option value="openai/gpt-4o-mini" {'selected' if val('OPENROUTER_MODEL') in ('','openai/gpt-4o-mini') else ''}>openai/gpt-4o-mini — rápido y económico (recomendado)</option>
              <option value="openai/gpt-4o" {'selected' if val('OPENROUTER_MODEL') == 'openai/gpt-4o' else ''}>openai/gpt-4o — máxima calidad OpenAI</option>
              <option value="openai/chatgpt-4o-latest" {'selected' if val('OPENROUTER_MODEL') == 'openai/chatgpt-4o-latest' else ''}>openai/chatgpt-4o-latest — versión más reciente</option>
              <option value="anthropic/claude-3-haiku" {'selected' if val('OPENROUTER_MODEL') == 'anthropic/claude-3-haiku' else ''}>anthropic/claude-3-haiku — económico de Anthropic</option>
              <option value="google/gemini-flash-1.5" {'selected' if val('OPENROUTER_MODEL') == 'google/gemini-flash-1.5' else ''}>google/gemini-flash-1.5 — Gemini vía OpenRouter</option>
              <option value="meta-llama/llama-3.1-70b-instruct" {'selected' if val('OPENROUTER_MODEL') == 'meta-llama/llama-3.1-70b-instruct' else ''}>meta-llama/llama-3.1-70b-instruct — open source</option>
            </select>
          </div>
        </div>
        <button type="button" class="test-btn" onclick="testApi('openrouter')">▶ Probar OpenRouter</button>
        <div class="test-result" id="test-openrouter"></div>
      </div>

      <!-- Grok -->
      <div class="provider-section {'active' if active_provider == 'grok' else ''}" id="section-grok">
        <div class="row one">
          <div class="field">
            <label>GROK_API_KEY {_dot('GROK_API_KEY', env)}</label>
            <input type="password" name="GROK_API_KEY"
                   value="{val('GROK_API_KEY') or val('XAI_API_KEY')}" placeholder="xai-...">
            <div class="hint">
              <a href="https://console.x.ai/" target="_blank">console.x.ai</a>
              → API Keys · Modelo: <strong>grok-3-mini</strong>
              · Compatible con OpenAI API · Gratis hasta $25/mes para nuevas cuentas
            </div>
          </div>
        </div>
        <div class="row one">
          <div class="field">
            <label>Modelo Grok</label>
            <select name="GROK_MODEL">
              <option value="grok-3-mini" {'selected' if val('GROK_MODEL') in ('','grok-3-mini') else ''}>grok-3-mini — rápido y económico (recomendado)</option>
              <option value="grok-3" {'selected' if val('GROK_MODEL') == 'grok-3' else ''}>grok-3 — máxima calidad</option>
            </select>
          </div>
        </div>
        <button type="button" class="test-btn" onclick="testApi('grok')">▶ Probar Grok</button>
        <div class="test-result" id="test-grok"></div>
      </div>

      <!-- Gemini -->
      <div class="provider-section {'active' if active_provider == 'gemini' else ''}" id="section-gemini">
        <div class="row one">
          <div class="field">
            <label>GEMINI_API_KEY {_dot('GEMINI_API_KEY', env)}</label>
            <input type="password" name="GEMINI_API_KEY"
                   value="{val('GEMINI_API_KEY')}" placeholder="AIzaSy...">
            <div class="hint">
              <a href="https://aistudio.google.com/app/apikey" target="_blank">aistudio.google.com</a>
              → Get API Key · Modelo: <strong>gemini-2.0-flash</strong>
              · Precio: $0.075/MTok entrada (o gratis con límite)
            </div>
          </div>
        </div>
        <div class="row one">
          <div class="field">
            <label>Modelo Gemini</label>
            <select name="GEMINI_MODEL">
              <option value="gemini-2.0-flash" {'selected' if val('GEMINI_MODEL') in ('','gemini-2.0-flash') else ''}>gemini-2.0-flash (recomendado)</option>
              <option value="gemini-1.5-flash" {'selected' if val('GEMINI_MODEL') == 'gemini-1.5-flash' else ''}>gemini-1.5-flash</option>
              <option value="gemini-1.5-pro" {'selected' if val('GEMINI_MODEL') == 'gemini-1.5-pro' else ''}>gemini-1.5-pro (más lento)</option>
            </select>
          </div>
        </div>
        <button type="button" class="test-btn" onclick="testApi('gemini')">▶ Probar Gemini</button>
        <div class="test-result" id="test-gemini"></div>
      </div>

      <!-- Claude -->
      <div class="provider-section {'active' if active_provider == 'claude' else ''}" id="section-claude">
        <div class="row one">
          <div class="field">
            <label>ANTHROPIC_API_KEY {_dot('ANTHROPIC_API_KEY', env)}</label>
            <input type="password" name="ANTHROPIC_API_KEY"
                   value="{val('ANTHROPIC_API_KEY')}" placeholder="sk-ant-api03-...">
            <div class="hint">
              <a href="https://console.anthropic.com/settings/keys" target="_blank">console.anthropic.com</a>
              → API Keys · Modelo: <strong>claude-haiku-20240307</strong>
              · Precio: $0.25/MTok entrada · Free tier: $5 de crédito al crear cuenta
            </div>
          </div>
        </div>
        <div class="row one">
          <div class="field">
            <label>Modelo Claude</label>
            <select name="CLAUDE_MODEL">
              <option value="claude-haiku-20240307" {'selected' if val('CLAUDE_MODEL') in ('','claude-haiku-20240307') else ''}>claude-haiku-20240307 — más rápido y barato</option>
              <option value="claude-3-5-haiku-20241022" {'selected' if val('CLAUDE_MODEL') == 'claude-3-5-haiku-20241022' else ''}>claude-3-5-haiku-20241022 — mejor calidad</option>
              <option value="claude-3-5-sonnet-20241022" {'selected' if val('CLAUDE_MODEL') == 'claude-3-5-sonnet-20241022' else ''}>claude-3-5-sonnet-20241022 — top calidad</option>
            </select>
          </div>
        </div>
        <button type="button" class="test-btn" onclick="testApi('claude')">▶ Probar Claude</button>
        <div class="test-result" id="test-claude"></div>
      </div>

      <!-- OpenAI -->
      <div class="provider-section {'active' if active_provider == 'openai' else ''}" id="section-openai">
        <div class="row one">
          <div class="field">
            <label>OPENAI_API_KEY {_dot('OPENAI_API_KEY', env)}</label>
            <input type="password" name="OPENAI_API_KEY"
                   value="{val('OPENAI_API_KEY')}" placeholder="sk-proj-...">
            <div class="hint">
              <a href="https://platform.openai.com/api-keys" target="_blank">platform.openai.com</a>
              → API Keys · Modelo: <strong>gpt-4o-mini</strong>
              · Precio: $0.15/MTok entrada · Free tier: $5 de crédito al crear cuenta
            </div>
          </div>
        </div>
        <div class="row one">
          <div class="field">
            <label>Modelo OpenAI</label>
            <select name="OPENAI_MODEL">
              <option value="gpt-4o-mini" {'selected' if val('OPENAI_MODEL') in ('','gpt-4o-mini') else ''}>gpt-4o-mini — más barato (recomendado)</option>
              <option value="gpt-4o" {'selected' if val('OPENAI_MODEL') == 'gpt-4o' else ''}>gpt-4o — mejor calidad</option>
              <option value="gpt-3.5-turbo" {'selected' if val('OPENAI_MODEL') == 'gpt-3.5-turbo' else ''}>gpt-3.5-turbo — legacy</option>
            </select>
          </div>
        </div>
        <button type="button" class="test-btn" onclick="testApi('openai')">▶ Probar OpenAI</button>
        <div class="test-result" id="test-openai"></div>
      </div>

    </div>
  </div>

  <!-- ── CRM ── -->
  <div class="card">
    <div class="card-header"><span>🗄️</span><div><h2>CRM EcoFiver</h2></div></div>
    <div class="card-body">
      <div class="row">
        <div class="field">
          <label>CRM_BASE_URL {_dot('CRM_BASE_URL', env)}</label>
          <input type="text" name="CRM_BASE_URL"
                 value="{val('CRM_BASE_URL')}" placeholder="https://eco-crm-dawn-fog-5476.fly.dev">
          <div class="hint">URL del CRM en Fly.io</div>
        </div>
        <div class="field">
          <label>CRM_API_KEY {_dot('CRM_API_KEY', env)}</label>
          <input type="password" name="CRM_API_KEY"
                 value="{val('CRM_API_KEY')}" placeholder="tu-clave-secreta">
        </div>
      </div>
      <button type="button" class="test-btn" onclick="testApi('crm')">▶ Probar CRM</button>
      <div class="test-result" id="test-crm"></div>
    </div>
  </div>

  <!-- ── WHATSAPP ── -->
  <div class="card">
    <div class="card-header"><span>💬</span><div><h2>WhatsApp Business API (Meta)</h2></div></div>
    <div class="card-body">
      <div class="row">
        <div class="field">
          <label>WA_TOKEN {_dot('WA_TOKEN', env)}</label>
          <input type="password" name="WA_TOKEN"
                 value="{val('WA_TOKEN')}" placeholder="EAABm0...">
          <div class="hint">Meta Business → WhatsApp → API Setup → Token de acceso permanente</div>
        </div>
        <div class="field">
          <label>WA_PHONE_ID {_dot('WA_PHONE_ID', env)}</label>
          <input type="text" name="WA_PHONE_ID"
                 value="{val('WA_PHONE_ID')}" placeholder="123456789012345">
          <div class="hint">Meta Business → WhatsApp → API Setup → Phone Number ID</div>
        </div>
      </div>
      <div class="row one">
        <div class="field">
          <label>WA_VERIFY_TOKEN</label>
          <input type="text" name="WA_VERIFY_TOKEN"
                 value="{val('WA_VERIFY_TOKEN') or 'eco_modules_verify_2026'}">
          <div class="hint">Token de verificación del webhook — copiá este valor en Meta Business</div>
        </div>
      </div>
      <button type="button" class="test-btn" onclick="testApi('whatsapp')">▶ Probar WhatsApp</button>
      <div class="test-result" id="test-whatsapp"></div>
    </div>
  </div>

  <!-- ── TELEGRAM ── -->
  <div class="card">
    <div class="card-header"><span>📱</span><div><h2>Telegram</h2></div></div>
    <div class="card-body">
      <div class="row">
        <div class="field">
          <label>TELEGRAM_BOT_TOKEN {_dot('TELEGRAM_BOT_TOKEN', env)}</label>
          <input type="password" name="TELEGRAM_BOT_TOKEN"
                 value="{val('TELEGRAM_BOT_TOKEN')}" placeholder="1234567890:AAF...">
          <div class="hint">@BotFather → /newbot</div>
        </div>
        <div class="field">
          <label>TELEGRAM_CHAT_ID_RODRIGO {_dot('TELEGRAM_CHAT_ID_RODRIGO', env)}</label>
          <input type="text" name="TELEGRAM_CHAT_ID_RODRIGO"
                 value="{val('TELEGRAM_CHAT_ID_RODRIGO')}" placeholder="123456789">
          <div class="hint">@userinfobot → te manda tu ID</div>
        </div>
      </div>
      <button type="button" class="test-btn" onclick="testApi('telegram')">▶ Probar Telegram</button>
      <div class="test-result" id="test-telegram"></div>
    </div>
  </div>

  <!-- ── CLOUDFLARE ── -->
  <div class="card">
    <div class="card-header"><span>☁️</span><div><h2>Cloudflare Workers</h2></div></div>
    <div class="card-body">
      <div class="row one">
        <div class="field">
          <label>CLOUDFLARE_WORKER_URL {_dot('CLOUDFLARE_WORKER_URL', env)}</label>
          <input type="text" name="CLOUDFLARE_WORKER_URL"
                 value="{val('CLOUDFLARE_WORKER_URL') or 'https://eco-agentes.growersb.workers.dev'}"
                 placeholder="https://eco-agentes.TU-USUARIO.workers.dev">
        </div>
      </div>
      <button type="button" class="test-btn" onclick="testApi('cloudflare')">▶ Probar Worker</button>
      <div class="test-result" id="test-cloudflare"></div>
    </div>
  </div>

  <!-- ── CONFIG WEB ── -->
  <div class="card">
    <div class="card-header"><span>🌐</span><div><h2>Configuración General</h2></div></div>
    <div class="card-body">
      <div class="row">
        <div class="field">
          <label>BASE_URL {_dot('BASE_URL', env)}</label>
          <input type="text" name="BASE_URL"
                 value="{val('BASE_URL')}" placeholder="https://eco-multiagente-polished-sunset-4227.fly.dev">
        </div>
        <div class="field">
          <label>GOOGLE_DRIVE_FOLDER_ID {_dot('GOOGLE_DRIVE_FOLDER_ID', env)}</label>
          <input type="text" name="GOOGLE_DRIVE_FOLDER_ID"
                 value="{val('GOOGLE_DRIVE_FOLDER_ID') or '1tXwe5E9M7R31Q8X-fMhpmn-TgVWPak4W'}">
        </div>
      </div>
      <div class="row">
        <div class="field">
          <label>ADMIN_PASSWORD — Rodrigo (dejá vacío para no cambiarla)</label>
          <input type="password" name="ADMIN_PASSWORD" value="" placeholder="Nueva contraseña Rodrigo...">
          <div class="hint">Acceso total: config, agentes, dashboard</div>
        </div>
        <div class="field">
          <label>RENZO_PASSWORD — Renzo (dejá vacío para no cambiarla)</label>
          <input type="password" name="RENZO_PASSWORD" value="" placeholder="Nueva contraseña Renzo...">
          <div class="hint">Acceso operativo: agentes y dashboard (sin cambiar APIs)</div>
        </div>
      </div>
    </div>
  </div>

  <div class="save-bar">
    <a href="/" class="btn-back">← Volver</a>
    <button type="button" class="btn-save" onclick="guardar()">💾 Guardar configuración</button>
    <span id="save-status" style="font-size:13px;color:#666"></span>
  </div>
</form>

<script>
const PASSWORD_KEY = 'eco_admin_pw';

window.onload = function() {{
  const pw = sessionStorage.getItem(PASSWORD_KEY);
  if (!pw) {{ window.location.href = '/admin'; return; }}
  document.getElementById('admin_password').value = pw;

  // Marcar tabs que tienen key configurada
  ['openrouter','grok','gemini','claude','openai'].forEach(p => {{
    const keyMap = {{openrouter:'OPENROUTER_API_KEY', grok:'GROK_API_KEY', gemini:'GEMINI_API_KEY', claude:'ANTHROPIC_API_KEY', openai:'OPENAI_API_KEY'}};
    const inp = document.querySelector(`[name="${{keyMap[p]}}"]`);
    if (inp && inp.value) {{
      document.querySelector(`.ptab[data-p="${{p}}"]`)?.classList.add('has-key');
    }}
  }});
}};

function selectProvider(pid) {{
  document.querySelectorAll('.ptab').forEach(b => b.classList.remove('active'));
  document.querySelector(`.ptab[data-p="${{pid}}"]`).classList.add('active');
  document.querySelectorAll('.provider-section').forEach(s => s.classList.remove('active'));
  document.getElementById('section-' + pid).classList.add('active');
  document.getElementById('ai_provider_input').value = pid;
}}

function guardar() {{
  const pw = sessionStorage.getItem(PASSWORD_KEY) || '';
  document.getElementById('admin_password').value = pw;
  document.getElementById('save-status').textContent = 'Guardando...';
  document.getElementById('configForm').submit();
}}

async function testApi(servicio) {{
  const btn = event.target;
  const resultEl = document.getElementById('test-' + servicio);
  const origText = btn.textContent;
  btn.textContent = '⏳ Probando...';
  btn.disabled = true;
  resultEl.style.display = 'none';

  const pw = sessionStorage.getItem(PASSWORD_KEY) || '';
  const body = {{
    admin_password: pw,
    OPENROUTER_API_KEY:     document.querySelector('[name=OPENROUTER_API_KEY]')?.value || '',
    OPENROUTER_MODEL:       document.querySelector('[name=OPENROUTER_MODEL]')?.value || '',
    GROK_API_KEY:           document.querySelector('[name=GROK_API_KEY]')?.value || '',
    GROK_MODEL:             document.querySelector('[name=GROK_MODEL]')?.value || '',
    GEMINI_API_KEY:         document.querySelector('[name=GEMINI_API_KEY]')?.value || '',
    GEMINI_MODEL:           document.querySelector('[name=GEMINI_MODEL]')?.value || '',
    ANTHROPIC_API_KEY:      document.querySelector('[name=ANTHROPIC_API_KEY]')?.value || '',
    CLAUDE_MODEL:           document.querySelector('[name=CLAUDE_MODEL]')?.value || '',
    OPENAI_API_KEY:         document.querySelector('[name=OPENAI_API_KEY]')?.value || '',
    OPENAI_MODEL:           document.querySelector('[name=OPENAI_MODEL]')?.value || '',
    CRM_BASE_URL:           document.querySelector('[name=CRM_BASE_URL]')?.value || '',
    CRM_API_KEY:            document.querySelector('[name=CRM_API_KEY]')?.value || '',
    TELEGRAM_BOT_TOKEN:     document.querySelector('[name=TELEGRAM_BOT_TOKEN]')?.value || '',
    WA_TOKEN:               document.querySelector('[name=WA_TOKEN]')?.value || '',
    CLOUDFLARE_WORKER_URL:  document.querySelector('[name=CLOUDFLARE_WORKER_URL]')?.value || '',
  }};

  try {{
    const r = await fetch('/admin/test/' + servicio, {{
      method: 'POST',
      headers: {{'Content-Type':'application/json'}},
      body: JSON.stringify(body)
    }});
    const data = await r.json();
    resultEl.style.display = 'block';
    resultEl.style.background = data.ok ? '#e8f5e9' : '#ffebee';
    resultEl.style.color      = data.ok ? '#2e7d32' : '#c62828';
    resultEl.textContent = (data.ok ? '✅ ' : '❌ ') + data.message;
  }} catch(e) {{
    resultEl.style.display = 'block';
    resultEl.style.background = '#ffebee';
    resultEl.style.color = '#c62828';
    resultEl.textContent = '❌ Error de red: ' + e.message;
  }} finally {{
    btn.textContent = origText;
    btn.disabled = false;
  }}
}}
</script>
</body>
</html>"""


# ── Login ──────────────────────────────────────────────────────────────────────
LOGIN_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Login — EcoFiver IA</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#f0f7f3;min-height:100vh;display:flex;align-items:center;
         justify-content:center;padding:24px}
    .card{background:white;border-radius:16px;box-shadow:0 4px 24px rgba(26,92,56,.12);
          padding:40px;max-width:380px;width:100%;text-align:center}
    .icon{font-size:48px;margin-bottom:16px}
    h1{color:#1A5C38;font-size:20px;margin-bottom:6px}
    p{color:#888;font-size:13px;margin-bottom:28px}
    input{width:100%;border:1.5px solid #dde;border-radius:8px;padding:11px 14px;
          font-size:14px;outline:none;margin-bottom:14px;transition:border .2s}
    input:focus{border-color:#1A5C38}
    button{width:100%;background:#1A5C38;color:white;border:none;border-radius:8px;
           padding:12px;font-size:14px;font-weight:700;cursor:pointer}
    button:hover{background:#145030}
    .err{background:#ffebee;color:#c62828;border-radius:8px;padding:10px;
         font-size:13px;margin-bottom:14px;display:none}
  </style>
</head>
<body>
<div class="card">
  <div class="icon">🔐</div>
  <h1>Panel de Configuración</h1>
  <p>EcoFiver — Sistema IA</p>
  <div class="err" id="err">Contraseña incorrecta</div>
  <form id="loginForm">
    <input type="password" id="pw" placeholder="Contraseña del panel" autofocus>
    <button type="submit">Ingresar →</button>
  </form>
</div>
<script>
document.getElementById('loginForm').onsubmit = async function(e) {
  e.preventDefault();
  const pw = document.getElementById('pw').value;
  const r = await fetch('/admin/check', {method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({password:pw})});
  const d = await r.json();
  if (d.ok) { sessionStorage.setItem('eco_admin_pw', pw); window.location.href = '/admin/panel'; }
  else { document.getElementById('err').style.display='block'; document.getElementById('pw').value=''; }
};
</script>
</body>
</html>"""


# ── Rutas ──────────────────────────────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse)
async def admin_login():
    return LOGIN_HTML


@router.post("/admin/check")
async def admin_check(request: Request):
    from auth import is_admin
    body = await request.json()
    # /admin solo para Rodrigo (admin completo)
    return JSONResponse({"ok": is_admin(body.get("password", ""))})


@router.get("/admin/panel", response_class=HTMLResponse)
async def admin_panel():
    return render_panel(read_env())


@router.post("/admin/save")
async def admin_save(request: Request):
    from auth import is_admin
    form = await request.form()
    if not is_admin(form.get("admin_password", "")):
        return HTMLResponse(render_panel(read_env(), "❌ Solo Rodrigo puede guardar la configuración.", "error"))

    campos = [
        "AI_PROVIDER",
        "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
        "GROK_API_KEY", "GROK_MODEL",
        "GEMINI_API_KEY", "GEMINI_MODEL",
        "ANTHROPIC_API_KEY", "CLAUDE_MODEL",
        "OPENAI_API_KEY", "OPENAI_MODEL",
        "CRM_BASE_URL", "CRM_API_KEY",
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID_RODRIGO",
        "WA_TOKEN", "WA_PHONE_ID", "WA_VERIFY_TOKEN",
        "CLOUDFLARE_WORKER_URL", "GOOGLE_DRIVE_FOLDER_ID",
        "BASE_URL", "PORT",
    ]
    values = {c: form.get(c, "") for c in campos if form.get(c, "")}

    nueva_pw = form.get("ADMIN_PASSWORD", "")
    if nueva_pw:
        values["ADMIN_PASSWORD"] = nueva_pw
    renzo_pw = form.get("RENZO_PASSWORD", "")
    if renzo_pw:
        values["RENZO_PASSWORD"] = renzo_pw

    save_env(values)
    load_dotenv(ENV_PATH, override=True)

    provider = values.get("AI_PROVIDER", "grok")
    provider_labels = {
        "openrouter": "OpenRouter ⭐",
        "grok": "Grok (xAI)",
        "gemini": "Google Gemini",
        "claude": "Claude (Anthropic)",
        "openai": "OpenAI",
    }
    label = provider_labels.get(provider, provider)

    return HTMLResponse(render_panel(
        read_env(),
        f"✅ Configuración guardada. Proveedor activo: {label}",
        "ok"
    ))


@router.post("/admin/test/{servicio}")
async def admin_test(servicio: str, request: Request):
    from auth import check_password
    body = await request.json()
    if not check_password(body.get("admin_password", "")):
        return JSONResponse({"ok": False, "message": "Contraseña incorrecta"})

    import httpx

    try:
        if servicio == "openrouter":
            key = body.get("OPENROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
            model = body.get("OPENROUTER_MODEL") or os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
            if not key:
                return JSONResponse({"ok": False, "message": "OPENROUTER_API_KEY no configurada"})
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://www.ecomodulosypiscinas.com.ar",
                        "X-Title": "EcoFiver",
                    },
                    json={"model": model, "max_tokens": 10,
                          "messages": [{"role": "user", "content": "Respondé solo: OK"}]},
                )
            if r.status_code == 200:
                reply = r.json()["choices"][0]["message"]["content"].strip()[:60]
                return JSONResponse({"ok": True, "message": f"✓ {model} responde: {reply}"})
            err = r.json().get("error", {}).get("message", r.text[:100])
            return JSONResponse({"ok": False, "message": f"Error {r.status_code}: {err}"})

        elif servicio == "grok":
            key = body.get("GROK_API_KEY") or os.getenv("GROK_API_KEY", "") or os.getenv("XAI_API_KEY", "")
            model = body.get("GROK_MODEL") or os.getenv("GROK_MODEL", "grok-3-mini")
            if not key:
                return JSONResponse({"ok": False, "message": "GROK_API_KEY no configurada"})
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": model, "max_tokens": 10,
                          "messages": [{"role": "user", "content": "Respondé solo: OK"}]},
                )
            if r.status_code == 200:
                reply = r.json()["choices"][0]["message"]["content"].strip()[:60]
                return JSONResponse({"ok": True, "message": f"✓ {model} responde: {reply}"})
            err = r.json().get("error", {}).get("message", r.text[:100])
            return JSONResponse({"ok": False, "message": f"Error {r.status_code}: {err}"})

        elif servicio == "gemini":
            from google import genai
            key = body.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", "")
            model = body.get("GEMINI_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
            if not key:
                return JSONResponse({"ok": False, "message": "GEMINI_API_KEY no configurada"})
            client = genai.Client(api_key=key)
            r = client.models.generate_content(model=model, contents="Respondé solo: OK")
            return JSONResponse({"ok": True, "message": f"✓ {model} responde: {(r.text or '').strip()[:60]}"})

        elif servicio == "claude":
            key = body.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "")
            model = body.get("CLAUDE_MODEL") or os.getenv("CLAUDE_MODEL", "claude-haiku-20240307")
            if not key:
                return JSONResponse({"ok": False, "message": "ANTHROPIC_API_KEY no configurada"})
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                             "content-type": "application/json"},
                    json={"model": model, "max_tokens": 10,
                          "messages": [{"role": "user", "content": "Respondé solo: OK"}]},
                )
            if r.status_code == 200:
                reply = r.json()["content"][0]["text"].strip()[:60]
                return JSONResponse({"ok": True, "message": f"✓ {model} responde: {reply}"})
            err = r.json().get("error", {}).get("message", r.text[:100])
            return JSONResponse({"ok": False, "message": f"Error {r.status_code}: {err}"})

        elif servicio == "openai":
            key = body.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
            model = body.get("OPENAI_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            if not key:
                return JSONResponse({"ok": False, "message": "OPENAI_API_KEY no configurada"})
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": model, "max_tokens": 10,
                          "messages": [{"role": "user", "content": "Respondé solo: OK"}]},
                )
            if r.status_code == 200:
                reply = r.json()["choices"][0]["message"]["content"].strip()[:60]
                return JSONResponse({"ok": True, "message": f"✓ {model} responde: {reply}"})
            err = r.json().get("error", {}).get("message", r.text[:100])
            return JSONResponse({"ok": False, "message": f"Error {r.status_code}: {err}"})

        elif servicio == "crm":
            url = body.get("CRM_BASE_URL") or os.getenv("CRM_BASE_URL", "")
            key = body.get("CRM_API_KEY") or os.getenv("CRM_API_KEY", "")
            if not url:
                return JSONResponse({"ok": False, "message": "CRM_BASE_URL no configurada"})
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"{url.rstrip('/')}/health",
                                headers={"Authorization": f"Bearer {key}"})
            return JSONResponse({"ok": r.status_code < 400,
                                 "message": f"CRM respondió {r.status_code}"})

        elif servicio == "telegram":
            token = body.get("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
            if not token:
                return JSONResponse({"ok": False, "message": "TELEGRAM_BOT_TOKEN no configurado"})
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"https://api.telegram.org/bot{token}/getMe")
            d = r.json()
            if d.get("ok"):
                bot = d["result"]
                return JSONResponse({"ok": True, "message": f"Bot: @{bot.get('username')}"})
            return JSONResponse({"ok": False, "message": d.get("description", "Error")})

        elif servicio == "whatsapp":
            token = body.get("WA_TOKEN") or os.getenv("WA_TOKEN", "")
            if not token:
                return JSONResponse({"ok": False, "message": "WA_TOKEN no configurado"})
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get("https://graph.facebook.com/v19.0/me",
                                headers={"Authorization": f"Bearer {token}"})
            d = r.json()
            if "id" in d:
                return JSONResponse({"ok": True, "message": f"Token válido: {d.get('name', d.get('id'))}"})
            return JSONResponse({"ok": False, "message": d.get("error", {}).get("message", "Token inválido")})

        elif servicio == "cloudflare":
            url = body.get("CLOUDFLARE_WORKER_URL") or os.getenv("CLOUDFLARE_WORKER_URL", "")
            if not url:
                return JSONResponse({"ok": False, "message": "URL no configurada"})
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{url}/health")
            return JSONResponse({"ok": r.status_code < 400,
                                 "message": f"Worker respondió {r.status_code}"})

        return JSONResponse({"ok": False, "message": f"Servicio '{servicio}' desconocido"})

    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)[:120]})
