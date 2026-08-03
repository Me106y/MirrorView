import type { ModelSettings, Step1Profile } from "../types";

export const MODEL_SETTINGS_KEY = "mirrorview:web:model-settings:v2";
export const CONSENT_ACCEPTED_KEY = "mirrorview:web:consent:v1";
export const RESUME_CRAFT_DRAFT_KEY = "mirrorview:web:resume-craft:draft:v1";
export const RESUME_CRAFT_RESULT_KEY = "mirrorview:web:resume-craft:result:v1";

export interface ResumeCraftResultArtifact {
  reportHtml: string;
  reportName: string;
  reportPdfName: string;
  reportPdfBase64: string;
  templateCode: string;
  language: string;
}

export const defaultSettings: ModelSettings = {
  mode: "platform",
  provider: "deepseek",
  model: "deepseek-chat",
  apiKey: "",
  baseUrl: "",
  turnstileToken: "",
  apiBaseUrl: ""
};

function isLocalDevHost(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const host = window.location.hostname.toLowerCase();
  return host === "localhost" || host === "127.0.0.1";
}

function normalizeApiBaseUrl(value: unknown): string {
  const raw = String(value ?? "").trim();
  if (!raw) {
    return isLocalDevHost() ? "/api" : "";
  }

  if (raw === "/api") {
    return isLocalDevHost() ? "/api" : "";
  }

  if (raw.startsWith("/")) {
    return raw;
  }

  // Allow local absolute URLs for developer debugging only.
  if (/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?(\/.*)?$/i.test(raw)) {
    return raw;
  }

  return isLocalDevHost() ? "/api" : "";
}

export function loadSettings(): ModelSettings {
  try {
    const raw = localStorage.getItem(MODEL_SETTINGS_KEY);
    if (!raw) {
      return defaultSettings;
    }
    const parsed = JSON.parse(raw) as Partial<ModelSettings>;
    const merged = {
      ...defaultSettings,
      ...parsed
    };
    return {
      ...merged,
      apiBaseUrl: normalizeApiBaseUrl(merged.apiBaseUrl),
    };
  } catch {
    return defaultSettings;
  }
}

export function saveSettings(settings: ModelSettings): void {
  localStorage.setItem(MODEL_SETTINGS_KEY, JSON.stringify(settings));
}

export function isConsentAccepted(): boolean {
  try {
    return localStorage.getItem(CONSENT_ACCEPTED_KEY) === "accepted";
  } catch {
    return false;
  }
}

export function setConsentAccepted(): void {
  localStorage.setItem(CONSENT_ACCEPTED_KEY, "accepted");
}

export function saveResumeCraftDraft(profile: Step1Profile): void {
  try {
    localStorage.setItem(RESUME_CRAFT_DRAFT_KEY, JSON.stringify(profile));
  } catch {
    // ignore storage errors (quota exceeded, privacy mode, etc.)
  }
}

export function loadResumeCraftDraft(): Step1Profile | null {
  try {
    const raw = localStorage.getItem(RESUME_CRAFT_DRAFT_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Step1Profile;
  } catch {
    return null;
  }
}

export function saveResumeCraftResult(artifact: ResumeCraftResultArtifact): void {
  try {
    sessionStorage.setItem(RESUME_CRAFT_RESULT_KEY, JSON.stringify(artifact));
  } catch {
    // The result is also passed through router state for the current navigation.
  }
}

export function loadResumeCraftResult(): ResumeCraftResultArtifact | null {
  try {
    const raw = sessionStorage.getItem(RESUME_CRAFT_RESULT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ResumeCraftResultArtifact>;
    if (typeof parsed.reportHtml !== "string" || !parsed.reportHtml.trim()) return null;
    return {
      reportHtml: parsed.reportHtml,
      reportName: typeof parsed.reportName === "string" && parsed.reportName.trim() ? parsed.reportName : "resume-craft-report.html",
      reportPdfName: typeof parsed.reportPdfName === "string" && parsed.reportPdfName.trim() ? parsed.reportPdfName : "resume-craft-report.pdf",
      reportPdfBase64: typeof parsed.reportPdfBase64 === "string" ? parsed.reportPdfBase64 : "",
      templateCode: typeof parsed.templateCode === "string" ? parsed.templateCode : "02",
      language: typeof parsed.language === "string" ? parsed.language : "zh",
    };
  } catch {
    return null;
  }
}
