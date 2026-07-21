# Prompts de imágenes — Landing de Financiación (campaña)

> **Cómo usar esto:**
> 1. Copiá el prompt en inglés tal cual en tu generador de imágenes (Google ImageFX / Imagen 3, Midjourney, DALL·E, etc.).
> 2. Cuando tengas la imagen, mandámela por este chat — yo la guardo en `landing-financiacion/img/` con el nombre de archivo indicado y queda anclada automáticamente (el HTML ya apunta a esos nombres, no hay que tocar nada más).
> 3. Mientras no haya foto real, la landing muestra un degradé verde/teal de marca en su lugar — no se rompe ni queda un ícono de "imagen rota".

**⚠️ Corrección visual (2026-07-10, en base a fotos reales de obra que me pasaste):** el revestimiento exterior real es **placa cementicia lisa color GRIS GRAFITO/OSCURO** (no beige ni blanco como tenía antes), con juntas verticales entre paneles y cabezas de tornillos visibles en grilla. La madera se ve SOLO en los marcos de ventanas/puertas (pino claro, sin pintar o apenas tratado) y en la base/pilotes que elevan la construcción unos 20-30 cm del piso. Techo plano o a un agua (estilo minimalista) con leve alero. Ventanas de aluminio simples, rectangulares. Todo esto reemplaza la descripción anterior (que decía tonos "off-white/beige" — estaba mal).

**Estado actual (auditoría 2026-07-10):** no falta ninguna imagen (los 7 slots que usa la landing tienen archivo, no hay degradé de fallback en ningún lado). Hay 2 que **hay que reemplazar sí o sí** porque muestran el material equivocado, y 2 más que son **opcionales/de menor prioridad** porque están muy desenfocadas o casi invisibles.

| Prioridad | Archivo | Motivo |
|---|---|---|
| 🔴 Alta | `producto-modulo.jpg` | Tarjeta principal de módulos — hoy muestra un interior con madera vista que no corresponde |
| 🔴 Alta | `testimonio-2.jpg` | Cliente de módulo — el fondo muestra una fachada de madera vista |
| 🟡 Opcional | `simulador-bg.jpg` | Textura de fondo al 12% de opacidad, apenas se nota |
| 🟡 Opcional | `testimonio-3.jpg` | Cliente combo — el módulo de fondo está muy desenfocado, no se nota tanto el material |
| ⚪ Sin uso | `hero-modulo.jpg`, `hero-bg.jpg` | Quedaron de una versión anterior del hero (antes de la Promo Mundial). No se muestran en ningún lado hoy — no hace falta tocarlas salvo que quieras reusarlas a futuro. |

**Estilo global (aplica a todos los prompts de módulos de esta landing):**
Professional Argentine real-estate photography, natural daylight, ultra-realistic textures, 8K. **Exterior wall cladding: smooth dark charcoal-grey cement fiber board panels (matte finish), with visible vertical panel seams and a subtle grid of screw/fastener heads** — this is the dominant look, covering almost the entire facade. **Wood is visible only as trim**: natural light pine (unpainted or lightly treated) window and door frames, and a wood beam/post foundation elevating the structure ~20-30cm off the ground. Roof: flat or single-slope ("minimalista") with a small overhang, OR classic gabled ("americana") — still clad in the same dark grey cement panels, never wood siding on the roof or walls. Simple rectangular aluminum-framed windows. Argentine suburban backyard setting — green lawn, mature deciduous trees. Turnkey/move-in-ready quality, no construction debris, no visible tools. **NO beige/off-white/cream panels, NO wood plank siding, NO log-cabin look, NO visible steel frame, NO corrugated metal roofing as the main cladding.**

---

## 0. `promo-hero.jpg` — ✅ ya cargada (piscina), no requiere cambios.

---

## 3. `hero-modulo.jpg` — sin uso actualmente en el hero (por si hace falta a futuro)

