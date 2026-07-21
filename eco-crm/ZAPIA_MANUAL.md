# 📖 MANUAL ZAPIA — Eco Módulos & Piscinas CRM
> Versión 3.0 | Todas las funciones disponibles para el agente + API de agentes IA

---

## 🔑 AUTENTICACIÓN

### Auth estándar (todos los endpoints `/api/ext/...`)
```
Header: X-Api-Key: eco-crm-api-key-2024
```

### Auth de agente IA (endpoints `/api/ext/agente/...`)
Requiere **ambos** headers:
```
X-Api-Key:    eco-crm-api-key-2024
X-Agent-Key:  agt_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX   ← clave única del agente
```
La `agente_key` se genera automáticamente cuando se activa la opción "Es agente IA" en la sección Usuarios del CRM.

Base URL: `https://eco-crm-dawn-fog-5476.fly.dev`

---

## 🧠 LÓGICA DE NEGOCIO — CONTEXTO PARA EL AGENTE

### Productos que vendemos
| Producto | Descripción | Modalidad |
|----------|-------------|-----------|
| **MODULO** | Módulo habitable NCE (tecnología composite liviana) | Instalación propia O envío Vía Cargo |
| **PISCINA** | Piscinas de distintos modelos y tamaños | Instalación propia O envío Vía Cargo |
| **COMBO** | Módulo + Piscina | Instalación propia |

### Formas de entrega
- **Instalación propia**: equipo de Eco Módulos instala en el lugar (zona de cobertura)
- **Vía Cargo / transporte terrestre**: producto terminado despachado a sucursal del cliente (todo el país)
  - Módulos hasta 24m² son aptos para este tipo de envío
  - Todas las piscinas son aptas para envío por Vía Cargo

### Estados de un Lead
```
NUEVO → INTENTADO → CONTACTADO → EN_SEGUIMIENTO → CALIFICADO →
COTIZADO → NEGOCIANDO → VIDEOLLAMADA_AGENDADA → ESPERANDO_ADMISION →
ADMITIDO | RECHAZADO_ADMISION → CERRADO_GANADO | CERRADO_PERDIDO | INACTIVO
```

### Roles del equipo
- **ASESOR_APERTURA**: maneja leads, agenda videollamadas
- **SUPERVISOR_CIERRE**: cierra ventas en videollamadas
- **COORDINADOR_OPERATIVO**: logística, entregas, contratos
- **FABRICA**: producción y stock
- **COBRANZAS**: seguimiento de cuotas
- **ADMIN**: acceso total

---

## 📡 ENDPOINTS DISPONIBLES

### 1. SISTEMA
```
GET  /api/ext/info          → Verifica conexión y lista todos los endpoints
GET  /api/ext/dashboard     → Resumen ejecutivo: leads hoy, ventas, fábrica, logística
```

---

### 2. LEADS
```
GET  /api/ext/leads                         → Lista leads (filtros: estado, producto, asesor_id, telefono, search)
POST /api/ext/leads                         → Crea lead (asigna asesor automáticamente por round-robin)
GET  /api/ext/leads/buscar?telefono=XXXX    → Busca lead por número (coincidencia parcial)
GET  /api/ext/leads/seguimientos-pendientes → Leads con seguimiento vencido (filtro: asesor_id, horas)
GET  /api/ext/leads/{id}                    → Detalle de un lead
PATCH /api/ext/leads/{id}                   → Actualiza campos del lead
POST /api/ext/leads/{id}/nota               → Agrega nota (se timestampea automáticamente)
POST /api/ext/leads/{id}/seguimiento        → Programa próximo seguimiento (fecha_hora en ISO)
POST /api/ext/leads/{id}/mensaje            → Guarda mensaje del agente en el historial
GET  /api/ext/leads/{id}/mensajes           → Historial de conversación
POST /api/ext/leads/reasignar-asesor        → Reasigna leads de un asesor a otro (o round-robin)
```

**Campos para crear lead:**
```json
{
  "nombre": "Juan Pérez",
  "telefono": "5491112345678",
  "localidad": "Córdoba",
  "producto_interes": "MODULO",        // PISCINA | MODULO | COMBO | SIN_DEFINIR
  "modelo_especifico": "Módulo 24m²",
  "forma_pago": "CONTADO",             // CONTADO | PMI | DIRECTA_50 | SIN_DEFINIR
  "origen": "WHATSAPP",               // WHATSAPP | INSTAGRAM | WEB | REFERIDO
  "notas": "",
  "asesor_apertura_id": null           // null = asignación automática
}
```

