# Incidente: enrutamiento en el canal admin de WhatsApp (28/10/2026)

## Causas verificadas

| Síntoma | Causa | Evidencia |
|---|---|---|
| Respondía un agente que no era Máximo | Respondió **Valentín**, el agente terapeuta personal, sin datos del negocio | `/health/ia` en producción: en `conversacion:whatsapp_admin`, Máximo hizo 5 llamadas y Valentín 8 |
| "Quiero hablar con Maximo" no volvía a Máximo | Máximo no estaba en la lista de agentes. Solo se volvía con frases exactas y con tilde | Reproducción con el enrutador de `main` |
| "No quiero hablar más con Valentín" dejaba a Valentín | La detección ignoraba la negación: "hablar con" + nombre → cambio **a** ese agente | Reproducción con el enrutador de `main` |
| Nombrar a "Valentina" activaba a Valentín | Coincidencia por subcadena ("valentin" está dentro de "valentina") | Reproducción con el enrutador de `main` |
| "Pasame el resumen de operaciones" cambiaba a Bruno | "pasame" (mandame) se tomaba como pedido de cambio | Reproducción con el enrutador de `main` |
| "No tengo acceso a los precios, consultá al fabricante" | Valentín no recibe precios ni catálogo (`AGENT_CRM_NEEDS`). Máximo y los vendedores sí | `tools/crm_context.py` |
| "Chau" seguía con promociones | No había manejo de fin de conversación | Código |
| Riesgo detectado: un cliente podía ser derivado a cualquier agente | `[DERIVAR:x]` en el canal de clientes aceptaba Máximo (CRM completo), Valentín y áreas internas | Código |

No verificado: el origen exacto del contenido promocional de Valentín, porque el texto de la conversación está en `/audit/session/admin_rodrigo`, que requiere credencial. La corrección hace que esa conversación no pueda volver a caer en Valentín por error.

## Corrección (`eco-multiagente/orchestrator/router.py`)
- El cambio de agente en el canal admin solo ocurre con un pedido explícito: "<verbo> con/a <agente>". Se compara la palabra completa y sin tildes. Máximo está incluido.
- Una negación ("no quiero hablar más con X", "no me pases con X", "basta de X") vuelve a Máximo.
- Confirmación visible: "🔀 Ahora estás hablando con X". Cuando no responde Máximo, cada respuesta lleva el nombre del agente.
- Si estás con Valentín y hacés una consulta del negocio (precios, ventas, leads…), la conversación vuelve sola a Máximo.
- Despedida ("chau", "listo gracias"…): cierre sin IA, se borra la memoria de la conversación admin y queda Máximo como agente.
- Clientes: la derivación solo llega a Valentina, Camila, Nicolás, Luciano, Mateo y Sebastián. Una despedida recibe un cierre sin promoción.
- Registro: cada respuesta del canal admin deja en el log qué agente respondió (además de la auditoría existente).

No se modificaron prompts, credenciales, la coexistencia de WhatsApp ni las líneas supervisadas (`channels/whatsapp.py` no cambia).

## Pendiente (decisión de negocio)
Baja de clientes ("no me escriban más"). Hoy no se marca en el CRM, y las tareas de seguimiento podrían volver a escribirle. Prometérselo al cliente sin cumplirlo sería peor que no responder, así que queda para una decisión aparte: dónde se registra la baja y qué tareas la respetan.
