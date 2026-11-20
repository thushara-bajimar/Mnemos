// Thin typed client for the Mnemos REST API.
const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function apiKey(): string | null {
  try {
    return localStorage.getItem("mnemos_api_key");
  } catch {
    return null;
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  const key = apiKey();
  if (key) headers["x-api-key"] = key;
  let res: Response;
  try {
    res = await fetch(BASE + path, {
      method: opts.method ?? (opts.body === undefined ? "GET" : "POST"),
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
  } catch {
    throw new ApiError(0, "Cannot reach the Mnemos API. Is the backend running on port 8000?");
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const d = data?.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((x: any) => `${x.loc?.slice(-1)[0]}: ${x.msg}`).join("; ") : res.statusText;
    throw new ApiError(res.status, msg || `HTTP ${res.status}`);
  }
  return data as T;
}

export const post = <T = any>(path: string, body: unknown = {}) => api<T>(path, { body });
export const put = <T = any>(path: string, body: unknown) => api<T>(path, { method: "PUT", body });

export type Memory = {
  id: string;
  content: string;
  memory_type: string;
  status: string;
  subject?: string | null;
  attribute?: string | null;
  value?: string | null;
  entities: string[];
  tags: string[];
  importance: number;
  confidence: number;
  source_trust: number;
  source_type?: string;
  reinforcement: number;
  storage_routes: string[];
  task_id?: string | null;
  agent_id?: string | null;
  session_id?: string | null;
  created_at: string;
  updated_at: string;
  valid_from?: string | null;
  valid_to?: string | null;
  expires_at?: string | null;
  version: number;
  access_count: number;
};

export type Decision = {
  action: string;
  memory_type: string;
  content: string;
  scores: Record<string, number>;
  reasons: string[];
  flags: string[];
  routes: string[];
  route_reasons: string[];
  classification: any;
  target_memory_id?: string | null;
  expires_at?: string | null;
};
