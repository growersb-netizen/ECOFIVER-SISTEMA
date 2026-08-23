"use client";

import { useEffect, useState } from "react";
import { Plus, Trash2, PencilLine, Layers, CheckCircle } from "lucide-react";
import { api, type Group, type Channel as FullChannel } from "@/lib/api";
import { useAuthStore } from "@/lib/store/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type EmbeddedChannel = { id: number; alias: string; platform: string };

function GroupCard({
  group,
  allChannels,
  onDelete,
  onRename,
  onAddChannel,
  onRemoveChannel,
}: {
  group: Group;
  allChannels: FullChannel[];
  onDelete: () => void;
  onRename: (name: string) => void;
  onAddChannel: (channelId: number) => void;
  onRemoveChannel: (channelId: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(group.name);
  const channels: EmbeddedChannel[] = group.channels ?? [];

  const groupChannelIds = new Set(channels.map((c) => c.id));
  const availableToAdd = allChannels.filter((c) => !groupChannelIds.has(c.id));

  return (
    <div className="bg-card border rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Layers className="h-4 w-4 text-muted-foreground shrink-0" />
        {editing ? (
          <form
            className="flex gap-2 flex-1"
            onSubmit={(e) => {
              e.preventDefault();
              onRename(name);
              setEditing(false);
            }}
          >
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-7 text-sm"
            />
            <Button type="submit" size="sm" className="h-7 px-2 text-xs">Guardar</Button>
          </form>
        ) : (
          <span className="font-medium text-sm flex-1">{group.name}</span>
        )}

        {!group.is_system && (
          <div className="flex gap-1 shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setEditing(!editing)}
            >
              <PencilLine className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-destructive"
              onClick={onDelete}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}
      </div>

      {/* Canales del grupo */}
      <div className="space-y-1.5">
        {channels.length === 0 ? (
          <p className="text-xs text-muted-foreground">Sin canales aún</p>
        ) : (
          channels.map((c) => (
            <div
              key={c.id}
              className="flex items-center justify-between rounded-md bg-muted px-2 py-1"
            >
              <div className="flex items-center gap-1.5">
                <CheckCircle className="h-3 w-3 text-green-500 shrink-0" />
                <span className="text-xs">{c.alias}</span>
                <span className="text-xs text-muted-foreground capitalize">({c.platform})</span>
              </div>
              {!group.is_system && (
                <button
                  onClick={() => onRemoveChannel(c.id)}
                  className="text-muted-foreground hover:text-destructive ml-2 shrink-0"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              )}
            </div>
          ))
        )}
      </div>

      {/* Agregar canal */}
      {!group.is_system && availableToAdd.length > 0 && (
        <select
          className="w-full text-xs border rounded-md bg-background p-1.5 text-muted-foreground"
          defaultValue=""
          onChange={(e) => {
            if (e.target.value) onAddChannel(Number(e.target.value));
            e.target.value = "";
          }}
        >
          <option value="">+ Agregar canal al grupo…</option>
          {availableToAdd.map((c) => (
            <option key={c.id} value={c.id}>
              {c.alias} ({c.platform})
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

export default function GruposPage() {
  const { workspace } = useAuthStore();
  const [groups, setGroups] = useState<Group[]>([]);
  const [allChannels, setAllChannels] = useState<FullChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const load = async () => {
    if (!workspace) return;
    setLoading(true);
    try {
      const [gr, ch] = await Promise.all([
        api.groups.list(workspace.id),
        api.channels.list(workspace.id),
      ]);
      setGroups(gr.groups);
      setAllChannels(ch.channels);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [workspace]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!workspace || !newName.trim()) return;
    setCreating(true);
    const g = await api.groups.create(workspace.id, newName.trim());
    setGroups((gs) => [...gs, { ...g, channels: [] }]);
    setNewName("");
    setCreating(false);
  };

  const handleDelete = async (groupId: number) => {
    if (!workspace || !confirm("¿Eliminar este grupo?")) return;
    await api.groups.delete(workspace.id, groupId);
    setGroups((gs) => gs.filter((g) => g.id !== groupId));
  };

  const handleRename = async (groupId: number, name: string) => {
    if (!workspace) return;
    await api.groups.update(workspace.id, groupId, name);
    setGroups((gs) => gs.map((g) => (g.id === groupId ? { ...g, name } : g)));
  };

  const handleAddChannel = async (groupId: number, channelId: number) => {
    if (!workspace) return;
    await api.groups.addChannel(workspace.id, groupId, channelId);
    const ch = allChannels.find((c) => c.id === channelId);
    if (ch) {
      setGroups((gs) =>
        gs.map((g) =>
          g.id === groupId
            ? { ...g, channels: [...(g.channels ?? []), { id: ch.id, alias: ch.alias, platform: ch.platform }] }
            : g
        )
      );
    }
  };

  const handleRemoveChannel = async (groupId: number, channelId: number) => {
    if (!workspace) return;
    await api.groups.removeChannel(workspace.id, groupId, channelId);
    setGroups((gs) =>
      gs.map((g) =>
        g.id === groupId
          ? { ...g, channels: (g.channels ?? []).filter((c) => c.id !== channelId) }
          : g
      )
    );
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Grupos</h1>
        <p className="text-muted-foreground">Organizá tus canales para publicar en varios a la vez</p>
      </div>

      {/* Crear grupo */}
      <form onSubmit={handleCreate} className="flex gap-2">
        <Input
          placeholder="Nombre del nuevo grupo…"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          className="max-w-xs"
        />
        <Button type="submit" disabled={creating || !newName.trim()}>
          <Plus className="h-4 w-4 mr-1" />
          Crear grupo
        </Button>
      </form>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2].map((i) => <div key={i} className="h-32 bg-muted rounded-xl animate-pulse" />)}
        </div>
      ) : groups.length === 0 ? (
        <p className="text-sm text-muted-foreground">No hay grupos todavía.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {groups.map((g) => (
            <GroupCard
              key={g.id}
              group={g}
              allChannels={allChannels}
              onDelete={() => handleDelete(g.id)}
              onRename={(name) => handleRename(g.id, name)}
              onAddChannel={(channelId) => handleAddChannel(g.id, channelId)}
              onRemoveChannel={(channelId) => handleRemoveChannel(g.id, channelId)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
