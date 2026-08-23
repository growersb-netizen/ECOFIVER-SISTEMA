"use client";

import { useEffect, useRef, useState } from "react";
import { Upload, Video, Image, Trash2, Film } from "lucide-react";
import { api, type MediaAsset } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

function formatBytes(b: number | undefined) {
  if (!b) return "—";
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}

function AssetCard({ asset, onArchive }: { asset: MediaAsset; onArchive: () => void }) {
  return (
    <div className="bg-card border rounded-xl overflow-hidden group">
      {/* Thumbnail */}
      <div className="aspect-video bg-muted flex items-center justify-center relative">
        {asset.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={asset.thumbnail_url}
            alt={asset.original_filename}
            className="w-full h-full object-cover"
          />
        ) : asset.media_type === "video" ? (
          <Film className="h-8 w-8 text-muted-foreground" />
        ) : (
          <Image className="h-8 w-8 text-muted-foreground" />
        )}
        <button
          onClick={onArchive}
          className="absolute top-2 right-2 bg-background/80 rounded-full p-1.5 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-destructive hover:text-destructive-foreground"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="p-3 space-y-1">
        <p className="text-sm font-medium truncate" title={asset.original_filename}>
          {asset.original_filename}
        </p>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>{formatBytes(asset.file_size)}</span>
          {asset.duration_seconds && (
            <>
              <span>·</span>
              <span>{Math.floor(asset.duration_seconds / 60)}:{String(asset.duration_seconds % 60).padStart(2, "0")}</span>
            </>
          )}
          <span>·</span>
          <Badge variant="secondary" className="text-xs py-0 px-1">
            {asset.media_type}
          </Badge>
        </div>
      </div>
    </div>
  );
}

export default function BibliotecaPage() {
  const { workspace } = useAuthStore();
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => {
    if (!workspace) return;
    api.media
      .list(workspace.id)
      .then((r) => setAssets(r.assets))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [workspace]);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !workspace) return;
    setUploading(true);
    setUploadMsg("Obteniendo URL de subida…");
    try {
      const { upload_url, asset_id, message } = await api.media.getUploadUrl(workspace.id, {
        filename: file.name,
        content_type: file.type,
        file_size: file.size,
      });

      if (!upload_url) {
        setUploadMsg(message ?? "Storage no configurado. Configurá R2 en el .env del backend.");
        return;
      }

      setUploadMsg("Subiendo archivo a R2…");
      await fetch(upload_url, {
        method: "PUT",
        body: file,
        headers: { "Content-Type": file.type },
      });

      setUploadMsg("Confirmando…");
      const asset = await api.media.confirmUpload(workspace.id, {
        asset_id,
        original_filename: file.name,
        file_size: file.size,
        media_type: file.type.startsWith("video") ? "video" : "image",
      });

      setAssets((prev) => [asset, ...prev]);
      setUploadMsg("✅ Subido correctamente");
      setTimeout(() => setUploadMsg(""), 3000);
    } catch (err) {
      setUploadMsg("❌ Error al subir el archivo");
      console.error(err);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const handleArchive = async (assetId: number) => {
    if (!workspace || !confirm("¿Archivar este archivo?")) return;
    await api.media.archive(workspace.id, assetId);
    setAssets((prev) => prev.filter((a) => a.id !== assetId));
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Biblioteca</h1>
          <p className="text-muted-foreground">Tus videos e imágenes para distribuir</p>
        </div>

        <div>
          <input
            ref={fileRef}
            type="file"
            accept="video/*,image/*"
            className="hidden"
            onChange={handleFileChange}
          />
          <Button onClick={() => fileRef.current?.click()} disabled={uploading}>
            <Upload className="h-4 w-4 mr-2" />
            {uploading ? "Subiendo…" : "Subir archivo"}
          </Button>
        </div>
      </div>

      {uploadMsg && (
        <div className="bg-muted rounded-lg px-4 py-2 text-sm">{uploadMsg}</div>
      )}

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <div key={i} className="aspect-video bg-muted rounded-xl animate-pulse" />)}
        </div>
      ) : assets.length === 0 ? (
        <div
          className="border-2 border-dashed rounded-xl p-12 text-center cursor-pointer hover:border-primary transition-colors"
          onClick={() => fileRef.current?.click()}
        >
          <Video className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
          <p className="font-medium">Subí tu primer video o imagen</p>
          <p className="text-sm text-muted-foreground mt-1">
            Arrastrá un archivo o hacé clic para seleccionar
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {assets.map((a) => (
            <AssetCard key={a.id} asset={a} onArchive={() => handleArchive(a.id)} />
          ))}
        </div>
      )}
    </div>
  );
}
