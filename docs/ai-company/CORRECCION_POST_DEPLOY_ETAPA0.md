# Corrección post-deploy Etapa 0 (28/10/2026)

Estado: **corregido en código y probado localmente. No verificado en producción** hasta el deploy y los pasos de abajo.

## 1. Máximo responde "Dame un momentito y te respondo enseguida 🙏"

Ese texto es la respuesta de espera de `BaseAgent.respond` cuando **fallan todos** los proveedores de IA.

| | Hallazgo | Evidencia |
|---|---|---|
| Causa raíz (código) | El historial guardaba el mensaje con todo el contexto inyectado. Máximo recibe el CRM completo (200 leads, todas las ventas, métricas) y su instancia para `admin_rodrigo` vive hasta el reinicio: cada turno sumaba otra copia del volcado. A los pocos turnos el request supera la ventana de contexto de cualquier modelo y toda la cadena falla. En Telegram la lista ni siquiera se recortaba. | `tests/test_maximo_ia.py::test_maximo_sigue_respondiendo_en_conversacion_larga`: con el código anterior falla en el turno 3; con el fix responde los 20 turnos |
| Eslabón roto | El fallback usaba `openrouter/auto:free`, que **no existe** en OpenRouter. También eran inválidos 3 modelos del selector del panel admin (`anthropic/claude-3-haiku`, `google/gemini-flash-1.5`, `openai/chatgpt-4o-latest`). | Contrastado con `https://openrouter.ai/api/v1/models` el 28/10/2026 |
| Descartado | El PR #3 no tocó la ruta de IA. La autenticación multiagente → CRM funciona (`/health/crm`: los fallos son 404 de `save_message("admin_rodrigo")`, que no existe como lead; comportamiento anterior, no afecta al inbox). | diff `764aef1..3d88324` |
| **No verificable desde acá** | Proveedor primario y modelo reales en producción, saldo de OpenRouter y errores concretos (los logs de Railway no son accesibles). | → `GET /health/ia` después del deploy |

Corrección: el historial guarda el mensaje original (el contexto se reinyecta fresco en cada turno), recorte in-place con tope `HISTORY_MAX_CHARS` (24000 por defecto), los turnos fallidos no se guardan, fallbacks válidos (`modelo configurado → openai/gpt-4o-mini → openrouter/free`, configurable con `OPENROUTER_FALLBACK_MODELS`) y normalización de IDs inexistentes.

Nuevo `GET /health/ia` (público, sin secretos): proveedor y modelo primario, qué claves existen (true/false) y, por proveedor, ok/fallos y **categoría** del último error (`sin_creditos`, `modelo_inexistente`, `contexto_excedido`, `clave_invalida`, `rate_limit`, `timeout`…).

## 2. Control Center → HTTP 401 `{"ok":false,"error":"no autorizado"}`

| Servicio | Credencial que usa |
|---|---|
| eco-multiagente `/api/comando` | Acepta `MULTIAGENTE_API_KEY` o `ADMIN_PASSWORD` (header `X-Api-Key`) |
| eco-crm (antes) | Solo `ConfiguracionSistema.orquestador_api_key`, **sin campo en la UI** (`PUT /api/config/orquestador_api_key` → 404). Vacía → no enviaba header → 401 |
| eco-crm (ahora) | 1) env `MULTIAGENTE_API_KEY` del CRM; 2) `orquestador_api_key` (Configuración → API Keys, cifrada). Siempre desde el servidor |

El checklist de la Etapa 0 pedía alinear `orquestador_api_key`, pero desde la UI eso no era posible.

## 3. Catálogo

El panel lista los 16 agentes reales de eco-multiagente. Los anteriores (Claudio, Pablo, Laura, Sabrina, Carlos, Marina, Diego, Ana, Marcos, Elena (versión anterior), Gabriel, Patricia, Sofía, Rodrigo IA) quedan como `AGENTES_HISTORICOS`: inactivos y visibles con su nombre solo en el historial. No se tocó ningún agente productivo ni la base de datos.

## Intervención requerida en Railway (Rodrigo)

Los valores se generan y se cargan directamente en Railway. Nunca se pegan en chats ni commits.

