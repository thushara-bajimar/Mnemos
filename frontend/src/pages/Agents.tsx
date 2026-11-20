import { Bot, Send } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorBox, Input, Mono, PageHeader, fmtDate } from "../components/ui";
import { api, post } from "../lib/api";
import { useLoad } from "../lib/hooks";

type Msg = { who: "you" | "agent"; text: string; detail?: any };

function AgentPane({ id, name, blurb, onAfter }: { id: string; name: string; blurb: string; onAfter: () => void }) {
  const [text, setText] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function send() {
    if (!text.trim()) return;
    const m = text;
    setText(""); setBusy(true); setErr(null);
    setMsgs((x) => [...x, { who: "you", text: m }]);
    try {
      const r = await post(`/api/agents/${id}/chat`, { message: m });
      setMsgs((x) => [...x, { who: "agent", text: r.reply, detail: r.memory_ops?.length ? r.memory_ops : r.tool_calls }]);
      onAfter();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }
  return (
    <Card title={<span className="flex items-center gap-2"><Bot className="h-4 w-4 text-brand-600" />{name}</span>}>
      <p className="mb-2 text-xs text-ink-500">{blurb}</p>
      <ErrorBox error={err} />
      <div className="mb-2 h-72 space-y-2 overflow-y-auto rounded-lg bg-ink-50 p-2">
        {!msgs.length && <div className="p-4 text-center text-xs text-ink-400">Tell {name} a fact (statement) or ask a question (end with “?”).</div>}
        {msgs.map((m, i) => (
          <div key={i} className={m.who === "you" ? "text-right" : ""}>
            <div className={`inline-block max-w-[90%] rounded-lg px-3 py-1.5 text-sm ${m.who === "you" ? "bg-brand-600 text-white" : "bg-white text-ink-800 shadow-sm"}`}>{m.text}</div>
            {m.detail && <details className="mt-0.5 text-[11px] text-ink-500"><summary className="cursor-pointer">{id === "bolt" ? "JSON tool calls" : "memory operations"}</summary><pre className="rounded bg-ink-900 p-2 text-left font-mono text-ink-100">{JSON.stringify(m.detail, null, 1)}</pre></details>}
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <Input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder={`Message ${name}…`} aria-label={`Message ${name}`} />
        <Button busy={busy} onClick={send}><Send className="h-4 w-4" /></Button>
      </div>
    </Card>
  );
}

export default function Agents() {
  const agents = useLoad(() => api("/api/agents"));
  const log = useLoad(() => api("/api/agents/log?limit=40"));
  const refresh = () => { agents.reload(); log.reload(); };
  return (
    <div>
      <PageHeader title="Agent Workspace" subtitle="Two different agent implementations share one persistent memory. Tell Atlas something, then ask Bolt — Bolt answers from the shared store." />
      <ErrorBox error={agents.error} />
      <div className="grid gap-4 lg:grid-cols-2">
        <AgentPane id="atlas" name="Atlas · planner" blurb="In-process Python SDK (MemoryClient). Splits your message into statements and runs each through the decision engine." onAfter={refresh} />
        <AgentPane id="bolt" name="Bolt · executor" blurb="Talks to memory only through JSON tool calls via the ToolGateway — the same protocol external agents use at POST /api/tools/invoke." onAfter={refresh} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card title="Registered agents">
          {!agents.data?.length ? <Empty>No agents.</Empty> : (
            <ul className="space-y-2 text-sm">{agents.data.map((a: any) => (
              <li key={a.id} className="rounded border border-ink-100 p-2">
                <div className="flex items-center gap-2 font-medium">{a.name} <Mono>{a.id}</Mono><Badge tone="type">{a.kind}</Badge></div>
                <div className="text-xs text-ink-500">{a.integration}</div>
                <div className="text-xs text-ink-500">{a.memories_written} memories written · {a.actions} logged actions</div>
              </li>))}</ul>
          )}
          <p className="mt-2 text-xs text-ink-500">External: run <Mono>node agents/node_agent.mjs demo</Mono> to register the Node.js agent “relay”.</p>
        </Card>
        <Card title="Activity log (redacted)" className="lg:col-span-2">
          {!log.data?.length ? <Empty>No activity yet.</Empty> : (
            <ul className="max-h-80 divide-y divide-ink-100 overflow-y-auto text-xs">{log.data.map((l: any) => (
              <li key={l.id} className="flex gap-2 py-1.5"><Badge tone="type">{l.agent_id}</Badge><Badge tone="src">{l.kind}</Badge><span className="flex-1 text-ink-700">{l.message}</span><span className="whitespace-nowrap text-ink-400">{fmtDate(l.created_at)}</span></li>
            ))}</ul>
          )}
        </Card>
      </div>
    </div>
  );
}
