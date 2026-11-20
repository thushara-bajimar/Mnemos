"""Build the Mnemos PDFs from the Markdown docs and the measured evaluation results.

    python scripts/build_pdfs.py

Outputs
  docs/Mnemos_Technical_Documentation.pdf   (from TECHNICAL_DOCUMENTATION.md + figures)
  docs/Mnemos_Project_Report.pdf            (from docs/PROJECT_REPORT.md + screenshots + charts)
  docs/images/charts/*.png                  (charts generated from docs/results/latest_eval.json)

Nothing is hard-coded: every number in the report tables and charts is read from
docs/results/latest_eval.json (produced by POST /api/eval/run).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.pdfbase import pdfmetrics  # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont  # noqa: E402
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate,  # noqa: E402
                                Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CHARTS = DOCS / "images" / "charts"
RESULTS = DOCS / "results" / "latest_eval.json"

BRAND = colors.HexColor("#2248eb")
INK = colors.HexColor("#1e2230")
MUTED = colors.HexColor("#667391")
LINE = colors.HexColor("#d5d9e2")
SOFT = colors.HexColor("#f6f7f9")

# ------------------------------------------------------------------ fonts
FONT, FONT_B, FONT_I, MONO = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Courier"


def _register_fonts() -> None:
    """Prefer TrueType fonts with wide Unicode coverage (arrows, ×, ≥, box drawing)."""
    global FONT, FONT_B, FONT_I, MONO
    candidates = [
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/ariali.ttf", "C:/Windows/Fonts/consola.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    ]
    for reg, bold, ital, mono in candidates:
        if all(Path(p).exists() for p in (reg, bold, ital, mono)):
            pdfmetrics.registerFont(TTFont("Body", reg))
            pdfmetrics.registerFont(TTFont("Body-Bold", bold))
            pdfmetrics.registerFont(TTFont("Body-Italic", ital))
            pdfmetrics.registerFont(TTFont("Mono", mono))
            from reportlab.pdfbase.pdfmetrics import registerFontFamily

            registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic", boldItalic="Body-Bold")
            FONT, FONT_B, FONT_I, MONO = "Body", "Body-Bold", "Body-Italic", "Mono"
            return


_register_fonts()

ss = getSampleStyleSheet()
S = {
    "body": ParagraphStyle("body", parent=ss["BodyText"], fontName=FONT, fontSize=9.6, leading=13.6, textColor=INK, spaceAfter=5),
    "h1": ParagraphStyle("h1", fontName=FONT_B, fontSize=17, leading=22, textColor=BRAND, spaceBefore=10, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName=FONT_B, fontSize=13.5, leading=18, textColor=INK, spaceBefore=12, spaceAfter=6),
    "h3": ParagraphStyle("h3", fontName=FONT_B, fontSize=11, leading=15, textColor=INK, spaceBefore=8, spaceAfter=4),
    "bullet": ParagraphStyle("bullet", fontName=FONT, fontSize=9.6, leading=13.4, textColor=INK, leftIndent=14, bulletIndent=4, spaceAfter=2),
    "code": ParagraphStyle("code", fontName=MONO, fontSize=7.4, leading=9.4, textColor=INK, backColor=SOFT, borderPadding=6,
                           leftIndent=4, rightIndent=4, spaceBefore=4, spaceAfter=8),
    "cell": ParagraphStyle("cell", fontName=FONT, fontSize=7.8, leading=10, textColor=INK),
    "cellh": ParagraphStyle("cellh", fontName=FONT_B, fontSize=7.8, leading=10, textColor=colors.white),
    "caption": ParagraphStyle("caption", fontName=FONT_I, fontSize=8.2, leading=11, textColor=MUTED, alignment=TA_CENTER, spaceAfter=10),
    "title": ParagraphStyle("title", fontName=FONT_B, fontSize=34, leading=40, textColor=BRAND, alignment=TA_CENTER),
    "subtitle": ParagraphStyle("subtitle", fontName=FONT, fontSize=14, leading=20, textColor=INK, alignment=TA_CENTER),
    "meta": ParagraphStyle("meta", fontName=FONT, fontSize=10, leading=15, textColor=MUTED, alignment=TA_CENTER),
}


# ------------------------------------------------------------------ inline markdown
def inline(text: str) -> str:
    t = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = re.sub(r"`([^`]+)`", lambda m: f'<font face="{MONO}" size="8.4" color="#1c2d8a">{m.group(1)}</font>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<font color="#2248eb">{m.group(1)}</font>', t)
    return t


def _table(rows: list[list[str]], width: float) -> Table:
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    data = [[Paragraph(inline(c), S["cellh"] if i == 0 else S["cell"]) for c in r] for i, r in enumerate(rows)]
    lens = [max(len(r[j]) for r in rows) + 4 for j in range(ncol)]
    tot = sum(lens)
    widths = [max(width * 0.13, width * L / tot) for L in lens]
    scale = width / sum(widths)
    t = Table(data, colWidths=[w * scale for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _image(path: Path, caption: str, width: float) -> list:
    if not path.exists():
        return [Paragraph(f"[missing image: {path.name}]", S["caption"])]
    from reportlab.lib.utils import ImageReader

    iw, ih = ImageReader(str(path)).getSize()
    w = min(width, iw)
    h = w * ih / iw
    max_h = 19 * cm
    if h > max_h:
        h = max_h
        w = h * iw / ih
    return [KeepTogether([Image(str(path), width=w, height=h), Paragraph(inline(caption), S["caption"])])]


def md_to_flowables(md: str, base: Path, width: float, skip_first_h1: bool = False) -> list:
    out: list = []
    lines = md.splitlines()
    i = 0
    para: list[str] = []
    seen_h1 = False

    def flush():
        if para:
            out.append(Paragraph(inline(" ".join(s.strip() for s in para)), S["body"]))
            para.clear()

    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if s.startswith("```"):
            flush()
            j = i + 1
            buf = []
            while j < len(lines) and not lines[j].strip().startswith("```"):
                buf.append(lines[j])
                j += 1
            out.append(Preformatted("\n".join(buf), S["code"], maxLineLength=118))
            i = j + 1
            continue
        if not s:
            flush()
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            flush()
            lvl = len(m.group(1))
            if lvl == 1 and skip_first_h1 and not seen_h1:
                seen_h1 = True
                i += 1
                continue
            out.append(Paragraph(inline(m.group(2)), S["h1" if lvl == 1 else "h2" if lvl == 2 else "h3"]))
            i += 1
            continue
        if s in ("---", "***"):
            flush()
            i += 1
            continue
        im = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", s)
        if im:
            flush()
            out += _image((base / im.group(2)).resolve(), im.group(1), width)
            i += 1
            continue
        if s.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            out.append(_table(rows, width))
            out.append(Spacer(1, 6))
            continue
        bm = re.match(r"^(\s*)([*\-]|\d+\.)\s+(.*)$", ln)
        if bm:
            flush()
            indent = len(bm.group(1)) // 2
            text = bm.group(3)
            # continuation lines
            while i + 1 < len(lines) and lines[i + 1].startswith(" " * (len(bm.group(1)) + 2)) and lines[i + 1].strip() \
                    and not re.match(r"^\s*([*\-]|\d+\.)\s+", lines[i + 1]):
                i += 1
                text += " " + lines[i].strip()
            sym = "•" if bm.group(2) in "*-" else bm.group(2)
            st = ParagraphStyle("b", parent=S["bullet"], leftIndent=14 + 12 * indent, bulletIndent=4 + 12 * indent)
            out.append(Paragraph(inline(text), st, bulletText=sym))
            i += 1
            continue
        para.append(ln)
        i += 1
    flush()
    return out


# ------------------------------------------------------------------ charts
def make_charts(res: dict) -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    d = res["details"]
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    palette = {"full_history": "#94a3b8", "summary": "#f59e0b", "selected": "#3866f6"}

    # context: answer support
    budgets = [500, 1000, 2000, 5000]
    rows = d["context"]["rows"]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    for strat, c in palette.items():
        ys = [next(r["answer_support"] for r in rows if r["strategy"] == strat and r["budget"] == b) for b in budgets]
        ax.plot([str(b) for b in budgets], ys, marker="o", color=c, lw=2.5 if strat == "selected" else 1.8, label=strat)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("token budget")
    ax.set_ylabel("answer support")
    ax.set_title("Answer support vs token budget (24 questions)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS / "context_support.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    w = 0.26
    for k, (strat, c) in enumerate(palette.items()):
        ys = [next(r["avg_tokens"] for r in rows if r["strategy"] == strat and r["budget"] == b) for b in budgets]
        ax.bar([x + (k - 1) * w for x in range(len(budgets))], ys, w, color=c, label=strat)
    ax.set_xticks(range(len(budgets)), [str(b) for b in budgets])
    ax.set_xlabel("token budget")
    ax.set_ylabel("avg tokens sent")
    ax.set_title("Tokens actually sent per question")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS / "context_tokens.png", dpi=180)
    plt.close(fig)

    st = d["storage"]["rows"]
    names = [r["strategy"] for r in st]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    for k, (key, lab, c) in enumerate([("r_precision", "R-precision", "#3866f6"), ("recall_at_5", "Recall@5", "#10b981"), ("mrr", "MRR", "#8b5cf6")]):
        ax.bar([x + (k - 1) * w for x in range(len(names))], [r[key] for r in st], w, label=lab, color=c)
    ax.set_xticks(range(len(names)), names)
    ax.set_ylim(0, 1.1)
    ax.set_title("Retrieval quality by storage strategy")
    ax.legend(frameon=False, ncol=3)
    fig.tight_layout()
    fig.savefig(CHARTS / "storage_quality.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    ax.bar(names, [r["query_ms_mean"] for r in st], color="#f59e0b", label="mean")
    ax.scatter(names, [r["query_ms_p95"] for r in st], color="#ef4444", zorder=3, label="p95")
    ax.set_ylabel("ms per query")
    ax.set_title("Query latency by storage strategy")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS / "storage_latency.png", dpi=180)
    plt.close(fig)

    cats = d["scenarios"]["by_category"]
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    ks = list(cats)
    ax.bar(ks, [cats[k]["passed"] for k in ks], color="#10b981", label="passed")
    ax.bar(ks, [cats[k]["total"] - cats[k]["passed"] for k in ks], bottom=[cats[k]["passed"] for k in ks], color="#ef4444", label="failed")
    ax.set_title(f"Scenarios: {d['scenarios']['passed']}/{d['scenarios']['total']} passed")
    plt.setp(ax.get_xticklabels(), rotation=35, ha="right")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(CHARTS / "scenarios.png", dpi=180)
    plt.close(fig)

    architecture_diagram()


def architecture_diagram() -> None:
    fig, ax = plt.subplots(figsize=(9, 6.2))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 70)
    ax.axis("off")

    def box(x, y, w, h, text, fc, ec="#1e2230", fs=8.5, bold=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=fc, ec=ec, lw=1))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, weight="bold" if bold else "normal", wrap=True)

    def arrow(x1, y1, x2, y2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color="#515c78", lw=1.2))

    # agents
    for i, (t, sub) in enumerate([("Atlas", "Python SDK"), ("Bolt", "JSON tool calls"), ("Relay", "Node.js · REST"), ("Dashboard", "React UI")]):
        box(4 + i * 24, 60, 19, 7, f"{t}\n{sub}", "#dae6ff", fs=8)
    box(4, 49, 91, 6, "FastAPI REST API  ·  ToolGateway  ·  validation  ·  API-key guard", "#eef4ff", bold=True)
    for i in range(4):
        arrow(13.5 + i * 24, 60, 13.5 + i * 24, 55.3)
    # pipeline
    steps = ["Safety scan", "Classifier", "Decision\nengine", "Storage\nrouter"]
    for i, t in enumerate(steps):
        box(4 + i * 17, 36, 14, 8, t, "#fef3c7", fs=8)
        if i:
            arrow(4 + i * 17 - 3, 40, 4 + i * 17, 40)
    box(73, 36, 22, 8, "Retriever\nhybrid · abstain · budget", "#d1fae5", fs=8)
    box(4, 26, 44, 6.5, "MemoryService: provenance · revisions · conflicts · expiry", "#f3e8ff", fs=8)
    box(51, 26, 44, 6.5, "ForgettingService: plan → execute → verify → audit", "#fee2e2", fs=8)
    arrow(50, 49, 50, 44.3)
    # stores
    stores = [("Structured", "SQLite rows"), ("Keyword", "FTS5 · BM25"), ("Vector", "hash embeddings"), ("Graph", "entities · edges"), ("File", "Markdown")]
    for i, (t, sub) in enumerate(stores):
        box(4 + i * 18.4, 9, 16, 9, f"{t}\n{sub}", "#e2e8f0", fs=8)
        arrow(4 + i * 18.4 + 8, 25.7, 4 + i * 18.4 + 8, 18.3)
    ax.text(50, 3.5, "SQLite (WAL, secure_delete=ON)  +  backend/data/files", ha="center", fontsize=8.5, color="#515c78")
    ax.set_title("Mnemos architecture", fontsize=12, weight="bold", color="#2248eb")
    fig.tight_layout()
    fig.savefig(CHARTS / "architecture.png", dpi=180)
    plt.close(fig)


# ------------------------------------------------------------------ report placeholders
def fill_report(md: str, res: dict) -> str:
    d = res["details"]
    sc = d["scenarios"]
    cats = ", ".join(f"{k} {v['passed']}/{v['total']}" for k, v in sc["by_category"].items())
    scen = f"**{sc['passed']} of {sc['total']} scenarios passed.** By category: {cats}."
    failed = [r for r in sc["rows"] if not r["passed"]]
    if failed:
        scen += " Failed: " + "; ".join(f"{r['id']} {r['title']}" for r in failed) + "."
    ctx = ["| Budget | Strategy | Answer support | Stale risk | Avg tokens | Within budget |", "|---|---|---|---|---|---|"]
    for r in d["context"]["rows"]:
        ctx.append(f"| {r['budget']} | {r['strategy']} | {r['answer_support']:.3f} | {r['stale_risk']:.3f} | {r['avg_tokens']:.0f} | {'yes' if r['within_budget'] else 'NO'} |")
    ds = d["context"]["dataset"]
    ctx.append("")
    ctx.append(f"Dataset: {ds['turns']} turns, {ds['full_history_tokens']} tokens of full history, {ds['questions']} questions. "
               f"Mnemos decisions while processing the transcript: " + ", ".join(f"{k} {v}" for k, v in ds["mnemos_decisions"].items()) + ".")
    sto = ["| Strategy | R-precision | Recall@5 | MRR | Query ms (mean) | Disk KB | Update correct | Delete physical |", "|---|---|---|---|---|---|---|---|"]
    for r in d["storage"]["rows"]:
        sto.append(f"| {r['strategy']} | {r['r_precision']:.3f} | {r['recall_at_5']:.3f} | {r['mrr']:.3f} | {r['query_ms_mean']:.2f} | "
                   f"{r['storage_bytes'] / 1024:.0f} | {'yes' if r['update_correct'] else 'no'} | {'yes' if r['delete_physical'] else 'no'} |")
    sd = d["storage"]["secure_delete_demo"]
    sdt = (f"**SQLite secure_delete check:** with it OFF, deleted text was "
           f"{'found' if sd['secure_delete_off']['token_found_in_file_after_delete'] else 'not found'} in the database file; with it ON, it was "
           f"{'found' if sd['secure_delete_on']['token_found_in_file_after_delete'] else 'not found'}.")
    tok = d["tokenizer"]["tokenizer"] + (" (estimate)" if d["tokenizer"]["is_estimate"] else "")
    return (md.replace("{{SCENARIO_SUMMARY}}", scen).replace("{{CONTEXT_TABLE}}", "\n".join(ctx))
            .replace("{{STORAGE_TABLE}}", "\n".join(sto)).replace("{{SECURE_DELETE}}", sdt).replace("{{TOKENIZER}}", tok))


# ------------------------------------------------------------------ documents
def _decorate(title: str):
    def on_page(canv, doc):
        canv.saveState()
        if doc.page > 1:
            canv.setFont(FONT, 7.5)
            canv.setFillColor(MUTED)
            canv.drawString(2 * cm, A4[1] - 1.2 * cm, f"Mnemos · {title}")
            canv.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Page {doc.page}")
            canv.setStrokeColor(LINE)
            canv.line(2 * cm, A4[1] - 1.35 * cm, A4[0] - 2 * cm, A4[1] - 1.35 * cm)
        canv.restoreState()
    return on_page


def cover(title: str, subtitle: str, lines: list[str]) -> list:
    out = [Spacer(1, 5 * cm), Paragraph("Mnemos", S["title"]), Spacer(1, 0.4 * cm),
           Paragraph("Memory with Meaning. Context with Control.", S["subtitle"]), Spacer(1, 1.6 * cm),
           Paragraph(f"<b>{title}</b>", ParagraphStyle("ct", parent=S["subtitle"], fontName=FONT_B, fontSize=18, leading=24)),
           Spacer(1, 0.4 * cm), Paragraph(subtitle, S["meta"]), Spacer(1, 3 * cm)]
    out += [Paragraph(x, S["meta"]) for x in lines]
    out.append(PageBreak())
    return out


def build(path: Path, title: str, story: list) -> None:
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.9 * cm,
                            bottomMargin=1.8 * cm, title=f"Mnemos — {title}", author="Mnemos project",
                            subject="Knowledge Brain: Memory That Knows What to Keep and When to Forget")
    deco = _decorate(title)
    doc.build(story, onFirstPage=deco, onLaterPages=deco)


def main() -> int:
    if not RESULTS.exists():
        print("docs/results/latest_eval.json not found — run POST /api/eval/run {'suite':'all'} first", file=sys.stderr)
        return 1
    res = json.loads(RESULTS.read_text(encoding="utf-8"))
    make_charts(res)
    width = A4[0] - 4 * cm
    today = date.today().isoformat()
    run_at = res.get("created_at", "")[:19].replace("T", " ")

    # Technical documentation
    tech_md = (ROOT / "TECHNICAL_DOCUMENTATION.md").read_text(encoding="utf-8")
    story = cover("Technical Documentation", "Knowledge Brain: Memory That Knows What to Keep and When to Forget",
                  [f"Version 1.0 · generated {today}", f"Results from evaluation run {res.get('id', '')} ({run_at} UTC)"])
    story += md_to_flowables(tech_md, ROOT, width, skip_first_h1=True)
    story += [PageBreak(), Paragraph("Appendix A — Figures from the measured evaluation", S["h1"])]
    for f, cap in [("architecture.png", "Figure A1 — System architecture"), ("scenarios.png", "Figure A2 — Scenario results by category"),
                   ("context_support.png", "Figure A3 — Answer support vs token budget"), ("context_tokens.png", "Figure A4 — Tokens sent per question"),
                   ("storage_quality.png", "Figure A5 — Retrieval quality by storage strategy"), ("storage_latency.png", "Figure A6 — Query latency by strategy")]:
        story += _image(CHARTS / f, cap, width * 0.92)
    story += [PageBreak(), Paragraph("Appendix B — Related documents", S["h1"])]
    for name in ["ARCHITECTURE.md", "MEMORY_DESIGN.md", "PROVENANCE_AND_CONTRADICTION.md", "FORGETTING_AND_PRIVACY.md",
                 "AGENT_INTEROPERABILITY.md", "API_DOCUMENTATION.md", "TESTING_AND_EVALUATION.md"]:
        story += [PageBreak()] + md_to_flowables((ROOT / name).read_text(encoding="utf-8"), ROOT, width)
    out1 = DOCS / "Mnemos_Technical_Documentation.pdf"
    build(out1, "Technical Documentation", story)

    # Project report
    rep_md = fill_report((DOCS / "PROJECT_REPORT.md").read_text(encoding="utf-8"), res)
    story = cover("Project Report", "Knowledge Brain: Memory That Knows What to Keep and When to Forget",
                  [f"Generated {today}", f"All results measured in evaluation run {res.get('id', '')} ({run_at} UTC)"])
    story += md_to_flowables(rep_md, DOCS, width, skip_first_h1=True)
    out2 = DOCS / "Mnemos_Project_Report.pdf"
    build(out2, "Project Report", story)

    for p in (out1, out2):
        print(f"wrote {p.relative_to(ROOT)} ({p.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