1. **eco-multiagente**: si no existe, crear `MULTIAGENTE_API_KEY` (`openssl rand -hex 32`). Es el paso B0 de `ROTACION_CREDENCIALES.md`: desacopla el Control Center de `ADMIN_PASSWORD`.
2. **eco-crm**: crear `MULTIAGENTE_API_KEY` como **referencia** `${{eco-multiagente.MULTIAGENTE_API_KEY}}` (así una rotación no requiere copiar el valor). Alternativa sin Railway: Configuración → API Keys → "Agentes IA — API Key (Control Center)" → pegar → **Probar**.
3. Desplegar los dos servicios (el orden no importa).
4. Abrir `https://eco-multiagente-production.up.railway.app/health/ia` y revisar `proveedor_primario`, `modelo_primario` y `claves_presentes`. Si después de unos mensajes `por_proveedor` muestra `sin_creditos`, `clave_invalida` o `modelo_inexistente`, eso es configuración/saldo, no código (ver tabla abajo).
5. Opcional: si existe `FORCE_OPENROUTER_MODEL` u `OPENROUTER_MODEL` con un ID viejo, corregirlo (el código ya traduce los 4 IDs inválidos conocidos).

| `last_categoria` en `/health/ia` | Acción |
|---|---|
| `sin_creditos` | Cargar saldo en OpenRouter o cambiar el proveedor primario |
| `clave_invalida` / `sin_clave` | Regenerar la clave del proveedor y cargarla en Railway |
| `modelo_inexistente` | Corregir `OPENROUTER_MODEL` / `GEMINI_MODEL` / `GROQ_MODEL` |
| `contexto_excedido` | No debería volver a aparecer; si aparece, bajar `HISTORY_MAX_CHARS` y avisar |
| `rate_limit` | Transitorio; si persiste, revisar el plan del proveedor |

## Verificación en producción

```bash
M=https://eco-multiagente-production.up.railway.app
curl -s $M/health/ia                                         # proveedor, claves (bool), contadores
curl -s -o /dev/null -w "%{http_code}\n" $M/api/comando/ping  # 401 (protegido)
curl -s -o /dev/null -w "%{http_code}\n" $M/audit/log         # 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST $M/send/whatsapp -H 'Content-Type: application/json' -d '{"phone_number":"0","text":"x"}'  # 401
curl -s $M/health/seguridad                                  # firmas válidas, sin rechazos
```

Funcional (manual):
1. Rodrigo escribe 5 o más mensajes seguidos a Máximo por WhatsApp → responde con contenido real, no con el mensaje de espera. `/health/ia` → `respuestas_ok` sube y `respuestas_de_espera` no.
2. Control Center: el indicador dice "Sistema online" (no "credencial rechazada"). "Resumen del pipeline" queda en estado `ENVIADO` (HTTP 200).
3. Mensaje de un cliente a la línea de agentes → responde; el inbox registra IN y OUT.
4. Línea supervisada (1383774158147416): sigue sin respuesta de IA y registra en el inbox.

## Limitación vigente (no es una regresión)

`/api/comando` del multiagente **solo registra** el comando en la auditoría y responde "Comando registrado". No ejecuta al agente ni devuelve el resumen del pipeline; así funcionaba antes de la Etapa 0. Que el Control Center ejecute comandos es una funcionalidad nueva (Etapa 1) que requiere definir permisos y aprobación humana para acciones sensibles.

## Rollback

Revertir los commits. No hay migraciones ni cambios de datos. Las variables nuevas son opcionales.

## Integración con el PR #4 (Etapa 1)

Cuando se fusione el PR #4, que fue integrado con este PR:

- **`/health/ia` pasa a ser la del PR #4** (`tools/ai_metrics.py`). Es la única ruta registrada, y lo verifica un test. Los campos `claves_presentes`, `por_proveedor` y `last_categoria` de esta guía dejan de existir. Se reemplazan por `proveedor_configurado`, `modelo_configurado`, `ultimo_proveedor_efectivo`, `pct_respaldo`, `por_agente`, `por_modelo` y `totales`. Los textos de error solo se ven con `?detalle=true` y la API key.
- **La cadena de respaldo pasa a ser la del PR #4:** solo usa OpenRouter, con modelos por rol validados contra el catálogo.
- **Se conserva entera la corrección de memoria de este PR.** Una regresión de punta a punta lo verifica: 20 mensajes por `route_message(canal="whatsapp_admin")` al Máximo real. Sin la corrección, falla en el 5.º mensaje.
- **Se conserva la normalización de IDs inexistentes** (`openrouter/auto:free` → `openrouter/free`). El PR #4 todavía tenía `openrouter/auto:free` como modelo por defecto.
