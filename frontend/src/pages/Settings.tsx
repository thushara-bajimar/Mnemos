import { useEffect, useState } from "react";
import { Badge, Button, Card, ErrorBox, Input, Label, Loading, PageHeader } from "../components/ui";
import { api, post, put } from "../lib/api";
import { useLoad } from "../lib/hooks";

const TUNABLE: { key: string; label: string; help: string; step: number; min: number; max: number }[] = [
  { key: "duplicate_threshold", label: "Duplicate threshold", help: "Cosine similarity at/above which a candidate is merged into an existing memory.", step: 0.01, min: 0.5, max: 1 },
  { key: "merge_threshold", label: "Related threshold", help: "Similarity at/above which a new memory is linked as related.", step: 0.01, min: 0.3, max: 1 },
  { key: "confirmation_threshold", label: "Confirmation threshold", help: "Confidence below this → NEEDS_CONFIRMATION.", step: 0.01, min: 0, max: 1 },
  { key: "min_relevance", label: "Minimum relevance", help: "Relevance below this → DISCARD.", step: 0.01, min: 0, max: 1 },
  { key: "abstain_threshold", label: "Abstention threshold", help: "Best retrieval score below this → answer ‘unknown’.", step: 0.01, min: 0, max: 1 },
  { key: "default_temporary_hours", label: "Default temporary TTL (h)", help: "Expiry for working memory without an explicit time cue.", step: 1, min: 1, max: 720 },
  { key: "default_token_budget", label: "Default token budget", help: "Budget used when none is given.", step: 50, min: 50, max: 20000 },
];

export default function Settings() {
  const s = useLoad(() => api("/api/settings"));
  const [vals, setVals] = useState<Record<string, any>>({});
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [key, setKey] = useState(() => { try { return localStorage.getItem("mnemos_api_key") ?? ""; } catch { return ""; } });
  useEffect(() => { if (s.data) setVals(s.data.settings); }, [s.data]);

  async function save() {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const values: Record<string, number | boolean> = Object.fromEntries(TUNABLE.map((t) => [t.key, Number(vals[t.key])]));
      values.retain_discarded_preview = !!vals.retain_discarded_preview;
      await put("/api/settings", { values });
      setMsg("Settings saved and persisted."); s.reload();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  async function reset() {
    if (prompt("This permanently deletes ALL local memory data. Type RESET to confirm.") !== "RESET") return;
    try { await post("/api/admin/reset", { confirm: "RESET" }); setMsg("All data deleted."); s.reload(); } catch (e: any) { setErr(e.message); }
  }

  return (
    <div>
      <PageHeader title="Settings & Configuration" subtitle="Tune the decision engine and retrieval thresholds. Changes are validated server-side and persisted in the database." />
      <ErrorBox error={err || s.error} />
      {msg && <div className="mb-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{msg}</div>}
      {s.loading && !s.data ? <Loading /> : s.data && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card title="Decision & retrieval thresholds" className="lg:col-span-2">
            <div className="grid gap-4 sm:grid-cols-2">
              {TUNABLE.map((t) => (
                <div key={t.key}>
                  <Label>{t.label}</Label>
                  <Input type="number" step={t.step} min={t.min} max={t.max} value={vals[t.key] ?? ""} onChange={(e) => setVals({ ...vals, [t.key]: e.target.value })} />
                  <p className="mt-0.5 text-[11px] text-ink-500">{t.help}</p>
                </div>
              ))}
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!vals.retain_discarded_preview} onChange={(e) => setVals({ ...vals, retain_discarded_preview: e.target.checked })} /> Keep previews of discarded input in the decision log (off = privacy-preserving default)</label>
            </div>
            <Button className="mt-4" busy={busy} onClick={save}>Save settings</Button>
          </Card>
          <div className="space-y-4">
            <Card title="Runtime">
              <dl className="space-y-1.5 text-sm">
                <div className="flex justify-between"><dt className="text-ink-500">Tokenizer</dt><dd><Badge tone={s.data.tokenizer.is_estimate ? "pending" : "active"}>{s.data.tokenizer.tokenizer}</Badge></dd></div>
                <div className="flex justify-between"><dt className="text-ink-500">Embedder</dt><dd className="font-mono text-xs">{s.data.embedder}</dd></div>
                <div className="flex justify-between"><dt className="text-ink-500">API key</dt><dd className="text-xs">{s.data.settings.api_key}</dd></div>
                <div><dt className="text-ink-500">Data directory</dt><dd className="break-all font-mono text-[11px]">{s.data.settings.data_dir}</dd></div>
              </dl>
            </Card>
            <Card title="Client API key">
              <p className="mb-2 text-xs text-ink-500">If the server sets MNEMOS_API_KEY, store the key here (kept only in this browser).</p>
              <div className="flex gap-2"><Input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="X-API-Key" />
                <Button variant="secondary" onClick={() => { try { localStorage.setItem("mnemos_api_key", key); setMsg("Key stored in this browser."); } catch { setErr("Browser storage unavailable."); } }}>Save</Button></div>
            </Card>
            <Card title="Storage routes">
              <ul className="space-y-1 text-xs text-ink-600">{Object.entries(s.data.routes).map(([k, v]: any) => <li key={k}><b>{k}</b>: {v}</li>)}</ul>
            </Card>
            <Card title="Danger zone"><Button variant="danger" onClick={reset}>Delete all local data</Button></Card>
          </div>
        </div>
      )}
    </div>
  );
}
