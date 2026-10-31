/*
 * Oficina virtual 3D de EcoFiver AI Company.
 * Geometría 100 % procedural (sin modelos ni texturas de terceros); motor Three.js r160 (MIT, vendorizado).
 * Todo lo que se ve sale del backend real; ver oficina-estado.js.
 */
import * as THREE from "/static/vendor/three/three.module.min.js";
import {
  NOMBRES, ROLES, SALAS, PUESTOS, COLORES, estadoVisual, aprobacionesPorAgente, resumenAdmision, agentesDibujables,
} from "/static/js/oficina-estado.js?v=20261031";

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

async function api(url, opts = {}) {
  const r = await fetch(url, {credentials: "same-origin", headers: {"Content-Type": "application/json"}, ...opts});
  let data = {};
  try { data = await r.json(); } catch (e) { /* sin cuerpo */ }
  if (!r.ok) { const e = new Error(data.detail || ("HTTP " + r.status)); e.status = r.status; throw e; }
  return data;
}

function webglDisponible() {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); }
  catch (e) { return false; }
}

// ── Escena ──────────────────────────────────────────────────────────────────
const lienzo = $("of-lienzo");
const reducirMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let renderer, scene, camera, luzSol, luzAmb, luzHemi;
const avatares = {};          // agente → {grupo, cuerpo, brazos, anillo, etiqueta, monitor, silla, estado}
const lamparas = [];
let admisionCartel = null;
let datos = {tablero: null, aprobaciones: {}, admision: null, conectado: false, ultima: null};
let seleccionado = null;

const mat = (color, extra = {}) => new THREE.MeshStandardMaterial({color, roughness: 0.75, metalness: 0.05, ...extra});

function caja(w, h, d, material, x, y, z, sombra = true) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  m.position.set(x, y, z);
  m.castShadow = sombra; m.receiveShadow = true;
  return m;
}

const etiquetasPantalla = [];   // carteles de tamaño fijo en pantalla (se leen igual de cerca y de lejos)
function cartel(texto, {ancho = 512, alto = 128, fuente = 44, fondo = "rgba(15,23,42,.82)", color = "#f8fafc", escala = 2.4,
                        px = 0} = {}) {
  const c = document.createElement("canvas");
  c.width = ancho; c.height = alto;
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: tex, depthTest: false, transparent: true, sizeAttenuation: !px}));
  sp.scale.set(escala, escala * alto / ancho, 1);
  if (px) { sp.userData.px = px; sp.userData.relacion = ancho / alto; etiquetasPantalla.push(sp); }
  sp.renderOrder = 10;
  sp.userData.dibujar = (lineas, colorBorde) => {
    const g = c.getContext("2d");
    g.clearRect(0, 0, ancho, alto);
    g.fillStyle = fondo;
    const r = 22;
    g.beginPath(); g.roundRect(4, 4, ancho - 8, alto - 8, r); g.fill();
    if (colorBorde) { g.lineWidth = 6; g.strokeStyle = colorBorde; g.stroke(); }
    g.fillStyle = color; g.textAlign = "center"; g.textBaseline = "middle";
    const ls = Array.isArray(lineas) ? lineas : [lineas];
    ls.forEach((l, i) => {
      g.font = `${i === 0 ? 700 : 500} ${i === 0 ? fuente : Math.round(fuente * 0.7)}px system-ui, sans-serif`;
      g.fillText(l, ancho / 2, alto / 2 + (i - (ls.length - 1) / 2) * fuente * 0.95);
    });
    tex.needsUpdate = true;
  };
  sp.userData.dibujar(texto);
  return sp;
}

