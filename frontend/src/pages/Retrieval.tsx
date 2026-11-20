import { HelpCircle, Layers, Search } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import MemoryDrawer from "../components/MemoryDrawer";
import { Badge, Button, Card, Empty, ErrorBox, Input, Label, Mono, PageHeader, Select } from "../components/ui";
import { post } from "../lib/api";

const BUDGETS = [500, 1000, 2000, 5000];

export default function Retrieval() {
  const [query, setQuery] = useState("What is the deadline for Project Orion?");
  const [mode, setMode] = useState("hybrid");
  const [budget, setBudget] = useState(1000);
  const [task, setTask] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [search, setSearch] = useState<any>(null);
  const [ask, setAsk] = useState<any>(null);
  const [ctx, setCtx] = useState<any>(null);
  const [cmp, setCmp] = useState<any>(null);
  const [open, setOpen] = useState<string | null>(null);

  async function go(kind: string, fn: () => Promise<void>) {
    if (!query.trim()) { setErr("Enter a query."); return; }
    setBusy(kind); setErr(null);
    try { await fn(); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  }
  const t = task || undefined;

  return (
    <div>
      <PageHeader title="Retrieval & Token Budget Lab" subtitle="Search memory with five strategies, ask with abstention, and assemble task context inside a hard token budget." />
      <Card>
        <ErrorBox error={err} />
        <div className="grid gap-3 lg:grid-cols-12">
          <div className="lg:col-span-6"><Label>Query / question</Label><Input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && go("ask", async () => setAsk(await post("/api/ask", { question: query, task_id: t })))} /></div>
          <div className="lg:col-span-2"><Label>Mode</Label><Select className="w-full" value={mode} onChange={setMode} options={["hybrid", "keyword", "semantic", "structured", "graph"]} /></div>
          <div className="lg:col-span-2"><Label>Task id (optional)</Label><Input value={task} onChange={(e) => setTask(e.target.value)} placeholder="task_…" /></div>
          <div className="lg:col-span-2"><Label>Budget: {budget} tokens</Label>
            <div className="flex gap-1">{BUDGETS.map((b) => <button key={b} onClick={() => setBudget(b)} className={`flex-1 rounded border px-1 py-1 text-xs ${b === budget ? "border-brand-500 bg-brand-50 text-brand-700" : "border-ink-200"}`}>{b}</button>)}</div>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button busy={busy === "ask"} onClick={() => go("ask", async () => setAsk(await post("/api/ask", { question: query, task_id: t })))}><HelpCircle className="h-4 w-4" />Ask (with abstention)</Button>
          <Button variant="secondary" busy={busy === "search"} onClick={() => go("search", async () => setSearch(await post("/api/search", { query, mode, task_id: t, limit: 10 })))}><Search className="h-4 w-4" />Search</Button>
          <Button variant="secondary" busy={busy === "ctx"} onClick={() => go("ctx", async () => setCtx(await post("/api/context", { query, budget, mode, task_id: t })))}><Layers className="h-4 w-4" />Assemble context</Button>
          <Button variant="secondary" busy={busy === "cmp"} onClick={() => go("cmp", async () => setCmp(await post("/api/context/compare", { query, budgets: BUDGETS })))}>Compare strategies</Button>
        </div>
      </Card>

      {ask && (
        <Card className="mt-4" title={<span className="flex items-center gap-2">Answer <Badge>{ask.status}</Badge></span>}>
          {ask.answer ? <div className="text-lg font-semibold text-ink-900">{ask.answer}</div> : <div className="text-ink-500">No answer given — Mnemos abstained instead of guessing.</div>}
          <p className="mt-1 text-sm text-ink-600">{ask.explanation}</p>
          {ask.candidates && <ul className="mt-2 text-sm">{ask.candidates.map((c: any) => <li key={c.memory_id}>• <b>{c.value}</b> (conf {c.confidence.toFixed(2)}) <button className="font-mono text-xs text-brand-700 underline" onClick={() => setOpen(c.memory_id)}>{c.memory_id}</button></li>)}</ul>}
          {ask.sources?.length > 0 && <div className="mt-2 text-xs text-ink-500">Sources: {ask.sources.map((s: any, i: number) => <span key={i} className="mr-2">{s.source_type}{s.source_label ? ` “${s.source_label}”` : ""}{s.agent_id ? ` via ${s.agent_id}` : ""}</span>)}</div>}
          {ask.memory_id && <button className="mt-1 text-xs text-brand-700 underline" onClick={() => setOpen(ask.memory_id)}>Trace memory {ask.memory_id}</button>}
        </Card>
      )}

      {search && (
        <Card className="mt-4" title={`Search results (${search.mode}) — ${search.results.length} hits in ${search.latency_ms} ms${search.cached ? " (cached)" : ""}`}>
          {!search.results.length ? <Empty>No matches.</Empty> : (
            <div className="overflow-x-auto"><table className="table-auto w-full text-sm">
              <thead><tr className="border-b border-ink-200"><th>Score</th><th>Memory</th><th>Why it ranked</th><th>Cover</th></tr></thead>
              <tbody>{search.results.map((r: any) => (
                <tr key={r.id} className="border-b border-ink-100">
                  <td className="tabular-nums font-semibold">{r.score.toFixed(3)}</td>
                  <td className="max-w-md"><button className="text-left hover:underline" onClick={() => setOpen(r.id)}>{r.content}</button><div className="mt-0.5 flex gap-1"><Badge tone="type">{r.memory_type}</Badge><Badge>{r.status}</Badge><span className="text-[11px] text-ink-400">{r.source_type}</span></div></td>
                  <td className="text-xs text-ink-600">{r.why}</td>
                  <td className="tabular-nums text-xs">{r.coverage}</td>
                </tr>))}</tbody>
            </table></div>
          )}
        </Card>
      )}

      {ctx && (
        <Card className="mt-4" title={`Assembled context: ${ctx.tokens_used} / ${ctx.budget} tokens (${ctx.tokenizer}${ctx.is_estimate ? ", ESTIMATE" : ""})`}>
          <div className="mb-2 h-2 rounded bg-ink-100"><div className="h-2 rounded bg-brand-500" style={{ width: `${Math.min(100, (ctx.tokens_used / ctx.budget) * 100)}%` }} /></div>
          <pre className="max-h-80 overflow-auto rounded-lg bg-ink-950 p-3 font-mono text-[11px] text-ink-100">{ctx.context}</pre>
          <div className="mt-3 grid gap-3 md:grid-cols-2 text-xs">
            <div><b>Included ({ctx.included.length})</b>{ctx.included.map((i: any) => <div key={i.id}><Mono>{i.id}</Mono> {i.tokens} tok · {i.form} · score {i.score.toFixed(3)}</div>)}</div>
            <div><b>Excluded ({ctx.excluded.length})</b>{ctx.excluded.slice(0, 12).map((i: any) => <div key={i.id}><Mono>{i.id}</Mono> {i.reason}</div>)}</div>
          </div>
        </Card>
      )}

      {cmp && (
        <Card className="mt-4" title={`Strategy comparison on live memory (${cmp.total_active_memories} active memories, full dump = ${cmp.full_dump_tokens} tokens)`}>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={BUDGETS.map((b) => ({ budget: String(b), ...Object.fromEntries(cmp.rows.filter((r: any) => r.budget === b).map((r: any) => [r.strategy, r.tokens])) }))}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="budget" fontSize={11} /><YAxis fontSize={11} label={{ value: "tokens sent", angle: -90, position: "insideLeft", fontSize: 11 }} />
              <Tooltip /><Legend /><Bar dataKey="full_dump" fill="#94a3b8" /><Bar dataKey="summary" fill="#f59e0b" /><Bar dataKey="selected" fill="#3866f6" />
            </BarChart>
          </ResponsiveContainer>
          <table className="table-auto mt-2 w-full text-xs">
            <thead><tr><th>Budget</th><th>Strategy</th><th>Tokens</th><th>Items</th><th>Query-term coverage</th><th>Latency ms</th></tr></thead>
            <tbody>{cmp.rows.map((r: any, i: number) => <tr key={i} className="border-t border-ink-100"><td>{r.budget}</td><td>{r.strategy}</td><td>{r.tokens}</td><td>{r.items}</td><td>{r.query_term_coverage}</td><td>{r.latency_ms}</td></tr>)}</tbody>
          </table>
          <p className="mt-2 text-xs text-ink-500">Live comparison measures tokens and query-term coverage only. Answer-support against ground truth is measured in the Evaluation Lab on a labelled synthetic dataset.</p>
        </Card>
      )}
      {open && <MemoryDrawer id={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
