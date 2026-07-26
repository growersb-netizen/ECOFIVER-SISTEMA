/**
 * EcoFiver — Widget de Chat con Valentina
 * Vanilla JS sin dependencias externas.
 * Conecta a: POST /chat/web
 */
(function () {
  "use strict";

  // ── Configuración ─────────────────────────────────────────────
  const API_URL     = window.ECO_CHAT_URL || "/chat/web";
  const AGENT_NAME  = "Valentina";
  const COMPANY     = "EcoFiver";
  const WELCOME_MSG =
    "¡Hola! ¿Cómo estás? 😊\nContame, ¿estás buscando una piscina o un módulo?";

  // ── Genera session_id único por visita (UUID v4) ───────────────
  function generateUUID() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      const r = (Math.random() * 16) | 0;
      const v = c === "x" ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  const SESSION_KEY = "eco_chat_session_id";
  let sessionId = sessionStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId = generateUUID();
    sessionStorage.setItem(SESSION_KEY, sessionId);
  }

  let isOpen        = false;
  let isWaiting     = false;
  let welcomeSent   = false;

  // ── Inyectar CSS ──────────────────────────────────────────────
  function injectCSS() {
    const cssUrl = (window.ECO_WIDGET_BASE || "") + "/web_widget/chat.css";
    const link   = document.createElement("link");
    link.rel     = "stylesheet";
    link.href    = cssUrl;
    document.head.appendChild(link);
  }

  // ── Crear HTML del widget ──────────────────────────────────────
  function createWidget() {
    const wrapper = document.createElement("div");
    wrapper.id    = "eco-chat-widget";
    wrapper.innerHTML = `
      <!-- Botón flotante -->
      <button id="eco-chat-btn" title="Chatear con ${AGENT_NAME}" aria-label="Abrir chat">
        <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <path d="M20 2H4C2.9 2 2 2.9 2 4v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2
           12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/>
        </svg>
        <span id="eco-chat-badge"></span>
      </button>

      <!-- Ventana de chat -->
      <div id="eco-chat-window" role="dialog" aria-label="Chat con ${AGENT_NAME}">
        <div id="eco-chat-header">
          <div id="eco-chat-avatar">🌿</div>
          <div id="eco-chat-header-info">
            <div id="eco-chat-header-name">${AGENT_NAME}</div>
            <div id="eco-chat-header-sub">${COMPANY}</div>
          </div>
          <button id="eco-chat-close" aria-label="Cerrar chat">
            <svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5
             6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
          </button>
        </div>

        <div id="eco-chat-messages" role="log" aria-live="polite"></div>

        <div id="eco-chat-input-area">
          <textarea
            id="eco-chat-input"
            placeholder="Escribí tu mensaje..."
            rows="1"
            aria-label="Escribir mensaje"
          ></textarea>
          <button id="eco-chat-send" aria-label="Enviar mensaje" disabled>
            <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(wrapper);
  }

  // ── Utilidades de tiempo ───────────────────────────────────────
  function getTimeStr() {
    const now = new Date();
    return now.getHours().toString().padStart(2, "0") +
           ":" + now.getMinutes().toString().padStart(2, "0");
  }

  // ── Agregar mensaje al chat ────────────────────────────────────
  function addMessage(text, type) {
    const messages = document.getElementById("eco-chat-messages");
    const div      = document.createElement("div");
    div.className  = `eco-msg ${type}`;

    // Reemplazar saltos de línea con <br>
    const escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\n/g, "<br>");

    div.innerHTML = `
      <div class="eco-msg-bubble">${escaped}</div>
      <div class="eco-msg-time">${getTimeStr()}</div>
    `;
    messages.appendChild(div);
    scrollToBottom();
    return div;
  }

  // ── Indicador de "escribiendo..." ─────────────────────────────
  function showTyping() {
    const messages = document.getElementById("eco-chat-messages");
    const div      = document.createElement("div");
    div.className  = "eco-msg agent";
    div.id         = "eco-typing-indicator";
    div.innerHTML  = `
      <div class="eco-typing">
        <div class="eco-typing-dot"></div>
        <div class="eco-typing-dot"></div>
        <div class="eco-typing-dot"></div>
      </div>
    `;
    messages.appendChild(div);
    scrollToBottom();
  }

  function hideTyping() {
    const el = document.getElementById("eco-typing-indicator");
    if (el) el.remove();
  }

  function scrollToBottom() {
    const messages = document.getElementById("eco-chat-messages");
    messages.scrollTop = messages.scrollHeight;
  }

  // ── Enviar mensaje al backend ──────────────────────────────────
  async function sendMessage(text) {
    if (!text.trim() || isWaiting) return;

    addMessage(text, "user");
    clearInput();
    isWaiting = true;
    setInputEnabled(false);
    showTyping();

    try {
      const res = await fetch(API_URL, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ session_id: sessionId, message: text }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      hideTyping();
      addMessage(data.reply || "...", "agent");

    } catch (err) {
      hideTyping();
      addMessage(
        "Disculpá, tuve un problema técnico. Intentá de nuevo en un momento. 🙏",
        "agent"
      );
      console.error("[EcoChat] Error:", err);
    } finally {
      isWaiting = false;
      setInputEnabled(true);
      document.getElementById("eco-chat-input").focus();
    }
  }

  // ── Helpers de input ──────────────────────────────────────────
  function clearInput() {
    const input = document.getElementById("eco-chat-input");
    input.value = "";
    input.style.height = "auto";
    updateSendBtn();
  }

  function setInputEnabled(enabled) {
    const input = document.getElementById("eco-chat-input");
    const send  = document.getElementById("eco-chat-send");
    input.disabled = !enabled;
    send.disabled  = !enabled || !input.value.trim();
  }

  function updateSendBtn() {
    const input = document.getElementById("eco-chat-input");
    const send  = document.getElementById("eco-chat-send");
    send.disabled = !input.value.trim() || isWaiting;
  }

  // ── Abrir / Cerrar chat ────────────────────────────────────────
  function openChat() {
    isOpen = true;
    document.getElementById("eco-chat-window").classList.add("open");
    document.getElementById("eco-chat-badge").classList.remove("visible");

    // Enviar mensaje de bienvenida la primera vez
    if (!welcomeSent) {
      welcomeSent = true;
      setTimeout(() => {
        addMessage(WELCOME_MSG, "agent");
        document.getElementById("eco-chat-input").focus();
      }, 300);
    } else {
      setTimeout(() => {
        document.getElementById("eco-chat-input").focus();
      }, 300);
    }
  }

  function closeChat() {
    isOpen = false;
    document.getElementById("eco-chat-window").classList.remove("open");
  }

  // ── Evento: auto-resize del textarea ──────────────────────────
  function setupAutoResize() {
    const input = document.getElementById("eco-chat-input");
    input.addEventListener("input", function () {
      this.style.height = "auto";
      this.style.height = Math.min(this.scrollHeight, 100) + "px";
      updateSendBtn();
    });
  }

  // ── Inicialización ────────────────────────────────────────────
  function init() {
    injectCSS();
    createWidget();

    // Botón flotante
    document.getElementById("eco-chat-btn").addEventListener("click", () => {
      isOpen ? closeChat() : openChat();
    });

    // Botón cerrar dentro de la ventana
    document.getElementById("eco-chat-close").addEventListener("click", closeChat);

    // Botón enviar
    document.getElementById("eco-chat-send").addEventListener("click", () => {
      const val = document.getElementById("eco-chat-input").value.trim();
      sendMessage(val);
    });

    // Enter para enviar (Shift+Enter = nueva línea)
    document.getElementById("eco-chat-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const val = document.getElementById("eco-chat-input").value.trim();
        if (val) sendMessage(val);
      }
    });

    setupAutoResize();

    // Mostrar badge al cargar si el chat está cerrado (invita a abrir)
    setTimeout(() => {
      if (!isOpen) {
        document.getElementById("eco-chat-badge").classList.add("visible");
      }
    }, 3000);
  }

  // ── Arrancar cuando el DOM esté listo ─────────────────────────
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