function construirEscena() {
  renderer = new THREE.WebGLRenderer({canvas: lienzo, antialias: true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0xdfe7ee);
  scene.fog = new THREE.Fog(0xdfe7ee, 45, 90);
  camera = new THREE.PerspectiveCamera(42, 1, 0.1, 200);

  luzHemi = new THREE.HemisphereLight(0xffffff, 0x8d7b68, 0.9);
  scene.add(luzHemi);
  luzAmb = new THREE.AmbientLight(0xffffff, 0.25);
  scene.add(luzAmb);
  luzSol = new THREE.DirectionalLight(0xfff4e0, 1.6);
  luzSol.position.set(-14, 26, 12);
  luzSol.castShadow = true;
  luzSol.shadow.mapSize.set(2048, 2048);
  Object.assign(luzSol.shadow.camera, {left: -30, right: 30, top: 22, bottom: -22, near: 1, far: 70});
  scene.add(luzSol);

  // Piso general y salas
  const piso = caja(46, 0.2, 30, mat(0xcfc6b8), 1.5, -0.1, -0.5, false);
  scene.add(piso);
  for (const [clave, s] of Object.entries(SALAS)) construirSala(clave, s);

  for (const [agente, p] of Object.entries(PUESTOS)) construirPuesto(agente, p);
  construirAdmision();
  decoracion();
}

function construirSala(clave, s) {
  const alfombra = caja(s.w - 0.3, 0.04, s.d - 0.3, mat(new THREE.Color(s.color).lerp(new THREE.Color(0xffffff), 0.72)),
                        s.x, 0.02, s.z, false);
  scene.add(alfombra);
  const pared = mat(0xf4f1ea);
  const vidrio = new THREE.MeshPhysicalMaterial({color: 0xbfe3f2, transparent: true, opacity: 0.28, roughness: 0.05});
  const h = s.humana || clave === "direccion" ? 2.6 : 0.9;              // oficinas cerradas: pared alta vidriada
  const m = s.humana || clave === "direccion" ? vidrio : pared;
  // fondo y laterales; frente abierto para ver adentro
  scene.add(caja(s.w, h, 0.12, clave === "direccion" ? pared : m, s.x, h / 2, s.z - s.d / 2));
  scene.add(caja(0.12, h, s.d, m, s.x - s.w / 2, h / 2, s.z));
  scene.add(caja(0.12, h, s.d, m, s.x + s.w / 2, h / 2, s.z));
  const t = cartel(s.titulo, {fondo: "#" + new THREE.Color(s.color).getHexString() + "e6", fuente: 40, px: 22});
  t.position.set(s.x, h + 0.7, s.z - s.d / 2);
  scene.add(t);
}

const EJE_Y = new THREE.Vector3(0, 1, 0);
const rotPuesto = p => p.rot ?? Math.PI;
function posicionAvatar(p, sentado) {
  const local = new THREE.Vector3(sentado ? 0 : 1.25, 0, sentado ? 0.85 : 0.9).applyAxisAngle(EJE_Y, rotPuesto(p));
  return new THREE.Vector3(p.x + local.x, sentado ? -0.1 : 0, p.z + local.z);
}

function construirPuesto(agente, p) {
  const g = new THREE.Group();
  g.position.set(p.x, 0, p.z);
  g.rotation.y = rotPuesto(p);               // el agente queda detrás del escritorio, mirando a la cámara
  const madera = mat(p.ejecutivo ? 0x5b3a29 : 0xc8a27a);
  const ancho = p.ejecutivo ? 2.8 : 1.8;
  g.add(caja(ancho, 0.08, 1, madera, 0, 0.76, 0));                                   // tapa
  for (const sx of [-1, 1]) g.add(caja(0.08, 0.76, 0.9, mat(0x4b5563), sx * (ancho / 2 - 0.08), 0.38, 0));
  // monitor
  const pantalla = new THREE.MeshStandardMaterial({color: 0x111827, emissive: 0x000000, roughness: 0.3});
  const monitor = caja(0.9, 0.55, 0.05, pantalla, 0, 1.18, -0.3);
  g.add(monitor);
  g.add(caja(0.08, 0.3, 0.08, mat(0x374151), 0, 0.92, -0.3));
  g.add(caja(0.5, 0.03, 0.18, mat(0xe5e7eb), 0, 0.81, 0.05));                        // teclado
  // silla
  const silla = new THREE.Group();
  silla.position.set(0, 0, 0.85);
  const tapiz = mat(p.ejecutivo ? 0x1f2937 : 0x334155);
  silla.add(caja(0.6, 0.1, 0.6, tapiz, 0, 0.5, 0));
  silla.add(caja(0.6, p.ejecutivo ? 0.95 : 0.7, 0.1, tapiz, 0, p.ejecutivo ? 1.0 : 0.88, 0.28));
  silla.add(caja(0.08, 0.45, 0.08, mat(0x6b7280), 0, 0.25, 0));
  g.add(silla);
  if (p.ejecutivo) {
    g.add(caja(1.2, 0.5, 0.5, mat(0x3f2a1e), -2.3, 0.25, -0.9));                     // credenza
    const placa = cartel("CEO", {fuente: 56, escala: 0.8, fondo: "#b08d57"});
    placa.position.set(0.9, 1.0, 0.45);
    g.add(placa);
  }
  scene.add(g);

  const av = construirAvatar(agente, SALAS[p.sala].color);
  av.grupo.rotation.y = Math.PI + rotPuesto(p);
  scene.add(av.grupo);
  avatares[agente] = {...av, monitor: pantalla, puesto: g, base: av.grupo.position.clone(), estado: null};
}

function construirAvatar(agente, colorDepto) {
  const grupo = new THREE.Group();
  grupo.userData.agente = agente;
  const semilla = [...agente].reduce((a, c) => a + c.charCodeAt(0), 0);
  const pieles = [0xf1c27d, 0xe0ac69, 0xc68642, 0x8d5524, 0xffdbac];
  const pelos = [0x2b1b10, 0x5a3825, 0x111111, 0xa0522d, 0xd6b370, 0x6b4423];
  const piel = mat(pieles[semilla % pieles.length]);
  const ropa = mat(colorDepto);
  const cuerpo = new THREE.Group();
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.26, 0.5, 6, 12), ropa);
  torso.position.y = 1.15; torso.castShadow = true;
  const cabeza = new THREE.Mesh(new THREE.SphereGeometry(0.22, 20, 16), piel);
  cabeza.position.y = 1.72; cabeza.castShadow = true;
  const pelo = new THREE.Mesh(new THREE.SphereGeometry(0.235, 20, 12, 0, Math.PI * 2, 0, Math.PI / 2), mat(pelos[semilla % pelos.length]));
  pelo.position.y = 1.74;
  const ojos = new THREE.Group();
  for (const sx of [-1, 1]) {
    const o = new THREE.Mesh(new THREE.SphereGeometry(0.028, 8, 8), mat(0x111827));
    o.position.set(sx * 0.08, 1.74, 0.2);
    ojos.add(o);
  }
  const piernas = new THREE.Group();
  for (const sx of [-1, 1]) {
    const pierna = new THREE.Mesh(new THREE.CapsuleGeometry(0.09, 0.55, 4, 8), mat(0x1f2937));
    pierna.position.set(sx * 0.12, 0.42, 0);
    pierna.castShadow = true;
    piernas.add(pierna);
  }
  const brazos = [];
  for (const sx of [-1, 1]) {
    const pivote = new THREE.Group();
    pivote.position.set(sx * 0.33, 1.38, 0);
    const brazo = new THREE.Mesh(new THREE.CapsuleGeometry(0.075, 0.42, 4, 8), ropa);
    brazo.position.y = -0.26;
    brazo.castShadow = true;
    const mano = new THREE.Mesh(new THREE.SphereGeometry(0.07, 10, 8), piel);
    mano.position.y = -0.52;
    pivote.add(brazo, mano);
    brazos.push(pivote);
  }
  cuerpo.add(torso, cabeza, pelo, ojos, piernas, ...brazos);
  grupo.add(cuerpo);
  const anillo = new THREE.Mesh(new THREE.TorusGeometry(0.48, 0.05, 8, 32),
                                new THREE.MeshBasicMaterial({color: COLORES.sin_datos}));
  anillo.rotation.x = Math.PI / 2;
  anillo.position.y = 0.03;
  grupo.add(anillo);
  const etiqueta = cartel(NOMBRES[agente], {fuente: 50, px: 30});
  etiqueta.position.y = 2.45;
  grupo.add(etiqueta);
  // área de clic generosa
  const zona = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.55, 2.2, 8), new THREE.MeshBasicMaterial({visible: false}));
  zona.position.y = 1.1;
  zona.userData.agente = agente;
  grupo.add(zona);
  return {grupo, cuerpo, brazos, piernas, anillo, etiqueta, zona, cabeza};
}