**Programar seguimiento:**
```json
{
  "fecha_hora": "2026-05-25T10:00:00",
  "nota": "El cliente dijo que llama el lunes"
}
```

---

### 3. VIDEOLLAMADAS
```
GET  /api/ext/videollamadas              → Lista VLs (filtros: estado, asesor_id, solo_hoy, fecha_desde/hasta)
POST /api/ext/videollamadas              → Crea videollamada
PATCH /api/ext/videollamadas/{id}        → Actualiza estado/resultado/supervisor
```

**Estados VL:** `AGENDADA | REALIZADA | NO_SE_PRESENTO | REPROGRAMAR`
**Resultados:** `PENDIENTE | AVANZO | NO_CALIFICO | CERRO`

---

### 4. VENTAS
```
GET  /api/ext/ventas                         → Lista ventas (filtro: tipo=contado|financiada, cliente, telefono)
GET  /api/ext/ventas/financiada/{id}         → Detalle de una venta financiada con historial de pagos
POST /api/ext/ventas/contado                 → Registra venta al contado
POST /api/ext/ventas/financiada              → Registra venta financiada (PMI, cuotas)
POST /api/ext/ventas/financiada/{id}/pago    → Registra pago de cuota
```

**Registrar venta al contado:**
```json
{
  "cliente_nombre": "Ana García",
  "cliente_telefono": "5493515555555",
  "cliente_localidad": "Mendoza",
  "producto": "PISCINA",               // PISCINA | MODULO | COMBO
  "modelo_especifico": "Minimalista Mediana",
  "color": "Celeste",
  "precio_final": 4500000,
  "forma_pago": "CONTADO",
  "vendedor_id": 3,
  "fecha_instalacion": "2026-06-15T09:00:00",
  "distancia_km": 45,
  "desde_stock": true,                 // true si sale de stock (no genera orden fábrica)
  "notas": ""
}
```

---

### 5. CATÁLOGO & COTIZACIÓN

```
GET  /api/ext/catalogo                    → Catálogo completo con modelos, colores y precios
GET  /api/ext/cotizar?producto=PISCINA&modelo=Minimalista%20Chica&localidad=Mendoza
GET  /api/ext/ranking?periodo=mes         → Ranking de ventas (periodo: dia | semana | mes)
```

**Respuesta de /catalogo:**
```json
{
  "piscinas": [
    { "modelo": "Minimalista Chica", "colores_disponibles": [...], "precio": 3500000, "tiene_precio": true }
  ],
  "modulos": [
    { "nombre": "Módulo 24m²", "superficie_m2": 24, "precio": 8000000, "apto_via_cargo": true }
  ],
  "colores_piscinas": ["Blanco", "Beige", "Verde agua", "Celeste", "Azul"]
}
```

**Respuesta de /cotizar:**
```json
{
  "producto": "PISCINA",
  "modelo": "Minimalista Chica",
  "precio_base": 3500000,
  "tiene_precio": true,
  "info_envio": {
    "via_cargo": "Despachamos por Vía Cargo u otras empresas a todo el país."
  },
  "proximos_pasos": ["Confirmar modelo y color", "Informar sucursal Vía Cargo más cercana", ...]
}
```

---

### 6. STOCK
```
GET  /api/ext/stock/disponible           → Vista unificada: piscinas + paneles disponibles con precio
GET  /api/ext/stock/piscinas             → Stock de piscinas (filtro: modelo)
GET  /api/ext/stock/paneles              → Stock de paneles NCE con alertas de mínimo
PATCH /api/ext/stock/piscinas/{id}       → Ajusta cantidad (campo: "cantidad" o "ajuste")
```

**Respuesta de /stock/disponible:**
```json
{
  "piscinas": [
    { "modelo": "Miniportante", "color": "Celeste", "cantidad": 2, "precio": 2800000, "apto_via_cargo": true }
  ],
  "paneles_nce": [...],
  "resumen_texto": "🏊 PISCINAS DISPONIBLES: 2x Piscina Miniportante color Celeste",
  "nota_via_cargo": "Todas las piscinas en stock pueden despacharse por Vía Cargo."
}
```

**Ajustar stock:**
```json
{ "cantidad": 3 }        // nuevo valor absoluto
{ "ajuste": -1 }         // delta (resta 1)
```

---

### 7. ENVÍOS VÍA CARGO 🚚
```
GET  /api/ext/envios                                          → Lista envíos (filtros: estado, cliente, telefono)
GET  /api/ext/envios/buscar?telefono=XXX                     → Busca por teléfono o numero_remito
POST /api/ext/envios                                         → Crea nuevo envío (genera venta contado automáticamente)
PATCH /api/ext/envios/{id}                                   → Actualiza estado/tracking/remito
GET  /api/envios-cargo/cotizar-flete?provincia=X&modelo=Y&cantidad=1  → Estima costo de flete por zona
```

