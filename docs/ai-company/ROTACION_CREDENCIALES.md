# Rotación de credenciales comprometidas — EcoFiver

Autorizada el 28/10/2026: **API key del CRM** y **ADMIN_PASSWORD del multiagente**.
Ambas estuvieron expuestas (historial de git, JavaScript del panel de socios, pantalla de login de `/dashboard`).

Reglas: los valores nuevos se generan y se cargan **directamente en Railway**. Nunca se pegan en chats, commits, issues ni logs.
Generar cada valor con: `openssl rand -hex 32`.

**Requisito previo:** el PR #3 desplegado. Aporta la aceptación simultánea de la clave vigente y la anterior en el CRM (`API_KEY_ANTERIOR` / `CRM_API_KEY_ANTERIOR`), que permite rotar sin cortes, y la prioridad de Railway sobre el `.env` del volumen para los secretos.

## 1. Consumidores identificados

### API key del CRM
| Consumidor | Variable | Uso |
|---|---|---|
| eco-crm | `API_KEY` | Valida `/api/ext/*` (Zapia), `/api/leads/*` y `/api/stats/*` de agentes (Bearer), ML, socios, catálogo, imágenes, ventas financiadas, meta ads |
| eco-crm | `CRM_API_KEY` | Valida el inbox (`/api/inbox/entrante`) que llama el multiagente |
| eco-multiagente | `CRM_API_KEY` (solo Railway, `_RAILWAY_ONLY`) | Todas las llamadas al CRM (crm_client, inbox, cron, monitor). Usa **una** clave para `API_KEY` e inbox → en el CRM ambas deben ser iguales |
| eco-multiagente | `R2_API_KEY` (si falta, usa `CRM_API_KEY`) | Subida de archivos al sitio web (`/api/admin/upload`) |
| ecofiver-mcp-server | `CRM_API_KEY` | Contratos y pagos vía `/api/contratos` |
| Zapia (externo) | Header `X-Api-Key` | API `/api/ext/*` |
| Sitio web (fuera de este repo) | Valida `x-api-key` en `/api/admin/upload` | Probablemente acepta el **valor viejo**: es otra credencial a rotar con quien administre el sitio |
| Scripts locales | `API_KEY` / `CRM_API_KEY` en el entorno | `actualizar_biblioteca.ps1`, `scripts/*.py` |

### ADMIN_PASSWORD (multiagente)
| Consumidor | Uso |
|---|---|
| Login de `/admin`, `/panel`, `/dashboard` | Rodrigo (y Renzo, según el código del dashboard) |
| Endpoints protegidos de la Etapa 0 | Se acepta como API key si no hay `MULTIAGENTE_API_KEY` |
| CRM → `ConfiguracionSistema.orquestador_api_key` | Si es igual a la contraseña, el Control Center se corta al rotarla → se desacopla en el paso B0 |
| `/data/.env` del volumen | Puede tener una copia, escrita desde el panel. Con el PR #3, si Railway la define, Railway manda |

## 2. Secuencia sin cortes

### A. API key del CRM
| Paso | Dónde | Acción | Verificación |
|---|---|---|---|
| A0 | multiagente | Definir `R2_API_KEY` explícita con el valor **actual** (desacopla el sitio web de la rotación) | Renata sigue subiendo archivos |
| A1 | eco-crm | `API_KEY_ANTERIOR` = valor actual de `API_KEY`; `CRM_API_KEY_ANTERIOR` = valor actual de `CRM_API_KEY`; luego `API_KEY` = **nueva**, `CRM_API_KEY` = **nueva** → redeploy | CRM sano (`/api/health`). Acepta clave vieja y nueva |
| A2 | multiagente | `CRM_API_KEY` = nueva (o automática si es referencia a la variable del CRM) → redeploy | `/health/crm`: `calls_fail` no crece; mensajes IN/OUT siguen apareciendo en el inbox |
| A3 | ecofiver-mcp-server | `CRM_API_KEY` = nueva → redeploy | Una consulta de contrato desde Claude.ai funciona |
| A4 | Zapia | Actualizar el header `X-Api-Key` | Zapia lista leads |
| A5 | eco-crm | **Borrar** `API_KEY_ANTERIOR` y `CRM_API_KEY_ANTERIOR` → redeploy | `curl -H "X-Api-Key: <vieja>" .../api/ext/leads` → **401** |
| A6 | Sitio web | Rotar su clave de upload y actualizar `R2_API_KEY` | Subida de prueba OK |

Rollback en cualquier paso entre A1 y A4: volver a cargar el valor viejo en `API_KEY` (los `_ANTERIOR` siguen aceptando ambos).

### B. ADMIN_PASSWORD
| Paso | Dónde | Acción | Verificación |
|---|---|---|---|
| B0 | multiagente + CRM | Definir `MULTIAGENTE_API_KEY` (nueva) en el multiagente y el mismo valor en `orquestador_api_key` del CRM (Configuración) | Un comando desde el Control Center da 200 |
| B1 | multiagente | `ADMIN_PASSWORD` = **nueva** en Railway → redeploy | Login en `/admin`, `/panel`, `/dashboard` con la nueva |
| B2 | — | Probar la contraseña vieja | Rechazada |
| B3 | — | Avisar a quienes usan el dashboard (Renzo) | — |

### C. Nueva credencial: MCP_AUTH_TOKEN (servidor MCP)
| Paso | Acción | Verificación |
|---|---|---|
| C1 | Definir `MCP_AUTH_TOKEN` en ecofiver-mcp-server → redeploy | `POST /mcp` sin token → 401 |
| C2 | En Claude.ai → Conectores: cambiar la URL del conector a `https://<mcp>/mcp/<token>` | El conector vuelve a listar las 3 herramientas |

Entre C1 y C2 el conector de Claude.ai deja de funcionar. Hacer ambos pasos juntos.