function construirAdmision() {
  const s = SALAS.admision;
  for (const dx of [-1.6, 1.6]) {
    const g = new THREE.Group();
    g.position.set(s.x + dx, 0, s.z - 0.5);
    g.rotation.y = Math.PI;
    g.add(caja(1.8, 0.08, 1, mat(0xd7ccc8), 0, 0.76, 0));
    g.add(caja(0.9, 0.55, 0.05, mat(0x111827), 0, 1.18, -0.3));
    g.add(caja(0.6, 0.1, 0.6, mat(0x5d4037), 0, 0.5, 0.85));
    g.add(caja(0.6, 0.7, 0.1, mat(0x5d4037), 0, 0.88, 1.13));
    scene.add(g);
  }
  admisionCartel = cartel(["Admisión", "personas · decisión humana"], {fuente: 42, alto: 160, px: 36});
  admisionCartel.position.set(s.x, 2.2, s.z + 0.8);
  scene.add(admisionCartel);
}

function decoracion() {
  const maceta = mat(0x9a6b4b), hoja = mat(0x2f7d32);
  const plantas = [[-17, -11], [-9, -11], [8.5, -11.5], [-17.5, 9.5], [19, 9.5], [-7.5, -1], [9.5, -0.5]];
  for (const [x, z] of plantas) {
    scene.add(caja(0.5, 0.5, 0.5, maceta, x, 0.25, z));
    const copa = new THREE.Mesh(new THREE.IcosahedronGeometry(0.55, 0), hoja);
    copa.position.set(x, 1.0, z); copa.castShadow = true;
    scene.add(copa);
  }
  // ventanal de la oficina ejecutiva
  const vent = new THREE.Mesh(new THREE.PlaneGeometry(6, 1.4), new THREE.MeshBasicMaterial({color: 0x9fd3ff}));
  vent.position.set(SALAS.direccion.x, 1.6, SALAS.direccion.z - SALAS.direccion.d / 2 + 0.07);
  scene.add(vent);
  // sillón y mesa de reuniones de dirección
  scene.add(caja(2.2, 0.45, 0.8, mat(0x374151), -16.5, 0.23, -5.5));
  scene.add(caja(1.6, 0.06, 1.0, mat(0x5b3a29), -11, 0.72, -5.5));
  // lámparas (se encienden fuera del horario de salientes)
  for (const [x, z] of [[-13, -8], [1, -6], [14, -6], [-13, 5], [10, 7]]) {
    const l = new THREE.PointLight(0xffd59a, 0, 14, 1.6);
    l.position.set(x, 3.2, z);
    scene.add(l);
    lamparas.push(l);
  }
}

