import { Play } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button, CHART_COLORS, Card, Empty, ErrorBox, Loading, PageHeader, fmtBytes, fmtDate } from "../components/ui";
import { api, post } from "../lib/api";
import { useLoad } from "../lib/hooks";

const QUALITATIVE = [
  ["structured", "SQLite table (subject/attribute/value)", "Exact facts, filters, temporal validity, status", "Paraphrases, fuzzy text"],
  ["keyword", "SQLite FTS5 + BM25", "Queryable keyword search, rare terms, explainable", "Synonyms, paraphrases"],
  ["vector", "Hashing n-gram embeddings + cosine", "Paraphrase/fuzzy similarity, dedup", "Exactness; larger index; needs re-embed on update"],
  ["graph", "Entities + typed edges", "Relationships, ‘everything about X’, multi-hop", "Ranking inside an entity; non-entity queries"],
  ["file", "Markdown / JSONL on disk", "Long procedures, human-readable, portable", "Search speed (linear scan); updates rewrite files"],
  ["hybrid", "Mnemos: decision engine + all stores + fusion", "Best ranking; abstention; provenance", "Higher latency and storage overhead"],
];

export default function Storage() {
  const latest = useLoad(() => api("/api/eval/latest?kind=storage"));
  const latestAll = useLoad(() => api("/api/eval/latest?kind=all"));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = latest.data?.details?.storage ? latest.data : latestAll.data?.details?.storage ? latestAll.data : null;
  const st = run?.details?.storage;

  async function go() {
    setBusy(true); setErr(null);
    try { await post("/api/eval/run", { suite: "storage" }); await latest.reload(); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }

  return (
    <div>
      <PageHeader title="Storage Strategy Comparison" subtitle="Six functional storage strategies run on the same labelled synthetic corpus. Every number below is measured on this machine when you press Run."
        actions={<Button busy={busy} onClick={go}><Play className="h-4 w-4" />Run storage benchmark</Button>} />
      <ErrorBox error={err || latest.error} />
      {latest.loading && !run ? <Loading /> : !st ? <Empty>No benchmark has been run yet. Press <b>Run storage benchmark</b> (takes a few seconds).</Empty> : (
        <>
          <p className="mb-3 text-xs text-ink-500">Run {fmtDate(run.created_at)} · corpus: {st.corpus.items} memories, {st.corpus.queries} labelled queries ({st.corpus.query_kinds.join(", ")}), seed {st.corpus.seed}.</p>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Retrieval quality (higher is better)">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={st.rows}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="strategy" fontSize={11} /><YAxis domain={[0, 1]} fontSize={11} /><Tooltip /><Legend />
                  <Bar dataKey="r_precision" name="R-precision" fill={CHART_COLORS[0]} /><Bar dataKey="recall_at_5" name="Recall@5" fill={CHART_COLORS[1]} /><Bar dataKey="mrr" name="MRR" fill={CHART_COLORS[4]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
            <Card title="Mean query latency (ms, lower is better)">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={st.rows}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="strategy" fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Legend />
                  <Bar dataKey="query_ms_mean" name="mean" fill={CHART_COLORS[2]} /><Bar dataKey="query_ms_p95" name="p95" fill={CHART_COLORS[3]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
            <Card title="Recall@5 by query kind">
              <ResponsiveContainer width="100%" height={280}>
                <RadarChart data={st.corpus.query_kinds.map((k: string) => ({ kind: k, ...Object.fromEntries(Object.entries(st.recall_by_query_kind).map(([s, v]: any) => [s, v[k]])) }))}>
                  <PolarGrid /><PolarAngleAxis dataKey="kind" fontSize={11} /><PolarRadiusAxis domain={[0, 1]} fontSize={9} />
                  {st.rows.map((r: any, i: number) => <Radar key={r.strategy} name={r.strategy} dataKey={r.strategy} stroke={CHART_COLORS[i]} fill={CHART_COLORS[i]} fillOpacity={0.06} />)}
                  <Legend /><Tooltip />
                </RadarChart>
              </ResponsiveContainer>
            </Card>
            <Card title="Storage on disk">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={st.rows}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="strategy" fontSize={11} /><YAxis fontSize={11} tickFormatter={(v) => fmtBytes(v)} /><Tooltip formatter={(v: any) => fmtBytes(v)} />
                  <Bar dataKey="storage_bytes" name="bytes" fill={CHART_COLORS[6]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>
          <Card className="mt-4" title="All measurements">
            <div className="overflow-x-auto"><table className="table-auto w-full text-xs">
              <thead><tr className="border-b border-ink-200"><th>Strategy</th><th>R-prec</th><th>Recall@5</th><th>MRR</th><th>Insert ms</th><th>Query ms (mean/p95)</th><th>Bytes</th><th>Update ms</th><th>Update correct</th><th>Delete logical</th><th>Delete physical</th></tr></thead>
              <tbody>{st.rows.map((r: any) => <tr key={r.strategy} className="border-b border-ink-100"><td className="font-semibold">{r.strategy}</td><td>{r.r_precision}</td><td>{r.recall_at_5}</td><td>{r.mrr}</td><td>{r.insert_ms}</td><td>{r.query_ms_mean} / {r.query_ms_p95}</td><td>{fmtBytes(r.storage_bytes)}</td><td>{r.update_ms}</td><td>{r.update_correct ? "✔" : "✖"}</td><td>{r.delete_logical ? "✔" : "✖"}</td><td>{r.delete_physical ? "✔" : "✖"}</td></tr>)}</tbody>
            </table></div>
            <p className="mt-2 text-xs text-ink-500">“Update correct” = after changing Ana’s city, the top-1 result for “Where does Ana live?” is the updated record. “Delete physical” = a unique token is absent from all raw bytes in the strategy’s directory. SQLite secure_delete demo: OFF → token found after delete: {String(st.secure_delete_demo.secure_delete_off.token_found_in_file_after_delete)}; ON → {String(st.secure_delete_demo.secure_delete_on.token_found_in_file_after_delete)}.</p>
          </Card>
        </>
      )}
      <Card className="mt-4" title="Strategy trade-offs (qualitative, from the design)">
        <table className="table-auto w-full text-xs"><thead><tr><th>Strategy</th><th>Implementation</th><th>Strong for</th><th>Weak for</th></tr></thead>
          <tbody>{QUALITATIVE.map((r) => <tr key={r[0]} className="border-t border-ink-100">{r.map((c, i) => <td key={i} className={i === 0 ? "font-semibold" : ""}>{c}</td>)}</tr>)}</tbody></table>
      </Card>
    </div>
  );
}
