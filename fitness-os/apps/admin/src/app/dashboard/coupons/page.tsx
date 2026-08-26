"use client";
/**
 * /dashboard/coupons — Gestión de cupones de descuento.
 * CRUD completo: crear, editar, activar/desactivar.
 */
import { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";

const NEON    = "#00FF87";
const CYAN    = "#00F5FF";
const CEREZA  = "#DE3163";
const CEREZA2 = "#B82050";

const API_URL     = process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:3001";
const TENANT_SLUG = process.env["NEXT_PUBLIC_TENANT_SLUG"] ?? "";

// ── Types ─────────────────────────────────────────────────────────────
interface Coupon {
  id: string;
  code: string;
  description?: string;
  discountPct?: number;
  discountAmt?: number;
  maxUses?: number;
  validUntil?: string;
  active: boolean;
  createdAt: string;
  _count?: { orders: number };
}

// ── Shared styles ─────────────────────────────────────────────────────
const inputStyle: React.CSSProperties = {
  width: "100%", background: "#0A0C18",
  border: "1px solid #2A2F45", borderRadius: 8,
  padding: "0.65rem 1rem", color: "#E8EDFF",
  fontSize: "0.9rem", outline: "none", boxSizing: "border-box",
};

function NavItem({ label, href, active }: { label: string; href: string; active?: boolean }) {
  return (
    <a href={href} style={{
      display: "block", padding: "0.6rem 1rem", borderRadius: 8,
      color: active ? NEON : "#A0AAC8",
      background: active ? "rgba(0,255,135,0.1)" : "transparent",
      textDecoration: "none", fontSize: "0.9rem",
      fontWeight: active ? 600 : 400,
      borderLeft: active ? `2px solid ${NEON}` : "2px solid transparent",
    }}>
      {label}
    </a>
  );
}

// ── Create/Edit Modal ─────────────────────────────────────────────────
function CouponModal({
  coupon,
  onClose,
  onSaved,
  token,
}: {
  coupon: Coupon | null;
  onClose: () => void;
  onSaved: () => void;
  token: string;
}) {
  const [code, setCode] = useState(coupon?.code ?? "");
  const [description, setDescription] = useState(coupon?.description ?? "");
  const [discountType, setDiscountType] = useState<"pct" | "amt">(coupon?.discountAmt ? "amt" : "pct");
  const [discountValue, setDiscountValue] = useState(
    String(coupon?.discountPct ?? coupon?.discountAmt ?? "")
  );
  const [maxUses, setMaxUses] = useState(String(coupon?.maxUses ?? ""));
  const [validUntil, setValidUntil] = useState(
    coupon?.validUntil ? coupon.validUntil.slice(0, 16) : ""
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEdit = !!coupon;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);

    const headers = {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
      "X-Tenant-Slug": TENANT_SLUG,
    };

    const body = {
      ...(isEdit ? {} : { code: code.toUpperCase().trim() }),
      description: description.trim() || undefined,
      discountPct: discountType === "pct" ? Number(discountValue) : undefined,
      discountAmt: discountType === "amt" ? Number(discountValue) : undefined,
      maxUses: maxUses ? Number(maxUses) : undefined,
      validUntil: validUntil ? new Date(validUntil).toISOString() : undefined,
    };

    const url = isEdit
      ? `${API_URL}/api/v1/admin/coupons/${coupon.id}`
      : `${API_URL}/api/v1/admin/coupons`;
    const method = isEdit ? "PATCH" : "POST";

    try {
      const res = await fetch(url, { method, headers, body: JSON.stringify(body) });
      const data = await res.json() as { error?: string };
      if (!res.ok) {
        setError(data.error ?? "Error guardando cupón");
        setSaving(false);
        return;
      }
      onSaved();
    } catch (err) {
      setError(String(err));
      setSaving(false);
    }
  }

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 200,
      background: "rgba(0,0,0,0.75)", backdropFilter: "blur(4px)",
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: "1rem",
    }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{
        background: "#0D0F1A", border: "1px solid #1E2240",
        borderRadius: 16, padding: "2rem",
        width: "100%", maxWidth: 480,
      }}>
        <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.5rem", fontWeight: 700, color: "#E8EDFF", margin: "0 0 1.5rem" }}>
          {isEdit ? "EDITAR CUPÓN" : "CREAR CUPÓN"}
        </h2>

        <form onSubmit={handleSubmit}>
          {!isEdit && (
            <div style={{ marginBottom: "1rem" }}>
              <label style={{ display: "block", fontSize: "0.75rem", color: "#6B7494", letterSpacing: "0.08em", marginBottom: 6 }}>
                CÓDIGO *
              </label>
              <input
                value={code}
                onChange={e => setCode(e.target.value.toUpperCase())}
                placeholder="VERANO25"
                required
                style={inputStyle}
              />
              <p style={{ color: "#3A3F55", fontSize: "0.72rem", margin: "4px 0 0" }}>
                Solo letras mayúsculas y números. Sin espacios.
              </p>
            </div>
          )}

          <div style={{ marginBottom: "1rem" }}>
            <label style={{ display: "block", fontSize: "0.75rem", color: "#6B7494", letterSpacing: "0.08em", marginBottom: 6 }}>
              DESCRIPCIÓN (opcional)
            </label>
            <input
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Descuento de temporada"
              style={inputStyle}
            />
          </div>

          <div style={{ marginBottom: "1rem" }}>
            <label style={{ display: "block", fontSize: "0.75rem", color: "#6B7494", letterSpacing: "0.08em", marginBottom: 6 }}>
              TIPO DE DESCUENTO *
            </label>
            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem" }}>
              {[
                { value: "pct", label: "% Porcentaje" },
                { value: "amt", label: "$ Monto fijo" },
              ].map(opt => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setDiscountType(opt.value as "pct" | "amt")}
                  style={{
                    flex: 1, padding: "0.55rem",
                    background: discountType === opt.value ? `${CEREZA}22` : "#0A0C18",
                    border: `1px solid ${discountType === opt.value ? CEREZA : "#2A2F45"}`,
                    borderRadius: 8, color: discountType === opt.value ? CEREZA : "#6B7494",
                    fontWeight: 700, fontSize: "0.85rem", cursor: "pointer",
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <input
              type="number"
              value={discountValue}
              onChange={e => setDiscountValue(e.target.value)}
              placeholder={discountType === "pct" ? "25 (= 25%)" : "5000 (= $5000)"}
              required
              min={1}
              max={discountType === "pct" ? 100 : undefined}
              style={inputStyle}
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
            <div>
              <label style={{ display: "block", fontSize: "0.75rem", color: "#6B7494", letterSpacing: "0.08em", marginBottom: 6 }}>
                USOS MÁXIMOS
              </label>
              <input
                type="number"
                value={maxUses}
                onChange={e => setMaxUses(e.target.value)}
                placeholder="Sin límite"
                min={1}
                style={inputStyle}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.75rem", color: "#6B7494", letterSpacing: "0.08em", marginBottom: 6 }}>
                VÁLIDO HASTA
              </label>
              <input
                type="datetime-local"
                value={validUntil}
                onChange={e => setValidUntil(e.target.value)}
                style={inputStyle}
              />
            </div>
          </div>

          {error && (
            <div style={{ padding: "0.75rem 1rem", background: `${CEREZA}15`, border: `1px solid ${CEREZA}33`, borderRadius: 8, color: CEREZA, fontSize: "0.85rem", marginBottom: "1rem" }}>
              {error}
            </div>
          )}

          <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end", marginTop: "1.5rem" }}>
            <button type="button" onClick={onClose} style={{
              padding: "0.65rem 1.25rem",
              background: "transparent", border: "1px solid #2A2F45",
              borderRadius: 8, color: "#6B7494",
              fontSize: "0.88rem", cursor: "pointer",
            }}>
              Cancelar
            </button>
            <button type="submit" disabled={saving} style={{
              padding: "0.65rem 1.5rem",
              background: saving ? "#1A1F35" : `linear-gradient(135deg, ${CEREZA}, ${CEREZA2})`,
              border: "none", borderRadius: 8, color: saving ? "#4A5070" : "#fff",
              fontWeight: 800, fontSize: "0.88rem", cursor: saving ? "not-allowed" : "pointer",
            }}>
              {saving ? "Guardando..." : isEdit ? "Guardar cambios" : "Crear cupón"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────
export default function CouponsPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingCoupon, setEditingCoupon] = useState<Coupon | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const getHeaders = (t: string) => ({
    "Content-Type": "application/json",
    "Authorization": `Bearer ${t}`,
    "X-Tenant-Slug": TENANT_SLUG,
  });

  async function loadCoupons(t: string) {
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/coupons`, { headers: getHeaders(t) });
      if (!res.ok) { router.push("/login"); return; }
      const data = await res.json() as { data: Coupon[] };
      setCoupons(data.data ?? []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }

  useEffect(() => {
    const t = localStorage.getItem("fitness_access_token");
    if (!t) { router.push("/login"); return; }
    setToken(t);
    loadCoupons(t);
  }, [router]);

  async function toggleActive(coupon: Coupon) {
    const res = await fetch(`${API_URL}/api/v1/admin/coupons/${coupon.id}`, {
      method: "PATCH",
      headers: getHeaders(token),
      body: JSON.stringify({ active: !coupon.active }),
    });
    if (res.ok) {
      setCoupons(prev => prev.map(c => c.id === coupon.id ? { ...c, active: !c.active } : c));
      setActionMsg(`Cupón "${coupon.code}" ${!coupon.active ? "activado" : "desactivado"}`);
      setTimeout(() => setActionMsg(null), 3000);
    }
  }

  function openCreate() { setEditingCoupon(null); setShowModal(true); }
  function openEdit(c: Coupon) { setEditingCoupon(c); setShowModal(true); }
  function closeModal() { setShowModal(false); setEditingCoupon(null); }
  function handleSaved() {
    closeModal();
    loadCoupons(token);
    setActionMsg("Cupón guardado correctamente");
    setTimeout(() => setActionMsg(null), 3000);
  }

  const formatDate = (iso?: string) => {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("es-AR", { day: "2-digit", month: "short", year: "numeric" });
  };

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", background: "#07080F", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ color: NEON, fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.5rem", letterSpacing: "0.1em" }}>CARGANDO...</p>
      </div>
    );
  }

  const activeCoupons = coupons.filter(c => c.active);
  const inactiveCoupons = coupons.filter(c => !c.active);

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#07080F", color: "#E8EDFF", fontFamily: "'DM Sans', system-ui, sans-serif" }}>
      {/* Sidebar */}
      <aside style={{ width: 220, flexShrink: 0, background: "#0A0B14", borderRight: "1px solid #1E2240", display: "flex", flexDirection: "column", padding: "1.5rem 1rem", position: "sticky", top: 0, height: "100vh" }}>
        <div style={{ marginBottom: "2rem", paddingLeft: "0.5rem" }}>
          <p style={{ fontSize: "0.65rem", letterSpacing: "0.2em", color: CYAN, textTransform: "uppercase", marginBottom: "2px" }}>FITNESS BUSINESS OS</p>
          <p style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.1rem", fontWeight: 700, color: NEON, margin: 0 }}>PANEL ADMIN</p>
        </div>
        <nav style={{ flex: 1, display: "flex", flexDirection: "column", gap: "2px" }}>
          <NavItem label="📊 Dashboard" href="/dashboard" />
          <NavItem label="📦 Productos" href="/dashboard/products" />
          <NavItem label="🛒 Órdenes" href="/dashboard/orders" />
          <NavItem label="🎟 Cupones" href="/dashboard/coupons" active />
          <NavItem label="👥 CRM / Leads" href="/dashboard/crm" />
          <NavItem label="🤖 IA" href="/dashboard/ai" />
          <NavItem label="📱 Redes Sociales" href="/dashboard/social" />
          <NavItem label="🏪 MercadoLibre" href="/dashboard/mercadolibre" />
          <NavItem label="🔗 Afiliadas" href="/dashboard/affiliates" />
          <NavItem label="🏋️ Coaches" href="/dashboard/coaches" />
          <NavItem label="⚙️ Configuración" href="/dashboard/settings" />
        </nav>
        <div style={{ borderTop: "1px solid #1E2240", paddingTop: "1rem" }}>
          <button onClick={() => { localStorage.clear(); window.location.href = "/login"; }}
            style={{ fontSize: "0.75rem", color: "#4A5070", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
            Cerrar sesión →
          </button>
        </div>
      </aside>

      {/* Main */}
      <main style={{ flex: 1, padding: "2rem", overflowX: "auto" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: "2rem" }}>
          <div>
            <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "2.25rem", fontWeight: 800, color: "#E8EDFF", margin: 0 }}>
              CUPONES
            </h1>
            <p style={{ color: "#4A5070", fontSize: "0.85rem", marginTop: "4px" }}>
              {activeCoupons.length} activo{activeCoupons.length !== 1 ? "s" : ""} · {inactiveCoupons.length} inactivo{inactiveCoupons.length !== 1 ? "s" : ""}
            </p>
          </div>
          <button
            onClick={openCreate}
            style={{
              padding: "0.7rem 1.5rem",
              background: `linear-gradient(135deg, ${CEREZA}, ${CEREZA2})`,
              border: "none", borderRadius: 8, color: "#fff",
              fontWeight: 800, fontSize: "0.88rem", cursor: "pointer",
            }}
          >
            + Nuevo cupón
          </button>
        </div>

        {/* Toast message */}
        {actionMsg && (
          <div style={{
            padding: "0.75rem 1.25rem",
            background: `${NEON}12`, border: `1px solid ${NEON}33`,
            borderRadius: 8, color: NEON,
            fontSize: "0.88rem", marginBottom: "1.5rem",
          }}>
            ✓ {actionMsg}
          </div>
        )}

        {/* Coupon list */}
        {coupons.length === 0 ? (
          <div style={{
            padding: "4rem", textAlign: "center",
            background: "#0D0F1A", border: "1px solid #1A1F35",
            borderRadius: 12,
          }}>
            <p style={{ color: "#4A5070", fontSize: "1.1rem", marginBottom: "1rem" }}>
              No hay cupones creados todavía.
            </p>
            <button onClick={openCreate} style={{
              padding: "0.65rem 1.5rem",
              background: `linear-gradient(135deg, ${CEREZA}, ${CEREZA2})`,
              border: "none", borderRadius: 8, color: "#fff",
              fontWeight: 700, cursor: "pointer",
            }}>
              Crear el primer cupón
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {coupons.map(coupon => (
              <div key={coupon.id} style={{
                background: "#0D0F1A",
                border: `1px solid ${coupon.active ? "#1E2240" : "#151825"}`,
                borderRadius: 12,
                padding: "1.1rem 1.25rem",
                display: "flex", alignItems: "center", gap: "1rem",
                opacity: coupon.active ? 1 : 0.6,
              }}>
                {/* Código */}
                <div style={{ flex: "0 0 140px" }}>
                  <code style={{
                    fontFamily: "monospace",
                    fontWeight: 800,
                    fontSize: "1rem",
                    color: coupon.active ? CEREZA : "#4A5070",
                    letterSpacing: "0.05em",
                  }}>
                    {coupon.code}
                  </code>
                  <p style={{ margin: "2px 0 0", color: "#4A5070", fontSize: "0.75rem" }}>
                    {coupon._count?.orders ?? 0} uso{(coupon._count?.orders ?? 0) !== 1 ? "s" : ""}
                  </p>
                </div>

                {/* Descuento */}
                <div style={{ flex: "0 0 120px" }}>
                  <span style={{
                    fontFamily: "'Barlow Condensed', sans-serif",
                    fontSize: "1.3rem", fontWeight: 800,
                    color: coupon.active ? NEON : "#4A5070",
                  }}>
                    {coupon.discountPct ? `${coupon.discountPct}%` : `$${coupon.discountAmt?.toLocaleString("es-AR")}`}
                  </span>
                  <p style={{ margin: "2px 0 0", color: "#4A5070", fontSize: "0.72rem" }}>descuento</p>
                </div>

                {/* Descripción */}
                <div style={{ flex: 1 }}>
                  <p style={{ margin: 0, color: "#A0AAC8", fontSize: "0.88rem" }}>
                    {coupon.description ?? "—"}
                  </p>
                  <p style={{ margin: "2px 0 0", color: "#4A5070", fontSize: "0.73rem" }}>
                    {coupon.maxUses ? `Máx. ${coupon.maxUses} usos` : "Usos ilimitados"}
                    {coupon.validUntil ? ` · Hasta ${formatDate(coupon.validUntil)}` : " · Sin vencimiento"}
                  </p>
                </div>

                {/* Estado */}
                <div>
                  <span style={{
                    display: "inline-block",
                    padding: "2px 10px", borderRadius: 20,
                    fontSize: "0.72rem", fontWeight: 700,
                    background: coupon.active ? `${NEON}15` : "#151825",
                    color: coupon.active ? NEON : "#4A5070",
                    border: `1px solid ${coupon.active ? `${NEON}33` : "#1A1F35"}`,
                  }}>
                    {coupon.active ? "Activo" : "Inactivo"}
                  </span>
                </div>

                {/* Acciones */}
                <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
                  <button
                    onClick={() => openEdit(coupon)}
                    style={{
                      padding: "0.4rem 0.85rem",
                      background: "#1A1F35", border: "none",
                      borderRadius: 6, color: "#A0AAC8",
                      fontSize: "0.8rem", cursor: "pointer",
                    }}
                  >
                    Editar
                  </button>
                  <button
                    onClick={() => toggleActive(coupon)}
                    style={{
                      padding: "0.4rem 0.85rem",
                      background: coupon.active ? `${CEREZA}18` : `${NEON}10`,
                      border: `1px solid ${coupon.active ? `${CEREZA}33` : `${NEON}22`}`,
                      borderRadius: 6,
                      color: coupon.active ? CEREZA : NEON,
                      fontSize: "0.8rem", cursor: "pointer",
                      fontWeight: 600,
                    }}
                  >
                    {coupon.active ? "Desactivar" : "Activar"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Información de uso */}
        <div style={{
          marginTop: "2rem",
          background: "#0D0F1A", border: "1px solid #1A1F35",
          borderRadius: 12, padding: "1.25rem",
        }}>
          <h3 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1rem", fontWeight: 700, color: "#E8EDFF", margin: "0 0 0.75rem" }}>
            ℹ️ Cómo funcionan los cupones
          </h3>
          <ul style={{ margin: 0, paddingLeft: "1.25rem", color: "#6B7494", fontSize: "0.85rem", lineHeight: 1.7 }}>
            <li>El cliente ingresa el código en el checkout antes de pagar</li>
            <li>El descuento se aplica al total de la orden</li>
            <li><strong style={{ color: "#A0AAC8" }}>% Porcentaje:</strong> descuenta N% del total (ej: 25% → $5000 se convierte en $3750)</li>
            <li><strong style={{ color: "#A0AAC8" }}>$ Monto fijo:</strong> descuenta un importe exacto del total</li>
            <li>Al desactivar un cupón, las órdenes ya creadas con ese cupón mantienen su descuento</li>
          </ul>
        </div>
      </main>

      {/* Modal */}
      {showModal && (
        <CouponModal
          coupon={editingCoupon}
          onClose={closeModal}
          onSaved={handleSaved}
          token={token}
        />
      )}
    </div>
  );
}