// ── Cámara (órbita simple: arrastrar rota, rueda/pellizco acerca) ───────────
const VISTA = {theta: -0.18, phi: 0.9, radio: 41, objetivo: [0.5, 0, 0]};
const orbita = {theta: VISTA.theta, phi: VISTA.phi, radio: VISTA.radio, objetivo: new THREE.Vector3(...VISTA.objetivo)};
function ubicarCamara() {
  const {theta, phi, radio, objetivo} = orbita;
  camera.position.set(objetivo.x + radio * Math.sin(phi) * Math.sin(theta), objetivo.y + radio * Math.cos(phi),
                      objetivo.z + radio * Math.sin(phi) * Math.cos(theta));
  camera.lookAt(objetivo);
}
function controles() {
  let arrastre = null, pellizco = null, movido = false;
  lienzo.addEventListener("pointerdown", e => { arrastre = {x: e.clientX, y: e.clientY}; movido = false; lienzo.setPointerCapture(e.pointerId); });
  lienzo.addEventListener("pointermove", e => {
    if (!arrastre || pellizco) return;
    const dx = e.clientX - arrastre.x, dy = e.clientY - arrastre.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) movido = true;
    orbita.theta -= dx * 0.006;
    orbita.phi = Math.min(1.35, Math.max(0.35, orbita.phi - dy * 0.005));
    arrastre = {x: e.clientX, y: e.clientY};
    ubicarCamara();
  });
  lienzo.addEventListener("pointerup", e => { if (!movido) clic(e); arrastre = null; });
  lienzo.addEventListener("wheel", e => {
    e.preventDefault();
    orbita.radio = Math.min(60, Math.max(10, orbita.radio * (1 + Math.sign(e.deltaY) * 0.08)));
    ubicarCamara();
  }, {passive: false});
  lienzo.addEventListener("touchmove", e => {
    if (e.touches.length !== 2) return;
    const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
    if (pellizco) orbita.radio = Math.min(60, Math.max(10, orbita.radio * pellizco / d));
    pellizco = d;
    ubicarCamara();
  }, {passive: true});
  lienzo.addEventListener("touchend", () => { pellizco = null; });
}

