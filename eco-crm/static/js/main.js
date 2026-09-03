// ─── THEME (DARK / LIGHT MODE) ───────────────────────────────────────────────
(function() {
  const saved = localStorage.getItem('crm_theme') || 'dark';
  if (saved === 'light') document.documentElement.setAttribute('data-theme', 'light');
})();

function toggleTheme() {
  const html = document.documentElement;
  const isLight = html.getAttribute('data-theme') === 'light';
  const next = isLight ? 'dark' : 'light';
  if (next === 'light') {
    html.setAttribute('data-theme', 'light');
  } else {
    html.removeAttribute('data-theme');
  }
  localStorage.setItem('crm_theme', next);
  _updateThemeIcon();
}

function _updateThemeIcon() {
  const btn = document.getElementById('theme-icon');
  if (!btn) return;
  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  btn.textContent = isLight ? '☀️' : '🌙';
}

// Inicializar ícono cuando el DOM esté listo
document.addEventListener('DOMContentLoaded', _updateThemeIcon);

// ─── GLOBAL STATE & UTILS ─────────────────────────────────────────────────────

const API = {
  async get(url) {
    const res = await fetch(url, { credentials: 'include' });
    if (res.status === 401) { window.location.href = '/login'; return null; }
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async post(url, data) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data)
    });
    if (res.status === 401) { window.location.href = '/login'; return null; }
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.detail || 'Error');
    return json;
  },
  async put(url, data) {
    const res = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data)
    });
    if (res.status === 401) { window.location.href = '/login'; return null; }
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.detail || 'Error');
    return json;
  },
  async patch(url, data) {
    const res = await fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data)
    });
    if (res.status === 401) { window.location.href = '/login'; return null; }
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.detail || 'Error');
    return json;
  },
  async delete(url) {
    const res = await fetch(url, { method: 'DELETE', credentials: 'include' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const det = data.detail;
      const msg = typeof det === 'string' ? det
                : Array.isArray(det) ? det.map(d => d.msg || JSON.stringify(d)).join('; ')
                : 'Error al eliminar';
      throw new Error(msg);
    }
    return data;
  },
  async patch(url, data) {
    const res = await fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data)
    });
    if (res.status === 401) { window.location.href = '/login'; return null; }
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.detail || 'Error');
    return json;
  },
  async postForm(url, formData) {
    const res = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      body: formData
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.detail || 'Error');
    return json;
  }
};

// ─── CUSTOM CONFIRM (reemplaza window.confirm bloqueado en PWA/webview) ───────
let __confirmResolveCallback = null;
function __confirmResolve(value) {
  const modal = document.getElementById('modal-confirm-global');
  if (modal) modal.style.display = 'none';
  if (__confirmResolveCallback) {
    __confirmResolveCallback(value);
    __confirmResolveCallback = null;
  }
}
function showConfirm(mensaje, titulo = '¿Confirmar acción?', colorBtn = '#ef4444') {
  return new Promise(resolve => {
    const modal = document.getElementById('modal-confirm-global');
    if (!modal) { resolve(window.confirm(mensaje)); return; }
    document.getElementById('modal-confirm-titulo').textContent = titulo;
    document.getElementById('modal-confirm-mensaje').textContent = mensaje;
    document.getElementById('modal-confirm-ok-btn').style.background = colorBtn;
    modal.style.display = 'flex';
    __confirmResolveCallback = resolve;
  });
}
// Alias para compatibilidad con código que llama confirmDialog()
const confirmDialog = showConfirm;

// ─── HTML ESCAPE (disponible globalmente para todos los templates) ─────────────
function escHtml(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toast(msg, type = 'success') {
  const container = document.getElementById('toast-container') || (() => {
    const c = document.createElement('div');
    c.id = 'toast-container';
    document.body.appendChild(c);
    return c;
  })();
  const icons = { success: '✓', error: '✕', info: 'ℹ' };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type] || icons.info}</span><span>${msg}</span>`;
  container.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function formatMoney(n) {
  if (n == null) return '—';
  return '$' + Number(n).toLocaleString('es-AR', { maximumFractionDigits: 0 });
}

function formatDate(s) {
  if (!s) return '—';
  const d = new Date(s);
  return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function formatDateTime(s) {
  if (!s) return '—';
  const d = new Date(s);
  return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' }) + ' ' +
    d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
}

function whatsappLink(telefono, mensaje = '') {
  const num = telefono.replace(/\D/g, '');
  const arg = num.startsWith('54') ? num : '54' + num;
  return `https://wa.me/${arg}?text=${encodeURIComponent(mensaje)}`;
}

function openModal(modalId) {
  document.getElementById(modalId).style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function closeModal(modalId) {
  const el = document.getElementById(modalId);
  if (el) { el.style.display = 'none'; document.body.style.overflow = ''; }
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.style.display = 'none';
    document.body.style.overflow = '';
  }
});

// Sidebar toggle (mobile)
function toggleSidebar() {
  const sidebar = document.querySelector('.sidebar');
  sidebar.classList.toggle('open');
}

// ─── STATUS BADGES ────────────────────────────────────────────────────────────

const ESTADO_LEAD = {
  NUEVO: ['badge-gray', 'Nuevo'],
  CONTACTADO: ['badge-blue', 'Contactado'],
  CALIFICADO: ['badge-teal', 'Calificado'],
  VIDEOLLAMADA_AGENDADA: ['badge-yellow', 'Videollamada'],
  CERRADO: ['badge-green', 'Cerrado'],
  PERDIDO: ['badge-red', 'Perdido'],
};

const ESTADO_VL = {
  AGENDADA: ['badge-yellow', 'Agendada'],
  REALIZADA: ['badge-green', 'Realizada'],
  NO_SE_PRESENTO: ['badge-red', 'No se presentó'],
  REPROGRAMAR: ['badge-gray', 'Reprogramar'],
};

const ESTADO_PLAN = {
  ACTIVO: ['badge-green', 'Activo'],
  ATRASADO: ['badge-red', 'Atrasado'],
  CANCELADO: ['badge-gray', 'Cancelado'],
  FINALIZADO: ['badge-teal', 'Finalizado'],
};

const ESTADO_ORDEN = {
  EN_ESPERA: ['badge-gray', 'En espera'],
  EN_PROCESO: ['badge-yellow', 'En proceso'],
  TERMINADA: ['badge-green', 'Terminada'],
  ENTREGADA: ['badge-teal', 'Entregada'],
};

const FORMA_PAGO = {
  PMI: ['badge-blue', 'PMI'],
  DIRECTA_50: ['badge-teal', 'Directa 50%'],
  CONTADO: ['badge-green', 'Contado'],
  SIN_DEFINIR: ['badge-gray', 'Sin definir'],
};

function badge(map, key) {
  const [cls, label] = map[key] || ['badge-gray', key || '—'];
  return `<span class="badge ${cls}">${label}</span>`;
}

// ─── NOTIFICATIONS ────────────────────────────────────────────────────────────

let _notifPanelOpen = false;

async function loadNotifications() {
  try {
    // Fetch last 20 notifications (all, not just unread) for the panel
    const notifs = await API.get('/api/notificaciones');
    if (!notifs) return;

    const unread = notifs.filter(n => !n.leida).length;

    // Update count badge
    const countEl = document.getElementById('notif-count');
    if (countEl) {
      countEl.textContent = unread > 99 ? '99+' : unread;
      countEl.style.display = unread > 0 ? 'flex' : 'none';
    }

    // Legacy badge (cobranzas nav)
    const legacyBadge = document.getElementById('notif-badge');
    if (legacyBadge) {
      legacyBadge.textContent = unread;
      legacyBadge.style.display = unread ? 'flex' : 'none';
    }

    // Render panel list
    const listEl = document.getElementById('notif-list');
    if (listEl) {
      if (!notifs.length) {
        listEl.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text-muted);font-size:13px">Sin notificaciones</div>';
      } else {
        listEl.innerHTML = notifs.map(n => `
          <div class="notif-item ${n.leida ? 'notif-read' : 'notif-unread'}"
               onclick="marcarLeida(${n.id}, this)">
            <div class="notif-item-titulo">${n.titulo}</div>
            <div class="notif-item-msg">${n.mensaje.replace(/\n/g, '<br>')}</div>
            <div class="notif-item-time">${_timeAgo(n.created_at)}</div>
          </div>
        `).join('');
      }
    }
  } catch (e) {}
}

function _timeAgo(iso) {
  if (!iso) return '';
  const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (diff < 60) return 'hace un momento';
  if (diff < 3600) return `hace ${Math.floor(diff/60)} min`;
  if (diff < 86400) return `hace ${Math.floor(diff/3600)} hs`;
  return `hace ${Math.floor(diff/86400)} días`;
}

function toggleNotifPanel() {
  const panel = document.getElementById('notif-panel');
  if (!panel) return;
  _notifPanelOpen = !_notifPanelOpen;
  panel.style.display = _notifPanelOpen ? 'block' : 'none';
}

// Close panel when clicking outside
document.addEventListener('click', (e) => {
  if (_notifPanelOpen && !e.target.closest('#notif-wrap')) {
    const panel = document.getElementById('notif-panel');
    if (panel) panel.style.display = 'none';
    _notifPanelOpen = false;
  }
});

