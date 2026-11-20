import { RefreshCw, Sprout, Timer } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, post } from "../lib/api";
import { useLoad } from "../lib/hooks";
import { Badge, Button, CHART_COLORS, Card, Empty, ErrorBox, Loading, PageHeader, Stat, fmtBytes, fmtDate } from "../components/ui";

const toRows = (o: Record<string, number> = {}) => Object.entries(o).map(([name, value]) => ({ name, value }));

export default function Overview() {
  const stats = useLoad(() => api("/api/stats"));
  const decisions = useLoad(() => api("/api/decisions?limit=12"));
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function run(label: string, fn: () => Promise<string>) {
    setBusy(label); setErr(null); setMsg(null);
    try { setMsg(await fn()); stats.reload(); decisions.reload(); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  }
  const s = stats.data;
  return (
    <div>
      <PageHeader title="Overview" subtitle="Live statistics of the persistent memory system. Everything here is read from the backend database."
        actions={<>
          <Button variant="secondary" busy={busy === "seed"} onClick={() => run("seed", async () => { const r = await post("/api/admin/seed"); return `Seeded ${r.seeded} demo statements through the decision engine.`; })}><Sprout className="h-4 w-4" />Seed demo data</Button>
          <Button variant="secondary" busy={busy === "exp"} onClick={() => run("exp", async () => { const r = await post("/api/maintenance/expire"); return `Expiry sweep: ${r.count} temporary memory(ies) expired.`; })}><Timer className="h-4 w-4" />Run expiry sweep</Button>
          <Button variant="ghost" onClick={() => { stats.reload(); decisions.reload(); }}><RefreshCw className="h-4 w-4" /></Button>
        </>} />
      <ErrorBox error={stats.error || err} />
      {msg && <div className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{msg}</div>}
      {stats.loading && !s && <Loading />}
      {s && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Stat label="Memories" value={s.total_memories} hint={`${s.by_status.active ?? 0} active`} />
            <Stat label="Open conflicts" value={s.open_conflicts} tone={s.open_conflicts ? "bad" : "good"} />
            <Stat label="Awaiting review" value={s.pending_confirmations} tone={s.pending_confirmations ? "warn" : "good"} hint="pending + quarantined" />
            <Stat label="Forgotten" value={s.deletions} hint={`${s.expired} expired`} />
            <Stat label="Graph" value={`${s.entities}/${s.edges}`} hint="entities / edges" />
            <Stat label="Storage" value={fmtBytes(s.db_bytes + s.file_bytes)} hint={`${s.vectors} vectors · ${s.files} files`} />
          </div>
          {s.total_memories === 0 ? (
            <div className="mt-6"><Empty>No memories yet. Click <b>Seed demo data</b> or use the Decision Lab to add some.</Empty></div>
          ) : (
            <div className="mt-6 grid gap-4 lg:grid-cols-3">
              <Card title="Decisions taken">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={toRows(s.by_decision)} layout="vertical" margin={{ left: 40 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} fontSize={11} />
                    <YAxis type="category" dataKey="name" fontSize={10} width={120} />
                    <Tooltip /><Bar dataKey="value" fill="#3866f6" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
              <Card title="Active memory by type">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={toRows(s.by_type)} dataKey="value" nameKey="name" innerRadius={45} outerRadius={80} label={({ name }) => name} fontSize={11}>
                      {toRows(s.by_type).map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                    </Pie><Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </Card>
              <Card title="Storage routes used">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={toRows(s.by_route)}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" fontSize={11} /><YAxis allowDecimals={false} fontSize={11} />
                    <Tooltip /><Bar dataKey="value" fill="#10b981" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </Card>
            </div>
          )}
          <div className="mt-4 grid gap-4 lg:grid-cols-3">
            <Card title="Recent decisions" className="lg:col-span-2">
              {decisions.data?.length ? (
                <ul className="divide-y divide-ink-100 text-sm">
                  {decisions.data.map((d: any) => (
                    <li key={d.id} className="flex items-start gap-2 py-2">
                      <Badge>{d.action}</Badge>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-ink-800">{d.preview ?? <span className="italic text-ink-400">content not retained (discarded input)</span>}</div>
                        <div className="truncate text-xs text-ink-500">{d.reasons[d.reasons.length - 1]}</div>
                      </div>
                      <span className="whitespace-nowrap text-[11px] text-ink-400">{fmtDate(d.created_at)}</span>
                    </li>
                  ))}
                </ul>
              ) : <Empty>No decisions yet.</Empty>}
            </Card>
            <Card title="System">
              <dl className="space-y-2 text-sm">
                <div className="flex justify-between"><dt className="text-ink-500">Tokenizer</dt><dd><Badge tone={s.tokenizer.is_estimate ? "pending" : "active"}>{s.tokenizer.tokenizer}</Badge></dd></div>
                <div className="flex justify-between"><dt className="text-ink-500">Embedder</dt><dd className="font-mono text-xs">{s.embedder}</dd></div>
                <div className="flex justify-between"><dt className="text-ink-500">Tasks / handovers</dt><dd>{s.tasks} / {s.handovers}</dd></div>
                <div className="flex justify-between"><dt className="text-ink-500">Evaluation runs</dt><dd>{s.eval_runs}</dd></div>
                <div className="flex justify-between"><dt className="text-ink-500">Sources</dt><dd className="text-right text-xs">{Object.entries(s.by_source).map(([k, v]) => `${k}:${v}`).join(" · ")}</dd></div>
              </dl>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