const rayo = new THREE.Raycaster();
function clic(e) {
  const r = lienzo.getBoundingClientRect();
  const p = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  rayo.setFromCamera(p, camera);
  const zonas = Object.values(avatares).filter(a => a.grupo.visible).map(a => a.zona);
  const hit = rayo.intersectObjects(zonas, false)[0];
  if (hit) seleccionar(hit.object.userData.agente, true);
}

function enfocar(agente) {
  const p = PUESTOS[agente];
  orbita.objetivo.set(p.x, 0, p.z);
  orbita.radio = 14;
  ubicarCamara();
}

// ── Estado real → escena ────────────────────────────────────────────────────
function aplicarEstados() {
  if (!scene) return;                       // sin WebGL: solo lista y ficha
  const filas = Object.fromEntries(agentesDibujables(datos.tablero).map(a => [a.agente, a]));
  for (const [agente, av] of Object.entries(avatares)) {
    const ev = estadoVisual(filas[agente] || null, datos.aprobaciones[agente] || 0, datos.conectado);
    av.estado = ev;
    av.grupo.visible = true;
    av.cuerpo.visible = ev.visible;
    av.zona.visible = true;
    av.anillo.material.color.setHex(COLORES[ev.modo]);
    const borde = "#" + new THREE.Color(COLORES[ev.modo]).getHexString();
    av.etiqueta.userData.dibujar([`${ev.icono ? ev.icono + " " : ""}${NOMBRES[agente]}${ev.alerta ? " ⚠" : ""}`, ev.etiqueta], borde);
    av.etiqueta.position.y = ev.visible ? (ev.sentado ? 2.15 : 2.45) : 1.4;
    // sentado frente al monitor o de pie al costado del escritorio
    const p = PUESTOS[agente];
    av.grupo.position.copy(posicionAvatar(p, ev.sentado));
    av.base.copy(av.grupo.position);
    av.piernas.visible = !ev.sentado;
    av.monitor.emissive.setHex(ev.modo === "trabajando" ? 0x1e6fd9 : ev.modo === "aprobacion" ? 0x1e3a8a : 0x000000);
    av.monitor.emissiveIntensity = ev.modo === "trabajando" ? 1.2 : 0.6;
  }
  // día / noche según el horario de salientes (el entrante sigue 24/7)
  const noche = datos.conectado && datos.tablero && !datos.tablero.en_horario;
  scene.background.setHex(noche ? 0x1b2433 : 0xdfe7ee);
  scene.fog.color.setHex(noche ? 0x1b2433 : 0xdfe7ee);
  luzSol.intensity = noche ? 0.25 : 1.6;
  luzHemi.intensity = noche ? 0.35 : 0.9;
  lamparas.forEach(l => { l.intensity = noche ? 22 : 0; });
  // Admisión: solo números agregados, sin datos personales
  const ad = resumenAdmision(datos.admision);
  admisionCartel.userData.dibujar(["Admisión · personas",
    ad ? `${ad.enCurso} esperan decisión · ${ad.aprobados} aprobados` : "decisión humana"], "#8d6e63");
}

