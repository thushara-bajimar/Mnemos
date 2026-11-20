import { CheckCircle2, ShieldAlert, Trash2, XCircle } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorBox, Input, Label, Mono, PageHeader, Select, fmtDate } from "../components/ui";
import { api, post } from "../lib/api";
import { useLoad } from "../lib/hooks";

export default function Forgetting() {
  const [scope, setScope] = useState("topic");
  const [value, setValue] = useState("");
  const [derived, setDerived] = useState(true);
  const [plan, setPlan] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [verifyId, setVerifyId] = useState("");
  const [verify, setVerify] = useState<any>(null);
  const audit = useLoad(() => api("/api/forget/audit"));

  async function doPlan() {
    if (!value.trim()) { setErr("Enter a value to match."); return; }
    setBusy("plan"); setErr(null); setResult(null);
    try { setPlan(await post("/api/forget/plan", { scope, value, include_derived: derived })); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  }
  async function execute() {
    setBusy("exec"); setErr(null);
    try { setResult(await post("/api/forget/execute", { confirm_token: plan.confirm_token })); setPlan(null); audit.reload(); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  }

  return (
    <div>
      <PageHeader title="Forgetting & Deletion Center" subtitle="Two-phase deletion: preview exactly what will be removed (including derived memories and older versions), confirm, then verify every store — including a raw byte scan of the database." />
      <ErrorBox error={err} />
      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="1 · Plan a deletion" className="xl:col-span-1">
          <Label>Scope</Label>
          <Select className="w-full" value={scope} onChange={setScope} options={[{ value: "topic", label: "topic (free-text match)" }, { value: "entity", label: "entity (person/project…)" }, { value: "source", label: "source (source id / agent / session)" }, { value: "id", label: "memory id(s), comma-separated" }]} />
          <div className="mt-2"><Label>Value</Label><Input value={value} onChange={(e) => setValue(e.target.value)} placeholder={scope === "entity" ? "Priya" : scope === "source" ? "s1 or doc:orion-arch" : scope === "id" ? "mem_…" : "Orion budget"} /></div>
          <label className="mt-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={derived} onChange={(e) => setDerived(e.target.checked)} /> Cascade to derived memories & older versions</label>
          <Button className="mt-3" busy={busy === "plan"} onClick={doPlan}>Preview deletion</Button>
        </Card>
        <Card title="2 · Review & confirm" className="xl:col-span-2">
          {!plan ? <Empty>Create a plan to see what would be deleted.</Empty> : plan.count === 0 ? <Empty>Nothing matches “{plan.value}”.</Empty> : (
            <>
              <div className="mb-2 text-sm">{plan.count} memory(ies) will be removed from every store. Token valid for {plan.expires_in_s / 60} minutes.</div>
              <ul className="max-h-72 space-y-1 overflow-auto text-sm">{plan.items.map((i: any) => (
                <li key={i.id} className="rounded border border-ink-100 p-2">
                  <div className="flex items-center gap-2"><Mono>{i.id}</Mono><Badge>{i.status}</Badge>{i.cascade && <Badge tone="pending">cascade</Badge>}</div>
                  <div className="text-ink-700">{i.content}</div>
                  <div className="mt-1 flex flex-wrap gap-1">{Object.entries(i.stores).filter(([, v]) => v).map(([k]) => <span key={k} className="rounded bg-ink-100 px-1 text-[10px]">{k}</span>)}</div>
                </li>))}</ul>
              <div className="mt-3 flex gap-2">
                <Button variant="danger" busy={busy === "exec"} onClick={execute}><Trash2 className="h-4 w-4" />Confirm permanent deletion</Button>
                <Button variant="secondary" onClick={() => setPlan(null)}>Cancel</Button>
              </div>
            </>
          )}
          {result && (
            <div className="mt-4 rounded-lg border border-ink-200 p-3 text-sm">
              <div className="flex items-center gap-2 font-semibold">{result.verification.all_clear ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : <XCircle className="h-5 w-5 text-rose-600" />}
                Deleted {result.count} — verification {result.verification.all_clear ? "passed" : "FAILED"}</div>
              <div className="mt-1 text-xs text-ink-600">Checked: {result.verification.checked_stores.join(", ")} + raw DB/WAL/file byte scan. Logical clear: {String(result.verification.logical_clear)} · Physical residue: {result.verification.physical_residue.length ? result.verification.physical_residue.join("; ") : "none"}</div>
              <div className="mt-1 text-xs text-ink-500">Audit record <Mono>{result.audit_id}</Mono> keeps only counts, store names and salted term hashes.</div>
            </div>
          )}
        </Card>
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card title="Verify a memory id">
          <div className="flex gap-2"><Input value={verifyId} onChange={(e) => setVerifyId(e.target.value)} placeholder="mem_…" /><Button variant="secondary" onClick={async () => { try { setVerify(await api(`/api/forget/verify/${verifyId.trim()}`)); } catch (e: any) { setErr(e.message); } }}>Verify</Button></div>
          {verify && Object.entries(verify.per_memory).map(([id, v]: any) => <div key={id} className="mt-2 text-sm">{v.clear ? <span className="text-emerald-700">✔ {id} is absent from all stores</span> : <span className="text-rose-700">✖ still in: {v.remaining_in.join(", ")}</span>}</div>)}
        </Card>
        <Card title="Deletion audit (privacy-safe)" className="xl:col-span-2">
          {!audit.data?.length ? <Empty>No deletions yet.</Empty> : (
            <table className="table-auto w-full text-xs"><thead><tr><th>When</th><th>Scope</th><th>Count</th><th>Verified</th><th>By</th></tr></thead>
              <tbody>{audit.data.map((a: any) => <tr key={a.id} className="border-t border-ink-100"><td>{fmtDate(a.created_at)}</td><td>{a.scope}</td><td>{a.deleted_count}</td><td>{a.verified ? "✔" : "✖"}</td><td>{a.requested_by}</td></tr>)}</tbody></table>
          )}
        </Card>
      </div>
      <Card className="mt-4" title={<span className="flex items-center gap-2"><ShieldAlert className="h-4 w-4 text-amber-600" />Limitations (honest)</span>}>
        <ul className="list-disc space-y-1 pl-5 text-sm text-ink-600">
          <li>Backups or copies of the data folder made outside Mnemos are not reached by deletion.</li>
          <li>Files are zero-overwritten before unlinking, but SSD wear-levelling and OS caches can retain old blocks; full-disk encryption is the real mitigation.</li>
          <li>Salted term hashes in the audit allow “this was deleted” answers; a determined attacker with DB access could test guessed words against them.</li>
          <li>Anything an external agent already copied out of Mnemos (e.g. into its own logs) cannot be recalled.</li>
        </ul>
      </Card>
    </div>
  );
}