```
Exterior photograph of an industrialized Wood Frame modular home, minimalist style, flat single-slope roof with a small overhang. Exterior walls entirely clad in smooth dark charcoal-grey cement fiber board panels with visible vertical seams and a subtle grid of screw heads. Natural light pine wood trim frames the windows and the front door, matching light wood at the base where the structure sits elevated on wood posts about 25cm above the ground. Simple rectangular aluminum-framed windows. Argentine backyard with green lawn and a bare deciduous tree, soft overcast daylight. Vertical portrait crop, 4:5 aspect ratio, ultra-realistic architectural photography, no people, no construction tools or debris.
```

---

## 5. `producto-modulo.jpg` — foto de la tarjeta "Viviendas industrializadas Wood Frame" (800×600, horizontal) — **REEMPLAZAR, la actual no corresponde**

**Opción A — estilo minimalista (el que se ve en tus fotos de obra):**
```
Exterior photograph of a small industrialized Wood Frame modular home/studio, minimalist style, flat single-slope roof with a slight overhang on one side. Exterior walls entirely clad in smooth dark charcoal-grey cement fiber board panels, visible vertical panel seams, subtle screw-head grid pattern. Natural light pine wood trim around a large window and a sliding glass door, and along the base where the structure is elevated on short wood posts. Set on a trimmed green lawn in an Argentine backyard with a bare-branched deciduous tree beside it, bright clear daylight. Professional architectural photography, 4:3 aspect ratio, ultra-realistic, no people, no construction tools, clean finished turnkey appearance.
```

**Opción B — estilo americana (techo a dos aguas, mismo revestimiento):**
```
Exterior photograph of an industrialized Wood Frame family home, "americana" style with a classic gabled roof (still clad in the same dark charcoal-grey cement fiber board panels, no shingles change to the wall material). Natural light pine wood trim around windows, front door, and a small entrance porch with simple wood posts. Elevated on a low wood post foundation. Well-maintained front garden with short green grass, suburban Buenos Aires setting, bright daylight. Professional architectural photography, 4:3 aspect ratio, ultra-realistic, no people, turnkey move-in-ready appearance, no wood siding on the walls.
```

---

## 6. `simulador-bg.jpg` — fondo sutil del simulador (opacidad ~12%, no urgente)

```
Abstract close-up texture photograph: the smooth dark charcoal-grey cement fiber board exterior wall of an industrialized Wood Frame home (visible panel seam and screw-head detail) transitioning into the glossy turquoise water surface of a fiberglass pool, shot at a low angle with shallow depth of field, warm late-afternoon light creating soft highlights. Abstract, textural, calm, no people. 16:9 aspect ratio.
```

---

## 8. `testimonio-2.jpg` — "Marcelo D. — Zárate" (cliente de módulo) — **reemplazar, la actual tiene una fachada equivocada de fondo**

```
Candid warm portrait of an Argentine man in his 40s, friendly natural smile, standing outdoors near his home with a blurred facade of an industrialized Wood Frame home softly out of focus behind him — dark charcoal-grey cement fiber board panels with light wood window trim, out of focus. Casual clothing, warm afternoon natural light. Square 1:1 crop, shallow depth of field, ultra-realistic, authentic — not a stock photo look.
```

---

## 9. `testimonio-3.jpg` — "Familia Ibáñez — Pilar" (cliente combo) — 🟡 opcional, está muy desenfocado

```
Candid warm portrait of an Argentine couple in their 30s-40s standing close together, both smiling naturally, outdoors in their backyard with a blurred industrialized Wood Frame home (dark charcoal-grey cement fiber board panels, light wood window trim) and a fiberglass pool softly out of focus behind them. Casual weekend clothing, warm golden hour light. Square 1:1 crop, shallow depth of field, ultra-realistic, authentic — not a stock photo look.
```

---

## Sin cambios (piscinas, no las toques)

`hero-piscina.jpg`, `producto-piscina.jpg`, `testimonio-1.jpg`.

---

## Notas

- Si alguna imagen te queda con manos/caras raras (típico de IA), pedí variantes.
- Cuando me pases los archivos, avisame a qué slot corresponde cada uno.
