"""
Base de Conocimiento de los agentes — Eco Módulos & Piscinas.

Permite a Rodrigo administrar, desde un panel, TODO el conocimiento que se
inyecta en los agentes en tiempo de respuesta:

  - Estilo de respuesta global (largo, tono, formato) → arregla respuestas largas/genéricas.
  - Documentos de conocimiento (texto o archivos importados) que aplican a todos
    los agentes (["*"]) o a agentes específicos (["mateo","camila",...]).

Todo se guarda en /data/knowledge.json (volumen persistente) para que sobreviva
a los deploys y se pueda editar 100% sin tocar código.

El contexto se inyecta en BaseAgent.respond() vía get_runtime_context(agent_name).
"""

import os
import json
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_base = Path(os.getenv("DATA_DIR", "")) if os.getenv("DATA_DIR") else Path(__file__).parent.parent
_KB_PATH = _base / "knowledge.json"

# ── Estilo por defecto (responde a la queja: largas, genéricas, poco profesionales) ──
_ESTILO_DEFAULT = (
    "ESTILO DE RESPUESTA — OBLIGATORIO:\n"
    "- Respuestas BREVES y al grano: 2 a 5 líneas, salvo que se pida un reporte o un detalle.\n"
    "- Profesional, concreto y seguro. Sin relleno, sin introducciones largas, sin listas genéricas.\n"
    "- Una idea principal por mensaje. Si hay opciones, RECOMENDÁ una; no enumeres todo.\n"
    "- No repitas lo ya dicho ni cierres con frases vacías ('¿en qué más puedo ayudarte?').\n"
    "- Castellano argentino, tono experto y directo, de igual a igual."
)


def _default_data() -> dict:
    return {
        "estilo": _ESTILO_DEFAULT,
        "docs": [
            {
                "id": "ejemplo",
                "titulo": "Ejemplo — cómo usar la base de conocimiento",
                "contenido": (
                    "Esto es un documento de ejemplo. Escribí acá datos reales del negocio que "
                    "querés que los agentes sepan y usen: políticas, argumentos de venta, datos "
                    "técnicos, preguntas frecuentes, condiciones comerciales, etc. Asigná a qué "
                    "agentes aplica y activalo. Podés desactivar o borrar este ejemplo."
                ),
                "agentes": ["*"],
                "activo": False,
                "orden": 0,
                "actualizado": "",
            }
        ],
    }


