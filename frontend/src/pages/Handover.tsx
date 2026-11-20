import { ArrowRight, CheckCircle2, Circle, Play, Rocket } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorBox, Input, Label, Mono, PageHeader, Select, Textarea, fmtDate } from "../components/ui";
import { api, post } from "../lib/api";
import { useLoad } from "../lib/hooks";

export default function Handover() {
  const tasks = useLoad(() => api("/api/tasks"));
  const handovers = useLoad(() => api("/api/handovers"));
  const agents = useLoad(() => api("/api/agents"));
  const [title, setTitle] = useState("Release billing v2");
  const [goal, setGoal] = useState("release billing v2 of the billing service");
  const [steps, setSteps] = useState("Check the deadline for the billing v2 release\nConfirm which database the billing service uses\nDeploy the billing service following the runbook\nSend the client a status report");
  const [taskId, setTaskId] = useState("");
  const [to, setTo] = useState("bolt");
  const [budget, setBudget] = useState(1000);
  const [notes, setNotes] = useState("");
  const [sel, setSel] = useState<any>(null);
  const [run, setRun] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const reload = () => { tasks.reload(); handovers.reload(); };
  async function act(k: string, fn: () => Promise<void>) {
    setBusy(k); setErr(null);
    try { await fn(); reload(); } catch (e: any) { setErr(e.message); } finally { setBusy(null); }
  }
  const task = tasks.data?.find((t: any) => t.id === taskId);

  return (
    <div>
      <PageHeader title="Task Handover" subtitle="Atlas plans and starts a task, then hands it to another agent with a checksummed, token-budgeted package. The receiver validates it and finishes the work using shared memory."
        actions={<Button busy={busy === "demo"} onClick={() => act("demo", async () => { const d = await post(`/api/demo/handover?budget=${budget}`); setSel(d.handover); setRun(d.bolt_run); setTaskId(d.task.id); })}><Rocket className="h-4 w-4" />Run full demo</Button>} />
      <ErrorBox error={err} />
      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="1 · Atlas plans a task">
          <Label>Title</Label><Input value={title} onChange={(e) => setTitle(e.target.value)} />
          <div className="mt-2"><Label>Goal</Label><Input value={goal} onChange={(e) => setGoal(e.target.value)} /></div>
          <div className="mt-2"><Label>Steps (one per line)</Label><Textarea rows={5} value={steps} onChange={(e) => setSteps(e.target.value)} /></div>
          <Button className="mt-3" busy={busy === "plan"} onClick={() => act("plan", async () => { const t = await post("/api/tasks", { title, goal, steps: steps.split("\n").map((s) => s.trim()).filter(Boolean) }); setTaskId(t.id); })}>Create task</Button>
        </Card>
        <Card title="2 · Atlas works, then hands over" className="xl:col-span-2">
          <div className="grid gap-2 sm:grid-cols-4">
            <div className="sm:col-span-2"><Label>Task</Label><Select className="w-full" value={taskId} onChange={setTaskId} options={[{ value: "", label: "— select —" }, ...(tasks.data ?? []).map((t: any) => ({ value: t.id, label: `${t.title} (${t.status})` }))]} /></div>
            <div><Label>Hand to</Label><Select className="w-full" value={to} onChange={setTo} options={(agents.data ?? []).filter((a: any) => a.id !== "atlas").map((a: any) => a.id)} /></div>
            <div><Label>Token budget</Label><Select className="w-full" value={String(budget)} onChange={(v) => setBudget(Number(v))} options={["300", "500", "1000", "2000", "5000"]} /></div>
          </div>
          {task ? (
            <>
              <ol className="mt-3 space-y-1 text-sm">{task.steps.map((s: any, i: number) => (
                <li key={i} className="flex items-start gap-2">{s.done ? <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-600" /> : <Circle className="mt-0.5 h-4 w-4 text-ink-300" />}
                  <div><span className={s.done ? "text-ink-500" : ""}>{s.text}</span>{s.by && <Badge tone="type">{s.by}</Badge>}{s.note && <div className="text-xs text-ink-500">{s.note}</div>}</div></li>))}</ol>
              {task.constraints.length > 0 && <div className="mt-2 text-xs text-ink-600"><b>Constraints:</b> {task.constraints.join(" · ")}</div>}
              <div className="mt-3"><Label>Notes for receiver</Label><Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="optional" /></div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="secondary" busy={busy === "work"} onClick={() => act("work", async () => { await post(`/api/tasks/${taskId}/work`, { max_steps: 2 }); })}>Atlas: complete 2 steps</Button>
                <Button busy={busy === "hand"} onClick={() => act("hand", async () => { const h = await post("/api/handovers", { task_id: taskId, from_agent: "atlas", to_agent: to, token_budget: budget, notes }); setSel(h); setRun(null); })}><ArrowRight className="h-4 w-4" />Create handover → {to}</Button>
              </div>
            </>
          ) : <div className="mt-3"><Empty>Select or create a task.</Empty></div>}
        </Card>
      </div>

      {sel && (
        <Card className="mt-4" title={<span className="flex items-center gap-2">Handover package <Mono>{sel.id}</Mono><Badge>{sel.status}</Badge><span className="text-xs font-normal text-ink-500">{sel.package_tokens}/{sel.token_budget} tokens · {sel.from_agent} → {sel.to_agent}</span></span>}
          actions={sel.to_agent === "bolt" && sel.status === "pending" && <Button busy={busy === "run"} onClick={() => act("run", async () => { const r = await post(`/api/handovers/${sel.id}/run`); setRun(r); setSel(await api(`/api/handovers/${sel.id}`)); })}><Play className="h-4 w-4" />Bolt: accept & execute</Button>}>
          {sel.to_agent !== "bolt" && sel.status === "pending" && <p className="mb-2 text-xs text-amber-700">Addressed to external agent “{sel.to_agent}”. Run: <Mono>node agents/node_agent.mjs handover {sel.id}</Mono></p>}
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="space-y-2 text-sm">
              <div><b>Task:</b> {sel.package.task.title} — {sel.package.task.goal}</div>
              <div><b>Progress:</b><ul className="list-disc pl-5 text-xs">{sel.package.progress.map((p: any) => <li key={p.index}>{p.text} <span className="text-ink-400">({p.by})</span></li>)}</ul></div>
              <div><b>Unfinished:</b><ul className="list-disc pl-5 text-xs">{sel.package.unfinished_steps.map((p: any) => <li key={p.index}>{p.text}</li>)}</ul></div>
              <div><b>Decisions:</b><ul className="list-disc pl-5 text-xs">{sel.package.decisions.map((d: string, i: number) => <li key={i}>{d}</li>)}</ul></div>
              <div><b>Constraints:</b><ul className="list-disc pl-5 text-xs">{sel.package.constraints.map((d: string, i: number) => <li key={i}>{d}</li>)}</ul></div>
              <div><b>Relevant memories ({sel.package.relevant_memories.length}):</b><ul className="text-xs">{sel.package.relevant_memories.map((m: any) => <li key={m.id}><Mono>{m.id}</Mono> {m.content} <span className="text-ink-400">[{m.sources?.map((s: any) => s.source_type).join(", ")}]</span></li>)}</ul></div>
              <div className="text-xs text-ink-500">Checksum <Mono>{sel.checksum.slice(0, 16)}…</Mono> · {sel.package.policy}</div>
            </div>
            <div>
              <div className="mb-1 text-xs font-semibold uppercase text-ink-500">Context included in package</div>
              <pre className="max-h-96 overflow-auto rounded-lg bg-ink-950 p-3 font-mono text-[11px] text-ink-100">{sel.package.context}</pre>
            </div>
          </div>
        </Card>
      )}

      {run && (
        <Card className="mt-4" title={<span className="flex items-center gap-2">Receiver result <Badge>{run.status}</Badge></span>}>
          {run.validation && <div className="mb-2 text-xs">Validation: {run.validation.valid ? "✔ checksum, budget and status valid" : `✖ ${run.validation.problems?.join("; ")}`}{run.validation.stale_memories?.length ? ` · stale: ${run.validation.stale_memories.length}` : ""}</div>}
          {run.result && <>
            <ul className="space-y-1 text-sm">{run.result.executed_steps.map((s: any) => <li key={s.index}>✔ Step {s.index + 1}: {s.step} <span className="text-xs text-ink-500">(memory {s.ask_status}; evidence {s.evidence.join(", ") || "none"})</span></li>)}</ul>
            <div className="mt-2 text-xs text-ink-500">All steps done: {String(run.result.all_steps_done)} · context {run.result.context_tokens}/{run.result.context_budget} tokens</div>
          </>}
          {run.tool_calls && <details className="mt-2 text-xs"><summary className="cursor-pointer text-ink-600">Bolt’s {run.tool_calls.length} JSON tool calls</summary><pre className="mt-1 max-h-64 overflow-auto rounded bg-ink-900 p-2 font-mono text-ink-100">{JSON.stringify(run.tool_calls.map((t: any) => t.call), null, 1)}</pre></details>}
        </Card>
      )}

      <Card className="mt-4" title="All handovers">
        {!handovers.data?.length ? <Empty>No handovers yet.</Empty> : (
          <table className="table-auto w-full text-sm"><thead><tr><th>Id</th><th>Task</th><th>From → To</th><th>Status</th><th>Tokens</th><th>Created</th></tr></thead>
            <tbody>{handovers.data.map((h: any) => <tr key={h.id} className="cursor-pointer border-t border-ink-100 hover:bg-brand-50/50" onClick={() => { setSel(h); setRun(h.result ? { status: h.status, result: h.result } : null); }}>
              <td><Mono>{h.id}</Mono></td><td>{h.package.task.title}</td><td>{h.from_agent} → {h.to_agent}</td><td><Badge>{h.status}</Badge></td><td>{h.package_tokens}/{h.token_budget}</td><td className="text-xs">{fmtDate(h.created_at)}</td></tr>)}</tbody></table>
        )}
      </Card>
    </div>
  );
}
