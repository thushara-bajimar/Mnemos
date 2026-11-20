import { useState } from "react";
import MemoryDrawer from "../components/MemoryDrawer";
import { Badge, Button, Card, Empty, ErrorBox, Loading, Mono, PageHeader, Select, fmtDate } from "../components/ui";
import { api, post } from "../lib/api";
import { useLoad } from "../lib/hooks";

export default function Conflicts() {
  const [status, setStatus] = useState("open");
  const conflicts = useLoad(() => api(`/api/conflicts${status ? `?status=${status}` : ""}`), [status]);
  const pending = useLoad(() => api("/api/pending"));
  const updates = useLoad(() => api("/api/updates"));
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  async function act(key: string, fn: () => Promise<unknown>) {
    setBusy(key); setErr(null);
    try { await fn(); conflicts.reload(); pending.reload(); updates.reload(); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  }

  return (
    <div>
      <PageHeader title="Contradiction & Update Center" subtitle="Conflicting facts are never silently overwritten. Resolve them here, review low-confidence or quarantined memories, and audit fact updates." />
      <ErrorBox error={err || conflicts.error || pending.error} />
      <Card title="Conflicts" actions={<Select value={status} onChange={setStatus} options={[{ value: "open", label: "open" }, { value: "resolved", label: "resolved" }, { value: "", label: "all" }]} />}>
        {conflicts.loading && !conflicts.data ? <Loading /> : !conflicts.data?.length ? <Empty>No {status} conflicts.</Empty> : (
          <div className="space-y-3">
            {conflicts.data.map((c: any) => (
              <div key={c.id} className="rounded-lg border border-ink-200 p-3">
                <div className="mb-2 flex flex-wrap items-center gap-2 text-sm"><Badge>{c.status}</Badge><Badge tone={c.kind === "low_trust_override" ? "quarantined" : "conflicted"}>{c.kind}</Badge><span className="text-ink-600">{c.explanation}</span></div>
                <div className="grid gap-2 md:grid-cols-2">
                  {[["A (existing)", c.a, "keep_a"], ["B (incoming)", c.b, "keep_b"]].map(([label, m, res]: any) => (
                    <div key={label} className="rounded bg-ink-50 p-2 text-sm">
                      <div className="text-xs font-semibold text-ink-500">{label}</div>
                      {m ? <>
                        <button className="text-left hover:underline" onClick={() => setOpen(m.id)}>{m.content}</button>
                        <div className="mt-1 text-xs text-ink-500">source {m.source_type} · trust {m.source_trust.toFixed(2)} · conf {m.confidence.toFixed(2)} · <Badge>{m.status}</Badge></div>
                        {c.status === "open" && <Button className="mt-2" variant="secondary" busy={busy === c.id + res} onClick={() => act(c.id + res, () => post(`/api/conflicts/${c.id}/resolve`, { resolution: res }))}>Keep this one</Button>}
                      </> : <span className="text-xs italic text-ink-400">memory deleted</span>}
                    </div>
                  ))}
                </div>
                {c.status === "open" ? <Button className="mt-2" variant="ghost" busy={busy === c.id + "both"} onClick={() => act(c.id + "both", () => post(`/api/conflicts/${c.id}/resolve`, { resolution: "keep_both" }))}>Both are valid (keep both)</Button>
                  : <div className="mt-2 text-xs text-ink-500">Resolved as <Mono>{c.resolution}</Mono> at {fmtDate(c.resolved_at)}</div>}
              </div>
            ))}
          </div>
        )}
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title={`Awaiting confirmation (${pending.data?.length ?? 0})`}>
          {!pending.data?.length ? <Empty>Nothing awaiting review.</Empty> : (
            <ul className="divide-y divide-ink-100 text-sm">{pending.data.map((m: any) => (
              <li key={m.id} className="py-2">
                <div className="flex items-start gap-2"><Badge>{m.status}</Badge><button className="text-left hover:underline" onClick={() => setOpen(m.id)}>{m.content}</button></div>
                <div className="mt-1 flex items-center gap-2 text-xs text-ink-500">source {m.source_type} · conf {m.confidence.toFixed(2)}
                  <Button variant="secondary" busy={busy === m.id + "y"} onClick={() => act(m.id + "y", () => post(`/api/memories/${m.id}/confirm`, { approve: true }))}>Confirm</Button>
                  <Button variant="ghost" busy={busy === m.id + "n"} onClick={() => act(m.id + "n", () => post(`/api/memories/${m.id}/confirm`, { approve: false }))}>Reject & forget</Button>
                </div>
              </li>))}</ul>
          )}
        </Card>
        <Card title="Fact updates (supersede history)">
          {!updates.data?.length ? <Empty>No updates yet. Try “Actually, the deadline for Project Orion is now …”.</Empty> : (
            <ul className="divide-y divide-ink-100 text-sm">{updates.data.map((u: any, i: number) => (
              <li key={i} className="py-2">
                <div className="text-xs text-ink-500">{fmtDate(u.at)} · {u.new?.subject} · {u.new?.attribute}</div>
                <div><span className="text-ink-400 line-through">{u.old?.value ?? u.old?.content ?? "(deleted)"}</span> → <b>{u.new?.value ?? u.new?.content ?? "(deleted)"}</b></div>
                {u.new && <button className="text-xs text-brand-700 underline" onClick={() => setOpen(u.new.id)}>view lineage</button>}
              </li>))}</ul>
          )}
        </Card>
      </div>
      {open && <MemoryDrawer id={open} onClose={() => setOpen(null)} onChanged={() => { conflicts.reload(); pending.reload(); }} />}
    </div>
  );
}
