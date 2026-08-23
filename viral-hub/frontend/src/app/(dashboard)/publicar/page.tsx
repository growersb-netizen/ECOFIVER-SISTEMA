"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Send, Calendar, Film, Users, Layers, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { api, type Channel, type Group, type MediaAsset } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------
function CheckboxItem({
  label,
  subtitle,
  checked,
  onChange,
}: {
  label: string;
  subtitle?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 rounded-lg border p-3 cursor-pointer hover:bg-muted/50 transition-colors">
      <input
        type="checkbox"
        className="h-4 w-4 rounded"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <div>
        <p className="text-sm font-medium leading-none">{label}</p>
        {subtitle && <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>}
      </div>
    </label>
  );
}

function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="bg-card border rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center justify-between p-4 text-left"
        onClick={() => setOpen(!open)}
      >
        <div className="flex items-center gap-2 font-medium text-sm">
          <Icon className="h-4 w-4" />
          {title}
        </div>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
      {open && <div className="px-4 pb-4 space-y-3">{children}</div>}
    </div>
  );
}

// -----------------------------------------------------------------------
// Page
// -----------------------------------------------------------------------
export default function PublicarPage() {
  const router = useRouter();
  const { workspace } = useAuthStore();

  const [channels, setChannels] = useState<Channel[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [assets, setAssets] = useState<MediaAsset[]>([]);

  const [selectedChannels, setSelectedChannels] = useState<Set<number>>(new Set());
  const [selectedGroups, setSelectedGroups] = useState<Set<number>>(new Set());
  const [selectedAsset, setSelectedAsset] = useState<number | null>(null);

  const [caption, setCaption] = useState("");
  const [perPlatformCaptions, setPerPlatformCaptions] = useState<Record<string, string>>({});
  const [scheduledAt, setScheduledAt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!workspace) return;
    Promise.all([
      api.channels.list(workspace.id),
      api.groups.list(workspace.id),
      api.media.list(workspace.id),
    ]).then(([ch, gr, med]) => {
      setChannels(ch.channels);
      setGroups(gr.groups);
      setAssets(med.assets);
    });
  }, [workspace]);

  const toggleChannel = (id: number, on: boolean) =>
    setSelectedChannels((s) => { const n = new Set(s); on ? n.add(id) : n.delete(id); return n; });

  const toggleGroup = (id: number, on: boolean) =>
    setSelectedGroups((s) => { const n = new Set(s); on ? n.add(id) : n.delete(id); return n; });

  const totalTargets = selectedChannels.size + selectedGroups.size;
  const selectedAssetObj = assets.find((a) => a.id === selectedAsset);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!workspace) return;
    if (totalTargets === 0) { setError("Seleccioná al menos un canal o grupo"); return; }
    if (!caption.trim()) { setError("Escribí una descripción"); return; }
    setError("");
    setSubmitting(true);
    try {
      await api.publications.create(workspace.id, {
        caption,
        per_platform_captions: Object.keys(perPlatformCaptions).length > 0 ? perPlatformCaptions : undefined,
        asset_id: selectedAsset ?? undefined,
        channel_ids: selectedChannels.size > 0 ? [...selectedChannels] : undefined,
        group_ids: selectedGroups.size > 0 ? [...selectedGroups] : undefined,
        scheduled_at: scheduledAt || undefined,
      });
      router.push("/cola");
    } catch (err: unknown) {
      setError((err as Error).message ?? "Error al crear publicación");
    } finally {
      setSubmitting(false);
    }
  };

  const platforms = [...new Set(channels.filter((c) => selectedChannels.has(c.id)).map((c) => c.platform))];

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Publicar contenido</h1>
        <p className="text-muted-foreground">Distribuí a múltiples canales de una sola vez</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Archivo */}
        <Section title="Archivo (opcional)" icon={Film}>
          {assets.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No tenés archivos en la biblioteca.{" "}
              <a href="/biblioteca" className="text-primary hover:underline">Subí uno primero</a>.
            </p>
          ) : (
            <div className="grid grid-cols-3 gap-2 max-h-48 overflow-y-auto">
              {assets.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => setSelectedAsset(selectedAsset === a.id ? null : a.id)}
                  className={`aspect-video rounded-lg border-2 overflow-hidden text-xs transition-colors ${
                    selectedAsset === a.id ? "border-primary" : "border-transparent"
                  }`}
                >
                  {a.thumbnail_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={a.thumbnail_url} alt={a.original_filename} className="w-full h-full object-cover" />
                  ) : (
                    <div className="w-full h-full bg-muted flex items-center justify-center p-1 text-center text-muted-foreground">
                      {a.original_filename.slice(0, 20)}
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}
          {selectedAssetObj && (
            <p className="text-xs text-muted-foreground">✅ Seleccionado: {selectedAssetObj.original_filename}</p>
          )}
        </Section>

        {/* Descripción global */}
        <Section title="Descripción" icon={Send}>
          <div className="space-y-1.5">
            <Label htmlFor="caption">Descripción general</Label>
            <textarea
              id="caption"
              value={caption}
              onChange={(e) => setCaption(e.target.value)}
              rows={4}
              placeholder="Escribí la descripción para tus publicaciones…"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring resize-none"
            />
          </div>

          {/* Captions por plataforma (si hay canales seleccionados de distintas plataformas) */}
          {platforms.length > 1 && (
            <div className="space-y-2 pt-2">
              <p className="text-xs text-muted-foreground font-medium">
                Personalizar por plataforma (opcional — deja vacío para usar la descripción general):
              </p>
              {platforms.map((p) => (
                <div key={p} className="space-y-1">
                  <Label className="text-xs capitalize">{p}</Label>
                  <textarea
                    rows={2}
                    placeholder={`Caption específico para ${p}…`}
                    value={perPlatformCaptions[p] ?? ""}
                    onChange={(e) =>
                      setPerPlatformCaptions((prev) => ({ ...prev, [p]: e.target.value }))
                    }
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring resize-none"
                  />
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* Canales */}
        <Section title={`Canales individuales (${selectedChannels.size} seleccionados)`} icon={Users}>
          {channels.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Sin canales conectados.{" "}
              <a href="/canales" className="text-primary hover:underline">Conectá uno</a>.
            </p>
          ) : (
            <div className="space-y-2">
              {channels.map((c) => (
                <CheckboxItem
                  key={c.id}
                  label={c.alias}
                  subtitle={`${c.platform}${c.remote_username ? ` · @${c.remote_username}` : ""}`}
                  checked={selectedChannels.has(c.id)}
                  onChange={(v) => toggleChannel(c.id, v)}
                />
              ))}
            </div>
          )}
        </Section>

        {/* Grupos */}
        <Section title={`Grupos (${selectedGroups.size} seleccionados)`} icon={Layers}>
          {groups.length === 0 ? (
            <p className="text-xs text-muted-foreground">Sin grupos creados.</p>
          ) : (
            <div className="space-y-2">
              {groups.map((g) => (
                <CheckboxItem
                  key={g.id}
                  label={g.name}
                  checked={selectedGroups.has(g.id)}
                  onChange={(v) => toggleGroup(g.id, v)}
                />
              ))}
            </div>
          )}
        </Section>

        {/* Programar */}
        <Section title="Programar (opcional)" icon={Calendar}>
          <div className="space-y-1.5">
            <Label htmlFor="scheduled_at">Fecha y hora (dejá vacío para publicar ahora)</Label>
            <Input
              id="scheduled_at"
              type="datetime-local"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
            />
          </div>
        </Section>

        {error && (
          <div className="bg-destructive/10 text-destructive text-sm rounded-md p-3 border border-destructive/20">
            {error}
          </div>
        )}

        <Button
          type="submit"
          className="w-full"
          disabled={submitting || totalTargets === 0}
        >
          {submitting ? (
            <><Loader2 className="h-4 w-4 animate-spin mr-2" />Enviando a la cola…</>
          ) : scheduledAt ? (
            <><Calendar className="h-4 w-4 mr-2" />Programar publicación</>
          ) : (
            <><Send className="h-4 w-4 mr-2" />Publicar ahora ({totalTargets} destinos)</>
          )}
        </Button>
      </form>
    </div>
  );
}