function pintarLista() {
  const filas = Object.fromEntries(agentesDibujables(datos.tablero).map(a => [a.agente, a]));
  $("of-lista").innerHTML = Object.keys(PUESTOS).map(agente => {
    const ev = estadoVisual(filas[agente] || null, datos.aprobaciones[agente] || 0, datos.conectado);
    const c = "#" + new THREE.Color(COLORES[ev.modo]).getHexString();
    return `<button class="of-item${seleccionado === agente ? " of-sel" : ""}" onclick="ofSeleccionar('${agente}')">
      <span class="of-punto" style="background:${c}"></span><b>${esc(NOMBRES[agente])}</b>
      <span class="of-sub">${esc(ev.etiqueta)}${ev.alerta ? " · ⚠ fallas hoy" : ""}</span></button>`;
  }).join("");
}

function pintarFicha() {
  const f = $("of-ficha");
  if (!seleccionado) { f.innerHTML = `<div class="of-sub">Tocá un agente en la oficina o en la lista.</div>`; return; }
  const a = agentesDibujables(datos.tablero).find(x => x.agente === seleccionado);
  const ev = estadoVisual(a || null, datos.aprobaciones[seleccionado] || 0, datos.conectado);
  const act = a?.actividad || {};
  f.innerHTML = `
    <div class="of-sub">${esc(a?.departamento || PUESTOS[seleccionado].sala)} · ${esc(ROLES[seleccionado])}</div>
    <h3 style="margin:2px 0 6px">${esc(NOMBRES[seleccionado])}</h3>
    <span class="op-estado op-${esc(a?.estado || "")}">${esc(a?.estado || "SIN DATOS")}</span>
    ${a?.motivo ? `<div class="of-sub">Motivo: ${esc(a.motivo)}</div>` : ""}
    <div style="margin:8px 0;font-size:13px">${esc(ev.etiqueta)}${ev.tarea ? `: ${esc(ev.tarea.titulo)}` : ""}</div>
    <div class="of-sub">Hoy: ${act.completadas_hoy ?? "—"} completadas · ${act.fallidas_hoy ?? "—"} fallidas · ${act.pendientes ?? "—"} en cola</div>
    <div class="of-sub">Salientes: ${a ? (a.salientes_permitidos ? "permitidos" : esc(a.salientes_motivo)) : "—"}</div>
    <div class="of-sub">Última actividad: ${act.ultima_actividad ? esc(new Date(act.ultima_actividad + (act.ultima_actividad.endsWith("Z") ? "" : "Z")).toLocaleString("es-AR")) : "—"}</div>
    <div class="op-btns">
      <button onclick="ofEstado('ACTIVO')">Activar</button>
      <button onclick="ofEstado('PAUSADO')">Pausar</button>
      <button onclick="ofEstado('DESACTIVADO')">Desactivar</button>
      <a class="of-link" href="/operaciones-ia">Dar instrucción / ver tareas →</a>
    </div>`;
}

function seleccionar(agente, desdeEscena = false) {
  seleccionado = agente;
  if (!desdeEscena || window.innerWidth < 900) enfocar(agente);
  pintarFicha(); pintarLista();
}
window.ofSeleccionar = a => seleccionar(a);
window.ofEstado = async estado => {
  if (!seleccionado) return;
  const motivo = estado === "ACTIVO" ? "" : (prompt(`Motivo para ${estado.toLowerCase()} a ${NOMBRES[seleccionado]}:`) || "");
  if (estado !== "ACTIVO" && !motivo) return;
  try {
    await api(`/api/agentes/${seleccionado}/estado`, {method: "POST", body: JSON.stringify({estado, motivo})});
    await cargar();
  } catch (e) { alert("No se pudo cambiar el estado: " + e.message); }
};
window.ofVista = () => { Object.assign(orbita, {theta: VISTA.theta, phi: VISTA.phi, radio: VISTA.radio}); orbita.objetivo.set(...VISTA.objetivo); ubicarCamara(); };

