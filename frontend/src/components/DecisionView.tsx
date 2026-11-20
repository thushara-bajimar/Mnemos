import type { Decision } from "../lib/api";
import { Badge, Mono, ScoreBar } from "./ui";

export default function DecisionView({ d }: { d: Decision }) {
  const c = d.classification ?? {};
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>{d.action}</Badge>
        <Badge tone="type">{d.memory_type}</Badge>
        {d.flags.map((f) => <Badge key={f} tone="FLAG_CONFLICT">{f}</Badge>)}
        {d.target_memory_id && <span className="text-xs text-ink-500">target <Mono>{d.target_memory_id}</Mono></span>}
        {d.expires_at && <span className="text-xs text-amber-700">expires {new Date(d.expires_at).toLocaleString()}</span>}
      </div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
        {["relevance", "utility", "confidence", "durability", "source_trust"].map((k) => <ScoreBar key={k} label={k.replace("_", " ")} value={d.scores[k] ?? 0} />)}
        {["redundancy", "privacy_risk", "injection_risk"].map((k) => <ScoreBar key={k} label={k.replace("_", " ")} value={d.scores[k] ?? 0} invert />)}
      </div>
      <div>
        <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-500">Why</div>
        <ol className="list-decimal space-y-1 pl-5 text-sm text-ink-700">{d.reasons.map((r, i) => <li key={i}>{r}</li>)}</ol>
      </div>
      {(c.subject || c.entities?.length) && (
        <div className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-500">Extracted fact</div>
            {c.subject ? <div><Mono>{c.subject}</Mono> · <Mono>{c.attribute}</Mono> = <b>{c.value}</b> <span className="text-xs text-ink-400">({c.extraction})</span></div> : <span className="text-ink-400">none</span>}
          </div>
          <div>
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-500">Entities</div>
            <div className="flex flex-wrap gap-1">{(c.entities ?? []).map((e: string) => <Badge key={e} tone="entity">{e}</Badge>)}</div>
          </div>
        </div>
      )}
      {c.signals?.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-500">Classification signals</div>
          <ul className="list-disc space-y-0.5 pl-5 text-xs text-ink-600">{c.signals.map((s: string, i: number) => <li key={i}>{s}</li>)}</ul>
        </div>
      )}
      {d.routes.length > 0 && (
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-500">Storage routing</div>
          <ul className="space-y-0.5 text-xs text-ink-600">{d.route_reasons.map((s, i) => <li key={i}>→ {s}</li>)}</ul>
        </div>
      )}
      <div className="text-xs text-ink-500">Content as stored (after redaction): <span className="italic text-ink-700">“{d.content}”</span></div>
    </div>
  );
}