async function marcarLeida(id, el) {
  try {
    await API.post(`/api/notificaciones/${id}/leer`, {});
    if (el) el.classList.replace('notif-unread', 'notif-read');
    // Refresh count
    loadNotifications();
  } catch (e) {}
}

async function togglePushSub() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    toast('Tu navegador no soporta notificaciones push', 'error'); return;
  }
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  const btn = document.getElementById('push-toggle-btn');

  if (sub) {
    // Desuscribir
    await sub.unsubscribe();
    await API.delete('/api/push/subscribe').catch(() => {});
    if (btn) btn.textContent = '🔕';
    toast('Notificaciones push desactivadas');
  } else {
    // Suscribir
    await initPush();
    if (btn) btn.textContent = '🔔';
    toast('Notificaciones push activadas ✅');
  }
  updatePushBtn();
}

async function updatePushBtn() {
  const btn = document.getElementById('push-toggle-btn');
  if (!btn || !('serviceWorker' in navigator) || !('PushManager' in window)) return;
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    btn.textContent = sub ? '🔔' : '🔕';
    btn.title = sub ? 'Push activo — click para desactivar' : 'Push inactivo — click para activar';
  } catch(e) {}
}

async function marcarTodasLeidas() {
  try {
    await API.post('/api/notificaciones/leer-todas', {});
    toast('Notificaciones marcadas como leídas');
    loadNotifications();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── DASHBOARD ────────────────────────────────────────────────────────────────

let _dashRankingPeriodo = 'mes';

async function loadDashboard(rol) {
  const container = document.getElementById('dashboard-content');
  if (!container) return;
  container.innerHTML = '<div class="loading"><div class="spinner"></div> Cargando...</div>';

  try {
    // Carga en paralelo — datos base + alertas
    const [data, alertas] = await Promise.all([
      API.get(`/api/dashboard/${rol}`),
      API.get('/api/dashboard/alertas').catch(() => []),
    ]);
    if (!data) return;

    let html = '';

    // ── ALERTAS CONTEXTUALES ─────────────────────────────────────────────────
    const alertasHtml = renderAlertasDashboard(alertas || []);
    if (alertasHtml) html += alertasHtml;

    if (rol === 'ADMIN') {
      html += _dashboardAdmin(data, alertas || []);
    } else if (rol === 'ASESOR_APERTURA') {
      html += _dashboardAsesor(data);
    } else if (rol === 'SUPERVISOR_CIERRE') {
      html += _dashboardSupervisor(data);
    } else if (rol === 'COORDINADOR_OPERATIVO') {
      html += _dashboardCoordinador(data);
    } else if (rol === 'COBRANZAS') {
      html += _dashboardCobranzas(data);
    } else if (rol === 'FABRICA' || rol === 'ADMINISTRACION') {
      html += _dashboardFabrica(data);
    }

    // ── ACCESOS RÁPIDOS ──────────────────────────────────────────────────────
    html += `<div style="margin-top:4px"><div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:10px">🚀 ACCESO RÁPIDO</div>`;
    html += `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:8px">`;
    for (const a of getQuickAccess(rol)) {
      html += `<a href="${a.url}" class="card" style="display:flex;flex-direction:column;align-items:center;padding:16px 8px;gap:6px;text-decoration:none;transition:all 0.15s" onmouseenter="this.style.borderColor='var(--green)';this.style.transform='translateY(-2px)'" onmouseleave="this.style.borderColor='var(--border)';this.style.transform='none'">
        <span style="font-size:28px">${a.icon}</span>
        <span style="font-size:12px;font-weight:600;color:var(--text-primary);text-align:center;line-height:1.2">${a.label}</span>
      </a>`;
    }
    html += '</div></div>';

    container.innerHTML = html;

    // Post-render: cargar ranking y stock si es ADMIN o tiene acceso
    if (rol === 'ADMIN') {
      cargarRankingDashboard('mes');
      cargarStockOferta();
    } else if (rol === 'ASESOR_APERTURA' || rol === 'SUPERVISOR_CIERRE') {
      cargarRankingDashboard('mes');
    }

  } catch (e) {
    container.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

function renderAlertasDashboard(alertas) {
  if (!alertas.length) return '';
  const colores = {
    rojo:     { border: '#ef444466', bg: '#ef444410', dot: '#ef4444', icon: '🔴' },
    amarillo: { border: '#f59e0b66', bg: '#f59e0b10', dot: '#f59e0b', icon: '🟡' },
    verde:    { border: '#22c55e66', bg: '#22c55e10', dot: '#22c55e', icon: '🟢' },
  };
  let html = `<div style="margin-bottom:16px">
    <div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px">⚡ ALERTAS DE ACTIVIDAD</div>
    <div style="display:flex;flex-direction:column;gap:6px">`;
  for (const a of alertas) {
    const c = colores[a.urgencia] || colores.amarillo;
    html += `<div style="padding:10px 14px;background:${c.bg};border:1px solid ${c.border};border-left:4px solid ${c.dot};border-radius:10px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;cursor:pointer" onclick="window.location='${a.url}'">
      <span style="font-size:18px;flex-shrink:0">${c.icon}</span>
      <div style="flex:1;min-width:0">
        <div style="font-weight:600;font-size:13px">${a.titulo}</div>
        <div style="font-size:12px;color:var(--text-muted)">${a.detalle || ''}</div>
      </div>
      ${a.puede_redistribuir ? `<button onclick="event.stopPropagation();redistribuirRapido()" class="btn btn-sm btn-secondary" style="font-size:11px;padding:4px 10px;border-color:#f59e0b;color:#f59e0b;flex-shrink:0">🔀 Redistribuir</button>` : ''}
      <span style="font-size:12px;color:var(--text-muted);flex-shrink:0">Ver →</span>
    </div>`;
  }
  html += '</div></div>';
  return html;
}

function _dashboardAdmin(data, alertas) {
  let html = '';

  // ── STATS GENERALES ───────────────────────────────────────────────────────
  html += `<div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:10px">📊 PANORAMA GENERAL</div>
    <div class="stats-grid">`;
  html += statCard(data.leads_hoy,          'Leads hoy',         'green',   data.leads_ayer ? `vs ${data.leads_ayer} ayer` : '', '', '/leads');
  html += statCard(data.ventas_dia || 0,    'Ventas hoy',        'green',   '', '', '/ventas-contado');
  html += statCard(data.ventas_mes,         'Ventas mes',        'teal',    data.ventas_semana ? `semana: ${data.ventas_semana}` : '', '', '/ventas-contado');
  html += statCard(data.videollamadas_hoy,  'VL hoy',            'teal',    '', '', '/semana-vls');
  html += statCard(data.cuotas_vencidas,    'Cuotas vencidas',   'error',   data.monto_vencido ? `$${Number(data.monto_vencido).toLocaleString('es-AR')}` : '', '', '/cobranzas');
  html += statCard(data.ordenes_fabrica,    'Órdenes fábrica',   'teal',    '', '', '/fabrica');
  html += statCard(data.presentes_hoy,      'Personal hoy',      'green',   '', '', '/personal?tab=asistencia');
  html += statCard(data.reclamos_abiertos || 0, 'Reclamos',      data.reclamos_abiertos > 0 ? 'error' : 'green', '', '', '/logistica?tab=reclamos');
  html += statCard(data.leads_sin_contactar || 0, 'Sin contactar', data.leads_sin_contactar > 5 ? 'error' : data.leads_sin_contactar > 0 ? 'warning' : 'green', '', '', '/leads');
  html += '</div></div>';

  // ── RANKING + STOCK (side by side en desktop) ─────────────────────────────
  html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px" class="dash-2col">
    <div>
      <div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:10px">🏆 RANKING DE VENTAS</div>
      <div style="background:var(--bg-secondary);border-radius:12px;padding:16px">
        <div style="display:flex;gap:6px;margin-bottom:12px">
          <button onclick="cargarRankingDashboard('dia')" id="rank-btn-dia" class="btn btn-sm btn-ghost" style="font-size:12px">Hoy</button>
          <button onclick="cargarRankingDashboard('semana')" id="rank-btn-semana" class="btn btn-sm btn-ghost" style="font-size:12px">Semana</button>
          <button onclick="cargarRankingDashboard('mes')" id="rank-btn-mes" class="btn btn-sm btn-primary" style="font-size:12px">Mes</button>
        </div>
        <div id="ranking-container"><div class="loading"><div class="spinner"></div></div></div>
      </div>
    </div>
    <div>
      <div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:10px">📦 STOCK DISPONIBLE PARA VENDER</div>
      <div id="stock-oferta-container" style="background:var(--bg-secondary);border-radius:12px;padding:16px">
        <div class="loading"><div class="spinner"></div></div>
      </div>
    </div>
  </div>`;

  // ── LIQUIDACIÓN PENDIENTE (sólo sábado) ───────────────────────────────────
  if (data.liquidacion_pendiente > 0) {
    html += `<div style="margin-bottom:20px;padding:14px 18px;background:rgba(245,158,11,0.1);border:2px solid rgba(245,158,11,0.4);border-radius:12px;display:flex;align-items:center;gap:12px">
      <span style="font-size:24px">💰</span>
      <div style="flex:1"><div style="font-weight:700;color:#f59e0b">Liquidación pendiente — ${data.liquidacion_pendiente} empleado${data.liquidacion_pendiente!==1?'s':''}</div>
      <div style="font-size:12px;color:var(--text-muted)">Hay sueldos sin pagar esta semana</div></div>
      <a href="/personal?tab=liquidacion" class="btn btn-sm btn-primary">Ver →</a>
    </div>`;
  }

  return html;
}

function _dashboardAsesor(data) {
  let html = `<div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:10px">📊 MIS NÚMEROS</div>
    <div class="stats-grid">`;
  html += statCard(data.mis_leads_activos,    'Mis leads activos',  'green',  '', '', '/leads');
  html += statCard(data.videollamadas_hoy,    'VL hoy',             'teal',   '', '', '/videollamadas');
  html += statCard(data.cierres_mes,          'Cierres este mes',   'green',  '', '', '/ventas-contado');
  html += statCard(data.sin_contactar_48h||0, 'Sin contactar +48h', data.sin_contactar_48h > 0 ? 'error' : 'green', '', '', '/leads');
  html += statCard(data.ventas_canceladas||0, 'Ventas canceladas',  data.ventas_canceladas > 0 ? 'error' : 'green', data.ventas_canceladas > 0 ? 'Requieren gestión' : '', '', '/ventas-contado');
  html += '</div></div>';

  // Banner de alerta si hay ventas canceladas
  if ((data.ventas_canceladas || 0) > 0) {
    html += `<div style="background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.4);border-radius:12px;padding:14px 18px;margin-bottom:20px;display:flex;align-items:center;gap:12px">
      <span style="font-size:22px">⚠️</span>
      <div>
        <div style="font-weight:700;color:#f87171;font-size:15px">Tenés ${data.ventas_canceladas} venta${data.ventas_canceladas > 1 ? 's' : ''} cancelada${data.ventas_canceladas > 1 ? 's' : ''} que requieren atención</div>
        <div style="font-size:13px;color:var(--text-muted);margin-top:3px">Gestioná el reagendamiento o reacomodamiento de cada operación.</div>
      </div>
      <a href="/ventas-contado" class="btn btn-sm" style="margin-left:auto;white-space:nowrap;background:rgba(239,68,68,.2);color:#f87171;border:1px solid rgba(239,68,68,.4)">Ver en ventas</a>
    </div>`;
  }

  html += `<div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:10px">🏆 RANKING DEL MES</div>
    <div style="background:var(--bg-secondary);border-radius:12px;padding:16px">
      <div style="display:flex;gap:6px;margin-bottom:12px">
        <button onclick="cargarRankingDashboard('dia')" id="rank-btn-dia" class="btn btn-sm btn-ghost" style="font-size:12px">Hoy</button>
        <button onclick="cargarRankingDashboard('semana')" id="rank-btn-semana" class="btn btn-sm btn-ghost" style="font-size:12px">Semana</button>
        <button onclick="cargarRankingDashboard('mes')" id="rank-btn-mes" class="btn btn-sm btn-primary" style="font-size:12px">Mes</button>
      </div>
      <div id="ranking-container"><div class="loading"><div class="spinner"></div></div></div>
    </div>
  </div>`;
  // Estado de mis leads por estado
  if (data.por_estado) {
    html += `<div style="margin-bottom:20px">
      <div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:10px">🔄 MIS LEADS POR ESTADO</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px">`;
    const coloresEstado = { NUEVO:'#3b82f6', INTENTADO:'#f59e0b', CONTACTADO:'#22c55e', EN_SEGUIMIENTO:'#8b5cf6', CALIFICADO:'#06b6d4', VIDEOLLAMADA_AGENDADA:'#ec4899' };
    for (const [estado, cnt] of Object.entries(data.por_estado)) {
      const c = coloresEstado[estado] || '#64748b';
      html += `<a href="/leads" style="background:${c}18;border:1px solid ${c}44;border-radius:8px;padding:8px 14px;text-decoration:none;display:flex;flex-direction:column;align-items:center">
        <span style="font-size:20px;font-weight:800;color:${c}">${cnt}</span>
        <span style="font-size:11px;color:var(--text-muted)">${estado.replace(/_/g,' ')}</span>
      </a>`;
    }
    html += '</div></div>';
  }
  return html;
}

function _dashboardSupervisor(data) {
  let html = `<div style="margin-bottom:20px"><div class="stats-grid">`;
  html += statCard(data.videollamadas_sin_asignar, 'Sin asignar ⚠',  'error',   '', '', '/videollamadas');
  html += statCard(data.mis_videollamadas_hoy,     'Mis VL hoy',      'teal',    '', '', '/semana-vls');
  html += statCard(data.cierres_mes,               'Cierres del mes', 'green',   '', '', '/ventas-financiadas');
  html += '</div></div>';
  html += `<div style="margin-bottom:20px">
    <div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:10px">🏆 RANKING DE VENTAS</div>
    <div style="background:var(--bg-secondary);border-radius:12px;padding:16px">
      <div style="display:flex;gap:6px;margin-bottom:12px">
        <button onclick="cargarRankingDashboard('dia')" id="rank-btn-dia" class="btn btn-sm btn-ghost" style="font-size:12px">Hoy</button>
        <button onclick="cargarRankingDashboard('semana')" id="rank-btn-semana" class="btn btn-sm btn-ghost" style="font-size:12px">Semana</button>
        <button onclick="cargarRankingDashboard('mes')" id="rank-btn-mes" class="btn btn-sm btn-primary" style="font-size:12px">Mes</button>
      </div>
      <div id="ranking-container"><div class="loading"><div class="spinner"></div></div></div>
    </div>
  </div>`;
  return html;
}

function _dashboardCoordinador(data) {
  let html = `<div style="margin-bottom:20px"><div class="stats-grid">`;
  html += statCard(data.instalaciones_hoy,               'Instalaciones hoy',    'green',   '', '', '/semana-entregas');
  html += statCard(data.instalaciones_manana,            'Mañana',               'teal',    '', '', '/semana-entregas');
  html += statCard(data.ordenes_terminadas_sin_coordinar,'Listas p/coordinar',   'warning', '', '', '/fabrica');
  html += statCard(data.reclamos_abiertos,               'Reclamos abiertos',    data.reclamos_abiertos > 0 ? 'error' : 'green', '', '', '/logistica?tab=reclamos');
  html += statCard(data.contratos_pendientes || 0,       'Contratos pendientes', 'teal',    '', '', '/contratos');
  html += '</div></div>';
  return html;
}

function _dashboardCobranzas(data) {
  let html = `<div style="margin-bottom:20px"><div class="stats-grid">`;
  html += statCard(data.vencen_hoy,     'Vencen hoy',     'warning', '', '', '/cobranzas');
  html += statCard(data.vencidas,       'Total vencidas',  'error',   '', '', '/cobranzas');
  html += statCard(data.gestiones_hoy,  'Gestiones hoy',   'teal',    '', '', '/cobranzas');
  html += statCard(data.pagos_mes,      'Pagos este mes',  'green',   '', '', '/cobranzas');
  html += '</div></div>';
  return html;
}

function _dashboardFabrica(data) {
  let html = `<div style="margin-bottom:20px"><div class="stats-grid">`;
  html += statCard(data.ordenes_en_proceso,    'En proceso',    'teal',    '', '', '/fabrica');
  html += statCard(data.stock_critico,         'Stock crítico', data.stock_critico > 0 ? 'error' : 'green', '', '', '/fabrica?tab=stock');
  html += statCard(data.presentes_hoy,         'Presentes hoy', 'green',   '', '', '/personal?tab=asistencia');
  if (data.es_sabado && data.liquidacion_pendiente > 0) {
    html += statCard(data.liquidacion_pendiente, 'Liquidar', 'warning', '', '', '/personal?tab=liquidacion');
  }
  html += '</div></div>';
  return html;
}

async function cargarRankingDashboard(periodo) {
  _dashRankingPeriodo = periodo;
  const container = document.getElementById('ranking-container');
  if (!container) return;

  // Actualizar botones activos
  ['dia','semana','mes'].forEach(p => {
    const btn = document.getElementById(`rank-btn-${p}`);
    if (!btn) return;
    btn.className = p === periodo ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-ghost';
    btn.style.fontSize = '12px';
  });

  container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

  try {
    const data = await API.get(`/api/dashboard/ranking?periodo=${periodo}`);
    if (!data?.ranking?.length) {
      container.innerHTML = `<div style="text-align:center;padding:20px;color:var(--text-muted)">Sin ventas en este período</div>`;
      return;
    }

    const maxMonto = data.ranking[0].monto_total;
    const medallas = ['🥇','🥈','🥉'];

    container.innerHTML = data.ranking.map((r, i) => {
      const pct = maxMonto > 0 ? Math.round(r.monto_total / maxMonto * 100) : 0;
      const medal = medallas[i] || `<span style="font-size:13px;font-weight:700;color:var(--text-muted)">${i+1}°</span>`;
      // Nombre abreviado: primer nombre + inicial apellido
      const partes = (r.nombre || '').trim().split(' ');
      const nombreCorto = partes.length >= 2
        ? `${partes[0]} ${partes[1][0]}.`
        : partes[0] || `#${r.usuario_id}`;
      // Tags de tipo de venta
      let tags = '';
      if (r.vc > 0) tags += `<span style="font-size:10px;background:#16a34a22;color:#22c55e;border-radius:4px;padding:1px 6px">${r.vc} contado</span>`;
      if (r.vf > 0) tags += `<span style="font-size:10px;background:#6366f122;color:#818cf8;border-radius:4px;padding:1px 6px">${r.vf} financ.</span>`;
      return `
        <div style="margin-bottom:12px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">
            <span style="font-size:18px;width:26px;text-align:center;flex-shrink:0">${medal}</span>
            <span style="font-weight:700;flex:1;font-size:14px;color:var(--text-primary)" title="${r.nombre}">${nombreCorto}</span>
            <span style="font-weight:800;color:#22c55e;font-size:14px">${formatMoney(r.monto_total)}</span>
          </div>
          <div style="display:flex;align-items:center;gap:6px;padding-left:34px">
            <div style="flex:1;height:5px;background:var(--border-color);border-radius:3px;overflow:hidden">
              <div style="width:${pct}%;height:100%;background:linear-gradient(90deg,#22c55e,#16a34a);border-radius:3px;transition:width .6s ease"></div>
            </div>
          </div>
          <div style="padding-left:34px;margin-top:4px;display:flex;gap:4px;flex-wrap:wrap">${tags}</div>
        </div>`;
    }).join('');
  } catch (e) {
    container.innerHTML = `<div style="color:var(--text-muted);font-size:13px">No se pudo cargar el ranking</div>`;
  }
}

async function cargarStockOferta() {
  const container = document.getElementById('stock-oferta-container');
  if (!container) return;

  try {
    const data = await API.get('/api/dashboard/stock-oferta');
    if (!data) return;

    if (!data.total_piscinas && !data.total_paneles) {
      container.innerHTML = `<div style="text-align:center;padding:20px;color:var(--text-muted)">Sin stock disponible actualmente</div>`;
      return;
    }

    let html = '';

    if (data.piscinas?.length) {
      html += `<div style="margin-bottom:12px">
        <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">🏊 PISCINAS (${data.total_piscinas} unidades)</div>
        <div style="display:flex;flex-direction:column;gap:6px">`;
      for (const p of data.piscinas) {
        html += `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:rgba(6,182,212,0.08);border:1px solid rgba(6,182,212,0.2);border-radius:8px;cursor:pointer" onclick="window.location='/fabrica?tab=stock'">
          <span style="font-weight:600;font-size:13px">${p.modelo}${p.color?' · '+p.color:''}</span>
          <span style="background:#0891b2;color:#fff;border-radius:20px;padding:2px 10px;font-size:12px;font-weight:700">${p.cantidad} u.</span>
        </div>`;
      }
      html += '</div></div>';
    }

    if (data.paneles?.length) {
      html += `<div>
        <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">🏠 MÓDULOS (${data.total_paneles} paneles)</div>
        <div style="display:flex;flex-direction:column;gap:6px">`;
      for (const p of data.paneles.slice(0, 5)) {
        html += `<div style="display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.2);border-radius:8px;cursor:pointer" onclick="window.location='/fabrica?tab=stock'">
          <span style="font-weight:600;font-size:13px">${p.tipo}</span>
          <span style="background:#16a34a;color:#fff;border-radius:20px;padding:2px 10px;font-size:12px;font-weight:700">${p.cantidad} u.</span>
        </div>`;
      }
      html += '</div></div>';
    }

    container.innerHTML = html || `<div style="text-align:center;padding:20px;color:var(--text-muted)">Sin stock disponible</div>`;
    const link = document.createElement('a');
    link.href = '/fabrica?tab=stock';
    link.style.cssText = 'display:block;text-align:center;font-size:12px;color:var(--text-muted);margin-top:10px';
    link.textContent = 'Ver todo el stock →';
    container.appendChild(link);

  } catch(e) {
    container.innerHTML = `<div style="color:var(--text-muted);font-size:13px">No se pudo cargar el stock</div>`;
  }
}

// ─── PANEL "ATENCIÓN AHORA" (TDAH) ───────────────────────────────────────────

async function cargarAtencionAhora() {
  const panel = document.getElementById('atencion-ahora-panel');
  if (!panel) return;

  try {
    const [sinContactar, vlHoy] = await Promise.all([
      API.get('/api/leads/sin-contactar?horas=24'),
      API.get('/api/videollamadas/hoy'),
    ]);

    const items = [];

    // 🔴 Leads sin contactar >24h
    if (sinContactar?.length) {
      items.push({
        urgencia: 'rojo',
        emoji: '🔴',
        titulo: `${sinContactar.length} lead${sinContactar.length !== 1 ? 's' : ''} esperando hace +24hs`,
        detalle: sinContactar.slice(0, 3).map(l => l.nombre).join(', ') + (sinContactar.length > 3 ? '...' : ''),
        acciones: [
          { label: 'Ver leads', onclick: `window.location='/leads'` },
          { label: '🔀 Redistribuir', onclick: `redistribuirRapido()`, primary: true },
        ]
      });
    }

    // 🟡 VL de hoy sin tomar
    const vlSinSupervisor = (vlHoy || []).filter(v => !v.supervisor_cierre_id);
    if (vlSinSupervisor.length) {
      items.push({
        urgencia: 'amarillo',
        emoji: '📹',
        titulo: `${vlSinSupervisor.length} videollamada${vlSinSupervisor.length !== 1 ? 's' : ''} hoy sin supervisor asignado`,
        detalle: vlSinSupervisor.slice(0, 2).map(v =>
          `${v.cliente_nombre} ${v.fecha_hora ? '· ' + new Date(v.fecha_hora).toLocaleTimeString('es-AR',{hour:'2-digit',minute:'2-digit'}) : ''}`
        ).join(', '),
        acciones: [{ label: 'Ir a Videollamadas', onclick: `window.location='/videollamadas'` }]
      });
    }

    // 🟢 VL de hoy agendadas (resumen positivo)
    const vlAgendadas = (vlHoy || []).filter(v => v.estado === 'AGENDADA' && v.supervisor_cierre_id);
    if (vlAgendadas.length) {
      items.push({
        urgencia: 'verde',
        emoji: '✅',
        titulo: `${vlAgendadas.length} videollamada${vlAgendadas.length !== 1 ? 's' : ''} listas para hoy`,
        detalle: '',
        acciones: []
      });
    }

    if (!items.length) {
      panel.innerHTML = `
        <div style="padding:14px 16px;background:rgba(45,158,79,0.1);border:1px solid rgba(45,158,79,0.3);border-radius:var(--radius);display:flex;align-items:center;gap:10px;margin-bottom:4px">
          <span style="font-size:24px">✨</span>
          <span style="font-weight:600;color:var(--green-light)">Todo al día — sin pendientes urgentes</span>
        </div>`;
      return;
    }

    const colorMap = {
      rojo:     { border: 'rgba(229,57,53,0.4)',   bg: 'rgba(229,57,53,0.08)',   dot: 'var(--error)' },
      amarillo: { border: 'rgba(245,158,11,0.4)',  bg: 'rgba(245,158,11,0.07)',  dot: 'var(--warning)' },
      verde:    { border: 'rgba(45,158,79,0.4)',   bg: 'rgba(45,158,79,0.08)',   dot: 'var(--green)' },
    };

    panel.innerHTML = `
      <div style="font-size:11px;font-weight:700;color:var(--text-muted);letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px">⚡ ATENCIÓN AHORA</div>
      <div style="display:flex;flex-direction:column;gap:8px">
        ${items.map(item => {
          const c = colorMap[item.urgencia];
          return `
          <div style="padding:12px 16px;background:${c.bg};border:1px solid ${c.border};border-left:4px solid ${c.dot};border-radius:var(--radius);display:flex;align-items:center;gap:12px;flex-wrap:wrap">
            <span style="font-size:22px;flex-shrink:0">${item.emoji}</span>
            <div style="flex:1;min-width:0">
              <div style="font-weight:700;font-size:14px">${item.titulo}</div>
              ${item.detalle ? `<div style="font-size:12px;color:var(--text-secondary);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${item.detalle}</div>` : ''}
            </div>
            ${item.acciones.length ? `<div style="display:flex;gap:6px;flex-shrink:0">
              ${item.acciones.map(a =>
                `<button onclick="${a.onclick}" class="btn btn-sm ${a.primary ? 'btn-primary' : 'btn-secondary'}">${a.label}</button>`
              ).join('')}
            </div>` : ''}
          </div>`;
        }).join('')}
      </div>`;
  } catch(e) {}
}

async function redistribuirRapido() {
  try {
    const data = await API.get('/api/leads/sin-contactar?horas=24');
    if (!data?.length) { toast('No hay leads para redistribuir', 'info'); return; }
    const ok = await showConfirm(
      `¿Redistribuir automáticamente ${data.length} leads sin actividad entre los asesores del pool?`,
      'Redistribuir leads',
      '#f59e0b'
    );
    if (!ok) return;
    const res = await API.post('/api/leads/reasignar-masivo', { ids: data.map(l => l.id), asesor_id: null });
    toast(`✅ ${res.reasignados} leads redistribuidos`);
    cargarAtencionAhora();
  } catch(e) { toast(e.message, 'error'); }
}

function statCard(value, label, type = 'green', delta = '', cls = '', url = '') {
  const inner = `
    <div class="stat-value">${value ?? 0}</div>
    <div class="stat-label">${label}</div>
    ${delta ? `<div class="stat-delta">${delta}</div>` : ''}
    ${url ? `<div class="stat-hint">Ver detalle →</div>` : ''}
  `;
  if (url) {
    return `<a href="${url}" class="stat-card ${type} ${cls} stat-clickable" style="text-decoration:none;cursor:pointer">${inner}</a>`;
  }
  return `<div class="stat-card ${type} ${cls}">${inner}</div>`;
}

function getQuickAccess(rol) {
  const all = [
    { url: '/leads', icon: '👥', label: 'Leads', roles: ['ADMIN', 'ASESOR_APERTURA', 'SUPERVISOR_CIERRE'] },
    { url: '/videollamadas', icon: '📹', label: 'Videollamadas', roles: ['ADMIN', 'ASESOR_APERTURA', 'SUPERVISOR_CIERRE'] },
    { url: '/ventas-contado', icon: '💰', label: 'Contado', roles: ['ADMIN', 'ASESOR_APERTURA', 'SUPERVISOR_CIERRE', 'COORDINADOR_OPERATIVO'] },
    { url: '/ventas-financiadas', icon: '📋', label: 'Financiadas', roles: ['ADMIN', 'ASESOR_APERTURA', 'SUPERVISOR_CIERRE', 'COBRANZAS'] },
    { url: '/cobranzas', icon: '💳', label: 'Cobranzas', roles: ['ADMIN', 'COBRANZAS'] },
    { url: '/fabrica', icon: '🏭', label: 'Fábrica', roles: ['ADMIN', 'FABRICA', 'ADMINISTRACION'] },
    { url: '/semana-entregas', icon: '📅', label: 'Sem. Entregas', roles: ['ADMIN', 'COORDINADOR_OPERATIVO'] },
    { url: '/semana-vls', icon: '📹', label: 'Sem. VLs', roles: ['ADMIN', 'SUPERVISOR_CIERRE'] },
    { url: '/logistica', icon: '🚚', label: 'Logística', roles: ['ADMIN', 'COORDINADOR_OPERATIVO'] },
    { url: '/contratos', icon: '📄', label: 'Contratos', roles: ['ADMIN', 'COORDINADOR_OPERATIVO'] },
    { url: '/personal', icon: '👷', label: 'Personal', roles: ['ADMIN', 'FABRICA', 'ADMINISTRACION'] },
    { url: '/importar', icon: '📥', label: 'Importar', roles: ['ADMIN', 'COORDINADOR_OPERATIVO'] },
  ];
  return all.filter(a => a.roles.includes('ADMIN') ? true : a.roles.includes(rol));
}

// ─── LEADS MODULE ─────────────────────────────────────────────────────────────

let leadsData = [];
let leadsView = 'list'; // 'list' or 'kanban'
let leadsFilter = {};

async function loadLeads() {
  const params = new URLSearchParams();
  Object.entries(leadsFilter).forEach(([k, v]) => { if (v) params.set(k, v); });

  const data = await API.get(`/api/leads?${params}`);
  if (!data) return;
  leadsData = data.leads;

  if (leadsView === 'kanban') {
    renderLeadsKanban();
  } else {
    renderLeadsList();
  }
}

function renderLeadsList() {
  const tbody = document.getElementById('leads-tbody');
  if (!tbody) return;

  const cols = typeof isAdmin !== 'undefined' && isAdmin ? 9 : 8;

  if (!leadsData.length) {
    tbody.innerHTML = `<tr><td colspan="${cols}" style="text-align:center;padding:40px;color:var(--text-muted)">No hay leads</td></tr>`;
    return;
  }

  // Reset selección al re-renderizar
  if (typeof leadsSeleccionados !== 'undefined') leadsSeleccionados.clear();
  if (typeof actualizarToolbarSeleccion === 'function') actualizarToolbarSeleccion();

  const checkAll = document.getElementById('check-all');
  if (checkAll) checkAll.checked = false;

  const ESTADOS_ACTIVOS = ['NUEVO','INTENTADO','CONTACTADO','EN_SEGUIMIENTO','CALIFICADO'];

  tbody.innerHTML = leadsData.map(l => {
    // Días sin actividad (para estados activos)
    let diasSinActividad = 0;
    if (ESTADOS_ACTIVOS.includes(l.estado)) {
      const ref = l.updated_at || l.created_at;
      if (ref) diasSinActividad = Math.floor((Date.now() - new Date(ref)) / 86400000);
    }
    const sinActividad = diasSinActividad > 0;
    let badgeDias = '';
    if (diasSinActividad >= 7) {
      badgeDias = `<span style="font-size:10px;font-weight:700;background:#ef4444;color:#fff;border-radius:4px;padding:1px 6px;margin-left:4px">${diasSinActividad}d</span>`;
    } else if (diasSinActividad >= 4) {
      badgeDias = `<span style="font-size:10px;font-weight:700;background:#f97316;color:#fff;border-radius:4px;padding:1px 6px;margin-left:4px">${diasSinActividad}d</span>`;
    } else if (diasSinActividad >= 2) {
      badgeDias = `<span style="font-size:10px;font-weight:700;background:#f59e0b;color:#fff;border-radius:4px;padding:1px 6px;margin-left:4px">${diasSinActividad}d</span>`;
    }

    const rowBg = diasSinActividad >= 7 ? ';background:rgba(239,68,68,0.05)'
                : diasSinActividad >= 4 ? ';background:rgba(249,115,22,0.04)'
                : '';

    const checkboxCell = (typeof isAdmin !== 'undefined' && isAdmin)
      ? `<td onclick="event.stopPropagation()"><input type="checkbox" class="lead-check" data-id="${l.id}" onchange="toggleLead(${l.id}, this.checked)"></td>`
      : '';

    return `
    <tr onclick="editLead(${l.id})" style="cursor:pointer${rowBg}">
      ${checkboxCell}
      <td><span style="color:var(--text-muted);font-size:12px">#${l.id}</span></td>
      <td>
        <div style="font-weight:600">${l.nombre}</div>
        <div style="font-size:12px;color:var(--text-muted)">${l.localidad || ''}</div>
      </td>
      <td>
        <a href="${whatsappLink(l.telefono)}" target="_blank" onclick="event.stopPropagation()" class="btn btn-whatsapp btn-sm">
          📱 ${l.telefono}
        </a>
      </td>
      <td>
        <div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px">
          ${badge(ESTADO_LEAD, l.estado)}
          ${badgeDias}
        </div>
      </td>
      <td>${l.producto_interes || '—'}</td>
      <td>${badge(FORMA_PAGO, l.forma_pago)}</td>
      <td style="font-size:13px">${l.asesor_apertura_nombre || '—'}</td>
      <td style="font-size:12px;color:var(--text-muted)">${formatDate(l.created_at)}</td>
    </tr>`;
  }).join('');
}

const KANBAN_ESTADOS = ['NUEVO', 'CONTACTADO', 'CALIFICADO', 'VIDEOLLAMADA_AGENDADA', 'CERRADO', 'PERDIDO'];
const KANBAN_LABELS = { NUEVO: 'Nuevo', CONTACTADO: 'Contactado', CALIFICADO: 'Calificado', VIDEOLLAMADA_AGENDADA: 'VL Agendada', CERRADO: 'Cerrado', PERDIDO: 'Perdido' };

function renderLeadsKanban() {
  const board = document.getElementById('leads-kanban');
  if (!board) return;

  const grouped = {};
  KANBAN_ESTADOS.forEach(e => grouped[e] = []);
  leadsData.forEach(l => { if (grouped[l.estado]) grouped[l.estado].push(l); });

  board.innerHTML = KANBAN_ESTADOS.map(estado => `
    <div class="kanban-column">
      <div class="kanban-header">
        <span class="kanban-title">${KANBAN_LABELS[estado]}</span>
        <span class="kanban-count">${grouped[estado].length}</span>
      </div>
      <div class="kanban-cards">
        ${grouped[estado].map(l => `
          <div class="kanban-card" onclick="editLead(${l.id})">
            <div class="card-name">${l.nombre}</div>
            <div class="card-detail">${l.localidad || ''}</div>
            <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
              ${badge(FORMA_PAGO, l.forma_pago)}
              <span style="font-size:11px;color:var(--text-muted)">${l.asesor_apertura_nombre || ''}</span>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `).join('');
}

function switchLeadsView(view) {
  leadsView = view;
  document.querySelectorAll('.view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  document.getElementById('leads-list-view').style.display = view === 'list' ? 'block' : 'none';
  document.getElementById('leads-kanban-view').style.display = view === 'kanban' ? 'block' : 'none';
  if (view === 'kanban') renderLeadsKanban();
  else renderLeadsList();
}

async function editLead(id) {
  const lead = await API.get(`/api/leads/${id}`);
  if (!lead) return;

  const form = document.getElementById('lead-form');
  if (!form) return;

  form.dataset.id = id;
  document.getElementById('modal-lead-title').textContent = 'Editar Lead';
  fillForm('lead-form', lead);
  updateModeloOptions('lead-producto', 'lead-modelo');
  openModal('modal-lead');
}

function newLead() {
  const form = document.getElementById('lead-form');
  if (!form) return;
  form.dataset.id = '';
  form.reset();
  document.getElementById('modal-lead-title').textContent = 'Nuevo Lead';
  openModal('modal-lead');
}

async function saveLead() {
  const form = document.getElementById('lead-form');
  const id = form.dataset.id;
  const data = formToObj(form);

  try {
    if (id) {
      await API.put(`/api/leads/${id}`, data);
      toast('Lead actualizado');
    } else {
      await API.post('/api/leads', data);
      toast('Lead creado');
    }
    closeModal('modal-lead');
    loadLeads();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function quickEstado(leadId, estado) {
  try {
    await API.put(`/api/leads/${leadId}/estado`, { estado });
    toast('Estado actualizado');
    loadLeads();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── VIDEOLLAMADAS ────────────────────────────────────────────────────────────

let vlData = [];

async function loadVL() {
  const params = new URLSearchParams();
  const fecha = document.getElementById('vl-fecha')?.value;
  if (fecha) params.set('fecha', fecha);
  const sinSup = document.getElementById('vl-sin-supervisor')?.checked;
  if (sinSup) params.set('sin_supervisor', 'true');

  const data = await API.get(`/api/videollamadas?${params}`);
  if (!data) return;
  vlData = data;
  renderVLList();
}

function renderVLList() {
  const tbody = document.getElementById('vl-tbody');
  if (!tbody) return;

  if (!vlData.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;color:var(--text-muted)">No hay videollamadas</td></tr>';
    return;
  }

  tbody.innerHTML = vlData.map(v => `
    <tr onclick="editVL(${v.id})" style="cursor:pointer">
      <td>
        <div style="font-weight:600">${v.cliente_nombre}</div>
        <div style="font-size:12px;color:var(--text-muted)">${v.producto_interes || ''}</div>
      </td>
      <td>
        <a href="${whatsappLink(v.cliente_telefono)}" target="_blank" onclick="event.stopPropagation()" class="btn btn-whatsapp btn-sm">
          📱 ${v.cliente_telefono}
        </a>
      </td>
      <td style="font-size:13px">${v.fecha_hora ? formatDateTime(v.fecha_hora) : '—'}</td>
      <td>${badge(ESTADO_VL, v.estado)}</td>
      <td style="font-size:13px">${v.asesor_apertura_nombre || '—'}</td>
      <td>
        ${v.supervisor_cierre_nombre ||
          `<button onclick="event.stopPropagation();tomarVL(${v.id})" class="btn btn-sm btn-primary">Tomar</button>`}
      </td>
      <td>${badge({ AVANZO: ['badge-green','Avanzó'], NO_CALIFICO: ['badge-red','No calificó'], CERRO: ['badge-teal','Cerró'], PENDIENTE: ['badge-gray','Pendiente'] }, v.resultado)}</td>
    </tr>
  `).join('');
}

async function tomarVL(id) {
  try {
    await API.post(`/api/videollamadas/${id}/tomar`, {});
    toast('Videollamada tomada');
    loadVL();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function editVL(id) {
  const vl = vlData.find(v => v.id === id);
  if (!vl) return;
  document.getElementById('vl-form').dataset.id = id;
  fillForm('vl-form', vl);
  openModal('modal-vl');
}

function newVL() {
  document.getElementById('vl-form').dataset.id = '';
  document.getElementById('vl-form').reset();
  openModal('modal-vl');
}

async function saveVL() {
  const form = document.getElementById('vl-form');
  const id = form.dataset.id;
  const data = formToObj(form);

  try {
    if (id) {
      await API.put(`/api/videollamadas/${id}`, data);
      toast('Videollamada actualizada');
    } else {
      await API.post('/api/videollamadas', data);
      toast('Videollamada creada');
    }
    closeModal('modal-vl');
    loadVL();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── COBRANZAS ────────────────────────────────────────────────────────────────

async function loadCartera() {
  const container = document.getElementById('cartera-container');
  if (!container) return;
  container.innerHTML = '<div class="loading"><div class="spinner"></div> Cargando cartera...</div>';

  try {
    const data = await API.get('/api/cobranzas/cartera');
    if (!data) return;

    if (!data.length) {
      container.innerHTML = '<div class="empty-state"><span class="empty-icon">💳</span><p>No hay clientes en cartera activa</p></div>';
      return;
    }

    container.innerHTML = data.map(v => {
      const clsCard = v.dias_atraso > 0 ? 'atraso' : (v.alerta === 'AMARILLA' ? 'vence-hoy' : 'al-dia');
      const pctPago = Math.min(100, Math.round((v.cuotas_pagas / v.cantidad_cuotas) * 100));

      return `
        <div class="cobranza-card ${clsCard}">
          <div class="cliente-info">
            <div>
              <div style="font-size:16px;font-weight:700">${v.cliente_nombre}</div>
              <div style="font-size:13px;color:var(--text-secondary)">${v.modelo_especifico || v.producto}</div>
            </div>
            <div style="text-align:right">
              ${v.dias_atraso > 0
                ? `<div style="color:var(--error);font-weight:700;font-size:14px">⚠ ${v.dias_atraso} días atraso</div>`
                : v.alerta === 'AMARILLA' ? '<div style="color:var(--warning);font-size:13px">⏰ Vence en 3 días</div>' : ''
              }
              <div style="font-size:13px;color:var(--text-secondary)">
                ${v.cuotas_pagas}/${v.cantidad_cuotas} cuotas
              </div>
            </div>
          </div>

          <div class="progress-bar">
            <div class="progress-fill ${v.dias_atraso > 0 ? 'danger' : ''}" style="width:${pctPago}%"></div>
          </div>

          <div style="display:flex;justify-content:space-between;margin-top:10px;gap:8px;flex-wrap:wrap">
            <div style="font-size:13px;color:var(--text-secondary)">
              Próx. ${v.proximo_vencimiento ? formatDate(v.proximo_vencimiento) : '—'}
              · ${formatMoney(v.monto_proxima_cuota)}
              ${v.ultimo_contacto ? `· Contacto: ${formatDate(v.ultimo_contacto)}` : ''}
            </div>
            <div style="display:flex;gap:6px">
              <a href="${whatsappLink(v.cliente_telefono, v.mensaje_whatsapp)}"
                 target="_blank" class="btn btn-whatsapp btn-sm">📱 WA</a>
              <button onclick="openGestion(${v.id})" class="btn btn-sm btn-secondary">Registrar</button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    container.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

let gestionVentaId = null;

function openGestion(ventaId) {
  gestionVentaId = ventaId;
  openModal('modal-gestion');
}

async function saveGestion() {
  const data = {
    canal: document.getElementById('gestion-canal').value,
    resultado: document.getElementById('gestion-resultado').value,
    notas: document.getElementById('gestion-notas').value,
  };

  try {
    await API.post(`/api/cobranzas/${gestionVentaId}/gestion`, data);
    toast('Gestión registrada');
    closeModal('modal-gestion');
    loadCartera();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── ASISTENCIA ───────────────────────────────────────────────────────────────

let asistenciaData = [];

const ASISTENCIA_TIPOS = [
  { tipo: 'PRESENTE',  emoji: '✅', label: 'Presente',  color: '#22c55e' },
  { tipo: 'AUSENTE',   emoji: '❌', label: 'Ausente',   color: '#ef4444' },
  { tipo: 'MEDIO_DIA', emoji: '½',  label: 'Medio día', color: '#f59e0b' },
  { tipo: 'FERIADO',   emoji: '🏖️', label: 'Feriado',   color: '#6366f1' },
  { tipo: 'ENFERMO',   emoji: '🤒', label: 'Enfermo',   color: '#8b5cf6' },
];

async function loadAsistencia() {
  const fecha = document.getElementById('asistencia-fecha')?.value || new Date().toISOString().split('T')[0];
  const data = await API.get(`/api/personal/asistencia?fecha=${fecha}`);
  if (!data) return;
  asistenciaData = data;
  renderAsistencia();
}

function renderAsistencia() {
  const container = document.getElementById('asistencia-container');
  if (!container) return;

  if (!asistenciaData.length) {
    container.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text-muted)">No hay empleados registrados</div>';
    return;
  }

  // Agrupar por sector (empleado_rol)
  const sectores = {};
  asistenciaData.forEach(emp => {
    const s = emp.empleado_rol || 'GENERAL';
    if (!sectores[s]) sectores[s] = [];
    sectores[s].push(emp);
  });

  // Calcular totales globales
  const total = asistenciaData.length;
  const presentes = asistenciaData.filter(e => e.tipo === 'PRESENTE').length;
  const ausentes  = asistenciaData.filter(e => e.tipo === 'AUSENTE').length;
  const medioDia  = asistenciaData.filter(e => e.tipo === 'MEDIO_DIA').length;
  const sinMarcar = asistenciaData.filter(e => !e.tipo).length;

  const pct = total > 0 ? Math.round((presentes + medioDia * 0.5) / total * 100) : 0;

  let html = `
    <!-- Resumen global -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin-bottom:20px">
      <div style="background:var(--bg-secondary);border-radius:12px;padding:14px;text-align:center;border:2px solid #22c55e22">
        <div style="font-size:28px;font-weight:800;color:#22c55e">${presentes}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:2px">Presentes</div>
      </div>
      <div style="background:var(--bg-secondary);border-radius:12px;padding:14px;text-align:center;border:2px solid #f59e0b22">
        <div style="font-size:28px;font-weight:800;color:#f59e0b">${medioDia}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:2px">Medio día</div>
      </div>
      <div style="background:var(--bg-secondary);border-radius:12px;padding:14px;text-align:center;border:2px solid #ef444422">
        <div style="font-size:28px;font-weight:800;color:#ef4444">${ausentes}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:2px">Ausentes</div>
      </div>
      <div style="background:var(--bg-secondary);border-radius:12px;padding:14px;text-align:center;border:2px solid #64748b22">
        <div style="font-size:28px;font-weight:800;color:var(--text-muted)">${sinMarcar}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:2px">Sin marcar</div>
      </div>
    </div>
    <!-- Barra de asistencia global -->
    <div style="background:var(--bg-secondary);border-radius:10px;padding:12px 16px;margin-bottom:20px;display:flex;align-items:center;gap:12px">
      <span style="font-size:13px;color:var(--text-secondary);white-space:nowrap">Asistencia del día</span>
      <div style="flex:1;background:var(--border-color);border-radius:6px;height:10px;overflow:hidden">
        <div style="width:${pct}%;background:linear-gradient(90deg,#22c55e,#16a34a);height:100%;border-radius:6px;transition:width .5s"></div>
      </div>
      <span style="font-weight:700;color:#22c55e;white-space:nowrap">${pct}%</span>
    </div>
  `;

  // Tarjetas por sector
  Object.entries(sectores).forEach(([sector, empleados]) => {
    const presS = empleados.filter(e => e.tipo === 'PRESENTE').length;
    const totalS = empleados.length;

    html += `
      <div style="margin-bottom:24px">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
          <div style="font-weight:700;font-size:15px;color:var(--text-primary);text-transform:uppercase;letter-spacing:.5px">${sector.replace(/_/g,' ')}</div>
          <div style="background:var(--bg-secondary);border-radius:20px;padding:2px 10px;font-size:12px;color:var(--text-muted)">${presS}/${totalS}</div>
          <div style="flex:1;height:2px;background:var(--border-color);border-radius:2px"></div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px">
          ${empleados.map(emp => {
            const tipoActual = ASISTENCIA_TIPOS.find(t => t.tipo === emp.tipo);
            const bgColor = tipoActual ? tipoActual.color + '18' : 'var(--bg-secondary)';
            const borderColor = tipoActual ? tipoActual.color + '44' : 'var(--border-color)';
            const iniciales = emp.empleado_nombre.split(' ').map(p=>p[0]).join('').slice(0,2).toUpperCase();
            return `
              <div id="emp-card-${emp.empleado_id}" style="background:${bgColor};border:2px solid ${borderColor};border-radius:14px;padding:14px;transition:all .2s">
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
                  <div style="width:38px;height:38px;border-radius:50%;background:${tipoActual ? tipoActual.color : 'var(--border-color)'};display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:14px;flex-shrink:0">${iniciales}</div>
                  <div>
                    <div style="font-weight:600;font-size:14px;line-height:1.2">${emp.empleado_nombre}</div>
                    ${tipoActual ? `<div style="font-size:11px;color:${tipoActual.color};font-weight:600">${tipoActual.emoji} ${tipoActual.label}</div>` : `<div style="font-size:11px;color:var(--text-muted)">Sin marcar</div>`}
                  </div>
                </div>
                <div style="display:flex;gap:6px;flex-wrap:wrap">
                  ${ASISTENCIA_TIPOS.map(t => `
                    <button title="${t.label}"
                      onclick="registrarAsistencia(${emp.empleado_id}, '${t.tipo}', this)"
                      style="flex:1;min-width:32px;padding:6px 2px;border:2px solid ${emp.tipo === t.tipo ? t.color : 'var(--border-color)'};border-radius:8px;background:${emp.tipo === t.tipo ? t.color + '22' : 'transparent'};cursor:pointer;font-size:16px;transition:all .15s;color:inherit">
                      ${t.emoji}
                    </button>
                  `).join('')}
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

async function registrarAsistencia(empleadoId, tipo, btn) {
  const fecha = document.getElementById('asistencia-fecha')?.value || new Date().toISOString().split('T')[0];
  try {
    await API.post('/api/personal/asistencia', { empleado_id: empleadoId, tipo, fecha });

    // Actualizar data local y re-renderizar la tarjeta
    const emp = asistenciaData.find(e => e.empleado_id === empleadoId);
    if (emp) emp.tipo = tipo;
    renderAsistencia();
    toast('Asistencia registrada');
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── LIQUIDACIÓN ──────────────────────────────────────────────────────────────

async function loadLiquidacion() {
  const container = document.getElementById('liquidacion-container');
  if (!container) return;
  container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';

  try {
    const data = await API.get('/api/personal/liquidacion');
    if (!data) return;

    const semana = `${formatDate(data.semana_inicio)} — ${formatDate(data.semana_fin)}`;
    let totalGeneral = 0;
    let totalPagado  = 0;
    let totalPendiente = 0;

    data.empleados.forEach(emp => {
      totalGeneral += emp.monto_total;
      if (emp.pagado) totalPagado += emp.monto_total;
      else totalPendiente += emp.monto_total;
    });

    // Agrupar por sector / rol
    const sectores = {};
    data.empleados.forEach(emp => {
      const s = emp.empleado_rol || 'GENERAL';
      if (!sectores[s]) sectores[s] = { empleados: [], total: 0, pendiente: 0 };
      sectores[s].empleados.push(emp);
      sectores[s].total += emp.monto_total;
      if (!emp.pagado) sectores[s].pendiente += emp.monto_total;
    });

    // Días de la semana para los indicadores
    const diasSemana = [];
    const inicio = new Date(data.semana_inicio + 'T00:00:00');
    for (let i = 0; i < 7; i++) {
      const d = new Date(inicio);
      d.setDate(d.getDate() + i);
      diasSemana.push(d.toISOString().split('T')[0]);
    }
    const diasCortos = ['L','M','X','J','V','S','D'];

    let html = `
      <!-- Header semana -->
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:10px">
        <div>
          <div style="font-size:13px;color:var(--text-muted)">Semana de liquidación</div>
          <div style="font-weight:700;font-size:16px">${semana}</div>
        </div>
        <div style="display:flex;gap:8px">
          <div style="background:#22c55e18;border:2px solid #22c55e44;border-radius:10px;padding:10px 16px;text-align:center">
            <div style="font-size:11px;color:#22c55e;font-weight:600">PAGADO</div>
            <div style="font-size:18px;font-weight:800;color:#22c55e">${formatMoney(totalPagado)}</div>
          </div>
          <div style="background:#f59e0b18;border:2px solid #f59e0b44;border-radius:10px;padding:10px 16px;text-align:center">
            <div style="font-size:11px;color:#f59e0b;font-weight:600">PENDIENTE</div>
            <div style="font-size:18px;font-weight:800;color:#f59e0b">${formatMoney(totalPendiente)}</div>
          </div>
          <div style="background:var(--bg-secondary);border:2px solid var(--border-color);border-radius:10px;padding:10px 16px;text-align:center">
            <div style="font-size:11px;color:var(--text-muted);font-weight:600">TOTAL</div>
            <div style="font-size:18px;font-weight:800">${formatMoney(totalGeneral)}</div>
          </div>
        </div>
      </div>
    `;

    // Sectores
    Object.entries(sectores).forEach(([sector, info]) => {
      const pctPagado = info.total > 0 ? Math.round((info.total - info.pendiente) / info.total * 100) : 0;

      html += `
        <div style="margin-bottom:24px">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
            <div style="font-weight:700;font-size:14px;text-transform:uppercase;letter-spacing:.5px">${sector.replace(/_/g,' ')}</div>
            <div style="font-size:12px;color:var(--text-muted);background:var(--bg-secondary);padding:2px 10px;border-radius:20px">${formatMoney(info.total)}</div>
            <div style="flex:1;height:2px;background:var(--border-color);border-radius:2px"></div>
            <div style="font-size:12px;color:${pctPagado===100?'#22c55e':'#f59e0b'}">${pctPagado}% pagado</div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px">
            ${info.empleados.map(emp => {
              // Indicadores de días
              const indicadores = diasSemana.map((d, i) => {
                const registro = (emp.detalle || []).find(r => r.fecha === d);
                const tipoR = registro ? registro.tipo : null;
                let color = '#e2e8f0';
                let title = diasCortos[i];
                if (tipoR === 'PRESENTE')  { color = '#22c55e'; title = `${diasCortos[i]}: Presente`; }
                else if (tipoR === 'AUSENTE')   { color = '#ef4444'; title = `${diasCortos[i]}: Ausente`; }
                else if (tipoR === 'MEDIO_DIA') { color = '#f59e0b'; title = `${diasCortos[i]}: Medio día`; }
                else if (tipoR === 'ENFERMO')   { color = '#8b5cf6'; title = `${diasCortos[i]}: Enfermo`; }
                else if (tipoR === 'FERIADO')   { color = '#6366f1'; title = `${diasCortos[i]}: Feriado`; }
                return `<div title="${title}" style="flex:1;height:28px;background:${color};border-radius:5px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:${color==='#e2e8f0'?'#94a3b8':'#fff'}">${diasCortos[i]}</div>`;
              }).join('');

              return `
                <div style="background:var(--bg-secondary);border-radius:14px;padding:16px;border:2px solid ${emp.pagado ? '#22c55e33' : 'var(--border-color)'}">
                  <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px">
                    <div>
                      <div style="font-weight:700;font-size:15px">${emp.empleado_nombre}</div>
                      <div style="font-size:12px;color:var(--text-muted)">${emp.tipo_tarifa === 'POR_DIA' ? `${formatMoney(emp.monto_tarifa)}/día` : `${formatMoney(emp.monto_tarifa)}/hs`} · ${emp.dias_trabajados} día${emp.dias_trabajados !== 1 ? 's' : ''}</div>
                    </div>
                    <div style="text-align:right">
                      <div style="font-size:20px;font-weight:800;color:${emp.pagado ? '#22c55e' : 'var(--text-primary)'}">${formatMoney(emp.monto_total)}</div>
                      <div style="font-size:11px;font-weight:600;color:${emp.pagado ? '#22c55e' : '#f59e0b'}">${emp.pagado ? '✓ Pagado' : '⏳ Pendiente'}</div>
                    </div>
                  </div>
                  <!-- Indicadores de días -->
                  <div style="display:flex;gap:4px;margin-bottom:12px">${indicadores}</div>
                  <!-- Acción -->
                  ${!emp.pagado ? `
                    <button onclick="marcarPagado(${emp.empleado_id}, ${emp.monto_total}, '${data.semana_inicio}')"
                      style="width:100%;padding:8px;background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff;border:none;border-radius:8px;font-weight:700;font-size:13px;cursor:pointer">
                      💰 Marcar como pagado
                    </button>
                  ` : `
                    <div style="text-align:center;font-size:12px;color:#22c55e;font-weight:600">✓ Liquidación pagada esta semana</div>
                  `}
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    });

    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

async function marcarPagado(empleadoId, monto, fechaInicio) {
  const ok = await showConfirm(
    `¿Confirmar pago de $${monto.toLocaleString('es-AR')}?`,
    'Confirmar liquidación',
    '#22c55e'
  );
  if (!ok) return;
  try {
    await API.post('/api/personal/liquidacion/pagar', {
      empleado_id: empleadoId,
      monto_total: monto,
      fecha_inicio: fechaInicio,
    });
    toast('Pago registrado');
    loadLiquidacion();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── CATALOGO ────────────────────────────────────────────────────────────────

async function loadCatalogo() {
  const data = await API.get('/api/catalogo');
  if (!data) return data;
  return data;
}

async function addModeloPiscina() {
  const nombre = prompt('Nombre del nuevo modelo de piscina:');
  if (!nombre) return;
  try {
    await API.post('/api/catalogo/piscinas/modelos', { nombre });
    toast('Modelo agregado');
    location.reload();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function addColorPiscina() {
  const color = prompt('Nuevo color:');
  if (!color) return;
  try {
    await API.post('/api/catalogo/piscinas/colores', { color });
    toast('Color agregado');
    location.reload();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function addModeloModulo() {
  const nombre = prompt('Nombre del modelo personalizado (ej: "Módulo Industrial 80m²"):');
  if (!nombre) return;
  try {
    await API.post('/api/catalogo/modulos/modelos-custom', { nombre });
    toast('Modelo agregado');
    location.reload();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function addSuperficie() {
  const m2 = prompt('Nueva superficie en m²:');
  if (!m2) return;
  try {
    await API.post('/api/catalogo/modulos/superficies', { m2: parseInt(m2) });
    toast('Superficie agregada');
    location.reload();
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── IMPORTAR ────────────────────────────────────────────────────────────────

async function previewImportacion(tipo) {
  const fileInput = document.getElementById(`import-file-${tipo}`);
  if (!fileInput?.files[0]) { toast('Seleccioná un archivo', 'error'); return; }

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  try {
    const data = await API.postForm(`/api/importar/preview?tipo=${tipo}`, formData);
    const container = document.getElementById(`preview-${tipo}`);
    if (!container) return;

    let html = `<div class="alert alert-info" style="margin-bottom:12px">
      <strong>${data.total_filas}</strong> filas detectadas.
      Columnas mapeadas: ${Object.keys(data.columnas_detectadas).length}/${Object.keys(data.columnas_detectadas).length}
    </div>`;

    if (data.preview.length) {
      html += '<div class="table-wrapper"><table><thead><tr>';
      Object.keys(data.preview[0]).forEach(k => { html += `<th>${k}</th>`; });
      html += '</tr></thead><tbody>';
      data.preview.forEach(row => {
        html += '<tr>' + Object.values(row).map(v => `<td style="font-size:12px">${v || '—'}</td>`).join('') + '</tr>';
      });
      html += '</tbody></table></div>';
    }

    container.innerHTML = html;
    document.getElementById(`btn-import-${tipo}`)?.removeAttribute('disabled');
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function ejecutarImportacion(tipo) {
  const fileInput = document.getElementById(`import-file-${tipo}`);
  if (!fileInput?.files[0]) return;

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  try {
    const data = await API.postForm(`/api/importar/${tipo}`, formData);
    toast(`✅ ${data.importados} registros importados`);

    if (data.errores?.length) {
      console.error('Errores de importación:', data.errores);
    }

    document.getElementById(`preview-${tipo}`).innerHTML =
      `<div class="alert alert-success">${data.mensaje}</div>`;
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────

function formToObj(form) {
  const data = {};
  const fd = new FormData(form);
  fd.forEach((val, key) => {
    data[key] = val === '' ? null : val;
  });
  return data;
}

function fillForm(formId, obj) {
  const form = document.getElementById(formId);
  if (!form) return;
  Object.entries(obj).forEach(([key, val]) => {
    const el = form.querySelector(`[name="${key}"]`);
    if (!el) return;
    if (el.type === 'checkbox') {
      el.checked = Boolean(val);
    } else if (el.type === 'datetime-local' && val) {
      el.value = val.substring(0, 16);
    } else {
      el.value = val ?? '';
    }
  });
}

function updateModeloOptions(productoSelectId, modeloSelectId) {
  const prod = document.getElementById(productoSelectId);
  const modelo = document.getElementById(modeloSelectId);
  if (!prod || !modelo) return;

  const tipo = prod.value;
  const current = modelo.value;

  // Fetch from API
  API.get(`/api/catalogo/modelos?tipo=${tipo}`).then(data => {
    if (!data) return;
    const modelos = data.modelos || [];
    modelo.innerHTML = '<option value="">— Seleccionar —</option>' +
      modelos.map(m => `<option value="${m}" ${m === current ? 'selected' : ''}>${m}</option>`).join('');
  });
}

// ─── WEB PUSH ─────────────────────────────────────────────────────────────────

function _urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)));
}

async function initPush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;

  try {
    // Registrar Service Worker desde la raíz para scope completo
    const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
    await navigator.serviceWorker.ready;

    // Verificar si ya está suscripto
    const existingSub = await reg.pushManager.getSubscription();
    if (existingSub) {
      // Ya suscripto — sincronizar con backend silenciosamente
      await API.post('/api/push/subscribe', existingSub.toJSON()).catch(() => {});
      return;
    }

    // Obtener clave pública VAPID
    const resp = await API.get('/api/push/vapid-public-key');
    if (!resp?.key) return;

    // Solicitar permiso
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') return;

    // Suscribirse
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: _urlBase64ToUint8Array(resp.key),
    });

    await API.post('/api/push/subscribe', sub.toJSON());
    console.log('[Push] Suscripción registrada ✅');
  } catch (e) {
    console.warn('[Push] No se pudo activar push:', e.message);
  }
}

// Active nav item
document.addEventListener('DOMContentLoaded', () => {
  const path = window.location.pathname;
  document.querySelectorAll('.nav-item, .bottom-nav-item').forEach(item => {
    const href = item.getAttribute('href');
    if (href && (path === href || (href !== '/' && path.startsWith(href)))) {
      item.classList.add('active');
    }
  });
  loadNotifications();
  // Poll every 60 seconds
  setInterval(loadNotifications, 60000);
  // Inicializar Web Push (pide permiso la primera vez)
  initPush().then(() => updatePushBtn());
});
