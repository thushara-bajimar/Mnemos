import { Play } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, CHART_COLORS, Card, Empty, ErrorBox, Loading, PageHeader, Select, fmtDate } from "../components/ui";
import { api, post } from "../lib/api";
import { useLoad } from "../lib/hooks";

export default function Evaluation() {
  const runs = useLoad(() => api("/api/eval/runs"));
  const [sel, setSel] = useState<string>("");
  const detail = useLoad(() => (sel ? api(`/api/eval/runs/${sel}`) : api("/api/eval/latest?kind=all")), [sel]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cat, setCat] = useState("");

  async function go(suite: string) {
    setBusy(suite); setErr(null);
    try { const r = await post("/api/eval/run", { suite }); await runs.reload(); setSel(r.id); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  }
  const d = detail.data?.details;
  const sc = d?.scenarios;
  const ctx = d?.context;

  return (
    <div>
      <PageHeader title="Evaluation Lab" subtitle="Runs real scenario tests, a storage benchmark and a context-strategy comparison on isolated temporary databases. Results are measured, stored and shown as-is."
        actions={<>
          <Button busy={busy === "all"} onClick={() => go("all")}><Play className="h-4 w-4" />Run everything</Button>
          <Button variant="secondary" busy={busy === "scenarios"} onClick={() => go("scenarios")}>Scenarios</Button>
          <Button variant="secondary" busy={busy === "context"} onClick={() => go("context")}>Context comparison</Button>
        </>} />
      <ErrorBox error={err || runs.error} />
      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-ink-500">Showing run:</span>
        <Select value={sel} onChange={setSel} options={[{ value: "", label: "latest full run" }, ...(runs.data ?? []).map((r: any) => ({ value: r.id, label: `${r.kind} · ${fmtDate(r.created_at)}` }))]} />
        {detail.data && <span className="text-xs text-ink-500">{detail.data.kind} run in {detail.data.summary.duration_s}s · tokenizer {d?.tokenizer?.tokenizer}{d?.tokenizer?.is_estimate ? " (ESTIMATE)" : ""}</span>}
      </div>
      {detail.loading && !detail.data ? <Loading /> : !detail.data ? <Empty>No evaluation run yet. Press <b>Run everything</b> (≈30–60 s).</Empty> : (
        <div className="space-y-4">
          {sc && (
            <Card title={<span>Scenarios: <span className={sc.passed === sc.total ? "text-emerald-600" : "text-rose-600"}>{sc.passed}/{sc.total} passed</span></span>}
              actions={<Select value={cat} onChange={setCat} options={[{ value: "", label: "all categories" }, ...Object.keys(sc.by_category).map((c) => ({ value: c, label: c }))]} />}>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={Object.entries(sc.by_category).map(([k, v]: any) => ({ category: k, passed: v.passed, failed: v.total - v.passed }))}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="category" fontSize={10} /><YAxis allowDecimals={false} fontSize={11} /><Tooltip /><Legend />
                  <Bar dataKey="passed" stackId="a" fill="#10b981" /><Bar dataKey="failed" stackId="a" fill="#ef4444" />
                </BarChart>
              </ResponsiveContainer>
              <div className="mt-2 max-h-96 overflow-auto"><table className="table-auto w-full text-xs">
                <thead><tr className="border-b border-ink-200"><th>Id</th><th>Category</th><th>Scenario</th><th>Result</th><th>Observed evidence</th><th>ms</th></tr></thead>
                <tbody>{sc.rows.filter((r: any) => !cat || r.category === cat).map((r: any) => <tr key={r.id} className="border-b border-ink-100"><td className="font-mono">{r.id}</td><td>{r.category}</td><td>{r.title}</td><td><Badge tone={r.passed ? "pass" : "fail"}>{r.passed ? "pass" : "fail"}</Badge></td><td className="max-w-md text-ink-600">{r.error ?? r.evidence}</td><td>{r.ms}</td></tr>)}</tbody>
              </table></div>
              <p className="mt-2 text-xs text-ink-500">Caveat: scenarios were authored alongside the rules, so a high pass rate demonstrates that specified behaviour works — it is not an independent accuracy estimate on real-world data.</p>
            </Card>
          )}
          {ctx && (
            <Card title={`Context strategies — ${ctx.dataset.turns} turns, ${ctx.dataset.questions} questions, full history = ${ctx.dataset.full_history_tokens} tokens`}>
              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <div className="mb-1 text-xs font-semibold text-ink-600">Answer support vs budget</div>
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart data={[500, 1000, 2000, 5000].map((b) => ({ budget: String(b), ...Object.fromEntries(ctx.rows.filter((r: any) => r.budget === b).map((r: any) => [r.strategy, r.answer_support])) }))}>
                      <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="budget" fontSize={11} /><YAxis domain={[0, 1]} fontSize={11} /><Tooltip /><Legend />
                      <Line dataKey="full_history" stroke="#94a3b8" strokeWidth={2} /><Line dataKey="summary" stroke={CHART_COLORS[2]} strokeWidth={2} /><Line dataKey="selected" stroke={CHART_COLORS[0]} strokeWidth={3} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div>
                  <div className="mb-1 text-xs font-semibold text-ink-600">Average tokens actually sent</div>
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart data={[500, 1000, 2000, 5000].map((b) => ({ budget: String(b), ...Object.fromEntries(ctx.rows.filter((r: any) => r.budget === b).map((r: any) => [r.strategy, r.avg_tokens])) }))}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="budget" fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Legend />
                      <Bar dataKey="full_history" fill="#94a3b8" /><Bar dataKey="summary" fill={CHART_COLORS[2]} /><Bar dataKey="selected" fill={CHART_COLORS[0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <table className="table-auto mt-2 w-full text-xs"><thead><tr><th>Budget</th><th>Strategy</th><th>Answer support</th><th>Stale-value risk</th><th>Avg tokens</th><th>Max tokens</th><th>Within budget</th><th>Latency ms</th></tr></thead>
                <tbody>{ctx.rows.map((r: any, i: number) => <tr key={i} className="border-t border-ink-100"><td>{r.budget}</td><td>{r.strategy}</td><td>{r.answer_support}</td><td>{r.stale_risk}</td><td>{r.avg_tokens}</td><td>{r.max_tokens}</td><td>{r.within_budget ? "✔" : "✖"}</td><td>{r.latency_ms}</td></tr>)}</tbody></table>
              <p className="mt-2 text-xs text-ink-500">{ctx.note} Mnemos ingested the transcript in {ctx.dataset.mnemos_ingest_ms} ms; decisions: {Object.entries(ctx.dataset.mnemos_decisions).map(([k, v]) => `${k} ${v}`).join(", ")}.</p>
            </Card>
          )}
          {d?.storage && <Card title="Storage benchmark"><p className="text-sm text-ink-600">Included in this run — see the <a className="text-brand-700 underline" href="/storage">Storage Strategies</a> page for charts. Best MRR: <b>{detail.data.summary.best_mrr_strategy}</b>.</p></Card>}
        </div>
      )}
    </div>
  );
}
