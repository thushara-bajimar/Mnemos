import { Check, GitBranch, Pencil, Trash2, X } from "lucide-react";
import { useState } from "react";
import { api, post, put } from "../lib/api";
import { useLoad } from "../lib/hooks";
import { Badge, Button, ErrorBox, Loading, Mono, Textarea, fmtDate } from "./ui";

export default function MemoryDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged?: () => void }) {
  const { data: t, error, loading, reload } = useLoad(() => api(`/api/memories/${id}/trace`), [id]);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const m = t?.memory;

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      onChanged?.();
      await reload();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function forget() {
    if (!confirm("Permanently delete this memory (and derived memories / older versions) from every store?")) return;
    setBusy(true);
    try {
      const plan = await post("/api/forget/plan", { scope: "id", value: id });
      const out = await post("/api/forget/execute", { confirm_token: plan.confirm_token });
      alert(`Deleted ${out.count} memory(ies). Verified clear: ${out.verification.all_clear}`);
      onChanged?.();
      onClose();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <div className="h-full w-full max-w-2xl overflow-y-auto bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Memory <Mono>{id}</Mono></h2>
          <button aria-label="Close" onClick={onClose} className="rounded p-1 hover:bg-ink-100"><X className="h-5 w-5" /></button>
        </div>
        <ErrorBox error={error || err} />
        {loading && !t && <Loading />}
        {m && (
          <div className="space-y-5 text-sm">
            <div className="flex flex-wrap gap-2">
              <Badge>{m.status}</Badge><Badge tone="type">{m.memory_type}</Badge>
              <span className="text-xs text-ink-500">v{m.version} · confidence {m.confidence.toFixed(2)} · importance {m.importance.toFixed(2)} · reinforced ×{m.reinforcement} · accessed {m.access_count}×</span>
            </div>
            {editing ? (
              <div className="space-y-2">
                <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} />
                <div className="flex gap-2">
                  <Button busy={busy} onClick={() => act(async () => { await put(`/api/memories/${id}`, { content: text, reason: "edited in explorer" }); setEditing(false); })}><Check className="h-4 w-4" />Save revision</Button>
                  <Button variant="secondary" onClick={() => setEditing(false)}>Cancel</Button>
                </div>
              </div>
            ) : (
              <p className="rounded-lg bg-ink-50 p-3 text-ink-800">{m.content}</p>
            )}
            {m.subject && <div>Fact: <Mono>{m.subject}</Mono> · <Mono>{m.attribute}</Mono> = <b>{m.value}</b></div>}
            <div className="flex flex-wrap gap-2">
              {!editing && <Button variant="secondary" onClick={() => { setText(m.content); setEditing(true); }}><Pencil className="h-4 w-4" />Edit</Button>}
              {(m.status === "pending_confirmation" || m.status === "quarantined") && <>
                <Button busy={busy} onClick={() => act(() => post(`/api/memories/${id}/confirm`, { approve: true }))}>Confirm</Button>
                <Button variant="secondary" busy={busy} onClick={() => act(() => post(`/api/memories/${id}/confirm`, { approve: false }))}>Reject</Button>
              </>}
              <Button variant="danger" busy={busy} onClick={forget}><Trash2 className="h-4 w-4" />Forget</Button>
            </div>

            <section>
              <h3 className="mb-1 font-semibold">Why this memory exists</h3>
              <ul className="list-disc space-y-1 pl-5 text-ink-700">{t.explanation.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            </section>

            <section>
              <h3 className="mb-1 font-semibold">Provenance ({m.provenance.length})</h3>
              <div className="overflow-x-auto">
                <table className="table-auto w-full text-xs">
                  <thead><tr><th>source</th><th>label / id</th><th>agent</th><th>session</th><th>method</th><th>conf</th><th>at</th></tr></thead>
                  <tbody>{m.provenance.map((p: any) => (
                    <tr key={p.id} className="border-t border-ink-100"><td><Badge tone="src">{p.source_type}</Badge></td><td>{p.source_label ?? p.source_id ?? "—"}</td><td>{p.agent_id ?? "—"}</td><td>{p.session_id ?? "—"}</td><td><Mono>{p.extraction_method}</Mono></td><td>{p.confidence.toFixed(2)}</td><td>{fmtDate(p.created_at)}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </section>

            <section>
              <h3 className="mb-1 flex items-center gap-1 font-semibold"><GitBranch className="h-4 w-4" />Version lineage</h3>
              <ol className="space-y-1">{t.lineage.map((v: any) => (
                <li key={v.id} className="flex items-center gap-2 text-xs"><Badge>{v.status}</Badge><Mono>{v.id}</Mono><span className="truncate">{v.value ?? v.content}</span><span className="text-ink-400">{fmtDate(v.valid_from)} → {v.valid_to ? fmtDate(v.valid_to) : "now"}</span></li>
              ))}</ol>
            </section>

            <section>
              <h3 className="mb-1 font-semibold">Revision history</h3>
              <ul className="space-y-1 text-xs">{m.revisions.map((r: any) => (
                <li key={r.id} className="rounded border border-ink-100 p-2"><b>v{r.version}</b> · {r.change_type} · {r.actor} · {fmtDate(r.created_at)}<div className="text-ink-600">{r.reason}</div></li>
              ))}</ul>
            </section>

            {(t.derived_from.length > 0 || t.derived_memories.length > 0) && (
              <section>
                <h3 className="mb-1 font-semibold">Derivation</h3>
                {t.derived_from.filter(Boolean).map((d: any) => <div key={d.id} className="text-xs">⬆ derived from <Mono>{d.id}</Mono> {d.content}</div>)}
                {t.derived_memories.filter(Boolean).map((d: any) => <div key={d.id} className="text-xs">⬇ derived memory <Mono>{d.id}</Mono> {d.content}</div>)}
              </section>
            )}

            {m.conflicts.length > 0 && (
              <section>
                <h3 className="mb-1 font-semibold">Conflicts</h3>
                {m.conflicts.map((c: any) => <div key={c.id} className="text-xs"><Badge>{c.status}</Badge> {c.kind}: {c.explanation}</div>)}
              </section>
            )}

            <section>
              <h3 className="mb-1 font-semibold">Store presence</h3>
              <div className="flex flex-wrap gap-1">{Object.entries(m.store_presence).map(([k, v]) => <Badge key={k} tone={v ? "active" : "superseded"}>{k}: {v ? "yes" : "no"}</Badge>)}</div>
            </section>

            {m.file_content && (
              <section>
                <h3 className="mb-1 font-semibold">File store copy</h3>
                <pre className="rounded bg-ink-950 p-3 font-mono text-[11px] text-ink-100">{m.file_content}</pre>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