# ── Documentos "semilla": conocimiento que antes estaba hardcodeado y ahora
#    se migra a la base editable. Se instalan UNA vez; si el usuario los edita
#    o borra, su decisión se respeta (no se vuelven a agregar). ────────────────
_SEED_DOCS = [
    {
        "id": "nce_tecnico",
        "titulo": "Sistema constructivo NCE (técnico) — módulos",
        "agentes": ["luciano", "mateo", "sebastian"],
        "contenido": """=== SISTEMA CONSTRUCTIVO NCE (Núcleo de Celulosa Encapsulada) ===

PROCESO DE FABRICACIÓN (planta, Zárate):
1. ESTRUCTURA WOOD FRAME — tirante 2x6 de primera, cepillado a 2x2. Liviana y muy resistente.
2. PANELES — Panel A: 260x300 cm; Panel B: 260x200 cm.
3. ENSAMBLE FIJACIÓN TRIPLE — encolado industrial + pegado químico + atornillado estructural.
4. EMPLACADO NCE — placas de Núcleo de Celulosa Encapsulada. Aislamiento térmico/acústico superior a tradicional y steel frame.
5. BLINDAJE RESINA NÁUTICA — fibra de vidrio + resina náutica en toda la vuelta del panel. La madera queda encapsulada de por vida: sin humedad, sin bichos, sin rajaduras.
6. ACABADO OBRA BLANCA — perfilado, lijado, pintado. Sale de planta terminado, listo para instalar.
7. ANCLAJES instalados en planta antes del envío.
8. MONTAJE EN SECO — armado en sitio sin agua, sin escombros, rápido y limpio.

ARGUMENTOS TÉCNICOS DE VENTA:
- "No es cartón ni steel frame: es madera encapsulada de por vida con resina náutica."
- "Superior térmicamente a cualquier sistema tradicional o steel frame."
- "Sale en Obra Blanca: interior blanqueado e instalaciones listas, solo elegís artefactos y griferías."
- "Montaje en seco: sin obra sucia, sin escombros."
- "Mantiene valor de reventa; si te mudás, lo llevás."
- "Ahorrás hasta 60% de energía: el aislamiento NCE regula temperatura sin climatización constante."
""",
    },
    {
        "id": "captacion_contacto",
        "titulo": "Captación de contacto (convertir charlas en leads)",
        "agentes": ["valentina", "camila", "nicolas", "mateo", "luciano"],
        "contenido": """OBJETIVO: que ninguna conversación quede sin datos de contacto cargados.
Apenas haya interés real, pedí de forma natural y temprana (sin interrogar):
- NOMBRE: "¿Cómo es tu nombre así te asesoro mejor?"
- LOCALIDAD: "¿De qué localidad sos? Así te calculo el flete."
- TELÉFONO/WhatsApp (si entra por web): "Dejame tu WhatsApp y te paso la info y los modelos."
Pedí UN dato por mensaje, nunca todos juntos. Siempre dando una razón (flete, enviar fotos, reservar cupo).
Si el cliente da el dato, agradecé y seguí cerrando. Cuanto antes tengas nombre + localidad + contacto,
mejor podemos seguirlo. No cierres la charla sin haber intentado al menos pedir el nombre y la zona.
""",
    },
    {
        "id": "objeciones_financiacion",
        "titulo": "Manejo de objeciones de financiación / precio",
        "agentes": ["valentina", "camila", "nicolas", "mateo", "luciano", "tomas"],
        "contenido": """RESPUESTAS A OBJECIONES (financiación propia de fábrica, sin banco):
- "No tengo el dinero junto" → "Justamente para eso está la financiación propia: cuotas sin interés,
  sin banco ni financiera. Reservás hoy y la tenés para el verano."
- "Está caro" → "Comparado con obra tradicional sale menos, sin sorpresas y en días, no meses.
  Y lo podés hacer en cuotas fijas."
- "No tengo banco / estoy en Veraz" → "No trabajamos con bancos ni scoring. Es financiación directa
  de fábrica. No te pedimos eso."
- "Lo tengo que pensar" → "Claro. ¿Qué es lo que más te genera duda: el modelo, la zona o la cuota?"
- "¿Y si no me alcanza la cuota?" → "Armamos el plan a tu medida (más cuotas = cuota más baja).
  Te hago una simulación ahora si querés."
NUNCA cierres con un "no". Toda objeción se responde con una opción concreta y un próximo paso.
""",
    },
    {
        "id": "upsell_ticket",
        "titulo": "Aumentar el ticket (upsell / cross-sell) — más ingreso por venta",
        "agentes": ["valentina", "camila", "nicolas", "mateo", "luciano"],
        "contenido": """OBJETIVO: subir el monto de cada venta sin perder el cierre.
- COMBO módulo + piscina: ofrecelo siempre que tenga terreno. "Si sumás el módulo al combo, te
  queda 25% más barato que comprarlos por separado, y financiado." (más ticket + más margen).
- MODELO superior: si el cliente mira un modelo chico y el uso lo amerita, mostrá el siguiente
  ("por una diferencia de cuota chica saltás a uno bastante más grande").
- EXTRAS de piscina: cobertura/lona, iluminación LED, escalera premium, kit de mantenimiento.
- Anclá el upsell a la CUOTA, no al total: "son solo $X más por mes".
Regla: ofrecé el upgrade UNA vez, con beneficio claro. Si dice que no, cerrás igual el original.
Nunca pierdas la venta base por insistir en el upsell.
""",
    },
    {
        "id": "cierre_urgencia",
        "titulo": "Técnicas de cierre y urgencia — más conversión",
        "agentes": ["valentina", "camila", "nicolas", "mateo", "luciano", "tomas"],
        "contenido": """CERRÁ, no informes. Después de dar precio/cuota, SIEMPRE proponé el próximo paso concreto.
- Cierre por asunción: "¿Para qué semana lo coordinamos?" / "¿Te reservo el cupo de esta quincena?"
- Urgencia real: "Los cupos de fabricación por quincena se llenan; te puedo reservar uno hoy."
- Cierre por opción (no sí/no): "¿Lo hacés de contado o lo dejamos en cuotas?"
- Para financiado: la videollamada es el paso natural → "Coordinemos una videollamada corta y dejás todo listo."
- Quita de riesgo: "Se abona en domicilio, obra terminada. Ves todo funcionando antes de pagar."
- Si duda: identificá la objeción puntual y respondela (ver doc de objeciones), después volvé a cerrar.
Cada respuesta tuya termina con un paso hacia el cierre (reservar, coordinar, agendar). Nunca con un final pasivo.
""",
    },
    {
        "id": "estrategia_piscinas_anual",
        "titulo": "Estrategia de venta de piscinas todo el año (clave)",
        "agentes": ["valentina", "camila", "nicolas", "tomas", "aurora", "maximo"],
        "contenido": """REGLA DE ORO: NUNCA existe "no es temporada de piscinas". Se vende TODO el año.

- VERANO: se vende mucho de CONTADO (el cliente la quiere ya). Cerrar rápido + coordinar instalación.
- INVIERNO / fuera de temporada: se vende con FINANCIACIÓN PROPIA directa de fábrica.
  Pitch: "Comprala ahora en cuotas SIN INTERÉS, sin bancos ni financieras, con la compra
  planificada, y la tenés instalada para el próximo verano." Compra inteligente y sin apuro.

OBJETIVO INNEGOCIABLE: que el cliente NUNCA se vaya sin comprar.
- Si en invierno duda por el precio de contado → ofrecé el plan de financiación propia para el verano.
- Si quiere contado → Camila. Si quiere/conviene cuotas → Nicolás.
- La financiación es propia de fábrica: sin interés, sin banco, sin scoring, sin financieras.
- Nunca desalientes la compra por la época: la época es un argumento a favor (planificar para el verano).
""",
    },
]


