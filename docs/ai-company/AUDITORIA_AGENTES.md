# Auditoría y profesionalización de los 16 agentes de la empresa

Fecha: 2026-10-31 · Rama: `ccr-b6d2e636-iqq5ux-fase-1-motor`
Valentín (asistente personal del propietario) queda **fuera** de la empresa: no recibe capas, manual ni políticas.

## Qué se hizo

| Pieza | Estado | Dónde |
|---|---|---|
| Manual del puesto para los 16 agentes (misión, dominio, modelo de decisión, metodología, procedimientos, casos complejos, colaboración, autonomía, prohibiciones, indicadores, mejora continua) | IMPLEMENTADA + PROBADA | `eco-multiagente/agents/manuales/*.md` |
| El manual entra en la CAPA 3, debajo de seguridad (capa 1) y de las políticas aprobadas (capa 2) | IMPLEMENTADA + PROBADA | `tools/capas.py` (`manual`, `componer`) |
| Nicolás y Mateo registran la apertura con `abrir_financiacion`; Luciano cierra contado de módulos con `cerrar_venta_contado` | IMPLEMENTADA + PROBADA (texto del prompt; la acción ya estaba probada de punta a punta) | `agents/nicolas.py`, `mateo.py`, `luciano.py` |
| Test que importa los 17 agentes (detectó que los prompts f-string se rompían con señales JSON) | PROBADA | `tests/test_manuales.py` |
| Harness de evaluaciones: 14 casos con comprobaciones determinísticas de reglas de negocio | IMPLEMENTADA + PROBADA (el verificador); **NO EJECUTADA contra el modelo** (tiene costo, requiere aprobación) | `eco-multiagente/evals/` |

Los manuales no contienen precios: un test lo exige. Los precios salen solo del sistema (`[COTIZAR]`, `[SIMULAR]`, catálogo).
Cada manual cuesta ~2.000–2.500 caracteres por mensaje (≈600 tokens). Si el costo preocupa, se puede limitar a los agentes que hablan con clientes.

## Estado por agente

| Agente | Área | Líneas de prompt | Acciones de circuito | Observación |
|---|---|---|---|---|
| Máximo | Dirección | 342 | crear_tarea, proponer_politica, fijar_objetivo, carga en canal del propietario | Prompt largo; el manual ordena prioridades por impacto en dinero |
| Aurora | Comercial (gerencia) | 44 | delegar, proponer_politica | Prompt corto: el manual aporta el método |
| Tomás | Comercial (supervisión) | 60 | delegar, proponer_politica | |
| Valentina | Comercial (primer contacto) | 80 | — | Menciona flete bonificado y pérgola de regalo en financiadas (ver decisiones) |
| Camila | Piscinas contado | 79 | cerrar_venta_contado | Reescrita en fase anterior |
| Nicolás | Financiación piscinas | 65 | abrir_financiacion | Ver decisiones: "Aprobación el mismo día" |
| Luciano | Módulos contado | 54 | cerrar_venta_contado | |
| Mateo | Financiación módulos | 92 | abrir_financiacion | Ver decisiones: "Aprobación el mismo día" |
| Renata | Marketing | 86 | — | Campañas pagas siempre con aprobación |
| Bruno | Operaciones | 27 | — | Prompt muy corto: el manual define prioridades de entrega |
| Ezequiel | Administración | 28 | venta/pagos solo canal confiable | |
| Elena | Finanzas | 30 | — | |
| Ignacio | Cobranza | 34 | — | Contacto saliente pasa por autorización (bajas, ventana 24 h) |
| Sebastián | Postventa | 217 | — | Sin datos del CRM en contexto |
| Daniela | RRPP y crisis | 43 | — | |
| Franco | Socios | 236 | — | Sin datos del CRM en contexto |

## Decisiones que necesitan al propietario (no las cambié)

1. **"Aprobación el mismo día"** (Nicolás y Mateo). La regla obligatoria dice que la IA no promete aprobaciones y que Admisión, que son personas, decide. La frase promete tiempos de una decisión humana. Lo recomendable es pasarla a *"Admisión te responde en la videollamada"*, salvo que sea un compromiso operativo real.
2. **"Nunca revelás que sos IA"** aparece en 14 de los 16 prompts (decisión H). Tiene riesgo legal y reputacional. Una alternativa es no anunciarlo, pero no negarlo si el cliente lo pregunta directamente.
3. **Flete bonificado y pérgola de regalo en financiadas** (Valentina y Nicolás). Hay que confirmar que siguen vigentes. Si no lo están, son promesas comerciales falsas.
4. **Correr las evaluaciones contra el modelo.** Son 14 llamadas pagas, de bajo costo. Hacen falta tu aprobación y la `OPENROUTER_API_KEY` en un entorno de prueba.

## Cómo correr las evaluaciones

```bash
cd eco-multiagente
python -m evals.correr                     # valida casos, gratis
python -m evals.correr --ejecutar          # llama al modelo: TIENE COSTO
python -m evals.correr --ejecutar --agente camila
```