**Cotizador de flete:**
```
GET /api/envios-cargo/cotizar-flete?provincia=Córdoba&modelo=Miniportante&cantidad=1
```

Respuesta:
```json
{
  "provincia": "Córdoba",
  "zona": 3,
  "modelo": "Miniportante",
  "cantidad": 1,
  "bultos": 1,
  "peso_real_kg": 45.0,
  "peso_vol_kg": 18.3,
  "peso_cobrable_kg": 45.0,
  "costo_min": 22750,
  "costo_max": 32500,
  "costo_promedio": 27625,
  "referencia": "Zona 3 — estimación orientativa",
  "nota": "Los valores son estimativos. Confirmá con la empresa de transporte antes de cotizar.",
  "link_calculadora": "https://www.viacargo.com.ar/calculadora"
}
```

**Zonas de envío:**
| Zona | Provincias |
|------|-----------|
| 1 | CABA, Buenos Aires GBA |
| 2 | Buenos Aires interior |
| 3 | Santa Fe, Córdoba, Entre Ríos, Mendoza, San Juan, San Luis |
| 4 | Tucumán, Salta, Jujuy, Catamarca, La Rioja, Santiago del Estero, Neuquén, Río Negro, La Pampa |
| 5 | Corrientes, Misiones, Chaco, Formosa, Chubut, Santa Cruz |
| 6 | Tierra del Fuego |

**Estados de envío:** `PENDIENTE | EMPACADO | DESPACHADO | EN_TRANSITO | ENTREGADO | PROBLEMA`

**Crear envío:**
```json
{
  "cliente_nombre": "Carlos López",
  "cliente_telefono": "5493511234567",
  "cliente_localidad": "Villa María",
  "provincia": "Córdoba",
  "sucursal_cargo": "Via Cargo Villa María - Av. Buenos Aires 450",
  "producto": "PISCINA",
  "modelo_especifico": "Miniportante",
  "color": "Celeste",
  "cantidad": 1,
  "desde_stock": true,
  "precio_producto": 2800000,
  "costo_flete": 85000,
  "total": 2885000,
  "forma_pago": "TRANSFERENCIA",
  "vendedor_id": 3,
  "empresa_transporte": "VIA_CARGO",
  "notas": "Cliente paga al retirar en sucursal"
}
```

**Actualizar tracking:**
```json
{
  "estado": "DESPACHADO",
  "numero_remito": "VC-2026-04521",
  "fecha_despacho": "2026-05-20T09:00:00"
}
```

---

### 8. COBRANZAS
```
GET  /api/ext/cobranzas/vencidas              → Planes financiados con cuotas atrasadas
GET  /api/ext/cobranzas/buscar?telefono=XXX   → Busca cliente en ventas financiadas
POST /api/ext/cobranzas/{id}/gestion          → Registra contacto de cobranza
```

**Registrar gestión:**
```json
{
  "canal": "WHATSAPP",               // WHATSAPP | LLAMADA | PRESENCIAL
  "resultado": "PROMETIO_PAGAR",     // PROMETIO_PAGAR | PAGO | NO_CONTESTO | RECLAMA | ACUERDO_ESPECIAL
  "notas": "Dice que paga el viernes"
}
```

---

### 9. FÁBRICA
```
GET  /api/ext/fabrica/ordenes             → Órdenes activas (filtro: tipo=piscina|modulo, estado)
PATCH /api/ext/fabrica/ordenes/{id}       → Actualiza estado/notas de una orden
```

**Estados de orden:** `EN_ESPERA | EN_PROCESO | TERMINADA | ENTREGADA`

---

### 10. LOGÍSTICA / ENTREGAS
```
GET  /api/ext/logistica/entregas          → Entregas coordinadas (filtros: estado, fecha_desde/hasta)
PATCH /api/ext/logistica/entregas/{id}    → Actualiza estado/equipo/fecha
```

**Estados de entrega:** `COORDINADA | EN_CAMINO | INSTALADA | CON_PROBLEMA`

---

### 11. RECLAMOS
```
GET  /api/ext/reclamos                    → Lista reclamos (filtros: estado, telefono)
POST /api/ext/reclamos                    → Crea reclamo de cliente
PATCH /api/ext/reclamos/{id}             → Actualiza estado/solución
```

**Crear reclamo:**
```json
{
  "cliente_nombre": "Pedro Ruiz",
  "cliente_telefono": "5491155555555",
  "descripcion": "La piscina tiene una fisura en el lateral"
}
```

