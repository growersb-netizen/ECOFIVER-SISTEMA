"use client";
/**
 * Detalle / edición de producto — gestión de archivos y descarga.
 * GET /api/v1/products/:id        → carga datos
 * POST /api/v1/products/:id/files → asocia un archivo (URL o clave R2)
 * GET /api/v1/products/:id/download → genera URL presignada y descarga
 */
import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import { AdminLayout } from "@/components/AdminLayout";

const API_URL = process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:3001";
const NEON = "#00FF87";
const CYAN = "#00F5FF";
const PINK = "#FF2D9C";
const YELLOW = "#FFE234";

const STATUS_COLORS: Record<string, string> = {
  DRAFT: "#4A5070", AI_GENERATED: CYAN, EDITING: YELLOW,
  PROFESSIONAL_REVIEW: YELLOW, APPROVED: "#7C4DFF",
  PUBLISHED: NEON, PAUSED: "#FF9800", ARCHIVED: "#3A3F55",
};

interface ProductFile {
  id: string;
  name: string;
  fileType: string;
  storageKey: string;
  mimeType?: string;
  sizeBytes?: number;
  isPrimary: boolean;
  isCover: boolean;
  sortOrder: number;
  createdAt: string;
}

interface Product {
  id: string;
  sku: string;
  name: string;
  description?: string;
  status: string;
  productType: string;
  level?: string;
  durationWeeks?: number;
  objective?: string;
  coverImageUrl?: string;
  createdAt: string;
  updatedAt: string;
  category?: { id: string; name: string };
  prices?: Array<{ id: string; basePrice: number; currency: string; channel: string }>;
  files?: ProductFile[];
  _count?: { files: number; contentPacks: number };
}

// ── utilidades ─────────────────────────────────────────────────────
function Badge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? "#4A5070";
  return (
    <span style={{
      display: "inline-block", padding: "3px 10px", borderRadius: 6,
      fontSize: "0.75rem", fontWeight: 700, letterSpacing: "0.05em",
      background: `${color}22`, color, border: `1px solid ${color}44`,
    }}>
      {status}
    </span>
  );
}

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "#0D0F1A", border: "1px solid #1A1F35", borderRadius: 12, padding: "1.25rem", marginBottom: "1.25rem" }}>
      <h2 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "0.95rem", color: "#6B7494", letterSpacing: "0.1em", textTransform: "uppercase", margin: "0 0 1rem" }}>
        {title}
      </h2>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: "flex", gap: "1rem", marginBottom: "0.6rem", fontSize: "0.85rem" }}>
      <span style={{ color: "#4A5070", minWidth: 130, flexShrink: 0 }}>{label}</span>
      <span style={{ color: "#E8EDFF" }}>{value ?? "—"}</span>
    </div>
  );
}

