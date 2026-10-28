# EcoFiver AI Company — Etapa 1 (parte independiente): observabilidad e informes

Estado: **implementado y probado localmente** (92 tests del multiagente). **No desplegado.** Depende del PR de la Etapa 0 (se apoya en `security.require_api_key`).

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

## Hallazgo
Máximo y Valentín **no usan OpenRouter**: tienen modelo propio y van directo a Gemini (`base_agent._get_provider`). `/health/ia` lo muestra en `por_modelo`.

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
