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
  return {
    mode: "platform",
    provider: "deepseek",
    model: settings.model || "deepseek-chat",
    api_key: settings.apiKey.trim(),
    base_url: settings.baseUrl.trim()
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

async function postForm<T>(url: string, body: FormData): Promise<ApiEnvelope<T>> {
  const resp = await fetch(url, {
    method: "POST",
    body
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

export async function callCareerforgeSkillMultipart<T>(
  settings: ModelSettings,
  endpoint: string,
  payload: Record<string, unknown>,
  files: Record<string, File | null>
): Promise<ApiEnvelope<T>> {
  const runtime = buildRuntime(settings);
  const form = new FormData();

  Object.entries(payload).forEach(([key, value]) => {
    if (value === undefined || value === null) {
      return;
    }
    form.append(key, String(value));
  });

  Object.entries(files).forEach(([key, file]) => {
    if (!file) {
      return;
    }
    form.append(key, file, file.name);
  });

  form.append("runtime", JSON.stringify(runtime));
  form.append("turnstile_token", settings.turnstileToken || "");

  const url = `${settings.apiBaseUrl}${endpoint}`;
  return postForm<T>(url, form);
}