async function cargar() {
  try {
    const [tablero, aprob] = await Promise.all([api("/api/agentes/control"), api("/api/aprobaciones")]);
    datos.tablero = tablero;
    datos.aprobaciones = aprobacionesPorAgente(aprob.aprobaciones);
    datos.conectado = true;
    datos.ultima = new Date();
    try { datos.admision = (await api("/api/admision/resumen")).por_estado; } catch (e) { datos.admision = null; }
    $("of-conexion").textContent = `🟢 En vivo · ${datos.ultima.toLocaleTimeString("es-AR")}`;
    $("of-conexion").style.color = "var(--green-light)";
    $("of-horario").textContent = tablero.en_horario ? "☀️ Horario de salientes" : "🌙 Fuera de horario de salientes (entrante 24/7)";
  } catch (e) {
    datos.conectado = false;                 // nunca mostrar un estado viejo como actual
    $("of-conexion").textContent = `🔴 Sin conexión con el motor (${e.message})`;
    $("of-conexion").style.color = "var(--error)";
  }
  aplicarEstados(); pintarLista(); pintarFicha();
}

// ── Bucle ───────────────────────────────────────────────────────────────────
const reloj = new THREE.Clock();
function animar() {
  requestAnimationFrame(animar);
  if (document.hidden) return;
  const t = reloj.getElapsedTime();
  for (const av of Object.values(avatares)) {
    const m = av.estado?.modo;
    if (!reducirMovimiento) {
      const respira = Math.sin(t * 2 + av.base.x) * 0.012;
      av.cuerpo.position.y = respira;
      if (m === "trabajando") {                            // tipea
        av.brazos[0].rotation.x = -1.1 + Math.sin(t * 14) * 0.12;
        av.brazos[1].rotation.x = -1.1 + Math.sin(t * 14 + 1.6) * 0.12;
        av.cabeza.rotation.x = 0.12 + Math.sin(t * 3) * 0.03;
      } else if (m === "aprobacion") {                     // levanta la mano: espera tu decisión
        av.brazos[0].rotation.x = 0; av.brazos[1].rotation.x = -2.9 + Math.sin(t * 4) * 0.12;
      } else if (av.estado?.sentado) {
        av.brazos[0].rotation.x = av.brazos[1].rotation.x = -0.9;
      } else {
        av.brazos[0].rotation.x = av.brazos[1].rotation.x = 0;
      }
      av.anillo.scale.setScalar(m === "trabajando" ? 1 + Math.sin(t * 4) * 0.06 : 1);
    }
    av.anillo.material.transparent = seleccionado && seleccionado !== av.grupo.userData.agente;
    av.anillo.material.opacity = av.anillo.material.transparent ? 0.45 : 1;
  }
  renderer.render(scene, camera);
}

function redimensionar() {
  const w = lienzo.clientWidth, h = lienzo.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.fov = w / h < 1 ? 62 : 42;             // en vertical (celular) se abre el campo para ver toda la planta
  camera.updateProjectionMatrix();
  const tan = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  const factor = w < 600 ? 0.62 : 1;            // en celular, etiquetas más chicas para que no se tapen
  for (const sp of etiquetasPantalla) {
    const hh = sp.userData.px * factor * 2 / Math.max(h, 1) * tan;
    sp.scale.set(hh * sp.userData.relacion, hh, 1);
  }
}

function iniciar() {
  if (!webglDisponible()) {
    $("of-escena").innerHTML = `<div class="of-sin3d">Este dispositivo no soporta 3D. Usá la
      <a href="/operaciones-ia">vista 2D de Operaciones IA</a> (mismos datos) o la lista de la derecha.</div>`;
    setInterval(cargar, 10000); cargar();
    return;
  }
  construirEscena();
  controles();
  ubicarCamara();
  redimensionar();
  new ResizeObserver(redimensionar).observe(lienzo);
  animar();
  cargar();
  setInterval(() => { if (!document.hidden) cargar(); }, 10000);
}

window.ofTest = {estadoVisual, avatares: () => avatares, datos: () => datos};   // inspección en pruebas
iniciar();
