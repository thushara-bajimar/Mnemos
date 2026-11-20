import {
  Activity, ArrowRightLeft, Bot, Brain, Database, FlaskConical, GitCompareArrows, LayoutDashboard, Menu, Search,
  Settings as SettingsIcon, Swords, Trash2, X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { cx } from "./components/ui";
import Agents from "./pages/Agents";
import Conflicts from "./pages/Conflicts";
import DecisionLab from "./pages/DecisionLab";
import Evaluation from "./pages/Evaluation";
import Forgetting from "./pages/Forgetting";
import Handover from "./pages/Handover";
import Memories from "./pages/Memories";
import Overview from "./pages/Overview";
import Retrieval from "./pages/Retrieval";
import Settings from "./pages/Settings";
import Storage from "./pages/Storage";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/memories", label: "Memory Explorer", icon: Database },
  { to: "/decide", label: "Decision Lab", icon: Brain },
  { to: "/retrieval", label: "Retrieval & Budget", icon: Search },
  { to: "/conflicts", label: "Contradictions", icon: Swords },
  { to: "/forget", label: "Forgetting", icon: Trash2 },
  { to: "/agents", label: "Agent Workspace", icon: Bot },
  { to: "/handover", label: "Task Handover", icon: ArrowRightLeft },
  { to: "/storage", label: "Storage Strategies", icon: GitCompareArrows },
  { to: "/evaluation", label: "Evaluation Lab", icon: FlaskConical },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export default function App() {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen bg-ink-50 text-ink-800">
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-ink-200 bg-white px-4 py-2 lg:hidden">
        <Brand />
        <button aria-label="Toggle navigation" onClick={() => setOpen(!open)} className="rounded p-1 hover:bg-ink-100">
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </header>
      <div className="flex">
        <aside className={cx("fixed inset-y-0 left-0 z-40 w-60 shrink-0 border-r border-ink-800 bg-ink-950 p-3 text-ink-200 transition-transform lg:sticky lg:top-0 lg:h-screen lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full")}>
          <div className="mb-5 hidden px-2 pt-2 lg:block"><Brand dark /></div>
          <nav className="space-y-0.5">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)}
                className={({ isActive }) => cx("flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition",
                  isActive ? "bg-brand-600 text-white" : "text-ink-300 hover:bg-ink-900 hover:text-white")}>
                <Icon className="h-4 w-4" /> {label}
              </NavLink>
            ))}
          </nav>
          <div className="absolute bottom-3 left-3 right-3 rounded-lg bg-ink-900 p-3 text-[11px] leading-relaxed text-ink-400">
            <Activity className="mb-1 h-3.5 w-3.5 text-emerald-400" />
            Local-first. No paid AI services. Memories are data, never instructions.
          </div>
        </aside>
        {open && <div className="fixed inset-0 z-30 bg-black/30 lg:hidden" onClick={() => setOpen(false)} />}
        <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/memories" element={<Memories />} />
            <Route path="/decide" element={<DecisionLab />} />
            <Route path="/retrieval" element={<Retrieval />} />
            <Route path="/conflicts" element={<Conflicts />} />
            <Route path="/forget" element={<Forgetting />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/handover" element={<Handover />} />
            <Route path="/storage" element={<Storage />} />
            <Route path="/evaluation" element={<Evaluation />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<div className="text-sm text-ink-500">Page not found.</div>} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function Brand({ dark }: { dark?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <div className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 font-bold text-white">M</div>
      <div>
        <div className={cx("text-sm font-semibold", dark ? "text-white" : "text-ink-900")}>Mnemos</div>
        <div className={cx("text-[10px]", dark ? "text-ink-400" : "text-ink-500")}>Memory with Meaning. Context with Control.</div>
      </div>
    </div>
  );
}
