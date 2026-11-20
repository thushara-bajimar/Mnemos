# Prompt for a slide-generation tool

Copy everything below the line into your slide tool (Gamma, Beautiful.ai, Tome, Canva Magic Design,
Google Slides with Gemini, PowerPoint Copilot, or similar). Then upload the images listed under
"Assets" when the tool asks for them, or place them by hand.

---

Create an **11-slide** technical hackathon presentation for a project called **Mnemos**. The
tagline is "Memory with Meaning. Context with Control." Mnemos is a local-first memory system for
AI agents, built for the problem statement "Knowledge Brain: Memory That Knows What to Keep and
When to Forget".

**Audience and tone.** The audience is hackathon judges and engineers. The tone should be
confident, precise and honest. The deck should be technical but understandable, with little text
per slide: at most 5 bullets of at most 14 words each. Put detail in the speaker notes.

**Visual style**

* A clean, modern dark-navy theme: background `#13151f`, text `#eceef2`.
* One accent colour, royal blue `#3866f6`. Use green `#10b981` for good results and amber
  `#f59e0b` for warnings and baselines.
* Sans-serif fonts (Inter or similar); monospace for code-like terms such as `STORE` and `cl100k_base`.
* Generous whitespace and one strong visual per slide. No stock photos of robots or brains;
  prefer diagrams, the provided screenshots and the provided charts.
* Tables must stay small: at most 5 rows and 4 columns.

**Accuracy rules (important)**

* Use ONLY the numbers given below. Do not invent metrics, users, customers or claims.
* Do not describe the bundled agents as LLM-powered. They are deterministic, rule-based agents.
* Keep the limitations slide. Honesty is part of the pitch.

**Slides**

1. **Title.** "Mnemos — Memory with Meaning. Context with Control." Subtitle: "Knowledge Brain:
   memory that knows what to keep and when to forget." Small line: "Local-first · FastAPI ·
   SQLite · React · no paid AI services."
2. **The problem.** A 4×2 grid of icons and labels: stores everything (noise and secrets); silent
   overwrite (stale facts); weak retrieval; whole-history prompts (token waste); no provenance;
   fake forgetting; memory poisoning; siloed agents.
3. **Why existing approaches fall short.** Vector stores have no notion of truth, time, trust or
   deletion. Summaries lose detail and keep stale values. History windows forget early facts.
   Highlight one measured stat: "a 500-token history window contained the answer for only 12.5% of
   questions." Use the chart `context_support.png`.
4. **The Mnemos idea: six questions.** Keep it? What is it? Where should it live? Is it new, a
   repeat or a contradiction? What does this task need within N tokens? How do we prove it's gone?
   Show the seven decision actions as chips: STORE, UPDATE, MERGE, TEMPORARY, DISCARD,
   NEEDS_CONFIRMATION, FLAG_CONFLICT.
5. **Architecture.** Use the image `architecture.png`. Caption: "3 agents → FastAPI + ToolGateway →
   safety scan → classifier → decision engine → router → 5 stores (structured, keyword/FTS5,
   vector, graph, file) in one SQLite file."
6. **Decision mechanism.** Left: the scores (relevance, utility, confidence, durability,
   redundancy, privacy risk, injection risk, source trust). Right: four live examples.
   "ok thanks!" → DISCARD. "My password is …" → DISCARD (secret). "Actually, the deadline is now
   Feb 3" → UPDATE (history kept). A web post "budget is 900000" contradicting a document →
   FLAG_CONFLICT (quarantined). Image: `decision.png`.
7. **Storage and provenance.** A small table (R-precision / MRR / query ms): keyword 0.595 / 0.775 /
   0.09; vector 0.821 / 0.897 / 0.06; graph 0.333 / 0.627 / 0.12; **hybrid 0.976 / 1.000 / 4.60**.
   Caption: "220 memories, 63 labelled queries." One line on provenance: source, agent, session,
   method, versions and derived memories, all traceable. Chart: `storage_quality.png`.
8. **Retrieval and token efficiency.** Answers carry a status: answered, conflicting,
   low_confidence, deleted, expired or unknown ("never guesses"). The headline comparison uses a
   1,430-turn conversation (12,437 tokens) and 24 questions. At 500 tokens: full history 12.5%,
   summary 16.7%, **Mnemos 100% using 404 tokens**. At 5,000 tokens: 75% / 83% / **100% using 546
   tokens**. Chart: `context_tokens.png`.
9. **Forgetting and privacy.** Flow: plan → confirm token → execute → verify → audit. Scopes are
   id, topic, entity and source, with cascades. Verification scans every store plus the raw
   database, WAL and file bytes. Finding: "with SQLite secure_delete OFF, deleted text survived in
   the file; with it ON, it was gone." Secrets are never stored and PII is redacted. Image:
   `forgetting.png`.
10. **Agents and handover.** Atlas (Python SDK), Bolt (JSON tool calls) and Relay (Node.js over
    REST) share one memory. The handover package holds the task, progress, decisions, constraints,
    unfinished steps, memories with sources, a budgeted context and a SHA-256 checksum. Live
    result: "completed at 993/1,000 tokens; steps done by Atlas, Atlas, Bolt, Bolt; tampered
    packages rejected." Images: `handover.png` and `agents.png`.
11. **Results, limitations, conclusion.** Results: 53/53 scenarios passed; 95 backend and 4
    frontend tests pass; 100% vs 12.5% answer support at 500 tokens. Limitations: rule-based
    extraction; lexical (not neural) embeddings; synthetic evaluation written by the same authors;
    deterministic agents; cannot erase external backups. Next steps: LLM extractor with a rules
    fallback, neural embeddings with an ANN index, an MCP server, public benchmarks. Closing line:
    "Memory that is selective, explainable, verifiable — and frugal."

**Speaker notes.** For every slide, write 3–4 sentences that explain the slide in plain language,
mention where the evidence comes from ("measured by the evaluation lab"), and include one
transition sentence to the next slide.

**Assets** (from the repository folder `docs/images/`):

* `charts/architecture.png`
* `charts/context_support.png`
* `charts/context_tokens.png`
* `charts/storage_quality.png`
* `charts/scenarios.png`
* `overview.png`
* `decision.png`
* `forgetting.png`
* `handover.png`
* `agents.png`
* `evaluation.png`
* `explorer.png`
