import { useState } from "react";
import MemoryDrawer from "../components/MemoryDrawer";
import { Badge, Button, Card, Empty, ErrorBox, Input, Loading, PageHeader, Select, fmtDate } from "../components/ui";
import { api, type Memory } from "../lib/api";
import { useLoad } from "../lib/hooks";

const TYPES = ["", "episodic", "semantic", "procedural", "preference", "working", "relational"];
const STATUSES = ["", "active", "superseded", "conflicted", "quarantined", "pending_confirmation", "expired"];
const SOURCES = ["", "user", "agent", "document", "tool", "web", "system"];
const PAGE = 25;

export default function Memories() {
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [agent, setAgent] = useState("");
  const [page, setPage] = useState(0);
  const [sel, setSel] = useState<string | null>(null);
  const params = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
  if (q) params.set("q", q);
  if (type) params.set("memory_type", type);
  if (status) params.set("status", status);
  if (source) params.set("source_type", source);
  if (agent) params.set("agent_id", agent);
  const list = useLoad<{ total: number; items: Memory[] }>(() => api(`/api/memories?${params}`), [q, type, status, source, agent, page]);
  const total = list.data?.total ?? 0;

  return (
    <div>
      <PageHeader title="Memory Explorer" subtitle="Browse every stored memory with its status, type, source and storage routes. Click a row for provenance, history and store presence." />
      <Card>
        <div className="mb-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
          <Input className="lg:col-span-2" placeholder="Filter text…" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} aria-label="Filter text" />
          <Select label="Type" value={type} onChange={(v) => { setType(v); setPage(0); }} options={TYPES.map((t) => ({ value: t, label: t || "all types" }))} />
          <Select label="Status" value={status} onChange={(v) => { setStatus(v); setPage(0); }} options={STATUSES.map((t) => ({ value: t, label: t || "all statuses" }))} />
          <Select label="Source" value={source} onChange={(v) => { setSource(v); setPage(0); }} options={SOURCES.map((t) => ({ value: t, label: t || "all sources" }))} />
          <Input placeholder="agent id" value={agent} onChange={(e) => { setAgent(e.target.value); setPage(0); }} aria-label="Agent id" />
        </div>
        <ErrorBox error={list.error} />
        {list.loading && !list.data ? <Loading /> : !list.data?.items.length ? <Empty>No memories match these filters.</Empty> : (
          <div className="overflow-x-auto">
            <table className="table-auto w-full text-sm">
              <thead><tr className="border-b border-ink-200"><th>Content</th><th>Type</th><th>Status</th><th>Source</th><th>Conf.</th><th>Routes</th><th>Created</th></tr></thead>
              <tbody>
                {list.data.items.map((m) => (
                  <tr key={m.id} onClick={() => setSel(m.id)} className="cursor-pointer border-b border-ink-100 hover:bg-brand-50/50">
                    <td className="max-w-md"><div className="line-clamp-2">{m.content}</div>{m.subject && <div className="text-[11px] text-ink-500">{m.subject} · {m.attribute} = {m.value}</div>}</td>
                    <td><Badge tone="type">{m.memory_type}</Badge></td>
                    <td><Badge>{m.status}</Badge>{m.expires_at && m.status === "active" && <div className="text-[10px] text-amber-700">temp</div>}</td>
                    <td className="text-xs">{m.source_type}{m.agent_id && <div className="text-ink-400">{m.agent_id}</div>}</td>
                    <td className="tabular-nums">{m.confidence.toFixed(2)}</td>
                    <td className="text-[11px] text-ink-500">{m.storage_routes.join(", ")}</td>
                    <td className="whitespace-nowrap text-[11px] text-ink-500">{fmtDate(m.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-3 flex items-center justify-between text-sm text-ink-500">
          <span>{total} memories</span>
          <div className="flex gap-2">
            <Button variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Prev</Button>
            <Button variant="secondary" disabled={(page + 1) * PAGE >= total} onClick={() => setPage(page + 1)}>Next</Button>
          </div>
        </div>
      </Card>
      {sel && <MemoryDrawer id={sel} onClose={() => setSel(null)} onChanged={list.reload} />}
    </div>
  );
}