def _ensure_seeds(data: dict) -> dict:
    """Instala los docs semilla una sola vez (respeta ediciones/borrados del usuario)."""
    instalados = data.setdefault("_seeds_instalados", [])
    docs = data.setdefault("docs", [])
    cambio = False
    for seed in _SEED_DOCS:
        if seed["id"] not in instalados:
            docs.append({
                "id": seed["id"],
                "titulo": seed["titulo"],
                "contenido": seed["contenido"].strip(),
                "agentes": seed["agentes"],
                "activo": True,
                "orden": 1,
                "actualizado": time.strftime("%Y-%m-%d %H:%M"),
            })
            instalados.append(seed["id"])
            cambio = True
    return data if not cambio else data


def _load() -> dict:
    if _KB_PATH.exists():
        try:
            data = json.loads(_KB_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[KB] No se pudo leer knowledge.json: {e}")
            data = _default_data()
    else:
        data = _default_data()
    # Migración: asegurar docs semilla y persistir si cambió
    antes = list(data.get("_seeds_instalados", []))
    data = _ensure_seeds(data)
    if list(data.get("_seeds_instalados", [])) != antes:
        _save(data)
    return data


def _save(data: dict) -> None:
    try:
        _KB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _KB_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[KB] No se pudo guardar knowledge.json: {e}")


# ── API de lectura para el runtime ──────────────────────────────────────────

def get_estilo() -> str:
    return _load().get("estilo", _ESTILO_DEFAULT)


def get_runtime_context(agent_name: str) -> str:
    """
    Devuelve el bloque de conocimiento + estilo a inyectar para este agente.
    agent_name puede venir como 'Tomás' o 'tomas' → se normaliza.
    """
    data = _load()
    name = (agent_name or "").strip().lower()
    # normalizar acentos comunes
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u")):
        name = name.replace(a, b)

    partes = []
    estilo = data.get("estilo", "").strip()
    if estilo:
        partes.append("[ESTILO Y FORMATO DE RESPUESTA]\n" + estilo)

    docs_aplicables = []
    for d in data.get("docs", []):
        if not d.get("activo"):
            continue
        agentes = d.get("agentes", ["*"])
        aplica = ("*" in agentes) or any(
            name == str(a).strip().lower() for a in agentes
        )
        if aplica and d.get("contenido", "").strip():
            docs_aplicables.append(d)

    docs_aplicables.sort(key=lambda d: d.get("orden", 0))
    if docs_aplicables:
        bloque = ["[BASE DE CONOCIMIENTO DEL NEGOCIO — usá estos datos como verdad]"]
        for d in docs_aplicables:
            bloque.append(f"## {d.get('titulo','(sin título)')}\n{d['contenido'].strip()}")
        partes.append("\n\n".join(bloque))

    return "\n\n".join(partes)


# ── API de administración (para el panel) ───────────────────────────────────

def listar() -> dict:
    """Devuelve estilo + lista de docs (sin recortar contenido)."""
    return _load()


def set_estilo(texto: str) -> None:
    data = _load()
    data["estilo"] = texto
    _save(data)


def guardar_doc(doc: dict) -> dict:
    """Crea o actualiza un documento. Si trae 'id' existente, lo reemplaza."""
    data = _load()
    docs = data.get("docs", [])
    did = doc.get("id") or f"k{int(time.time()*1000)}"
    nuevo = {
        "id": did,
        "titulo": (doc.get("titulo") or "Sin título").strip()[:120],
        "contenido": (doc.get("contenido") or "").strip(),
        "agentes": doc.get("agentes") or ["*"],
        "activo": bool(doc.get("activo", True)),
        "orden": int(doc.get("orden", 0) or 0),
        "actualizado": time.strftime("%Y-%m-%d %H:%M"),
    }
    encontrado = False
    for i, d in enumerate(docs):
        if d.get("id") == did:
            docs[i] = nuevo
            encontrado = True
            break
    if not encontrado:
        docs.append(nuevo)
    data["docs"] = docs
    _save(data)
    return nuevo


def borrar_doc(doc_id: str) -> bool:
    data = _load()
    antes = len(data.get("docs", []))
    data["docs"] = [d for d in data.get("docs", []) if d.get("id") != doc_id]
    _save(data)
    return len(data["docs"]) < antes


def restaurar_estilo_default() -> str:
    set_estilo(_ESTILO_DEFAULT)
    return _ESTILO_DEFAULT
