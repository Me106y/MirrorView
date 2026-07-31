import type { ModelSettings, ModelProvider } from "../types";

export const RUNTIME_STATUS_KEY = "mirrorview:web:runtime:test-status:v1";
const RUNTIME_STATUS_TTL_MS = 15 * 60 * 1000;

export interface PersistedRuntimeStatus {
  success: boolean;
  provider: ModelProvider;
  model: string;
  baseUrl: string;
  apiKeyFingerprint: string;
  testedAt: number;
}

function apiKeyFingerprint(apiKey: string): string {
  const trimmed = String(apiKey || "").trim();
  if (!trimmed) {
    return "";
  }
  const tail = trimmed.slice(-6);
  return `${trimmed.length}:${tail}`;
}

export function createRuntimeStatus(settings: Pick<ModelSettings, "provider" | "model" | "apiKey" | "baseUrl">): PersistedRuntimeStatus {
  return {
    success: true,
    provider: settings.provider,
    model: settings.model.trim() || "deepseek-chat",
    baseUrl: settings.baseUrl.trim(),
    apiKeyFingerprint: apiKeyFingerprint(settings.apiKey),
    testedAt: Date.now(),
  };
}

export function loadRuntimeStatus(): PersistedRuntimeStatus | null {
  try {
    const raw = localStorage.getItem(RUNTIME_STATUS_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as PersistedRuntimeStatus;
    if (!parsed?.success || !parsed.model || !parsed.provider || !parsed.testedAt) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function saveRuntimeStatus(status: PersistedRuntimeStatus | null): void {
  try {
    if (!status) {
      localStorage.removeItem(RUNTIME_STATUS_KEY);
      return;
    }
    localStorage.setItem(RUNTIME_STATUS_KEY, JSON.stringify(status));
  } catch {
    // ignore localStorage failures
  }
}

export function hasFreshRuntimeStatus(settings: Pick<ModelSettings, "provider" | "model" | "apiKey" | "baseUrl">, status: PersistedRuntimeStatus | null): boolean {
  if (!status?.success) {
    return false;
  }
  if (Date.now() - status.testedAt > RUNTIME_STATUS_TTL_MS) {
    return false;
  }
  return (
    status.provider === settings.provider &&
    status.model === (settings.model.trim() || "deepseek-chat") &&
    status.baseUrl === settings.baseUrl.trim() &&
    status.apiKeyFingerprint === apiKeyFingerprint(settings.apiKey)
  );
}
