const API_BASE = (window as any).__API_BASE__ || '/api/com.ictrek.desensitize';

export interface Rule {
  id: string;
  name: string;
  description: string;
  pattern: string;
  placeholder: string;
  priority: number;
  enabled: boolean;
  builtin: boolean;
  category: string;
}

export interface ReplacedItem {
  rule: string;
  placeholder: string;
  occurrences: number;
}

export interface DesensitizeTextResponse {
  text: string;
  replaced: ReplacedItem[];
  latency_ms: number;
}

export interface DesensitizeResponse {
  messages: { role: string; content: string }[];
  replaced: ReplacedItem[];
  metadata: { latency_ms: number; engine: string; rule_count: number };
}

export interface AboutInfo {
  service_id: string;
  service: string;
  app_version: string;
  profile: string;
  backend_image: string;
  frontend_image: string;
  ner: {
    enabled: boolean;
    state: string;
    requested_provider: string;
    active_provider: string | null;
    model_id: string;
    model_dir: string;
    max_concurrency: number;
    queue_timeout_seconds: number;
    error: string | null;
  };
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(detail);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

export const api = {
  // Rules
  listRules: (enabledOnly = false) =>
    request<Rule[]>(`/api/v1/rules?enabled_only=${enabledOnly}`),

  listBuiltinRules: () =>
    request<Rule[]>(`/api/v1/rules/builtin`),

  listCustomRules: () =>
    request<Rule[]>(`/api/v1/rules/custom`),

  createRule: (rule: Partial<Rule>) =>
    request<Rule>(`/api/v1/rules`, {
      method: 'POST',
      body: JSON.stringify(rule),
    }),

  updateRule: (id: string, updates: Partial<Rule>) =>
    request<Rule>(`/api/v1/rules/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    }),

  deleteRule: (id: string) =>
    request<void>(`/api/v1/rules/${id}`, { method: 'DELETE' }),

  testPattern: (pattern: string, text: string, placeholder = '[REDACTED]') => {
    const params = new URLSearchParams({ pattern, text, placeholder });
    return request<{ matched: boolean; matches: { value: string; start: number; end: number }[]; result: string; match_count: number }>(
      `/api/v1/rules/test?${params}`,
      { method: 'POST' },
    );
  },

  // Desensitize
  desensitizeText: (text: string, rules?: string[], ner = false) =>
    request<DesensitizeTextResponse>(`/api/v1/desensitize/text`, {
      method: 'POST',
      body: JSON.stringify({ text, rules, ner }),
    }),

  desensitizeMessages: (messages: { role: string; content: string }[], options?: object) =>
    request<DesensitizeResponse>(`/api/v1/desensitize`, {
      method: 'POST',
      body: JSON.stringify({ messages, options }),
    }),

  // Health
  health: () => request<{ status: string; service: string }>(`/health`),

  about: () => request<AboutInfo>(`/api/v1/system/about`),
};
