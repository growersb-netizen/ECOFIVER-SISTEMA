# Bajas comerciales y sesiones del widget web

Fecha: 31/10/2026 · PR #9

## 1. Bajas de comunicaciones comerciales

**Qué pasa cuando un contacto pide no recibir más mensajes** ("no me escriban más", "dame de baja", "STOP"…):

1. El router lo detecta sin llamar a la IA y le pide al CRM que registre la baja (`POST /api/contactos/baja`).
2. El CRM guarda la baja en `exclusiones_comerciales`. La clave son los últimos 10 dígitos del teléfono, así que vale para todos los leads con ese número, también los que se creen después.
3. Si el CRM confirmó el registro, el contacto recibe: *"No te vamos a enviar más mensajes comerciales"*. Si no lo confirmó, recibe un cierre que no promete nada, y queda un error en el log.

**Qué queda bloqueado para quien tiene la baja:**

| Origen | Cómo |
|---|---|
| Seguimiento multitouch, primer contacto, nutrición 24 h, reactivación (tareas programadas) | El CRM los saca de los listados y el multiagente vuelve a consultar antes de cada envío |
| Acciones de agentes internos (`contactar_lead`, `contactar_leads_sin_respuesta`, `reactivar_leads_frios`), aunque las pida Máximo | Consulta antes de enviar |
| Primer contacto de formularios Meta | El lead se registra igual (reparto intacto); solo no se le escribe |
| WhatsApp extra después de responder un email, scraper | Consulta antes de enviar |
| Pedido de testimonio post-instalación (CRM) | Consulta antes de enviar |

Si no se puede confirmar con el CRM si el contacto tiene baja, **no se envía** (falla cerrado). Los contadores están en `/health/seguridad` → `contacto_comercial`.

**Qué NO bloquea, a propósito:**
- **Responder cuando el contacto escribe por su cuenta.** Se le responde, pero el agente recibe la indicación de no ofrecer promociones ni seguimientos. Volver a escribir **no levanta la baja**.
- **Avisos contractuales:** cobranza de cuotas y recordatorio de una videollamada que el cliente agendó.
- **Mensajes manuales de una persona desde la bandeja del CRM.** Es una decisión humana.

**Levantar una baja** (por ejemplo, el cliente pidió volver a recibir novedades): `POST /api/contactos/baja/reactivar` con `{"telefono": "...", "motivo": "..."}`. Solo lo puede hacer un **administrador humano** con sesión del CRM: la API key de los agentes no sirve. Queda registrado quién la levantó y por qué.

**Migración:** `0039_exclusiones_comerciales`. Solo crea la tabla nueva, no toca datos existentes, y el rollback está bloqueado porque borraría bajas.

## 2. Sesiones del widget web

Antes, el navegador inventaba su `session_id` y el servidor lo aceptaba. Quien conociera el id de otra persona podía leer y continuar su conversación. Ahora:

- El widget pide la sesión a `POST /chat/web/sesion`. El servidor genera el id y una firma HMAC.
- `POST /chat/web` exige `session_id` y `session_token`. Sin una firma válida responde 401 y no llama al router.
- Si la sesión venció (por un reinicio o porque cambió el secreto), el widget pide una nueva y reintenta solo.
- `chat.js` se sirve con `Cache-Control: no-cache` para que los navegadores tomen la versión nueva.

**Variable recomendada (la configura Rodrigo en Railway, servicio multiagente):** `WEB_SESSION_SECRET` = un valor largo y aleatorio, por ejemplo la salida de `openssl rand -hex 32`. Sin ella el widget funciona igual, pero con un secreto temporal: cada reinicio corta las conversaciones abiertas en el widget. `/health/seguridad` → `widget_sesiones.secreto` muestra si está configurada.
