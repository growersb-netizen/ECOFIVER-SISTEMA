# EcoFiver AI Company — Etapa 1 (parte independiente): observabilidad e informes

Estado: **implementado y probado localmente** (107 tests del multiagente, 16 del CRM). **No desplegado.** Depende del PR de la Etapa 0 (se apoya en `security.require_api_key`).

## Qué incluye

| Componente | Qué hace | Dónde |
|---|---|---|
| Métricas de IA | Cada llamada a un proveedor (principal y respaldos) registra agente, proceso, proveedor efectivo, modelo, ok/error, latencia, tokens y costo (real si el proveedor lo informa; si no, tokens × tabla de precios; si no hay tokens, estimados por caracteres). Registra cuando todos los proveedores fallan (respuesta genérica al cliente) y alerta por Telegram | `tools/ai_metrics.py`, `agents/base_agent.py`, `providers/*` |
| Límite de costo diario | `AI_DAILY_COST_LIMIT_USD` (default 5). Alerta al 80 % y al 100 %, una vez por día. **No bloquea respuestas** | `tools/ai_metrics.py` |
| `GET /health/ia` | Resumen del día: proveedor configurado y efectivo, % de respaldo, tokens, costo, por agente / proceso / modelo. Los textos de error solo con `?detalle=true` + API key | `main.py` |
| Registro del scheduler | Todas las tareas programadas (≈22) quedan envueltas: inicio, fin, duración, estado, resultado y error. Memoria + `DATA_DIR/scheduler_runs.jsonl` | `scheduler/run_log.py` |
| `GET /health/scheduler` | Última ejecución de cada tarea. `?detalle=true` + API key: resultados y errores | `main.py` |
| Tomás | La alerta de leads sin seguimiento ya no se le pide a la IA (y se descartaba): se arma con los datos del CRM y llega al Telegram de Rodrigo. Sin repetir el mismo lead durante 6 h. **No escribe a clientes** | `scheduler/cron.py` |
| Aurora | Informe de la mañana (09:00) y cierre del día (18:00) con números reales, prioridades y acciones con responsable → Telegram | `scheduler/cron.py` |
| Renata | La propuesta de calendario semanal (lunes) → Telegram, en vez de descartarse | `scheduler/cron.py` |

Feature flag: `ETAPA1_INFORMES_TELEGRAM=0` vuelve al comportamiento anterior (sin envíos).

## Política: todo el consumo de IA pasa por OpenRouter
Decisión del 28/10/2026. Antes había llamadas directas a Groq, Grok, Gemini, Claude y HuggingFace.

| Uso | Antes | Ahora |
|---|---|---|
| Agentes (todos, incluido Máximo) | Proveedor según `AI_PROVIDER` (el `.env` del volumen podía fijar grok/groq/gemini) | Siempre OpenRouter, modelo `OPENROUTER_MODEL` (default `openai/gpt-4o-mini`). `AI_PROVIDER` distinto se ignora con aviso en el log |
| Respaldo de agentes | Groq → OpenRouter free → Grok → Gemini directos | Otros modelos **dentro de OpenRouter**: `OPENROUTER_FALLBACK_MODELS` (default `openai/gpt-4o-mini,google/gemini-2.5-flash`, omitiendo el principal) |
| Transcripción de audios | Groq Whisper → OpenRouter (audio enviado como imagen) → Gemini SDK | OpenRouter con `input_audio`; OGG/Opus se convierte a mp3 con ffmpeg (agregado al Dockerfile). Modelos: `AUDIO_OPENROUTER_MODELS` |
| CRM `ai_complete` | OpenRouter y, sin clave, Grok/Gemini/Claude | Solo OpenRouter |
| EcoPost imágenes | OpenRouter → Worker → Gemini Imagen directo | OpenRouter → Worker (que usa OpenRouter) |
| CRM imágenes | OpenRouter → HuggingFace | Solo OpenRouter |
| Visión (DNI), Worker de Cloudflare | Ya usaban OpenRouter | Sin cambios |

Quedan, sin uso en el tráfico: los módulos de otros proveedores en `providers/` y los botones de "probar conexión" de los paneles de configuración (solo se ejecutan si alguien los presiona).

**Corrección:** un informe anterior decía que Máximo usaba Gemini directo. Era incorrecto: Máximo no define modelo propio y usaba el proveedor global.

**Riesgo a verificar después del deploy:** los audios dependen ahora de que el modelo de OpenRouter acepte `input_audio`. Prueba: mandar una nota de voz a la línea de agentes y ver en `/health/ia` el agente `transcripcion` con `ok`. Si falla, el cliente recibe el pedido de que escriba (comportamiento existente) y se cambia el modelo con `AUDIO_OPENROUTER_MODELS`, sin redeploy de código.

## Lo que NO incluye (y por qué)
| Pendiente de la Etapa 1 | Bloqueo real |
|---|---|
| Migrar mensajes proactivos a plantillas de WhatsApp | Hace falta saber qué plantillas están **aprobadas** en Meta y confirmar en los logs de producción los rechazos fuera de la ventana de 24 h (error 131047). Sin eso sería adivinar con clientes reales |
| Unificar cobranza (CRM + Ignacio) | Requiere ver en producción qué circuito envía realmente; la directiva prohíbe suspender el actual sin un reemplazo verificado |
| Unificar publicación (EcoPost + Renata) | Requiere ver qué publica cada uno en producción |
| Criterio de aceptación (7 días observables) | Empieza a contar desde el deploy |

## Verificación post-deploy
```bash
curl -s $M/health/ia | jq '.proveedor_configurado, .ultimo_proveedor_efectivo, .totales, .pct_respaldo'
curl -s $M/health/scheduler | jq '.tareas | to_entries | map(select(.value.estado=="error"))'
```
- A las 09:00 y 18:00 llega el informe de Aurora a Telegram.
- Si hay leads sin seguimiento, llega la alerta de Tomás (máximo una vez por lead cada 6 h).
