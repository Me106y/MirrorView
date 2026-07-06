import type { ModelSettings } from "../types";

interface ApiEnvelope<T> {
  result?: T;
  message?: string;
  error?: string;
  reply?: string;
  meta?: {
    runtime_mode?: string;
    runtime_provider?: string;
  };
}

function buildRuntime(settings: ModelSettings) {
  const byokEnabled = settings.mode === "byok" && settings.apiKey.trim();
  if (!byokEnabled) {
    return {
      mode: "platform",
      provider: "deepseek",
      model: settings.model || "deepseek-chat",
      api_key: "",
      base_url: settings.baseUrl || ""
    };
  }
  return {
    mode: "byok",
    provider: settings.provider,
    model: settings.model,
    api_key: settings.apiKey,
    base_url: settings.baseUrl || ""
  };
}

async function postJson<T>(url: string, body: Record<string, unknown>): Promise<ApiEnvelope<T>> {
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });

  let data: ApiEnvelope<T> = {};
  try {
    data = (await resp.json()) as ApiEnvelope<T>;
  } catch {
    data = {};
  }

  if (!resp.ok) {
    const message = data.message || data.error || `Request failed (${resp.status})`;
    throw new Error(message);
  }

  return data;
}

export async function callCareerforgeSkill<T>(
  settings: ModelSettings,
  endpoint: string,
  payload: Record<string, unknown>
): Promise<ApiEnvelope<T>> {
  const runtime = buildRuntime(settings);
  const body = {
    ...payload,
    runtime,
    turnstile_token: settings.turnstileToken || ""
  };
  const url = `${settings.apiBaseUrl}${endpoint}`;
  return postJson<T>(url, body);
}
