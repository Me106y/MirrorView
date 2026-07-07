export type RuntimeMode = "platform" | "byok";
export type ModelProvider = "deepseek" | "openai" | "anthropic";

export interface ModelSettings {
  mode: RuntimeMode;
  provider: ModelProvider;
  model: string;
  apiKey: string;
  baseUrl: string;
  turnstileToken: string;
  apiBaseUrl: string;
}

export interface RuntimeMeta {
  runtime_mode: RuntimeMode;
  runtime_provider: ModelProvider;
}

export interface EducationItem {
  school: string;
  major: string;
  degree: string;
  period: string;
  highlights: string;
}

export interface Step1Profile {
  template_code: string;
  language: string;
  photo_pref: string;
  target_role: string;
  jd_summary: string;
  focus_points: string;
  tone_pref: string;
  expected_experience_count: number;
  personal_info: {
    name: string;
    phone: string;
    email: string;
    city: string;
    links: string[];
  };
  education: EducationItem[];
  skills: string[];
  certificates: string[];
}

export interface ExperienceState {
  current_index: number;
  followup_count: number;
  drafts: string[];
  finalized_experiences: string[];
}
