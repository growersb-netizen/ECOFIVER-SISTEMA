# Modelo de IA por agente (todo vía OpenRouter)

Estado: **implementado y probado localmente** (122 tests del multiagente). No desplegado.

## Cómo funciona
- `tools/openrouter_catalog.py` descarga el catálogo real de OpenRouter (`/api/v1/models`) al iniciar y todos los días a las 04:10. Guarda los precios, el contexto y las entradas que acepta cada modelo (texto, imagen, audio), y los deja en caché en `DATA_DIR/openrouter_models.json`.
- `tools/model_policy.py` asigna a cada agente un **rol**, y a cada rol un modelo principal, sus respaldos, la temperatura y el largo máximo de respuesta.
- **Validación:** si el modelo configurado no existe en el catálogo, o no acepta la entrada que necesita el rol (audio para transcribir, imagen para visión), se usa el primer respaldo válido. El aviso queda en `/health/ia/modelos`.
- El costo en `/health/ia` usa los **precios reales del catálogo**.

## Roles
| Rol | Agentes | Criterio |
|---|---|---|
| ventas | Valentina, Camila, Nicolás, Luciano, Mateo | Alto volumen, conversación con clientes: rápido y económico |
| postventa | Sebastián | Tono cuidadoso, poca creatividad |
| socios | Franco | Volumen medio |
| direccion | Máximo | Poco volumen; decide y ejecuta acciones en el CRM: mayor capacidad de razonamiento |
| analisis | Aurora, Tomás, Elena, Ezequiel, Ignacio, Bruno | Mucho contexto del CRM y poco volumen: contexto amplio y económico, temperatura baja |
| contenido | Renata | Redacción creativa |
| reputacion | Daniela | Textos sensibles: más capacidad, temperatura baja |
| privado | Valentín | Decide el administrador |
| audio | transcripción de notas de voz | Debe aceptar audio |
| vision | lectura de DNI | Debe aceptar imagen |

## Perfiles
- `AI_PERFIL_MODELOS=base` (**default**): igual que hoy. Todos los agentes usan `OPENROUTER_MODEL` (`openai/gpt-4o-mini`), con temperatura 0.7 y 700 tokens. Al desplegar no cambia ni el costo ni el estilo de respuesta.
- `AI_PERFIL_MODELOS=recomendado`: un modelo según la función. Es una **hipótesis**; los precios de referencia están sin verificar desde este entorno:

| Rol | Modelo | Respaldo | Temp. | Máx. tokens |
|---|---|---|---|---|
| ventas | openai/gpt-4o-mini | google/gemini-2.5-flash | 0.6 | 600 |
| postventa | openai/gpt-4o-mini | google/gemini-2.5-flash | 0.4 | 700 |
| socios | openai/gpt-4o-mini | google/gemini-2.5-flash | 0.6 | 700 |
| direccion | anthropic/claude-sonnet-4 | gemini-2.5-flash, gpt-4o-mini | 0.3 | 1500 |
| analisis | google/gemini-2.5-flash | openai/gpt-4o-mini | 0.3 | 1200 |
| contenido | google/gemini-2.5-flash | openai/gpt-4o-mini | 0.8 | 1200 |
| reputacion | anthropic/claude-sonnet-4 | openai/gpt-4o-mini | 0.3 | 800 |
| audio | google/gemini-2.5-flash | google/gemini-2.0-flash-001 | 0 | 1000 |
| vision | openai/gpt-4o-mini | google/gemini-2.5-flash | 0 | 800 |

Ajuste fino sin cambiar código (se aplica encima del perfil activo):
```
AI_MODELOS_JSON={"maximo": {"modelo": "google/gemini-2.5-pro"}, "rol:ventas": {"temperatura": 0.5}}
```

## Cómo decidir (validar → medir → escalar)
1. Desplegar con el perfil `base`.
2. Después de un día de tráfico real, abrir `/health/ia/modelos`. La sección `comparacion_perfiles_hoy` estima cuánto habría costado ese mismo día con cada perfil, usando los precios reales del catálogo.
3. Si el costo es aceptable, activar `recomendado` o probar un solo rol con `AI_MODELOS_JSON` (por ejemplo, solo Máximo) y comparar la calidad de las respuestas.

## Pendiente
El CRM (respuestas de MercadoLibre, blog, textos de EcoPost) sigue usando un único modelo (`OPENROUTER_MODEL`). Llevarle esta misma política es un paso aparte.
