export type RuntimeMode = "platform" | "byok";
export type ModelProvider = "deepseek" | "openai" | "anthropic" | "ccswitch";

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

export interface GrillQuestion {
  id: string;
  text: string;
  dimension: string;
  status: "open" | "answered" | "skipped";
}

export interface GrillState {
  completed_rounds: number;
  pending_questions: GrillQuestion[];
  round_status: "awaiting_answers" | "round_completed" | "project_completed" | "skipped";
  user_skipped: boolean;
}

export interface ExperienceState {
  current_index: number;
  followup_count: number;
  drafts: string[];
  finalized_experiences: string[];
  active_focus?: {
    topic: string;
    stage: "implementation" | "tradeoff" | "validation" | "done";
    evidence: {
      implementation: boolean;
      tradeoff: boolean;
      validation: boolean;
    };
    turn_count: number;
    grill?: GrillState;
  };
}

export interface StepChatState {
  turn_count: number;
  confirmed: boolean;
  preview_ready?: boolean;
  awaiting_confirm?: boolean;
  preview_markdown?: string;
  draft_json?: Record<string, unknown>;
  revision_count?: number;
}

export interface StepCollectedData {
  education: string[];
  experiences: string[];
  skills_and_certs: string[];
  final_preferences: string;
  step6_confirmed: boolean;
}

export interface ResumeCraftWizardState {
  current_step: 3 | 4 | 5 | 6;
  collected_by_step: StepCollectedData;
  chat_history_by_step: {
    step3: string[];
    step4: string[];
    step5: string[];
    step6: string[];
  };
  step_states: {
    step3: StepChatState;
    step4: ExperienceState;
    step5: StepChatState;
    step6: StepChatState;
  };
}

export type ResumeCraftBackendStep = 4 | 5 | 6;

export interface ResumeCraftConversationMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  isPreview?: boolean;
  htmlLink?: {
    href: string;
    label: string;
  };
  backendStep: ResumeCraftBackendStep;
}

export type MockInterviewLanguage = "zh" | "en";
export type MockInterviewScope = "full" | "hr" | "business" | "executive" | "focused";
export type MockInterviewStage = "setup" | "active" | "reporting" | "completed" | "error";
export type MockInterviewMessageRole = "user" | "assistant";
export type MockInterviewMessageStatus = "sent" | "streaming" | "error";

export interface MockInterviewSetup {
  targetRole: string;
  jdText: string;
  resumeText: string;
  resumeFileName?: string;
  companyName: string;
  language: MockInterviewLanguage;
  scope: MockInterviewScope;
  focusTopic: string;
}

export interface MockInterviewConversationMessage {
  id: string;
  role: MockInterviewMessageRole;
  content: string;
  createdAt: string;
  status: MockInterviewMessageStatus;
}

export interface MockInterviewDimension {
  key: string;
  label: string;
  score: number;
  comment: string;
}

export interface MockInterviewQuestionFeedback {
  question: string;
  answerSummary: string;
  score: number;
  strength: string;
  gap: string;
  suggestion: string;
  sampleAnswer: string;
}

export interface MockInterviewRound {
  key: string;
  label: string;
  score: number;
  status: "completed" | "partial" | "not_started";
  summary: string;
  questions: MockInterviewQuestionFeedback[];
}

export interface MockInterviewQuestionBankItem {
  round: string;
  question: string;
  focus: string;
  score: number;
}

export interface MockInterviewActionItem {
  title: string;
  priority: "high" | "medium" | "low";
  details: string;
}

export interface MockInterviewReport {
  candidateName: string;
  targetRole: string;
  companyName: string;
  language: MockInterviewLanguage;
  scope: MockInterviewScope;
  overallScore: number;
  hireRecommendation: string;
  summary: string;
  dimensions: MockInterviewDimension[];
  rounds: MockInterviewRound[];
  questionBank: MockInterviewQuestionBankItem[];
  actionItems: MockInterviewActionItem[];
  htmlReport?: string;
}

export interface MockInterviewSession {
  stage: MockInterviewStage;
  setup: MockInterviewSetup;
  messages: MockInterviewConversationMessage[];
  startedAt: string;
  busy: boolean;
  errorMessage?: string;
  report?: MockInterviewReport | null;
}
