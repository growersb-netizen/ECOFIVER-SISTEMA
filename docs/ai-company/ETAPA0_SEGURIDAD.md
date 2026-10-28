# EcoFiver AI Company — Etapa 0: Seguridad crítica

Estado: **implementado y probado localmente** (multiagente 69 tests, CRM 12 tests, MCP verificado en ejecución). **No verificado en producción** hasta el deploy y el checklist de abajo.

## Qué se corrigió

| # | Problema (verificado en código) | Corrección | Archivo |
|---|---|---|---|
| 1 | `POST /send/whatsapp` sin autenticación: cualquiera podía escribir desde los números de la empresa | API key obligatoria | `eco-multiagente/channels/whatsapp.py` |
| 2 | `/audit/log` y `/audit/session/{id}` exponían conversaciones de clientes | API key obligatoria; `n` acotado a 500 | `eco-multiagente/main.py` |
| 3 | `/api/comando` aceptaba pedidos sin clave | Clave obligatoria (401/503) | `eco-multiagente/main.py` |
| 4 | `POST /leadgen/content/publish` (publica en Facebook) y `POST /leadgen/scraping/trigger` (contacta desconocidos) sin autenticación | API key obligatoria | `eco-multiagente/main.py` |
| 5 | Cualquier `[CRM_ACTION]` escrito por el modelo se ejecutaba, también en conversaciones con clientes (pagos, ventas, contratos, stock) | Política en servidor: nivel de acción + lista blanca por agente + canal. Sensibles nunca desde canal cliente; en canal cliente solo `update_lead` (lead propio, campos seguros) y `agendar_videollamada` (lead propio). `disparar_scraping` prohibida | `eco-multiagente/tools/action_policy.py`, `tools/crm_actions.py` |
| 6 | El widget web (y email) podía suplantar al admin: `session_id` igual al número de Rodrigo activaba el canal de Máximo | El canal admin solo se activa por `canal == "whatsapp_admin"` | `eco-multiagente/orchestrator/router.py` |
| 7 | Prompt injection: el cliente podía escribir señales (`[CRM_ACTION…]`, `[DERIVAR…]`) para que el modelo las repita | Se neutralizan en el texto del cliente antes de llegar al modelo | `eco-multiagente/orchestrator/router.py` |
| 8 | Webhook de WhatsApp sin verificación de firma ni deduplicación | Firma `X-Hub-Signature-256` (modos off/log/enforce); deduplicación por `wamid`; un webhook "del admin" sin firma válida se descarta | `eco-multiagente/security.py`, `channels/whatsapp.py` |
| 9 | Credenciales por defecto en el código (contraseña de admin, API key del CRM) | Eliminadas; el acceso falla cerrado si falta la variable | `auth.py`, `cron.py`, `channels/whatsapp.py`, `tools/content_poster.py` |
| 10 | **API key del CRM escrita en el JavaScript del panel de socios** (visible en el navegador de cualquier socio) | Quitada; el admin logueado sigue accediendo por sesión | `eco-crm/templates/panel_socio.html` |
| 11 | Inbox del CRM: con `CRM_API_KEY` vacía aceptaba requests sin clave | Falla cerrado | `eco-crm/routers/inbox.py` |
| 12 | `marketing.py` y `meta_ads.py` del CRM comparaban con `!=`: con `API_KEY` vacía y sin header, pasaban | Validación centralizada (`utils/api_keys.py`), falla cerrado, con soporte de rotación sin cortes (`API_KEY_ANTERIOR`) | `eco-crm/utils/api_keys.py` + 16 routers |
| 13 | **Servidor MCP sin autenticación**: `POST /mcp` creaba contratos y registraba pagos para cualquiera | `MCP_AUTH_TOKEN` (header Bearer o ruta `/mcp/<token>`); sin token mantiene el comportamiento anterior y lo advierte | `ecofiver-mcp-server/src/index.ts` |
| 14 | Contraseña por defecto `ADMIN_PASSWORD` en `dashboard.py` y `admin_panel.py`, y mostrada en la pantalla pública de login de `/dashboard` | Eliminadas | `eco-multiagente/dashboard.py`, `admin_panel.py` |
| 15 | El `.env` del volumen pisaba los secretos de Railway (una rotación en Railway podía no tener efecto) | Para secretos de autenticación manda Railway; el `.env` queda como respaldo | `eco-multiagente/main.py` |