---

### 12. ASESORES
```
GET  /api/ext/asesores                    → Lista asesores con roles y métricas (leads activos, VL pendientes)
```

---

### 13. ASIGNACIÓN DE LEADS A AGENTES IA (CRM admin)
```
POST /api/leads/asignar-a-agentes-ia   → Transfiere leads sin respuesta al pool de agentes IA
```
Requiere rol ADMIN. Distribuye en round-robin entre todos los usuarios con `es_agente_ia=true`.

**Body:**
```json
{
  "limite": 50,              // máx leads a asignar (default 50)
  "ids": [1, 2, 3],          // opcional: IDs específicos. Si vacío, toma NUEVO/INTENTADO
  "agente_ia_id": 7          // opcional: asignar todo a un agente específico
}
```

---

### 14. ENDPOINTS EXCLUSIVOS PARA AGENTES IA (`/api/ext/agente/...`)

> ⚠️ Todos estos endpoints requieren **ambos** headers: `X-Api-Key` + `X-Agent-Key`.
> El agente sólo ve y opera sobre los leads y VLs que le fueron asignados.

```
GET  /api/ext/agente/perfil                       → Datos del agente autenticado
GET  /api/ext/agente/mis-leads                    → Leads asignados al agente (filtros: estado, search)
GET  /api/ext/agente/mis-leads/siguiente          → Próximo lead a contactar (prioridad automática)
POST /api/ext/agente/leads/{id}/contactar         → Registra intento de contacto y actualiza estado
GET  /api/ext/agente/mis-vls                      → Videollamadas asignadas al agente
POST /api/ext/agente/leads/{id}/agendar-vl        → Agenda una videollamada para un lead
```

#### `GET /api/ext/agente/perfil`
Respuesta:
```json
{
  "id": 7,
  "nombre": "Pablo IA",
  "email": "pablo@ia",
  "roles": ["ASESOR_APERTURA"],
  "es_agente_ia": true,
  "leads_asignados": 12,
  "leads_contactados_hoy": 3
}
```

#### `GET /api/ext/agente/mis-leads`
Query params opcionales: `estado`, `search`
Respuesta: lista de leads (mismo formato que `/api/ext/leads`)

#### `GET /api/ext/agente/mis-leads/siguiente`
Devuelve el lead de mayor prioridad para contactar ahora:
```json
{
  "id": 42,
  "nombre": "Marcelo Fernández",
  "telefono": "5491155667788",
  "producto_interes": "PISCINA",
  "estado": "NUEVO",
  "notas": "",
  "prioridad": "ALTA",
  "motivo": "Lead nuevo sin intento de contacto"
}
```
Si no hay leads pendientes devuelve `{"siguiente": null}`.

#### `POST /api/ext/agente/leads/{id}/contactar`
Body:
```json
{
  "resultado": "CONTACTADO",       // NO_CONTESTO | CONTACTADO | NO_INTERESA | AGENDAR_VL
  "notas": "Habló 5 min, interesado en piscina mediana",
  "proximo_seguimiento": "2026-05-22T10:00:00"   // opcional
}
```

**Tabla de transiciones de estado según `resultado`:**
| resultado | Estado lead resultante |
|-----------|----------------------|
| `NO_CONTESTO` | `INTENTADO` |
| `CONTACTADO` | `CONTACTADO` |
| `NO_INTERESA` | `CERRADO_PERDIDO` |
| `AGENDAR_VL` | `VIDEOLLAMADA_AGENDADA` (requiere POST agendar-vl luego) |

Respuesta:
```json
{ "ok": true, "lead_id": 42, "nuevo_estado": "CONTACTADO" }
```

#### `GET /api/ext/agente/mis-vls`
Query params opcionales: `estado` (`AGENDADA | REALIZADA | NO_SE_PRESENTO | REPROGRAMAR`)
Respuesta: lista de videollamadas asignadas al agente.

#### `POST /api/ext/agente/leads/{id}/agendar-vl`
Body:
```json
{
  "fecha_hora": "2026-05-23T15:00:00",
  "producto_interes": "PISCINA",
  "forma_pago": "PMI",
  "notas": "Cliente quiere ver el showroom virtual"
}
```
Respuesta:
```json
{ "ok": true, "vl_id": 88, "lead_id": 42 }
```

---

### 15. GASTOS OPERATIVOS
```
POST /api/ext/gastos                      → Registra gasto (auto-vincula a venta/entrega/orden por cliente_nombre)
GET  /api/ext/gastos                      → Lista gastos (filtros: sector, desde, hasta)
```

