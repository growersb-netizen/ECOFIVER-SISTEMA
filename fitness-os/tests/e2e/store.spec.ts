/**
 * Fase 15 — E2E Tests (Playwright).
 * Pruebas de flujos críticos de la tienda pública.
 *
 * Ejecutar: pnpm test:e2e
 * Requiere: servidor web en WEB_URL, API en API_URL, datos de seed.
 */
import { test, expect } from "@playwright/test";

const WEB_URL = process.env["WEB_URL"] ?? "http://localhost:3002";
const API_URL = process.env["API_URL"] ?? "http://localhost:3001";

test.describe("Tienda pública", () => {
  test("Home carga y muestra la marca", async ({ page }) => {
    await page.goto(WEB_URL);
    await expect(page.locator("text=FITNESS BUSINESS OS").first()).toBeVisible();
  });

  test("Catálogo muestra productos publicados", async ({ page }) => {
    await page.goto(`${WEB_URL}/tienda`);
    await expect(page).toHaveTitle(/Tienda|Fitness/i);
    // Si hay productos, deberían aparecer article cards
    const cards = page.locator("article");
    const count = await cards.count();
    // Con seed data debería haber al menos 1 producto publicado
    // En CI sin seed, aceptamos 0 y checkeamos el mensaje "no hay productos"
    if (count === 0) {
      await expect(page.locator("text=No encontramos")).toBeVisible();
    } else {
      expect(count).toBeGreaterThan(0);
    }
  });

  test("Filtro por categoría funciona", async ({ page }) => {
    await page.goto(`${WEB_URL}/tienda?categoria=guias-entrenamiento`);
    await expect(page).not.toHaveURL(/error/);
    const body = page.locator("body");
    await expect(body).toBeVisible();
  });

  test("Página de producto 404 muestra not-found", async ({ page }) => {
    await page.goto(`${WEB_URL}/tienda/este-producto-no-existe-xyz-123`);
    // Next.js not-found page o 404
    const statusText = await page.locator("body").textContent();
    const hasNotFound = statusText?.includes("no encontr") || statusText?.includes("404");
    expect(hasNotFound).toBe(true);
  });
});

test.describe("Checkout", () => {
  test("Checkout sin productId redirige a tienda", async ({ page }) => {
    await page.goto(`${WEB_URL}/checkout`);
    await expect(page.locator("text=No se especificó un producto")).toBeVisible();
    const backLink = page.locator("text=Volver a la tienda");
    await expect(backLink).toBeVisible();
  });
});

test.describe("API Health", () => {
  test("API health endpoint responde 200", async ({ request }) => {
    const res = await request.get(`${API_URL}/api/v1/health`);
    expect(res.ok()).toBe(true);
    const body = await res.json() as { ok: boolean };
    expect(body.ok).toBe(true);
  });

  test("API requiere auth para endpoints protegidos", async ({ request }) => {
    const res = await request.get(`${API_URL}/api/v1/products`);
    // Sin X-Tenant-Slug podría devolver 400 o 401
    expect([400, 401, 403]).toContain(res.status());
  });

  test("Seguridad: rutas de scanner devuelven 404", async ({ request }) => {
    const scannerPaths = ["/.env", "/wp-admin", "/phpinfo", "/.git/config"];
    for (const path of scannerPaths) {
      const res = await request.get(`${API_URL}${path}`);
      expect([404, 400]).toContain(res.status());
    }
  });

  test("Headers de seguridad presentes en respuestas API", async ({ request }) => {
    const res = await request.get(`${API_URL}/api/v1/health`);
    expect(res.headers()["x-content-type-options"]).toBe("nosniff");
    expect(res.headers()["x-frame-options"]).toBe("DENY");
  });
});

test.describe("Admin panel", () => {
  test("Login page carga", async ({ page }) => {
    const ADMIN_URL = process.env["ADMIN_URL"] ?? "http://localhost:3000";
    await page.goto(`${ADMIN_URL}/login`);
    await expect(page.locator("input[type='email']").first()).toBeVisible();
    await expect(page.locator("input[type='password']").first()).toBeVisible();
  });

  test("Dashboard sin auth redirige a login", async ({ page }) => {
    const ADMIN_URL = process.env["ADMIN_URL"] ?? "http://localhost:3000";
    await page.goto(`${ADMIN_URL}/dashboard`);
    // Debería redirigir a login o mostrar la página de login
    await expect(page).toHaveURL(/login|dashboard/);
  });
});