Endpoint nuevo de observabilidad (sin datos privados): `GET /health/seguridad`.

## Variables de entorno (multiagente)

| Variable | Obligatoria | Uso |
|---|---|---|
| `ADMIN_PASSWORD` | Sí | Paneles y endpoints protegidos. Sin ella → 503. |
| `CRM_API_KEY` | Sí (ya existía) | Llamadas al CRM. Ya no tiene valor por defecto. |
| `MULTIAGENTE_API_KEY` | No | Clave para integraciones. Si no está, se acepta `ADMIN_PASSWORD`. |
| `WA_APP_SECRET` | Recomendada | App Secret de la app de Meta del webhook de WhatsApp (si falta, se usa `META_APP_SECRET`). |
| `WA_WEBHOOK_SIGNATURE_MODE` | No (default `log`) | `off` / `log` / `enforce`. |
| `R2_API_KEY` | No | Si falta, se usa `CRM_API_KEY` (compatibilidad). |

## Checklist de deploy (antes de mergear)

1. En Railway (multiagente): confirmar `ADMIN_PASSWORD` y `CRM_API_KEY` configuradas.
2. En el CRM, `ConfiguracionSistema.orquestador_api_key` debe coincidir con `MULTIAGENTE_API_KEY` o `ADMIN_PASSWORD`; si no, el Control Center recibe 401 (antes los comandos solo se registraban: no se pierde funcionalidad).
3. Confirmar en Railway que el multiagente corre con **1 réplica** (la deduplicación es en memoria).

## Verificación en producción (después del deploy)

```bash
M=https://<url-multiagente>
curl -s -o /dev/null -w "%{http_code}\n" -X POST $M/send/whatsapp -H 'Content-Type: application/json' -d '{"phone_number":"0","text":"x"}'   # 401
curl -s -o /dev/null -w "%{http_code}\n" $M/audit/log                         # 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST $M/api/comando -H 'Content-Type: application/json' -d '{"instruccion":"x"}'  # 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST $M/leadgen/scraping/trigger  # 401
curl -s $M/health/seguridad                                                  # contadores
```

Luego de tráfico real en todas las líneas: cuando `/health/seguridad` muestre `listo_para_enforce: true` (cada línea vista —Melanie, agentes, supervisada— con firmas válidas y ninguna inválida o ausente), pasar `WA_WEBHOOK_SIGNATURE_MODE=enforce`. El modo `off` es solo una vía de emergencia, no un estado final.

Regresión a confirmar: un mensaje de cliente a la línea de agentes recibe respuesta; un mensaje de Rodrigo a Máximo por WhatsApp recibe respuesta; la línea supervisada (1383774158147416) sigue sin respuesta de IA y registra en el inbox.

## Rollback

- Firma de webhook: `WA_WEBHOOK_SIGNATURE_MODE=off` (sin redeploy de código).
- Todo lo demás: revertir el commit; no hay migraciones ni cambios de datos.

## Pendiente que requiere autorización (no ejecutado)

- **Rotación de credenciales**: autorizada; procedimiento en `ROTACION_CREDENCIALES.md`. Requiere acceso a Railway.
- ~~Rotar la API key del CRM~~ (ver procedimiento): el valor anterior está publicado en el historial de git y estuvo en el JavaScript del panel de socios. Rotarla implica cambiar `API_KEY`/`CRM_API_KEY` en eco-crm, eco-multiagente, ecofiver-mcp-server y cualquier integración externa (Zapia).
- **Rotar la contraseña de admin del multiagente** si es la que estaba como valor por defecto en el código.
- `/api/inbox/modo/{phone}` del CRM sigue sin autenticación (filtra modo y lead_id por teléfono). El multiagente ya envía la clave; cerrarlo en un segundo deploy, después de confirmar que este está activo.
- `/dashboard/home` inyecta configuración no secreta (IDs, emails, URLs) en el HTML sin autenticación. Severidad media; requiere cambiar la carga de esa página.
- CORS `*` en el multiagente (bajo).
- Bot legado en la raíz del repo (`ecomodulos-agentes`): confirmar que no está desplegado.
- Volumen persistente `/data` en Railway: no verificable desde este entorno.