**Registrar gasto:**
```json
{
  "monto": 15000,
  "descripcion": "Nafta para instalación en Córdoba",
  "categoria": "COMBUSTIBLE",            // MATERIALES|COMBUSTIBLE|COMIDA|HERRAMIENTAS|FLETE|INSTALACION|PRODUCCION|ADMINISTRATIVO|VEHICULO|SUELDO|OTRO
  "sector": "OPERACIONES",              // FABRICA|OPERACIONES|VENTAS|ADMINISTRACION|GENERAL
  "cliente_nombre": "Ana García",        // para auto-vincular a la venta/entrega
  "proveedor": "YPF Córdoba"
}
```

---

## 🔄 FLUJOS COMPLETOS PARA ZAPIA

### Flujo A — Lead nuevo de WhatsApp
```
1. POST /api/ext/leads          → crear lead, asesor asignado automáticamente
2. POST /api/ext/leads/{id}/mensaje  → guardar conversación
3. PATCH /api/ext/leads/{id}    → actualizar estado a CONTACTADO
4. POST /api/ext/leads/{id}/seguimiento  → agendar próximo contacto
```

### Flujo B — Consulta de precio y stock
```
1. GET /api/ext/stock/disponible    → ver qué hay listo
2. GET /api/ext/cotizar?producto=PISCINA&modelo=Miniportante  → precio y pasos
3. PATCH /api/ext/leads/{id}        → actualizar a COTIZADO + nota con precio
```

### Flujo C — Venta contado con envío Vía Cargo
```
1. POST /api/ext/envios             → crea envío (genera venta contado automáticamente)
2. PATCH /api/ext/stock/piscinas/{id}  → ajustar stock si desde_stock=true (auto si se especifica)
3. PATCH /api/ext/leads/{id}        → marcar lead como CERRADO_GANADO
4. PATCH /api/ext/envios/{id}       → actualizar con numero_remito cuando se despacha
```

### Flujo D — Seguimiento de cobranza
```
1. GET /api/ext/cobranzas/buscar?telefono=XXXX  → encontrar plan
2. POST /api/ext/cobranzas/{id}/gestion         → registrar contacto
3. POST /api/ext/ventas/financiada/{id}/pago    → si pagó, registrar pago
```

### Flujo E — Reclamo de cliente
```
1. GET /api/ext/leads/buscar?telefono=XXXX  → identificar cliente
2. POST /api/ext/reclamos                   → abrir reclamo
3. PATCH /api/ext/reclamos/{id}             → actualizar cuando se resuelve
```

---

## 📊 ESTADOS GLOBALES

| Entidad | Estados posibles |
|---------|-----------------|
| Lead | NUEVO → INTENTADO → CONTACTADO → EN_SEGUIMIENTO → CALIFICADO → COTIZADO → NEGOCIANDO → VIDEOLLAMADA_AGENDADA → CERRADO_GANADO \| CERRADO_PERDIDO \| INACTIVO |
| Videollamada | AGENDADA → REALIZADA \| NO_SE_PRESENTO \| REPROGRAMAR |
| Venta Financiada | ACTIVO → ATRASADO → FINALIZADO \| CANCELADO |
| Orden Fábrica | EN_ESPERA → EN_PROCESO → TERMINADA → ENTREGADA |
| Entrega | COORDINADA → EN_CAMINO → INSTALADA \| CON_PROBLEMA |
| Envío Cargo | PENDIENTE → EMPACADO → DESPACHADO → EN_TRANSITO → ENTREGADO \| PROBLEMA |
| Reclamo | NUEVO → EN_GESTION → RESUELTO |

---

## ⚡ RESPUESTAS RÁPIDAS SUGERIDAS PARA ZAPIA

**"¿Qué tienen disponible?"**
→ Llamar `GET /api/ext/stock/disponible` y responder con el campo `resumen_texto`

**"¿Cuánto sale X modelo?"**
→ Llamar `GET /api/ext/cotizar?producto=PISCINA&modelo=...` y usar `precio_base`

**"¿Lo pueden enviar a [ciudad]?"**
→ Responder: "Sí, despachamos por Vía Cargo a todo el país. Consultá la sucursal más cercana en viacargo.com.ar"
→ Crear envío con `POST /api/ext/envios` cuando el cliente confirma

**"¿Cuándo llega mi pedido?"**
→ `GET /api/ext/envios/buscar?telefono=XXXX` → mostrar `estado` y `fecha_entrega_est`

**"Quiero hacer un reclamo"**
→ `POST /api/ext/reclamos` con descripcion del problema

---

*Eco Módulos & Piscinas — Sistema multiagente v2.0*
