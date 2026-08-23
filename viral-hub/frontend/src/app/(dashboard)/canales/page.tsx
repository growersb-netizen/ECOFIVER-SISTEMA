"use client";

import { useEffect, useState } from "react";
import { Tv2, Trash2, PencilLine, RefreshCw, CheckCircle, AlertCircle, XCircle } from "lucide-react";
import { api, type Channel } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const PLATFORMS = [
  { id: "instagram", name: "Instagram", icon: "📸", color: "bg-gradient-to-br from-pink-500 to-orange-400" },
  { id: "tiktok", name: "TikTok", icon: "🎵", color: "bg-black" },
  { id: "youtube", name: "YouTube", icon: "▶️", color: "bg-red-600" },
  { id: "facebook", name: "Facebook", icon: "f", color: "bg-blue-600" },
];

const STATUS_CONFIG = {
  connected: { icon: CheckCircle, label: "Conectado", color: "text-green-600", badge: "success" as const },
  requires_reconnect: { icon: RefreshCw, label: "Reconectar", color: "text-yellow-600", badge: "warning" as const },
  revoked: { icon: XCircle, label: "Revocado", color: "text-red-600", badge: "destructive" as const },
  error: { icon: AlertCircle, label: "Error", color: "text-red-600", badge: "destructive" as const },
};

function ConnectButton({ platform }: { platform: typeof PLATFORMS[0] }) {
  const handleConnect = () => {
    // El OAuth redirect se genera en el backend
    // El frontend redirige al usuario al provider
    alert(`Para conectar ${platform.name}: el flujo OAuth se configurará cuando completes las credenciales de la app en el .env`);
  };

  return (
    <button
      onClick={handleConnect}
      className={`${platform.color} text-white rounded-xl p-4 text-left hover:opacity-90 transition-opacity`}
    >
      <div className="text-2xl mb-2">{platform.icon}</div>
      <p className="font-semibold text-sm">{platform.name}</p>
      <p className="text-xs opacity-75 mt-0.5">Conectar cuenta</p>
    </button>
  );
}

function ChannelCard({ channel, onDisconnect }: { channel: Channel; onDisconnect: () => void }) {
  const statusConfig = STATUS_CONFIG[channel.status] ?? STATUS_CONFIG.error;
  const Icon = statusConfig.icon;

  return (
    <div className="bg-card border rounded-xl p-4 flex items-center gap-3">
      {/* Avatar o plataforma icon */}
      <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center overflow-hidden shrink-0">
        {channel.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={channel.avatar_url} alt={channel.alias} className="w-full h-full object-cover" />
        ) : (
          <Tv2 className="h-5 w-5 text-muted-foreground" />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <p className="font-medium text-sm truncate">{channel.alias}</p>
        <p className="text-xs text-muted-foreground">
          {channel.platform} {channel.remote_username ? `· @${channel.remote_username}` : ""}
        </p>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <Badge variant={statusConfig.badge}>
          <Icon className="h-3 w-3 mr-1" />
          {statusConfig.label}
        </Badge>

        <Button
          variant="ghost"
          size="icon"
          onClick={onDisconnect}
          className="h-8 w-8 text-muted-foreground hover:text-destructive"
          title="Desconectar canal"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

export default function CanalesPage() {
  const { workspace } = useAuthStore();
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);

  const loadChannels = () => {
    if (!workspace) return;
    api.channels
      .list(workspace.id)
      .then((r) => setChannels(r.channels))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadChannels(); }, [workspace]);

  const handleDisconnect = async (channelId: number) => {
    if (!workspace || !confirm("¿Desconectar este canal?")) return;
    await api.channels.disconnect(workspace.id, channelId);
    setChannels((ch) => ch.filter((c) => c.id !== channelId));
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Canales</h1>
          <p className="text-muted-foreground">Conectá y administrá tus cuentas sociales</p>
        </div>
      </div>

      {/* Canales conectados */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2].map((i) => <div key={i} className="h-16 bg-muted rounded-xl animate-pulse" />)}
        </div>
      ) : channels.length > 0 ? (
        <div>
          <h2 className="font-semibold mb-3">Canales conectados ({channels.length})</h2>
          <div className="space-y-2">
            {channels.map((ch) => (
              <ChannelCard key={ch.id} channel={ch} onDisconnect={() => handleDisconnect(ch.id)} />
            ))}
          </div>
        </div>
      ) : null}

      {/* Agregar nuevo canal */}
      <div>
        <h2 className="font-semibold mb-3">
          {channels.length === 0 ? "Conectá tu primer canal" : "Agregar otro canal"}
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {PLATFORMS.map((p) => <ConnectButton key={p.id} platform={p} />)}
        </div>
        <p className="text-xs text-muted-foreground mt-3">
          💡 Para habilitar la conexión OAuth, configurá las credenciales de cada plataforma en el <code className="bg-muted px-1 rounded">.env</code> del backend y revisá <code>backend/app/providers/</code>
        </p>
      </div>
    </div>
  );
}
