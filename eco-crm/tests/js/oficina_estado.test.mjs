// node --test tests/js/  — lógica de la oficina virtual (sin navegador)
import test from "node:test";
import assert from "node:assert/strict";
import {estadoVisual, aprobacionesPorAgente, resumenAdmision, agentesDibujables, PUESTOS, NOMBRES, SALAS}
  from "../../static/js/oficina-estado.js";

const fila = (estado, act = {}) => ({agente: "camila", estado, actividad: {pendientes: 0, completadas_hoy: 0, fallidas_hoy: 0, tarea_en_curso: null, ...act}});

test("16 puestos de la empresa, Valentín excluido, todos con sala existente", () => {
  assert.equal(Object.keys(PUESTOS).length, 16);
  assert.ok(!("valentin" in PUESTOS));
  for (const [a, p] of Object.entries(PUESTOS)) { assert.ok(SALAS[p.sala], a); assert.ok(NOMBRES[a], a); }
  assert.ok(SALAS.admision.humana && SALAS.direccion);
  assert.ok(PUESTOS.maximo.ejecutivo && PUESTOS.maximo.sala === "direccion");
});

test("trabajando solo con tarea en ejecución registrada", () => {
  assert.equal(estadoVisual(fila("ACTIVO")).modo, "disponible");
  const ev = estadoVisual(fila("ACTIVO", {tarea_en_curso: {id: 7, titulo: "x"}}));
  assert.equal(ev.modo, "trabajando"); assert.match(ev.etiqueta, /#7/);
});

test("prioridad: desactivado > pausado > trabajando > aprobación > cola", () => {
  const t = {tarea_en_curso: {id: 1}, pendientes: 3};
  assert.equal(estadoVisual(fila("DESACTIVADO", t), 2).modo, "desactivado");
  assert.equal(estadoVisual(fila("DESACTIVADO")).visible, false);
  assert.equal(estadoVisual(fila("PAUSADO", t), 2).modo, "pausado");
  assert.equal(estadoVisual(fila("ACTIVO", {pendientes: 3}), 2).modo, "aprobacion");
  assert.equal(estadoVisual(fila("ACTIVO", {pendientes: 3})).modo, "en_cola");
});

test("sin conexión o sin fila: sin datos, nunca un estado viejo", () => {
  assert.equal(estadoVisual(fila("ACTIVO", {tarea_en_curso: {id: 1}}), 0, false).modo, "sin_datos");
  assert.equal(estadoVisual(null).modo, "sin_datos");
});

test("alerta por fallas del día", () => {
  assert.equal(estadoVisual(fila("ACTIVO", {fallidas_hoy: 1})).alerta, true);
});

test("aprobaciones pendientes por agente y resumen de Admisión", () => {
  assert.deepEqual(aprobacionesPorAgente([{agente: "maximo", estado: "PENDIENTE"}, {agente: "maximo", estado: "PENDIENTE"},
    {agente: "aurora", estado: "EJECUTADA"}]), {maximo: 2});
  assert.deepEqual(resumenAdmision({EN_ADMISION: 2, DOCUMENTACION_PENDIENTE: 1, APROBADO_POR_ADMISION: 4, CONSULTA_RECIBIDA: 5}),
    {enCurso: 3, total: 12, aprobados: 4, cerrados: 0});
  assert.equal(resumenAdmision(null), null);
});

test("solo se dibujan agentes con puesto (si el backend mandara a Valentín, no aparece)", () => {
  const d = agentesDibujables({agentes: [{agente: "camila"}, {agente: "valentin"}]});
  assert.deepEqual(d.map(x => x.agente), ["camila"]);
});
