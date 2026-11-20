import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { api, ApiError } from "./lib/api";

const STATS = {
  total_memories: 3, by_status: { active: 3 }, by_type: { semantic: 2, preference: 1 }, by_decision: { STORE: 3, DISCARD: 1 },
  by_source: { user: 3 }, by_route: { structured: 3 }, open_conflicts: 0, pending_confirmations: 0, deletions: 0, expired: 0,
  entities: 2, edges: 1, vectors: 3, files: 0, handovers: 0, tasks: 0, eval_runs: 0, db_bytes: 4096, file_bytes: 0,
  tokenizer: { tokenizer: "tiktoken:cl100k_base", is_estimate: false }, embedder: "hashing-ngram-v1",
};

function mockFetch(routes: Record<string, unknown>) {
  return vi.fn(async (url: string) => {
    const key = Object.keys(routes).find((k) => url.startsWith(k));
    if (!key) return new Response(JSON.stringify({ detail: "not mocked" }), { status: 404 });
    return new Response(JSON.stringify(routes[key]), { status: 200 });
  });
}

afterEach(() => vi.restoreAllMocks());

describe("Mnemos UI", () => {
  it("renders navigation and overview statistics from the API", async () => {
    vi.stubGlobal("fetch", mockFetch({ "/api/stats": STATS, "/api/decisions": [] }));
    render(<MemoryRouter><App /></MemoryRouter>);
    expect(screen.getAllByText("Memory Explorer").length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText("tiktoken:cl100k_base")).toBeTruthy());
    expect(screen.getByText("Open conflicts")).toBeTruthy();
  });

  it("decision lab shows a dry-run decision with reasons", async () => {
    const decision = {
      decision: { action: "DISCARD", memory_type: "semantic", content: "ok thanks", scores: { relevance: 0, utility: 0.1, confidence: 0.9, durability: 0.8, redundancy: 0, privacy_risk: 0, injection_risk: 0, source_trust: 0.9 },
        reasons: ["filler / small talk carries no durable information"], flags: [], routes: [], route_reasons: [], classification: { signals: [] } },
      memory: null, dry_run: true,
    };
    vi.stubGlobal("fetch", mockFetch({ "/api/decide": decision }));
    render(<MemoryRouter initialEntries={["/decide"]}><App /></MemoryRouter>);
    fireEvent.change(screen.getByPlaceholderText(/deadline for Project Orion/), { target: { value: "ok thanks" } });
    fireEvent.click(screen.getByText("Preview (dry run)"));
    await waitFor(() => expect(screen.getByText("filler / small talk carries no durable information")).toBeTruthy());
    expect(screen.getByText("DISCARD")).toBeTruthy();
  });

  it("api client surfaces backend error details", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "memory not found" }), { status: 404 })));
    await expect(api("/api/memories/x")).rejects.toMatchObject({ status: 404, message: "memory not found" });
  });

  it("api client reports an unreachable backend clearly", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("fetch failed"); }));
    const err = await api("/api/stats").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toMatch(/Cannot reach the Mnemos API/);
  });
});
