"""
Inyección de contexto CRM en tiempo real para cada agente.

Cada agente tiene definido qué datos del CRM necesita.
Los datos se fetchean en paralelo antes de cada respond() para que el agente
pueda responder con información real y actualizada.

Máximo (admin) recibe el contexto COMPLETO: todos los leads, todas las ventas,
métricas avanzadas, ranking, stock, materiales — conocimiento total del negocio.

Si el CRM no responde, retorna string vacío (nunca rompe el flujo).
"""

import asyncio
import logging
from tools import crm_client

logger = logging.getLogger(__name__)

# ── Qué datos del CRM necesita cada agente ───────────────────────────────────
AGENT_CRM_NEEDS: dict[str, list[str]] = {
    "Máximo":    [
        "pipeline_stats", "ventas_hoy", "cuotas_vencidas",
        "leads_sin_respuesta", "stock", "materiales", "stock_piscinas",
        "precios", "flete",
        # Contexto completo para conocimiento total del negocio:
        "todos_leads", "ventas_contado", "ventas_financiadas",
        "metricas_avanzadas", "ranking",
    ],
    "Aurora":    ["pipeline_stats", "ventas_hoy", "leads_sin_respuesta", "precios", "flete"],
    "Tomás":     ["pipeline_stats", "leads_sin_respuesta"],
    "Ignacio":   ["cuotas_vencidas"],
    "Elena":     ["pipeline_stats", "ventas_hoy", "cuotas_vencidas", "precios"],
    "Bruno":     ["stock", "pipeline_stats", "materiales", "stock_piscinas", "flete"],
    "Ezequiel":  ["pipeline_stats", "cuotas_vencidas"],
    "Renata":    ["pipeline_stats"],
    "Daniela":   ["pipeline_stats"],
    # Agentes de ventas: precios y flete para cotizar con exactitud, siempre en vivo
    "Valentina": ["precios", "flete"],
    "Camila":    ["precios", "flete"],
    "Mateo":     ["precios", "flete"],
    "Nicolás":   ["precios", "flete"],
    "Luciano":   ["precios", "flete"],
    "Sebastián": ["pipeline_stats"],
}


def _fecha_corta(iso: str) -> str:
    """Convierte '2025-05-15T10:30:00' → '15/05'."""
    try:
        return iso[8:10] + "/" + iso[5:7]
    except Exception:
        return ""


async def get_crm_context(agent_name: str) -> str:
    """
    Fetchea los datos del CRM relevantes para el agente dado.
    Todas las llamadas se hacen en paralelo.
    Retorna un string formateado listo para inyectar como contexto.
    """
    needs = AGENT_CRM_NEEDS.get(agent_name, [])
    if not needs:
        return ""

    # Lanzar todas las llamadas en paralelo
    tasks = {}
    if "pipeline_stats" in needs:
        tasks["pipeline"] = crm_client.get_pipeline_stats()
    if "ventas_hoy" in needs:
        tasks["ventas"] = crm_client.get_ventas_hoy()
    if "cuotas_vencidas" in needs:
        tasks["cuotas"] = crm_client.get_cuotas_vencidas(0)
    if "leads_sin_respuesta" in needs:
        tasks["leads_sin_resp"] = crm_client.get_leads_sin_respuesta(2)
    if "stock" in needs:
        tasks["stock"] = crm_client.get_stock()
    if "precios" in needs:
        tasks["precios"] = crm_client.get_precios_actuales()
    if "flete" in needs:
        tasks["flete"] = crm_client.get_flete_config()
    if "materiales" in needs:
        tasks["materiales"] = crm_client.get_materiales_inventario()
    if "stock_piscinas" in needs:
        tasks["stock_piscinas"] = crm_client.get_stock_piscinas()
    # ── Contexto completo (solo Máximo) ──────────────────────────────────────
    if "todos_leads" in needs:
        tasks["todos_leads"] = crm_client.get_todos_leads(limit=200)
    if "ventas_contado" in needs:
        tasks["ventas_contado"] = crm_client.get_ventas_contado_todas()
    if "ventas_financiadas" in needs:
        tasks["ventas_financiadas"] = crm_client.get_ventas_financiadas_todas()
    if "metricas_avanzadas" in needs:
        tasks["metricas_avanzadas"] = crm_client.get_metricas_avanzadas()
    if "ranking" in needs:
        tasks["ranking"] = crm_client.get_ranking_ventas("mes")

    try:
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        data = dict(zip(tasks.keys(), results))
    except Exception as e:
        logger.warning(f"[CRMCtx] Error fetching para {agent_name}: {e}")
        return ""

    parts = ["[DATOS CRM EN TIEMPO REAL]"]

    try:
        _build_context_parts(parts, data)
    except Exception:
        logger.exception(f"[CRMCtx] Error armando contexto para {agent_name} (se usa lo parcial)")

    if len(parts) == 1:  # solo el header — nada se pudo armar
        return ""

    return "\n\n".join(parts)