// ── página principal ───────────────────────────────────────────────
export default function ProductDetailPage() {
  const params = useParams<{ id: string }>();
  const productId = params?.id ?? "";

  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" } | null>(null);

  // Formulario agregar archivo
  const [fileUrl, setFileUrl] = useState("");
  const [fileName, setFileName] = useState("");
  const [fileType, setFileType] = useState("zip");
  const [isPrimary, setIsPrimary] = useState(true);
  const [addingFile, setAddingFile] = useState(false);

  // Estado de descarga
  const [downloadState, setDownloadState] = useState<"idle" | "loading" | "error">("idle");
  const [downloadError, setDownloadError] = useState("");

  const token = typeof window !== "undefined" ? localStorage.getItem("fitness_access_token") : null;
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const load = useCallback(async () => {
    if (!productId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/products/${productId}`, { headers });
      if (!res.ok) throw new Error("No encontrado");
      const data = await res.json() as { data: Product };
      setProduct(data.data);
    } catch {
      showToast("Error cargando producto", "err");
    } finally {
      setLoading(false);
    }
  }, [productId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { load(); }, [load]);

  // ── Agregar / actualizar archivo ──────────────────────────────────
  const handleAddFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fileUrl.trim()) { showToast("Ingresá la URL o clave del archivo", "err"); return; }
    setAddingFile(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/products/${productId}/files`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          storageKey: fileUrl.trim(),
          filename: fileName.trim() || `${product?.sku ?? productId}.${fileType}`,
          mimeType: fileType === "zip" ? "application/zip"
            : fileType === "pdf" ? "application/pdf"
            : fileType === "mp4" ? "video/mp4"
            : undefined,
          isPrimary,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: "Error" })) as { error: string };
        throw new Error(err.error);
      }
      showToast("Archivo guardado ✓");
      setFileUrl("");
      setFileName("");
      load();
    } catch (err) {
      showToast((err as Error).message ?? "Error al guardar", "err");
    } finally {
      setAddingFile(false);
    }
  };

  // ── Descargar archivo principal ───────────────────────────────────
  const handleDownload = async (fileId?: string) => {
    setDownloadState("loading");
    setDownloadError("");
    try {
      // Si el archivo tiene URL directa, abrirla
      const files = product?.files ?? [];
      const file = fileId ? files.find(f => f.id === fileId) : files.find(f => f.isPrimary) ?? files[0];

      if (file?.storageKey.startsWith("http://") || file?.storageKey.startsWith("https://")) {
        window.open(file.storageKey, "_blank");
        setDownloadState("idle");
        return;
      }

      // Llamar al endpoint de descarga (genera URL presignada)
      const url = `${API_URL}/api/v1/products/${productId}/download`;
      const res = await fetch(url, { headers, redirect: "follow" });

      if (res.ok && res.url && res.url !== url) {
        // Se siguió un redirect: abrir la URL final
        window.open(res.url, "_blank");
        setDownloadState("idle");
        return;
      }

      if (res.status === 422) {
        const data = await res.json() as { message: string; storageKey: string };
        setDownloadError(data.message ?? "R2 no configurado");
        setDownloadState("error");
        return;
      }

      // Intentar abrir el endpoint directamente (el redirect lo maneja el browser)
      window.open(url, "_blank");
      setDownloadState("idle");
    } catch {
      setDownloadError("Error al generar el enlace de descarga");
      setDownloadState("error");
    }
  };

  // ── render ────────────────────────────────────────────────────────
  const inputStyle = {
    background: "#070810", border: "1px solid #1A1F35", borderRadius: 8,
    color: "#E8EDFF", padding: "0.5rem 0.75rem", fontSize: "0.85rem",
    outline: "none", width: "100%", boxSizing: "border-box" as const,
  };

  if (loading) {
    return (
      <AdminLayout>
        <div style={{ padding: "4rem", textAlign: "center", color: "#4A5070" }}>Cargando…</div>
      </AdminLayout>
    );
  }

  if (!product) {
    return (
      <AdminLayout>
        <div style={{ padding: "4rem", textAlign: "center", color: PINK }}>
          Producto no encontrado.{" "}
          <a href="/dashboard/products" style={{ color: NEON }}>← Volver</a>
        </div>
      </AdminLayout>
    );
  }

  const primaryFile = product.files?.find(f => f.isPrimary) ?? product.files?.[0];
  const hasDownloadableFile = !!primaryFile && (
    primaryFile.storageKey.startsWith("http") || true /* R2 or local handled by API */
  );

  return (
    <AdminLayout>
      {/* Toast */}
      {toast && (
        <div style={{
          position: "fixed", top: 70, right: 24, zIndex: 9999,
          padding: "0.75rem 1.25rem", borderRadius: 10,
          background: toast.type === "ok" ? `${NEON}22` : `${PINK}22`,
          border: `1px solid ${toast.type === "ok" ? NEON : PINK}`,
          color: toast.type === "ok" ? NEON : PINK, fontSize: "0.85rem",
        }}>
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: "1rem", marginBottom: "1.5rem", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <a href="/dashboard/products" style={{ color: "#4A5070", fontSize: "0.8rem", textDecoration: "none", display: "inline-block", marginBottom: "0.4rem" }}>
            ← Volver a Productos
          </a>
          <h1 style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.75rem", fontWeight: 700, margin: 0, color: "#E8EDFF" }}>
            {product.name}
          </h1>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <Badge status={product.status} />
            <span style={{ color: "#4A5070", fontSize: "0.75rem", fontFamily: "monospace" }}>{product.sku}</span>
            <span style={{ color: "#4A5070", fontSize: "0.75rem" }}>{product.productType}</span>
          </div>
        </div>

        {/* Botón de descarga principal */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "0.5rem" }}>
          <button
            onClick={() => handleDownload()}
            disabled={downloadState === "loading" || !primaryFile}
            style={{
              padding: "0.65rem 1.5rem",
              background: primaryFile ? NEON : "#2A2F45",
              border: "none", borderRadius: 10,
              color: primaryFile ? "#06080F" : "#4A5070",
              fontWeight: 700, fontSize: "0.9rem",
              cursor: primaryFile ? "pointer" : "not-allowed",
              display: "flex", alignItems: "center", gap: "0.5rem",
            }}
          >
            {downloadState === "loading" ? "⏳ Generando…" : "⬇️ Descargar ZIP"}
          </button>
          {!primaryFile && (
            <span style={{ fontSize: "0.72rem", color: "#4A5070" }}>Sin archivos — agregá uno abajo</span>
          )}
          {downloadState === "error" && (
            <div style={{ maxWidth: 320, padding: "0.6rem 0.85rem", background: `${PINK}15`, border: `1px solid ${PINK}44`, borderRadius: 8, fontSize: "0.78rem", color: PINK }}>
              {downloadError}
            </div>
          )}
        </div>
      </div>

      {/* Info básica */}
      <SectionCard title="Información del producto">
        <Row label="Nombre" value={product.name} />
        <Row label="SKU" value={<span style={{ fontFamily: "monospace" }}>{product.sku}</span>} />
        <Row label="Tipo" value={product.productType} />
        <Row label="Categoría" value={product.category?.name} />
        <Row label="Nivel" value={product.level} />
        <Row label="Duración" value={product.durationWeeks ? `${product.durationWeeks} semanas` : undefined} />
        <Row label="Objetivo" value={product.objective} />
        {product.description && (
          <div style={{ marginTop: "0.75rem", padding: "0.75rem", background: "#070810", borderRadius: 8, fontSize: "0.82rem", color: "#A0AAC8", lineHeight: 1.6 }}>
            {product.description}
          </div>
        )}
      </SectionCard>

      {/* Precios */}
      {product.prices && product.prices.length > 0 && (
        <SectionCard title="Precios">
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            {product.prices.map(price => (
              <div key={price.id} style={{ padding: "0.75rem 1.25rem", background: "#070810", borderRadius: 10, border: `1px solid ${CYAN}22` }}>
                <div style={{ color: CYAN, fontFamily: "'Barlow Condensed', sans-serif", fontSize: "1.5rem", fontWeight: 700 }}>
                  ${Number(price.basePrice).toLocaleString("es-AR")} {price.currency}
                </div>
                <div style={{ color: "#4A5070", fontSize: "0.72rem", marginTop: 2 }}>{price.channel}</div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {/* Archivos */}
      <SectionCard title={`Archivos (${product.files?.length ?? 0})`}>
        {product.files && product.files.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", marginBottom: "1.25rem" }}>
            {product.files.map(file => {
              const isUrl = file.storageKey.startsWith("http");
              return (
                <div key={file.id} style={{
                  display: "flex", alignItems: "center", gap: "0.75rem",
                  padding: "0.75rem 1rem", background: "#070810",
                  borderRadius: 10, border: `1px solid ${file.isPrimary ? NEON + "44" : "#1A1F35"}`,
                  flexWrap: "wrap",
                }}>
                  {/* icono tipo */}
                  <span style={{ fontSize: "1.25rem", flexShrink: 0 }}>
                    {file.fileType === "zip" ? "🗜️"
                      : file.fileType === "pdf" ? "📄"
                      : file.fileType === "mp4" || file.fileType === "video" ? "🎬"
                      : file.fileType === "image" || file.isCover ? "🖼️"
                      : "📁"}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: "#E8EDFF", fontSize: "0.85rem", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {file.name}
                      {file.isPrimary && (
                        <span style={{ marginLeft: 8, padding: "1px 6px", borderRadius: 4, background: `${NEON}22`, color: NEON, fontSize: "0.65rem", fontWeight: 700 }}>PRINCIPAL</span>
                      )}
                    </div>
                    <div style={{ color: "#4A5070", fontSize: "0.72rem", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {isUrl ? (
                        <a href={file.storageKey} target="_blank" rel="noreferrer" style={{ color: CYAN }}>
                          {file.storageKey.length > 60 ? file.storageKey.slice(0, 60) + "…" : file.storageKey}
                        </a>
                      ) : (
                        <span style={{ fontFamily: "monospace" }}>{file.storageKey}</span>
                      )}
                    </div>
                  </div>
                  {file.sizeBytes && (
                    <span style={{ color: "#4A5070", fontSize: "0.72rem", flexShrink: 0 }}>
                      {(Number(file.sizeBytes) / 1024 / 1024).toFixed(1)} MB
                    </span>
                  )}
                  <button
                    onClick={() => handleDownload(file.id)}
                    style={{
                      padding: "4px 12px", background: `${NEON}15`,
                      border: `1px solid ${NEON}44`, borderRadius: 6,
                      color: NEON, fontSize: "0.75rem", cursor: "pointer", flexShrink: 0,
                    }}
                  >
                    ⬇️ Descargar
                  </button>
                </div>
              );
            })}
          </div>
        ) : (
          <p style={{ color: "#4A5070", fontSize: "0.85rem", marginBottom: "1rem" }}>
            Sin archivos. Agregá el ZIP con la guía y materiales del producto.
          </p>
        )}

        {/* Formulario agregar archivo */}
        <div style={{ background: "#070810", border: "1px dashed #2A2F45", borderRadius: 10, padding: "1rem" }}>
          <h3 style={{ color: "#6B7494", fontSize: "0.8rem", letterSpacing: "0.05em", textTransform: "uppercase", margin: "0 0 0.75rem" }}>
            {product.files?.some(f => f.isPrimary) ? "Actualizar / agregar archivo" : "Agregar archivo principal"}
          </h3>
          <form onSubmit={handleAddFile} style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
            <div>
              <label style={{ color: "#6B7494", fontSize: "0.75rem", display: "block", marginBottom: "0.3rem" }}>
                URL o clave R2 del archivo *
              </label>
              <input
                style={inputStyle}
                type="text"
                placeholder="https://drive.google.com/… ó products/abc123/guia.zip"
                value={fileUrl}
                onChange={e => setFileUrl(e.target.value)}
                required
              />
              <p style={{ color: "#3A3F55", fontSize: "0.7rem", margin: "0.25rem 0 0" }}>
                Usá una URL directa de descarga (Google Drive, Dropbox, S3) o la clave R2 cuando esté configurado.
              </p>
            </div>
            <div style={{ display: "flex", gap: "0.65rem", flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 160 }}>
                <label style={{ color: "#6B7494", fontSize: "0.75rem", display: "block", marginBottom: "0.3rem" }}>Nombre del archivo</label>
                <input style={inputStyle} type="text" placeholder={`${product.sku}.zip`} value={fileName} onChange={e => setFileName(e.target.value)} />
              </div>
              <div style={{ minWidth: 120 }}>
                <label style={{ color: "#6B7494", fontSize: "0.75rem", display: "block", marginBottom: "0.3rem" }}>Tipo</label>
                <select style={{ ...inputStyle, width: "auto" }} value={fileType} onChange={e => setFileType(e.target.value)}>
                  <option value="zip">ZIP (guía completa)</option>
                  <option value="pdf">PDF</option>
                  <option value="mp4">Video MP4</option>
                  <option value="image">Imagen</option>
                </select>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", paddingTop: "1.5rem" }}>
                <input type="checkbox" id="isPrimary" checked={isPrimary} onChange={e => setIsPrimary(e.target.checked)} style={{ accentColor: NEON }} />
                <label htmlFor="isPrimary" style={{ color: "#6B7494", fontSize: "0.8rem", cursor: "pointer" }}>Archivo principal</label>
              </div>
            </div>
            <button
              type="submit"
              disabled={addingFile}
              style={{
                alignSelf: "flex-start", padding: "0.5rem 1.25rem",
                background: addingFile ? "#2A2F45" : NEON,
                border: "none", borderRadius: 8,
                color: addingFile ? "#4A5070" : "#06080F",
                fontWeight: 700, fontSize: "0.85rem",
                cursor: addingFile ? "not-allowed" : "pointer",
              }}
            >
              {addingFile ? "Guardando…" : "💾 Guardar archivo"}
            </button>
          </form>
        </div>
      </SectionCard>

      {/* Meta */}
      <div style={{ color: "#3A3F55", fontSize: "0.72rem", marginTop: "0.5rem" }}>
        Creado: {new Date(product.createdAt).toLocaleString("es-AR")} ·
        Actualizado: {new Date(product.updatedAt).toLocaleString("es-AR")} ·
        ID: <span style={{ fontFamily: "monospace" }}>{product.id}</span>
      </div>
    </AdminLayout>
  );
}
