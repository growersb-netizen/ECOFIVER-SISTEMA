(function () {
  "use strict";

  // ────────────────────────────────────────────────────────────
  // CONFIG — reemplazar antes de publicar
  // ────────────────────────────────────────────────────────────
  // Número real de WhatsApp comercial de esta campaña.
  const WHATSAPP_NUMBER = "5491168733406"; // formato: código país + área + número, sin + ni espacios
  const WHATSAPP_DISPLAY = "+54 9 11 6873-3406";

  // Endpoint público (sin API key) del CRM real para guardar leads del formulario.
  // Si el CRM no responde, el formulario igual abre WhatsApp — no depende de esto.
  const CRM_LEAD_ENDPOINT = "https://eco-crm-dawn-fog-5476.fly.dev/api/public/landing-lead";

  // ────────────────────────────────────────────────────────────
  // Reglas de precios (memoria comercial vigente al 2026-06-15,
  // confirmar con el dueño del negocio antes de publicar)
  // ────────────────────────────────────────────────────────────
  const MODULO_PRECIO_M2_FINANCIADO = 690000; // $/m², financiado
  const MODULO_FACTOR_INGRESO = 2; // inscripción = 2 cuotas del plan

  // Lista de precios de piscinas — real, "Eco_Modulos_Piscinas_Lista_Completa.pdf".
  // Fórmula verificada contra las 64 celdas de la lista oficial (12/18/24/36 cuotas):
  //   cuota   = round(lista / (cuotas + 2))
  //   entrada = round(2 * lista / (cuotas + 2))   (equivale a 2 cuotas)
  // El total financiado es el precio de LISTA (no el de contado).
  const PISCINAS = [
    { nombre: "Minideck",                          medidas: "3x2x70",                    contado: 3000000, lista: 4370000 },
    { nombre: "Miniportante",                       medidas: "2,50x2,10x70",               contado: 2500000, lista: 3640000 },
    { nombre: "Autoportante",                       medidas: "4,10x2,10x70",               contado: 3000000, lista: 4370000 },
    { nombre: "Arco Romano Chico Recto",            medidas: "4,60x2,47x1,20",              contado: 3000000, lista: 4370000 },
    { nombre: "Arco Romano Chico C/Desnivel",       medidas: "4,60x2,35x1,10 a 1,30",       contado: 2990000, lista: 4350000 },
    { nombre: "Arco Romano Mediano Recto",          medidas: "6,40x2,94x1,40",              contado: 4900000, lista: 7130000 },
    { nombre: "Arco Romano Mediano C/Desnivel",     medidas: "7x3,35x1,25 a 1,70",          contado: 4900000, lista: 7130000 },
    { nombre: "Arco Romano Grande",                 medidas: "8,10x3,35x1,25 a 1,80",       contado: 4800000, lista: 6990000 },
    { nombre: "Playa Húmeda",                       medidas: "5,20x2,45x1,10 a 1,30",       contado: 3290000, lista: 4790000 },
    { nombre: "Minimalista Chica",                  medidas: "3,97x2,46x1,20",              contado: 2800000, lista: 4080000 },
    { nombre: "Minimalista Mediana",                medidas: "5,50x2,90x1,50",              contado: 4425000, lista: 6440000 },
    { nombre: "Minimalista Grande",                 medidas: "6,40x3x1,40",                 contado: 3690000, lista: 5370000 },
    { nombre: "Recta C/Mini Escalera",               medidas: "4,63x2,48x1,25",              contado: 3375000, lista: 4910000 },
    { nombre: "Playa Húmeda Chica C/Escalera",      medidas: "4,10x2,40x1,20",              contado: 2850000, lista: 4150000 },
    { nombre: "Semi Playa Húmeda C/Escalera",       medidas: "6,70x2,95x1,50",              contado: 3990000, lista: 5810000 },
    { nombre: "Playa y Abanico",                    medidas: "9,20x3,80x1,25 a 1,80",       contado: 5500000, lista: 8000000 }
  ];

  function formatearPesos(valor) {
    return Math.round(valor).toLocaleString("es-AR");
  }

  function waLink(mensaje) {
    return "https://wa.me/" + WHATSAPP_NUMBER + "?text=" + encodeURIComponent(mensaje);
  }

  // ────────────────────────────────────────────────────────────
  // Header: menú móvil + estado "scrolled"
  // ────────────────────────────────────────────────────────────
  const header = document.getElementById("site-header");
  const menuToggle = document.getElementById("menu-toggle");
  const mainNav = document.getElementById("main-nav");

  menuToggle.addEventListener("click", function () {
    const isOpen = mainNav.classList.toggle("open");
    menuToggle.setAttribute("aria-expanded", String(isOpen));
  });

  mainNav.querySelectorAll("a").forEach(function (link) {
    link.addEventListener("click", function () {
      mainNav.classList.remove("open");
      menuToggle.setAttribute("aria-expanded", "false");
    });
  });

  window.addEventListener("scroll", function () {
    header.style.boxShadow = window.scrollY > 8 ? "0 8px 24px -12px rgba(0,0,0,.4)" : "none";
  });

  // ────────────────────────────────────────────────────────────
  // Todos los CTA de WhatsApp: arman el link con mensaje contextual
  // ────────────────────────────────────────────────────────────
  const MENSAJES_WA = {
    "header": "Hola! Vi la landing de EcoFiver y quiero info sobre financiación.",
    "hero": "Hola! Quiero financiar una piscina o un módulo en pesos.",
    "promo-mundial": null, // se arma dinámicamente
    "cooperativa": "Hola! Quiero hablar con la cooperativa sobre financiar mi vivienda, una piscina, o ambas cosas.",
    "combo-quincho-piscina": null, // se arma dinámicamente
    "producto-piscina": "Hola! Quiero información para financiar una piscina.",
    "producto-modulo": "Hola! Quiero información para financiar un módulo habitable.",
    "simulador-modulo": null, // se arma dinámicamente
    "simulador-piscina": null, // se arma dinámicamente
    "footer": "Hola! Vi la landing de EcoFiver y quiero hacer una consulta.",
    "float": "Hola! Quiero consultar por financiación de piscinas o módulos."
  };

  function actualizarLinksWhatsapp() {
    document.querySelectorAll("[data-wa-cta]").forEach(function (el) {
      const key = el.getAttribute("data-wa-cta");
      if (key === "simulador-modulo" || key === "simulador-piscina" || key === "promo-mundial" || key === "combo-quincho-piscina") return; // se arman aparte
      el.setAttribute("href", waLink(MENSAJES_WA[key] || MENSAJES_WA.hero));
    });
    document.querySelectorAll("[data-wa-display]").forEach(function (el) {
      el.textContent = WHATSAPP_DISPLAY;
    });
  }

  // ────────────────────────────────────────────────────────────
  // Hero Promo Mundial: tarjeta de precio (misma fuente de datos que el simulador)
  // ────────────────────────────────────────────────────────────
  const PROMO_MODELO_INDEX = 11; // Minimalista Grande (6,40x3x1,40)
  const PROMO_CUOTAS = 36;

  function pintarPromoMundial() {
    const modelo = PISCINAS[PROMO_MODELO_INDEX];
    const cuota = modelo.lista / (PROMO_CUOTAS + 2);
    const nombreEl = document.getElementById("promo-modelo-nombre");
    const medidasEl = document.getElementById("promo-modelo-medidas");
    const cuotaEl = document.getElementById("promo-cuota");
    const cuotasNEl = document.getElementById("promo-cuotas-n");
    if (!nombreEl) return;

    nombreEl.textContent = modelo.nombre;
    medidasEl.textContent = modelo.medidas;
    cuotaEl.textContent = formatearPesos(cuota);
    cuotasNEl.textContent = PROMO_CUOTAS;

    const promoCta = document.querySelector('[data-wa-cta="promo-mundial"]');
    if (promoCta) {
      const msg = "Hola! Vi la Promo Mundial de la piscina " + modelo.nombre + " (" + modelo.medidas +
        ") a $" + formatearPesos(cuota) + "/mes en " + PROMO_CUOTAS + " cuotas fijas. Quiero reservar mi lugar y la pérgola de regalo de las primeras 100 suscripciones.";
      promoCta.setAttribute("href", waLink(msg));
    }
  }

  // ────────────────────────────────────────────────────────────
  // Combo destacado: Quincho 18 m² + Piscina Playa y Abanico
  // Mismas reglas que el combo general: se suma el valor nominal
  // (quincho a $690.000/m² + piscina a precio de lista), sin
  // descuento, financiado con ingreso equivalente a 2 cuotas.
  // ────────────────────────────────────────────────────────────
  const COMBO_QUINCHO_M2 = 18;
  const COMBO_PISCINA_INDEX = 15; // Playa y Abanico (9,20x3,80x1,25 a 1,80)
  const COMBO_CUOTAS_MOSTRADAS = [36, 60, 120];

  function pintarCombo() {
    const totalEl = document.getElementById("combo-total");
    if (!totalEl) return;

    const piscina = PISCINAS[COMBO_PISCINA_INDEX];
    const quinchoTotal = COMBO_QUINCHO_M2 * MODULO_PRECIO_M2_FINANCIADO;
    const comboTotal = quinchoTotal + piscina.lista;

    totalEl.textContent = formatearPesos(comboTotal);

    COMBO_CUOTAS_MOSTRADAS.forEach(function (n) {
      const el = document.getElementById("combo-cuota-" + n);
      if (el) el.textContent = formatearPesos(comboTotal / (n + 2));
    });

    const comboCta = document.querySelector('[data-wa-cta="combo-quincho-piscina"]');
    if (comboCta) {
      const cuota60 = comboTotal / 62;
      const msg = "Hola! Quiero el combo Quincho 18 m² + Piscina " + piscina.nombre + " (" + piscina.medidas +
        "). Total a financiar $" + formatearPesos(comboTotal) + ", por ejemplo $" + formatearPesos(cuota60) +
        "/mes en 60 cuotas. Quiero armar mi plan.";
      comboCta.setAttribute("href", waLink(msg));
    }
  }

  // ────────────────────────────────────────────────────────────
  // Simulador: tabs
  // ────────────────────────────────────────────────────────────
  const simTabs = document.querySelectorAll(".sim-tab");
  const simPanels = document.querySelectorAll(".sim-panel");

  simTabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      simTabs.forEach(function (t) { t.classList.remove("active"); t.setAttribute("aria-selected", "false"); });
      simPanels.forEach(function (p) { p.classList.remove("active"); });
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");
      document.querySelector('.sim-panel[data-panel="' + tab.dataset.tab + '"]').classList.add("active");
    });
  });

  // ────────────────────────────────────────────────────────────
  // Simulador: módulo (fórmula real)
  // cuota = (m2 * 690000) / (n_cuotas + 2)
  // ────────────────────────────────────────────────────────────
  const moduloM2 = document.getElementById("sim-modulo-m2");
  const moduloCuotas = document.getElementById("sim-modulo-cuotas");
  const moduloCuotasOut = document.getElementById("sim-modulo-cuotas-out");
  const moduloCuotaEl = document.getElementById("sim-modulo-cuota");
  const moduloTotalEl = document.getElementById("sim-modulo-total");
  const moduloInscripcionEl = document.getElementById("sim-modulo-inscripcion");
  const simuladorModuloCta = document.querySelector('[data-wa-cta="simulador-modulo"]');

  function calcularModulo() {
    const m2 = parseInt(moduloM2.value, 10);
    const nCuotas = parseInt(moduloCuotas.value, 10);
    const total = m2 * MODULO_PRECIO_M2_FINANCIADO;
    const cuota = total / (nCuotas + MODULO_FACTOR_INGRESO);
    const inscripcion = cuota * MODULO_FACTOR_INGRESO;

    moduloCuotasOut.textContent = nCuotas;
    moduloCuotaEl.textContent = formatearPesos(cuota);
    moduloTotalEl.textContent = "$" + formatearPesos(total);
    moduloInscripcionEl.textContent = "$" + formatearPesos(inscripcion);

    if (simuladorModuloCta) {
      const msg = "Hola! Simulé un módulo de " + m2 + " m² en " + nCuotas +
        " cuotas (aprox. $" + formatearPesos(cuota) + "/mes). Quiero confirmar el plan con un asesor.";
      simuladorModuloCta.setAttribute("href", waLink(msg));
    }
  }

  moduloM2.addEventListener("change", calcularModulo);
  moduloCuotas.addEventListener("input", calcularModulo);

  // ────────────────────────────────────────────────────────────
  // Simulador: piscina (precio de lista, sin inventar cuota financiada)
  // ────────────────────────────────────────────────────────────
  const piscinaModelo = document.getElementById("sim-piscina-modelo");
  const piscinaCuotas = document.getElementById("sim-piscina-cuotas");
  const piscinaCuotasOut = document.getElementById("sim-piscina-cuotas-out");
  const piscinaCuotaEl = document.getElementById("sim-piscina-cuota");
  const piscinaEntradaEl = document.getElementById("sim-piscina-entrada");
  const piscinaTotalEl = document.getElementById("sim-piscina-total");
  const piscinaContadoEl = document.getElementById("sim-piscina-contado");
  const simuladorPiscinaCta = document.querySelector('[data-wa-cta="simulador-piscina"]');

  function calcularPiscina() {
    const modelo = PISCINAS[parseInt(piscinaModelo.value, 10)];
    const nCuotas = parseInt(piscinaCuotas.value, 10);

    const cuota = modelo.lista / (nCuotas + 2);
    const entrada = (2 * modelo.lista) / (nCuotas + 2);

    piscinaCuotasOut.textContent = nCuotas;
    piscinaCuotaEl.textContent = formatearPesos(cuota);
    piscinaEntradaEl.textContent = "$" + formatearPesos(entrada);
    piscinaTotalEl.textContent = "$" + formatearPesos(modelo.lista);
    piscinaContadoEl.textContent = "$" + formatearPesos(modelo.contado) + " (31% OFF)";

    if (simuladorPiscinaCta) {
      const msg = "Hola! Simulé la piscina " + modelo.nombre + " (" + modelo.medidas + ") en " + nCuotas +
        " cuotas fijas: $" + formatearPesos(cuota) + "/mes + entrada de $" + formatearPesos(entrada) +
        ". Quiero reservar este plan.";
      simuladorPiscinaCta.setAttribute("href", waLink(msg));
    }
  }

  piscinaModelo.addEventListener("change", calcularPiscina);
  piscinaCuotas.addEventListener("input", calcularPiscina);

  // ────────────────────────────────────────────────────────────
  // FAQ acordeón
  // ────────────────────────────────────────────────────────────
  document.querySelectorAll(".faq-question").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const item = btn.closest(".faq-item");
      const isOpen = item.classList.contains("open");
      document.querySelectorAll(".faq-item.open").forEach(function (openItem) {
        openItem.classList.remove("open");
        openItem.querySelector(".faq-question").setAttribute("aria-expanded", "false");
      });
      if (!isOpen) {
        item.classList.add("open");
        btn.setAttribute("aria-expanded", "true");
      }
    });
  });

  // ────────────────────────────────────────────────────────────
  // Formulario de contacto → arma mensaje y abre WhatsApp
  // ────────────────────────────────────────────────────────────
  const leadForm = document.getElementById("lead-form");
  leadForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const nombre = document.getElementById("f-nombre").value.trim();
    const telefono = document.getElementById("f-telefono").value.trim();
    const localidad = document.getElementById("f-localidad").value.trim();
    const interes = document.getElementById("f-interes").value;
    const mensaje = document.getElementById("f-mensaje").value.trim();

    let texto = "Hola! Soy " + nombre + " de " + localidad + ". Me interesa: " + interes + ". Mi WhatsApp: " + telefono + ".";
    if (mensaje) texto += " Detalle: " + mensaje;

    // Guardar el lead en el CRM real, sin bloquear el flujo de WhatsApp
    // si el CRM no responde (fire-and-forget, con timeout corto).
    try {
      const controller = new AbortController();
      setTimeout(function () { controller.abort(); }, 3000);
      fetch(CRM_LEAD_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre: nombre, telefono: telefono, localidad: localidad, interes: interes, mensaje: mensaje, origen: "LANDING_PROMO_MUNDIAL" }),
        signal: controller.signal
      }).catch(function () { /* silencioso: WhatsApp sigue funcionando igual */ });
    } catch (err) { /* fetch no disponible o CRM caído: no bloquea nada */ }

    window.open(waLink(texto), "_blank", "noopener");

    const submitBtn = leadForm.querySelector('button[type="submit"]');
    const original = submitBtn.textContent;
    submitBtn.textContent = "¡Listo! Te contactamos por WhatsApp";
    submitBtn.disabled = true;
    setTimeout(function () {
      submitBtn.textContent = original;
      submitBtn.disabled = false;
      leadForm.reset();
    }, 3500);
  });

  // ────────────────────────────────────────────────────────────
  // Compartir esta promo por WhatsApp (share intent, sin destinatario)
  // ────────────────────────────────────────────────────────────
  const shareBtn = document.getElementById("compartir-promo");
  if (shareBtn) {
    shareBtn.addEventListener("click", function (e) {
      e.preventDefault();
      const msg = "Mirá esta promo de EcoFiver: pileta financiada en cuotas fijas + pérgola de regalo. " + window.location.href;
      window.open("https://wa.me/?text=" + encodeURIComponent(msg), "_blank", "noopener");
    });
  }

  // ────────────────────────────────────────────────────────────
  // Animación sutil al hacer scroll (respeta "reducir movimiento")
  // ────────────────────────────────────────────────────────────
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches && "IntersectionObserver" in window) {
    const revealTargets = document.querySelectorAll(
      ".section-head, .product-card, .step-card, .feature-card, .testimonial-card, .combo-card, .faq-item, .coop-trust-bar"
    );
    revealTargets.forEach(function (el) { el.classList.add("reveal"); });

    const revealObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("reveal-visible");
          revealObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15, rootMargin: "0px 0px -40px 0px" });

    revealTargets.forEach(function (el) { revealObserver.observe(el); });
  }

  // ────────────────────────────────────────────────────────────
  // Init
  // ────────────────────────────────────────────────────────────
  actualizarLinksWhatsapp();
  pintarPromoMundial();
  pintarCombo();
  calcularModulo();
  calcularPiscina();
})();