def _build_context_parts(parts: list, data: dict) -> None:
    """Agrega secciones a `parts` in-place. Si una sección individual falla,
    se loguea y se sigue con las demás (nunca se pierde todo el contexto)."""

    # ── Pipeline ─────────────────────────────────────────────────────────────
    if "pipeline" in data and isinstance(data["pipeline"], dict):
        p = data["pipeline"]
        parts.append(
            f"Pipeline hoy:\n"
            f"  Leads recibidos: {p.get('leads_recibidos', 0)}\n"
            f"  Leads calificados: {p.get('leads_calificados', 0)}\n"
            f"  Cierres contado: {p.get('cierres_contado', 0)} (${p.get('monto_contado', 0):,.0f})\n"
            f"  Videollamadas: {p.get('videollamadas', 0)}\n"
            f"  Cuotas cobradas: {p.get('cuotas_cobradas', 0)} (${p.get('monto_cuotas', 0):,.0f})\n"
            f"  Cuotas vencidas sin pagar: {p.get('cuotas_vencidas', 0)}\n"
            f"  Leads desde web: {p.get('leads_web', 0)}\n"
            f"  Publicaciones hoy: {p.get('publicaciones', 0)}"
        )

    # ── Ventas hoy ────────────────────────────────────────────────────────────
    if "ventas" in data and isinstance(data["ventas"], dict):
        v = data["ventas"]
        parts.append(
            f"Ventas del día:\n"
            f"  Cierres: {v.get('cierres', 0)}\n"
            f"  Monto total: ${v.get('monto_total', 0):,.0f}\n"
            f"  Leads nuevos: {v.get('leads_nuevos', 0)}"
        )

    # ── Cuotas vencidas ───────────────────────────────────────────────────────
    if "cuotas" in data and isinstance(data["cuotas"], list):
        cuotas = data["cuotas"]
        if cuotas:
            lines = [f"Cuotas vencidas ({len(cuotas)} total):"]
            for c in cuotas[:20]:
                cliente  = c.get("cliente_nombre", c.get("cliente", c.get("nombre", "Sin nombre")))
                monto    = c.get("valor_cuota", c.get("monto", 0)) or 0
                dias     = c.get("dias_atraso", c.get("dias_vencido", c.get("dias", 0))) or 0
                telefono = c.get("cliente_telefono", c.get("telefono", c.get("phone", "")))
                venta_id = c.get("id", c.get("venta_id", "?"))
                producto = c.get("modelo_especifico", c.get("producto", ""))
                lines.append(f"  • [V#{venta_id}] {cliente} — {producto} — ${monto:,.0f} — {dias}d vencida — Tel: {telefono}")
            if len(cuotas) > 20:
                lines.append(f"  ... y {len(cuotas) - 20} más")
            parts.append("\n".join(lines))
        else:
            parts.append("Cuotas vencidas: ninguna ✅")

    # ── Leads sin respuesta ───────────────────────────────────────────────────
    if "leads_sin_resp" in data and isinstance(data["leads_sin_resp"], list):
        leads = data["leads_sin_resp"]
        if leads:
            lines = [f"Leads sin respuesta +2hs ({len(leads)} total):"]
            for l in leads[:10]:
                nombre  = l.get("nombre", "Sin nombre")
                canal   = l.get("origen", l.get("canal_origen", "?"))
                agente  = l.get("agente_asignado", "?")
                tel     = l.get("telefono", "")
                lines.append(f"  • {nombre} — {canal} — Agente: {agente} — Tel: {tel}")
            if len(leads) > 10:
                lines.append(f"  ... y {len(leads) - 10} más")
            parts.append("\n".join(lines))
        else:
            parts.append("Leads sin respuesta: ninguno ✅")

    # ── Stock (piscinas + paneles) ───────────────────────────────────────────
    if "stock" in data and isinstance(data["stock"], dict) and data["stock"]:
        st = data["stock"]
        lines = ["Stock actual:"]
        for p in st.get("piscinas", []) or []:
            cantidad = p.get("cantidad", 0) or 0
            icono = "🔴" if cantidad == 0 else "🟡" if cantidad <= 3 else "🟢"
            lines.append(f"  {icono} Piscina {p.get('modelo','?')} {p.get('color','')}: {cantidad} unidades")
        for pa in st.get("paneles", []) or []:
            cantidad = pa.get("cantidad", 0) or 0
            bajo = pa.get("bajo_minimo", False)
            icono = "🔴" if bajo else "🟢"
            lines.append(f"  {icono} Panel {pa.get('tipo','?')}: {cantidad} unidades")
        if len(lines) > 1:
            parts.append("\n".join(lines))

    # ── Precios actuales ──────────────────────────────────────────────────────
    if "precios" in data and isinstance(data["precios"], dict) and data["precios"]:
        pr = data["precios"]
        lines = ["Precios actuales (catálogo vigente):"]
        piscinas = pr.get("piscinas", {})
        modulos  = pr.get("modulos", {})
        if piscinas:
            lines.append("  Piscinas (precio de lista, contado):")
            precios_p = piscinas.get("precios", {})
            for modelo, precio in precios_p.items():
                lines.append(f"    • {modelo}: ${precio:,.0f}")
        if modulos:
            lines.append("  Módulos (precio de lista, contado):")
            precios_m = modulos.get("precios", {})
            for sup, precio in precios_m.items():
                lines.append(f"    • {sup}: ${precio:,.0f}")
        combos = pr.get("combos", {})
        if combos:
            lines.append("  Combos:")
            for nombre, c in combos.items():
                pl = c.get("precio_lista", c.get("precio", 0)) if isinstance(c, dict) else c
                lines.append(f"    • {nombre}: ${pl:,.0f}")
        lines.append("  NOTA: estos son TODOS los precios reales vigentes — si un modelo pedido no está en esta lista, decí que no está cargado, NUNCA inventes un precio para completarlo.")
        parts.append("\n".join(lines))

    # ── Flete ────────────────────────────────────────────────────────────────
    if "flete" in data and isinstance(data["flete"], dict) and data["flete"]:
        fl = data["flete"]
        km = fl.get("negocio_flete_km")
        if km:
            parts.append(f"Flete vigente: ${km}/km desde Zárate (valor único real — usar SIEMPRE este, nunca uno de memoria).")

    # ── Materiales / Insumos ──────────────────────────────────────────────────
    if "materiales" in data and isinstance(data["materiales"], list) and data["materiales"]:
        mats = data["materiales"]
        lines = [f"Inventario de materiales ({len(mats)} items):"]
        for m in mats:
            mat_id = m.get("id", "?")
            nombre = m.get("nombre", m.get("material", "?"))
            stock  = m.get("stock_actual", m.get("cantidad", 0))
            unidad = m.get("unidad", "")
            icono  = "🔴" if stock == 0 else "🟡" if stock <= 5 else "🟢"
            lines.append(f"  {icono} [{mat_id}] {nombre}: {stock} {unidad}".rstrip())
        parts.append("\n".join(lines))

    # ── Stock piscinas (fábrica) ──────────────────────────────────────────────
    if "stock_piscinas" in data and isinstance(data["stock_piscinas"], list) and data["stock_piscinas"]:
        ps = data["stock_piscinas"]
        lines = [f"Stock piscinas en fábrica ({len(ps)} registros):"]
        for p in ps:
            modelo   = p.get("modelo", "?")
            color    = p.get("color", "?")
            cantidad = p.get("cantidad", 0)
            pid      = p.get("id", "?")
            icono    = "🔴" if cantidad == 0 else "🟡" if cantidad <= 2 else "🟢"
            lines.append(f"  {icono} [#{pid}] {modelo} {color}: {cantidad} unidad(es)")
        parts.append("\n".join(lines))

    # ══════════════════════════════════════════════════════════════════════════
    # CONTEXTO COMPLETO — Solo para Máximo (admin)
    # ══════════════════════════════════════════════════════════════════════════

    # ── Todos los leads ───────────────────────────────────────────────────────
    if "todos_leads" in data and isinstance(data["todos_leads"], dict):
        payload = data["todos_leads"]
        leads_list = payload.get("leads", [])
        total = payload.get("total", len(leads_list))
        if leads_list:
            lines = [f"TODOS LOS LEADS ({total} total, mostrando {len(leads_list)}):"]
            lines.append("  Formato: [#ID] ESTADO — Nombre — Tel — Localidad — Producto/Pago — Agente — Fecha")
            for l in leads_list:
                lid      = l.get("id", "?")
                estado   = l.get("estado", "?")
                nombre   = l.get("nombre", "?")
                tel      = l.get("telefono", "")
                loc      = l.get("localidad", "")
                prod     = l.get("producto_interes", "")
                pago     = l.get("forma_pago", "")
                agente   = l.get("asesor_apertura_nombre", l.get("agente_asignado", ""))
                fecha    = _fecha_corta(l.get("created_at", ""))
                prod_pago = f"{prod}/{pago}" if pago and pago != "SIN_DEFINIR" else prod
                lines.append(f"  [#{lid}] {estado} — {nombre} — {tel} — {loc} — {prod_pago} — {agente} — {fecha}")
            parts.append("\n".join(lines))

    # ── Ventas al contado ─────────────────────────────────────────────────────
    if "ventas_contado" in data and isinstance(data["ventas_contado"], list):
        vc = data["ventas_contado"]
        if vc:
            lines = [f"VENTAS AL CONTADO ({len(vc)} total):"]
            lines.append("  Formato: [#ID] Fecha — Cliente — Tel — Producto/Modelo — $Precio — FormaPago — Estado")
            for v in vc:
                vid     = v.get("id", "?")
                fecha   = _fecha_corta(v.get("created_at", ""))
                cliente = v.get("cliente_nombre", "?")
                tel     = v.get("cliente_telefono", "")
                modelo  = v.get("modelo_especifico", v.get("producto", "?"))
                color   = v.get("color", "")
                precio  = v.get("precio_final", 0)
                fpago   = v.get("forma_pago", "")
                estado  = v.get("estado", "")
                modelo_color = f"{modelo} {color}".strip()
                lines.append(f"  [#{vid}] {fecha} — {cliente} — {tel} — {modelo_color} — ${precio:,.0f} — {fpago} — {estado}")
            parts.append("\n".join(lines))

    # ── Ventas financiadas ────────────────────────────────────────────────────
    if "ventas_financiadas" in data and isinstance(data["ventas_financiadas"], list):
        vf = data["ventas_financiadas"]
        if vf:
            lines = [f"VENTAS FINANCIADAS ({len(vf)} total):"]
            lines.append("  Formato: [#ID] Fecha — Cliente — Tel — Modelo — $Total — Cuotas — Pagadas — Estado — DiasAtraso")
            for v in vf:
                vid      = v.get("id", "?")
                fecha    = _fecha_corta(v.get("created_at", ""))
                cliente  = v.get("cliente_nombre", "?")
                tel      = v.get("cliente_telefono", "")
                modelo   = v.get("modelo_especifico", v.get("producto", "?"))
                total    = v.get("precio_total", 0)
                ncuotas  = v.get("cantidad_cuotas", 0)
                vcuota   = v.get("valor_cuota", 0)
                pagas    = v.get("cuotas_pagas", 0)
                estado   = v.get("estado_plan", "?")
                atraso   = v.get("dias_atraso", 0)
                atraso_s = f" ⚠️{atraso}d" if atraso > 0 else ""
                lines.append(
                    f"  [#{vid}] {fecha} — {cliente} — {tel} — {modelo} — "
                    f"${total:,.0f} — {ncuotas}c/${vcuota:,.0f} — {pagas}/{ncuotas} — {estado}{atraso_s}"
                )
            parts.append("\n".join(lines))

    # ── Métricas avanzadas ────────────────────────────────────────────────────
    if "metricas_avanzadas" in data and isinstance(data["metricas_avanzadas"], dict):
        ma = data["metricas_avanzadas"]
        if ma:
            lines = ["MÉTRICAS AVANZADAS (últimos 30 días):"]
            funnel = ma.get("funnel", {})
            if funnel:
                lines.append(
                    f"  Funnel: {funnel.get('total_ingresados',0)} leads → "
                    f"{funnel.get('contactados',0)} contactados ({funnel.get('tasa_contacto',0)}%) → "
                    f"{funnel.get('calificados',0)} calificados ({funnel.get('tasa_calificacion',0)}%) → "
                    f"{funnel.get('ventas',0)} ventas ({funnel.get('tasa_conversion',0)}%)"
                )
                if funnel.get("perdidos"):
                    lines.append(f"  Perdidos: {funnel.get('perdidos',0)}")
            tp = ma.get("ticket_promedio", 0) or 0
            if tp:
                lines.append(f"  Ticket promedio: ${tp:,.0f}")
            total_ventas_mes = ma.get("total_ventas_mes", 0) or 0
            revenue_mes = ma.get("revenue_mes", 0) or 0
            lines.append(f"  Ventas del mes: {total_ventas_mes} — Facturación del mes: ${revenue_mes:,.0f}")
            perf = ma.get("performance_asesores", [])
            if perf:
                perf_strs = []
                for p in perf[:8]:
                    perf_strs.append(
                        f"{p.get('nombre','?')}: {p.get('ventas_30d',0)}v "
                        f"({p.get('conversion',0)}%) | {p.get('leads_activos',0)} activos"
                    )
                lines.append("  Performance asesores:\n    " + "\n    ".join(perf_strs))
            total_flujo = ma.get("total_flujo_esperado_30d", 0) or 0
            lines.append(f"  Cobranza esperada próximos 30 días: ${total_flujo:,.0f}")
            flujo_detalle = ma.get("flujo_caja_30d", [])
            if flujo_detalle and isinstance(flujo_detalle, list):
                det_strs = [f"{f.get('fecha','?')}: ${f.get('monto',0):,.0f}" for f in flujo_detalle[:10]]
                lines.append("  Detalle por fecha:\n    " + "\n    ".join(det_strs))
            parts.append("\n".join(lines))

    # ── Ranking de ventas ─────────────────────────────────────────────────────
    if "ranking" in data and isinstance(data["ranking"], dict):
        rk = data["ranking"]
        vendedores = rk.get("vendedores", rk.get("ranking", []))
        if vendedores:
            lines = ["RANKING DEL MES:"]
            for i, v in enumerate(vendedores[:10], 1):
                nombre = v.get("nombre", "?")
                ventas = v.get("ventas", v.get("total_ventas", 0))
                monto  = v.get("monto", v.get("monto_total", 0))
                lines.append(f"  {i}. {nombre}: {ventas} ventas — ${monto:,.0f}")
            parts.append("\n".join(lines))

    if len(parts) == 1:  # solo el header
        return ""

    return "\n\n".join(parts)
