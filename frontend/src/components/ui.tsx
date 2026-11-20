import { AlertTriangle, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-ink-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, children, className, actions }: { title?: ReactNode; children: ReactNode; className?: string; actions?: ReactNode }) {
  return (
    <section className={cx("rounded-xl border border-ink-200 bg-white p-4 shadow-sm", className)}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold text-ink-800">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Button({
  children, onClick, variant = "primary", disabled, busy, type = "button", className, title,
}: {
  children: ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "danger" | "ghost";
  disabled?: boolean; busy?: boolean; type?: "button" | "submit"; className?: string; title?: string;
}) {
  const styles = {
    primary: "bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-300",
    secondary: "border border-ink-200 bg-white text-ink-700 hover:bg-ink-50 disabled:text-ink-300",
    danger: "bg-rose-600 text-white hover:bg-rose-700 disabled:bg-rose-300",
    ghost: "text-ink-600 hover:bg-ink-100",
  }[variant];
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled || busy}
      className={cx("inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed", styles, className)}>
      {busy && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx("w-full rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-sm outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100", props.className)} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx("w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100", props.className)} />;
}

export function Select({ value, onChange, options, className, label }: {
  value: string; onChange: (v: string) => void; options: (string | { value: string; label: string })[]; className?: string; label?: string;
}) {
  return (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}
      className={cx("rounded-lg border border-ink-200 bg-white px-2 py-1.5 text-sm outline-none focus:border-brand-400", className)}>
      {options.map((o) => typeof o === "string" ? <option key={o} value={o}>{o || "any"}</option> : <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export function Label({ children }: { children: ReactNode }) {
  return <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-500">{children}</label>;
}

const BADGE: Record<string, string> = {
  STORE: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  UPDATE: "bg-sky-50 text-sky-700 ring-sky-200",
  MERGE: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  TEMPORARY: "bg-amber-50 text-amber-700 ring-amber-200",
  DISCARD: "bg-ink-100 text-ink-600 ring-ink-200",
  NEEDS_CONFIRMATION: "bg-orange-50 text-orange-700 ring-orange-200",
  FLAG_CONFLICT: "bg-rose-50 text-rose-700 ring-rose-200",
  active: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  superseded: "bg-ink-100 text-ink-500 ring-ink-200",
  conflicted: "bg-rose-50 text-rose-700 ring-rose-200",
  quarantined: "bg-fuchsia-50 text-fuchsia-700 ring-fuchsia-200",
  pending_confirmation: "bg-orange-50 text-orange-700 ring-orange-200",
  expired: "bg-amber-50 text-amber-700 ring-amber-200",
  answered: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  unknown: "bg-ink-100 text-ink-600 ring-ink-200",
  deleted: "bg-rose-50 text-rose-700 ring-rose-200",
  conflicting: "bg-rose-50 text-rose-700 ring-rose-200",
  low_confidence: "bg-orange-50 text-orange-700 ring-orange-200",
  pending: "bg-amber-50 text-amber-700 ring-amber-200",
  accepted: "bg-sky-50 text-sky-700 ring-sky-200",
  completed: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  rejected: "bg-rose-50 text-rose-700 ring-rose-200",
  open: "bg-rose-50 text-rose-700 ring-rose-200",
  resolved: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  pass: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  fail: "bg-rose-50 text-rose-700 ring-rose-200",
};

export function Badge({ children, tone }: { children: ReactNode; tone?: string }) {
  const k = tone ?? String(children);
  return <span className={cx("inline-flex items-center whitespace-nowrap rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset", BADGE[k] ?? "bg-brand-50 text-brand-700 ring-brand-200")}>{children}</span>;
}

export function ErrorBox({ error }: { error: string | null | undefined }) {
  if (!error) return null;
  return (
    <div role="alert" className="mb-3 flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> <span>{error}</span>
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="flex items-center gap-2 py-6 text-sm text-ink-500"><Loader2 className="h-4 w-4 animate-spin" /> {label}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-ink-200 px-4 py-6 text-center text-sm text-ink-500">{children}</div>;
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: "good" | "warn" | "bad" }) {
  const c = tone === "good" ? "text-emerald-600" : tone === "warn" ? "text-amber-600" : tone === "bad" ? "text-rose-600" : "text-ink-900";
  return (
    <div className="rounded-xl border border-ink-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</div>
      <div className={cx("mt-1 text-2xl font-semibold tabular-nums", c)}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-ink-400">{hint}</div>}
    </div>
  );
}

export function ScoreBar({ label, value, invert }: { label: string; value: number; invert?: boolean }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const good = invert ? value < 0.35 : value >= 0.6;
  const mid = invert ? value < 0.7 : value >= 0.35;
  return (
    <div className="text-xs">
      <div className="flex justify-between text-ink-600"><span>{label}</span><span className="tabular-nums">{value.toFixed(2)}</span></div>
      <div className="mt-0.5 h-1.5 rounded bg-ink-100">
        <div className={cx("h-1.5 rounded", good ? "bg-emerald-500" : mid ? "bg-amber-500" : "bg-rose-500")} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return <code className="rounded bg-ink-100 px-1 py-0.5 font-mono text-[11px] text-ink-700">{children}</code>;
}

export function fmtDate(s?: string | null) {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString();
}

export function fmtBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

export const CHART_COLORS = ["#3866f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#64748b", "#ec4899"];
