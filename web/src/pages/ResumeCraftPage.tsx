import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { gsap } from "gsap";
import { NavLink, useLocation } from "react-router-dom";
import { callCareerforgeSkill } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";
import { useCareerFeatureGuard } from "../components/CareerFeatureGuard";
import { loadResumeCraftDraft, saveResumeCraftDraft, type ResumeCraftEditorState } from "../lib/storage";
import type {
  EducationItem,
  ResumeCraftBackendStep,
  ResumeCraftConversationMessage,
  ResumeCraftWizardState,
  Step1Profile,
} from "../types";
import { ConsentModal } from "../components/ConsentModal";
import { useConsent } from "../context/ConsentContext";

type Msg = Omit<ResumeCraftConversationMessage, "backendStep">;
type StepNumber = 1 | 2 | 3;
type ChatStep = 3 | 4 | 5;

type ResultState = {
  kind: "idle" | "pending" | "success" | "error";
  message: string;
};

type GeneratedResumeState = {
  html: string;
  htmlUrl: string;
  pdfBase64: string;
  pdfName: string;
};

type ResumeView = "chat" | "generating" | "result";

type RenderRequest = {
  template_code?: string;
  language?: string;
  wizardState?: ResumeCraftWizardState;
  conversationMessages?: ResumeCraftConversationMessage[];
  activeBackendStep?: ResumeCraftBackendStep;
  bypassConsent?: boolean;
};

type ResumeCraftRouteState = {
  resumeCraftStep?: number;
  editorState?: ResumeCraftEditorState;
};

const STEP_SHIFT = 100 / 3;

const TEMPLATE_OPTIONS = [
  { value: "01", label: "杂志编辑风" },
  { value: "02", label: "极简主义" },
  { value: "03", label: "深蓝双栏" },
  { value: "04", label: "深灰左栏" },
  { value: "05", label: "深色头部" },
  { value: "06", label: "清新青色" },
  { value: "07", label: "优雅对称" },
];

function templateLabel(code: string) {
  return TEMPLATE_OPTIONS.find((item) => item.value === normalizeTemplateCodeForUI(code))?.label || "未选择模板";
}

const LANGUAGE_OPTIONS = [
  { value: "zh", label: "中文" },
  { value: "en", label: "英文" },
  { value: "both", label: "中英文双版" },
];

const INITIAL_CHAT_MESSAGES: Record<ResumeCraftBackendStep, string> = {
  4: "请描述一段工作或项目经历，可以包括项目背景、你的职责、采取的关键行动，以及最终结果或影响。我会围绕目标岗位帮你提炼亮点并进行追问。",
  5: "请补充与目标岗位相关的技能、工具、编程语言、语言能力或证书，并说明你的掌握程度和实际使用场景。我会帮你整理成简历中的技能信息。",
  6: "简历预览已经整理完成。如需修改请直接说明，确认无误后可以输入“生成简历”。",
};

const CHAT_INPUT_PLACEHOLDERS: Record<ResumeCraftBackendStep, string> = {
  4: "描述一段工作或项目经历，包含背景、职责、行动和结果",
  5: "补充技能、工具、语言能力或证书信息",
  6: "修改预览内容，或输入“生成简历”",
};

const CHAT_STEP_DESCRIPTIONS: Record<ResumeCraftBackendStep, string> = {
  4: "围绕工作或项目经历的背景、职责、行动和结果，提炼与目标岗位匹配的亮点。",
  5: "整理技能、工具、语言能力和证书，并补充掌握程度与实际使用场景。",
  6: "确认预览内容；如需修改请直接说明，确认无误后输入“生成简历”。",
};

const CHAT_PHASES: Array<{ step: ResumeCraftBackendStep; label: string }> = [
  { step: 4, label: "工作/项目经历" },
  { step: 5, label: "技能与证书" },
  { step: 6, label: "确认预览" },
];

const STEP_TITLES: Record<StepNumber, string> = {
  1: "Step1 基础信息",
  2: "Step2 个人信息与教育背景",
  3: "Step3-5 简历内容整理",
};

const EMPTY_PROFILE: Step1Profile = {
  template_code: "02",
  language: "zh",
  photo_pref: "no_photo",
  target_role: "",
  jd_summary: "",
  focus_points: "",
  tone_pref: "专业简洁",
  expected_experience_count: 1,
  personal_info: {
    name: "",
    phone: "",
    email: "",
    city: "",
    links: [],
  },
  education: [],
  skills: [],
  certificates: [],
};

const EMPTY_WIZARD: ResumeCraftWizardState = {
  current_step: 3,
  collected_by_step: {
    education: [],
    experiences: [],
    skills_and_certs: [],
    final_preferences: "",
    step6_confirmed: false,
  },
  chat_history_by_step: {
    step3: [],
    step4: [],
    step5: [],
    step6: [],
  },
  step_states: {
    step3: { turn_count: 0, confirmed: false },
    step4: {
      current_index: 1,
      followup_count: 0,
      drafts: [],
      finalized_experiences: [],
      active_focus: {
        topic: "",
        stage: "implementation",
        evidence: {
          implementation: false,
          tradeoff: false,
          validation: false,
        },
        turn_count: 0,
        grill: {
          completed_rounds: 0,
          pending_questions: [],
          round_status: "awaiting_answers",
          user_skipped: false,
        },
      },
    },
    step5: { turn_count: 0, confirmed: false },
    step6: {
      turn_count: 0,
      confirmed: false,
      preview_ready: false,
      awaiting_confirm: false,
      preview_markdown: "",
      draft_json: {},
      revision_count: 0,
    },
  },
};

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function mergeWizardState(
  base: ResumeCraftWizardState,
  patch: unknown,
): ResumeCraftWizardState {
  const mergeValue = (current: unknown, next: unknown): unknown => {
    if (!isPlainRecord(current) || !isPlainRecord(next)) {
      return next === undefined ? current : next;
    }

    const merged: Record<string, unknown> = { ...current };
    Object.entries(next).forEach(([key, value]) => {
      merged[key] = mergeValue(merged[key], value);
    });
    return merged;
  };

  return mergeValue(base, patch) as ResumeCraftWizardState;
}

const EMPTY_EDUCATION: EducationItem = {
  school: "",
  major: "",
  degree: "",
  period: "",
  highlights: "",
};

function simpleMarkdownToHtml(md: string): string {
  const escaped = md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");

  return escaped
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br/>')
    .replace(/^(?!<[huplo])((?!<).+)$/gm, '<p>$1</p>');
}

function mergePreviewAndReply(preview: string, reply: string): string {
  const replyLines = new Set(reply.trim().split("\n").map((line) => line.trim()).filter(Boolean));
  const previewText = preview.trim().split("\n").map((line) => line.trim()).filter((line) => line && !replyLines.has(line)).join("\n");
  return [previewText, reply.trim()].filter(Boolean).join("\n\n");
}

function normalizeAgentText(value: unknown): string {
  return String(value ?? "").replace(/[\u200B-\u200D\uFEFF]/g, "").trim();
}

function splitTags(input: string) {
  return input
    .split(/[，,\n；;|]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function isSupportedPhotoFile(file: File) {
  const fileName = file.name.toLowerCase();
  const byName = fileName.endsWith(".png") || fileName.endsWith(".jpg") || fileName.endsWith(".jpeg");
  const byType = file.type === "image/png" || file.type === "image/jpeg" || file.type === "image/jpg";
  return byName || byType;
}

function fileToDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("读取图片失败，请重试。"));
    reader.readAsDataURL(file);
  });
}

function normalizeBackendStep(value: unknown): ResumeCraftBackendStep {
  const numeric = Number(value);
  if (numeric === 5) return 5;
  if (numeric === 6) return 6;
  return 4;
}

function advanceBackendStep(step: ResumeCraftBackendStep): ResumeCraftBackendStep {
  return step === 4 ? 5 : 6;
}

function legacyUiStepToBackendStep(step: ChatStep): ResumeCraftBackendStep {
  return step === 3 ? 4 : step === 4 ? 5 : 6;
}

function normalizeConversationMessages(value: unknown, fallbackStep?: ResumeCraftBackendStep): ResumeCraftConversationMessage[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const candidate = item as Partial<ResumeCraftConversationMessage> & { backendStep?: unknown };
    const content = String(candidate.content || "").trim();
    const candidateLink = candidate.htmlLink;
    const htmlLink = candidateLink
      && typeof candidateLink === "object"
      && typeof candidateLink.href === "string"
      && candidateLink.href.trim()
      && typeof candidateLink.label === "string"
      && candidateLink.label.trim()
      ? { href: candidateLink.href.trim(), label: candidateLink.label.trim() }
      : undefined;
    // A generated assistant message can intentionally have no model text;
    // its user-facing content is the real HTML link attached below.
    if ((!content && !htmlLink) || (candidate.role !== "user" && candidate.role !== "assistant")) return [];
    return [{
      role: candidate.role,
      content,
      timestamp: String(candidate.timestamp || nowTimeLabel()),
      isPreview: candidate.isPreview === true,
      backendStep: normalizeBackendStep(candidate.backendStep ?? fallbackStep),
      ...(htmlLink ? { htmlLink } : {}),
    }];
  });
}

function legacyMessagesToConversation(messages: Record<ChatStep, Msg[]> | undefined): ResumeCraftConversationMessage[] {
  if (!messages) return [];
  return ([3, 4, 5] as ChatStep[]).flatMap((uiStep) =>
    normalizeConversationMessages(messages[uiStep], legacyUiStepToBackendStep(uiStep))
  );
}

function messagesByStepFromConversation(messages: ResumeCraftConversationMessage[]): Record<ChatStep, Msg[]> {
  const result: Record<ChatStep, Msg[]> = { 3: [], 4: [], 5: [] };
  for (const message of messages) {
    const uiStep = message.backendStep === 4 ? 3 : message.backendStep === 5 ? 4 : 5;
    const { backendStep: _backendStep, ...compatMessage } = message;
    result[uiStep].push(compatMessage);
  }
  return result;
}

function toAgentHistory(messages: ResumeCraftConversationMessage[]): Msg[] {
  return messages.map(({ backendStep: _backendStep, htmlLink: _htmlLink, ...message }) => message);
}

function looksLikeResumePreview(message: Pick<ResumeCraftConversationMessage, "role" | "content" | "isPreview">): boolean {
  return message.role === "assistant" && message.isPreview === true;
}

function hasPendingResumePreview(
  wizardState: ResumeCraftWizardState,
  messages: ResumeCraftConversationMessage[],
): boolean {
  const step6 = wizardState.step_states?.step6;
  if (step6?.preview_ready === true && step6.awaiting_confirm === true) return true;
  if (step6?.preview_ready === true && step6.confirmed !== true) return true;
  if (String(step6?.preview_markdown || "").trim() && step6?.confirmed !== true) return true;

  // Older editor snapshots can preserve the preview bubble but lose the
  // nested Step6 awaiting_confirm flag or the active backend phase. A visible
  // preview is still the version the user is confirming, so route the next
  // semantic turn through Step6 and let the server validate its draft state.
  return messages.some((message) => looksLikeResumePreview(message));
}

function normalizeTemplateCodeForUI(value: string) {
  const match = String(value || "").match(/[1-7]/);
  if (!match) return "02";
  return `0${match[0]}`;
}

function normalizeLanguageForUI(value: string) {
  const raw = String(value || "").trim().toLowerCase();
  if (["en", "english", "英文"].includes(raw)) return "en";
  if (["both", "zh-en", "zh_en", "双语", "中英文", "中英文双版"].includes(raw)) return "both";
  return "zh";
}

function nowTimeLabel() {
  return new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function parseMonthValue(value: string) {
  const raw = String(value || "").trim();
  if (!/^\d{4}-\d{2}$/.test(raw)) return null;
  const [yearStr, monthStr] = raw.split("-");
  const year = Number(yearStr);
  const month = Number(monthStr);
  if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) return null;
  return { year, month };
}

function formatMonthDisplay(value: string) {
  const parsed = parseMonthValue(value);
  if (!parsed) return "";
  return `${parsed.year}/${String(parsed.month).padStart(2, "0")}`;
}

function splitPeriod(period: string) {
  const raw = String(period || "").trim();
  if (!raw) return { start: "", end: "" };
  const parts = raw.split(/[~～]/).map((item) => item.trim());
  if (parts.length >= 2) return { start: parts[0], end: parts[1] };
  return { start: raw, end: "" };
}

export function ResumeCraftPage() {
  const { settings } = useModelSettings();
  const location = useLocation();
  const featureGuard = useCareerFeatureGuard(settings, "简历优化");
  const { accepted } = useConsent();
  const [showConsentPrompt, setShowConsentPrompt] = useState(false);

  const routeStep = (location.state as ResumeCraftRouteState | null)?.resumeCraftStep;
  const restoredEditorState = (location.state as ResumeCraftRouteState | null)?.editorState;
  const restoredMessages = restoredEditorState?.messagesByStep as Record<ChatStep, Msg[]> | undefined;
  const restoredConversation = normalizeConversationMessages(restoredEditorState?.conversationMessages);
  const initialConversationMessages = restoredConversation.length
    ? restoredConversation
    : legacyMessagesToConversation(restoredMessages);
  const initialCombinedMessages = initialConversationMessages.length
    ? initialConversationMessages
    : [{ role: "assistant" as const, content: INITIAL_CHAT_MESSAGES[4], timestamp: nowTimeLabel(), backendStep: 4 as const }];
  const [step, setStep] = useState<StepNumber>(routeStep === 5 ? 3 : routeStep === 2 ? 2 : 1);
  const [profile, setProfile] = useState<Step1Profile>(() => loadResumeCraftDraft() ?? EMPTY_PROFILE);
  const [linksInput, setLinksInput] = useState(() => profile.personal_info.links.join(", "));

  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoDataUrl, setPhotoDataUrl] = useState("");
  const [photoHint, setPhotoHint] = useState("");
  const [photoLoading, setPhotoLoading] = useState(false);

  const [wizardState, setWizardState] = useState<ResumeCraftWizardState>(() =>
    mergeWizardState(EMPTY_WIZARD, restoredEditorState?.wizardState),
  );
  const [messagesByStep, setMessagesByStep] = useState<Record<ChatStep, Msg[]>>(() => {
    return messagesByStepFromConversation(initialCombinedMessages);
  });
  const [conversationMessages, setConversationMessages] = useState<ResumeCraftConversationMessage[]>(initialCombinedMessages);
  const [activeBackendStep, setActiveBackendStep] = useState<ResumeCraftBackendStep>(() => {
    if (restoredEditorState?.activeBackendStep) return normalizeBackendStep(restoredEditorState.activeBackendStep);
    if (restoredEditorState?.wizardState?.step_states?.step6?.confirmed) return 6;
    return 4;
  });

  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [renderLoading, setRenderLoading] = useState(false);
  const [result, setResult] = useState<ResultState>({ kind: "idle", message: "" });
  const [generatedResume, setGeneratedResume] = useState<GeneratedResumeState | null>(null);
  const [viewportHeight, setViewportHeight] = useState<number | null>(null);
  const [openMonthPicker, setOpenMonthPicker] = useState<{ index: number; part: "start" | "end" } | null>(null);
  const [monthPickerYear, setMonthPickerYear] = useState<number>(new Date().getFullYear());
  const [expandedPill, setExpandedPill] = useState<string | null>(null);
  const [touchedFields, setTouchedFields] = useState<Record<string, boolean>>({});
  const [activeEducationIndex, setActiveEducationIndex] = useState(0);
  const generatedHtmlUrlsRef = useRef<string[]>([]);

  useEffect(() => () => {
    generatedHtmlUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  const photoInputRef = useRef<HTMLInputElement | null>(null);
  const wizardTrackRef = useRef<HTMLDivElement | null>(null);
  const resumeViewRef = useRef<HTMLDivElement | null>(null);
  const chatPanelRef = useRef<HTMLDivElement | null>(null);
  const generatingPanelRef = useRef<HTMLDivElement | null>(null);
  const resultPanelRef = useRef<HTMLElement | null>(null);
  const stepRefs = useRef<Record<StepNumber, HTMLElement | null>>({ 1: null, 2: null, 3: null });
  const educationCarouselRef = useRef<HTMLDivElement | null>(null);
  const previousEducationIndexRef = useRef(0);
  const monthPickerWrapRef = useRef<HTMLDivElement | null>(null);
  const pendingRenderRef = useRef<RenderRequest | null>(null);
  const rafRef = useRef<number>(0);
  const stepSnapshots = useRef<Record<number, {
    profile: Step1Profile;
    linksInput: string;
    photoDataUrl: string;
    photoFile: File | null;
  }>>({});

  const canStep1Next = useMemo(() => {
    const hasTemplate = TEMPLATE_OPTIONS.some((item) => item.value === profile.template_code);
    const hasLanguage = LANGUAGE_OPTIONS.some((item) => item.value === profile.language);
    const hasRole = profile.target_role.trim().length > 0;
    if (!hasTemplate || !hasLanguage || !hasRole || photoLoading) return false;
    return true;
  }, [profile.template_code, profile.language, profile.target_role, photoLoading]);

  const canStep2Next = useMemo(() => {
    const hasName = profile.personal_info.name.trim().length > 0;
    const hasPhone = profile.personal_info.phone.trim().length > 0;
    const hasEmail = profile.personal_info.email.trim().length > 0;
    const hasEducation = profile.education.some(
      (item) =>
        item.school.trim().length > 0 &&
        item.major.trim().length > 0 &&
        item.degree.trim().length > 0 &&
        item.period.trim().length > 0
    );
    return hasName && hasPhone && hasEmail && hasEducation;
  }, [profile.personal_info, profile.education]);

  const educationRows = profile.education.length ? profile.education : [{ ...EMPTY_EDUCATION }];
  const educationIndex = Math.min(activeEducationIndex, educationRows.length - 1);
  const edu = educationRows[educationIndex];
  const index = educationIndex;
  const activePhase = CHAT_PHASES.find((phase) => phase.step === activeBackendStep) ?? CHAT_PHASES[0];
  const resumeView: ResumeView = renderLoading ? "generating" : generatedResume ? "result" : "chat";

  useEffect(() => {
    const card = stepRefs.current[step];
    if (!card) return;

    const updateHeight = () => {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        setViewportHeight(card.offsetHeight);
      });
    };

    updateHeight();

    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(updateHeight);
    observer.observe(card);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(rafRef.current);
    };
  }, [step]);

  useEffect(() => {
    setActiveEducationIndex((current) => Math.min(current, Math.max(educationRows.length - 1, 0)));
  }, [educationRows.length]);

  useEffect(() => {
    const slide = educationCarouselRef.current?.querySelector<HTMLElement>(".resume-craft-edu-item");
    if (!slide) return;

    const direction = activeEducationIndex >= previousEducationIndexRef.current ? 1 : -1;
    previousEducationIndexRef.current = activeEducationIndex;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const context = gsap.context(() => {
      gsap.fromTo(
        slide,
        { x: reduceMotion ? 0 : direction * 28, autoAlpha: reduceMotion ? 1 : 0 },
        { x: 0, autoAlpha: 1, duration: reduceMotion ? 0 : 0.3, ease: "power2.out" },
      );
    }, educationCarouselRef);

    return () => context.revert();
  }, [activeEducationIndex]);

  useEffect(() => {
    const scope = resumeViewRef.current;
    if (!scope) return;

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const context = gsap.context(() => {
      const panels = [chatPanelRef.current, generatingPanelRef.current, resultPanelRef.current].filter(
        (panel): panel is HTMLElement => Boolean(panel),
      );
      const activePanel = resumeView === "chat"
        ? chatPanelRef.current
        : resumeView === "generating"
          ? generatingPanelRef.current
          : resultPanelRef.current;

      gsap.set(panels, { autoAlpha: 0, x: reduceMotion ? 0 : 28 });
      if (!activePanel) return;
      gsap.to(activePanel, {
        autoAlpha: 1,
        x: 0,
        duration: reduceMotion ? 0 : 0.32,
        ease: "power2.out",
      });
    }, scope);

    return () => context.revert();
  }, [resumeView]);

  useEffect(() => {
    const onDocumentClick = (event: MouseEvent) => {
      if (!openMonthPicker) return;
      const target = event.target as Element | null;
      if (
        target?.closest(".resume-craft-month-picker-field")
        || (monthPickerWrapRef.current && target && monthPickerWrapRef.current.contains(target))
      ) return;
      setOpenMonthPicker(null);
    };
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && openMonthPicker) {
        setOpenMonthPicker(null);
      }
    };
    document.addEventListener("click", onDocumentClick);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("click", onDocumentClick);
      document.removeEventListener("keydown", onEscape);
    };
  }, [openMonthPicker]);

  const savePhotoFile = async (file: File | null) => {
    if (!file) {
      setPhotoFile(null);
      setPhotoDataUrl("");
      setProfile((prev) => ({ ...prev, photo_pref: "no_photo" }));
      setPhotoHint("可选：未上传照片时将按“不放照片”处理。");
      if (photoInputRef.current) photoInputRef.current.value = "";
      return;
    }
    if (!isSupportedPhotoFile(file)) {
      setPhotoFile(null);
      setPhotoDataUrl("");
      setPhotoHint("仅支持 PNG/JPG/JPEG 图片。");
      if (photoInputRef.current) photoInputRef.current.value = "";
      return;
    }
    setPhotoLoading(true);
    setPhotoHint("");
    setPhotoFile(file);
    try {
      const dataUrl = await fileToDataUrl(file);
      setPhotoDataUrl(dataUrl);
      setProfile((prev) => ({ ...prev, photo_pref: "with_photo" }));
      setPhotoHint("");
    } catch (err) {
      setPhotoFile(null);
      setPhotoDataUrl("");
      setProfile((prev) => ({ ...prev, photo_pref: "no_photo" }));
      setPhotoHint((err as Error).message || "读取图片失败，请重试。");
    } finally {
      setPhotoLoading(false);
    }
  };

  const buildProfilePayload = (): Step1Profile => ({
    ...profile,
    photo_pref: photoDataUrl ? "with_photo" : "no_photo",
    personal_info: {
      ...profile.personal_info,
      links: splitTags(linksInput),
    },
    education: profile.education,
    skills: wizardState.collected_by_step.skills_and_certs,
    certificates: [],
  });

  const goNext = () => {
    if (step === 1 && !canStep1Next) return;
    if (step === 2 && !canStep2Next) return;
    if (step < 3) {
      stepSnapshots.current[step] = {
        profile: { ...profile },
        linksInput,
        photoDataUrl,
        photoFile,
      };
      saveResumeCraftDraft({
        ...profile,
        personal_info: { ...profile.personal_info, links: splitTags(linksInput) },
      });
      setExpandedPill(null);
      setStep((prev) => (prev + 1) as StepNumber);
    }
  };

  const goPrev = () => {
    if (step > 1) {
      setExpandedPill(null);
      const prevStep = (step - 1) as StepNumber;
      const snapshot = stepSnapshots.current[prevStep];
      if (snapshot) {
        setProfile(snapshot.profile);
        setLinksInput(snapshot.linksInput);
        setPhotoDataUrl(snapshot.photoDataUrl);
        setPhotoFile(snapshot.photoFile);
      }
      setStep(prevStep);
    }
  };

  const onRestartCurrentChat = () => {
    if (step !== 3) return;
    const initialMessage: ResumeCraftConversationMessage = {
      role: "assistant",
      content: INITIAL_CHAT_MESSAGES[4],
      timestamp: nowTimeLabel(),
      backendStep: 4,
    };
    setConversationMessages([initialMessage]);
    setMessagesByStep(messagesByStepFromConversation([initialMessage]));
    setActiveBackendStep(4);
    setWizardState((prev) => {
      const next = JSON.parse(JSON.stringify(EMPTY_WIZARD)) as ResumeCraftWizardState;
      next.current_step = 3;
      next.collected_by_step.education = prev.collected_by_step.education;
      return next;
    });
    setChatInput("");
    setResult({ kind: "idle", message: "" });
  };

  const releaseGeneratedHtmlUrl = (url: string) => {
    if (!url.startsWith("blob:")) return;
    URL.revokeObjectURL(url);
    generatedHtmlUrlsRef.current = generatedHtmlUrlsRef.current.filter((item) => item !== url);
  };

  const returnToChat = () => {
    if (generatedResume) releaseGeneratedHtmlUrl(generatedResume.htmlUrl);
    setGeneratedResume(null);
    setResult({ kind: "idle", message: "" });
  };

  const sendChatMessage = async (messageText: string) => {
    if (step !== 3 || !messageText.trim() || chatLoading) return;

    const storedStep6 = wizardState.step_states?.step6;
    const hasAwaitingPreview = storedStep6?.preview_ready === true
      && storedStep6?.awaiting_confirm === true;
    const visiblePreviewCount = conversationMessages.filter(
      (message) => looksLikeResumePreview(message),
    ).length;
    const hasPendingPreview = hasPendingResumePreview(wizardState, conversationMessages);
    // A preview is a Step6 contract even when an older editor snapshot left
    // the local phase pointer at Step4 or Step5. The preview state is the
    // source of truth for the next turn. The preview bubble is a compatibility
    // fallback for snapshots created before the nested state was persisted.
    const requestBackendStep: ResumeCraftBackendStep = hasPendingPreview
      ? 6
      : activeBackendStep;
    const userMessage: ResumeCraftConversationMessage = {
      role: "user",
      content: messageText.trim(),
      timestamp: nowTimeLabel(),
      backendStep: requestBackendStep,
    };
    const nextMessages = [...conversationMessages, userMessage];
    setConversationMessages(nextMessages);
    setMessagesByStep(messagesByStepFromConversation(nextMessages));
    setChatInput("");
    setResult({ kind: "idle", message: "" });
    setChatLoading(true);
  
    try {
      const step1Profile = buildProfilePayload();
      const resp = (await callCareerforgeSkill(settings, "/careerforge/resume-craft/chat-turn", {
        message: userMessage.content,
        history: toAgentHistory(nextMessages),
        current_step: requestBackendStep,
        step1_profile: step1Profile,
        wizard_state: wizardState,
        template_code: step1Profile.template_code,
        language: step1Profile.language,
        photo_pref: step1Profile.photo_pref,
      })) as Record<string, unknown>;
  
      const rawServerReply = normalizeAgentText(resp.reply);
      const responsePreviewMarkdown = normalizeAgentText(resp.step6_preview_markdown);
      const isRenderReadyResponse = resp.render_ready === true;

      if (!resp.wizard_state || typeof resp.wizard_state !== "object") {
        throw new Error("Agent response missing wizard_state");
      }
      if (resp.next_step_suggestion !== "stay" && resp.next_step_suggestion !== "next") {
        throw new Error("Agent response has invalid next_step_suggestion");
      }
      // The Agent contract returns a minimal wizard-state patch. Keep the
      // previously confirmed preview and other step data when a response only
      // includes the fields changed in this turn.
      // Accept a structurally valid draft even when an older runtime/model
      // places it at the response root instead of inside Step6.
      const responseDraft = isPlainRecord(resp.draft_json) && Object.keys(resp.draft_json).length > 0
        ? resp.draft_json
        : null;
      const wizardPatch = responseDraft
        ? mergeWizardState(resp.wizard_state as ResumeCraftWizardState, { step_states: { step6: { draft_json: responseDraft } } })
        : resp.wizard_state;
      const nextWizard = mergeWizardState(wizardState, wizardPatch);
      const nextStep6 = nextWizard.step_states?.step6;
      // The preview is an Agent-owned field. Accept the nested state copy as a
      // structural compatibility fallback when a model returns the same
      // preview there but omits the top-level convenience field.
      const step6PreviewMarkdown = responsePreviewMarkdown
        || normalizeAgentText(nextStep6?.preview_markdown);
      if (!rawServerReply && !step6PreviewMarkdown && !isRenderReadyResponse) {
        throw new Error("Agent response missing reply");
      }
      const responseLooksLikePreview = looksLikeResumePreview({
        role: "assistant",
        content: [step6PreviewMarkdown, rawServerReply].filter(Boolean).join("\n\n"),
        isPreview: Boolean(step6PreviewMarkdown),
      });
      const assistantContent = mergePreviewAndReply(step6PreviewMarkdown, rawServerReply);
      const shouldEnterPreviewStep = resp.next_step_suggestion === "next";
      const nextBackendStep = shouldEnterPreviewStep
        ? advanceBackendStep(requestBackendStep)
        : requestBackendStep;
      const nextDraft = nextStep6?.draft_json;
      // The nested confirmation state is the authoritative contract. The
      // frontend does not infer confirmation from user wording or local
      // preview heuristics.
      const responseClaimsGeneration = resp.render_ready === true;
      // `render_ready` is an explicit Agent decision. The page phase is only
      // navigation context and must not veto a confirmed render request; the
      // render route remains the final safety gate for confirmation and draft.
      const renderReady = responseClaimsGeneration
        && nextWizard.collected_by_step?.step6_confirmed === true
        && nextStep6?.confirmed === true
        && Boolean(nextDraft && Object.keys(nextDraft).length > 0);
      console.info("[resume-craft] chat response", JSON.stringify({
        activeBackendStep,
        requestBackendStep,
        nextBackendStep,
        hasAwaitingPreview,
        hasPendingPreview,
        visiblePreviewCount,
        action: String(resp.action || ""),
        suggestion: String(resp.next_step_suggestion || ""),
        phaseTransitioned: nextBackendStep !== activeBackendStep,
        renderReady,
        responseRenderReady: resp.render_ready === true,
        step6Confirmed: nextWizard.collected_by_step?.step6_confirmed === true,
        step6ConfirmedState: nextStep6?.confirmed === true,
        hasDraft: Boolean(nextDraft && Object.keys(nextDraft).length > 0),
        previewChars: step6PreviewMarkdown.length,
      }));
      // Generation is a terminal UI transition. Keep the confirmation turn
      // out of the transcript so the old preview and progress copy cannot be
      // mistaken for a second preview while the render request is running.
      const completedMessages = renderReady
        ? nextMessages
        : assistantContent
          ? [
            ...nextMessages,
            {
              role: "assistant" as const,
              content: assistantContent,
              timestamp: nowTimeLabel(),
              isPreview: responseLooksLikePreview,
              backendStep: nextBackendStep,
            },
          ]
          : nextMessages;
  
      setWizardState(nextWizard);
      setConversationMessages(completedMessages);
      setMessagesByStep(messagesByStepFromConversation(completedMessages));
      setActiveBackendStep(nextBackendStep);

      if (renderReady) {
        await renderResume({
          wizardState: nextWizard,
          conversationMessages: completedMessages,
          activeBackendStep: nextBackendStep,
        });
      } else if (responseClaimsGeneration) {
        // Keep the render route as the final safety gate, but surface a
        // rejected render attempt in the same workspace instead of logging it
        // and leaving the user without feedback.
        await renderResume({
          wizardState: nextWizard,
          conversationMessages: completedMessages,
          activeBackendStep: nextBackendStep,
        });
      } else if (activeBackendStep === 6 || nextBackendStep === 6) {
        console.warn("[resume-craft] render not triggered", JSON.stringify({
          activeBackendStep,
          nextBackendStep,
          responseRenderReady: resp.render_ready === true,
          responseClaimsGeneration,
          step6Confirmed: nextWizard.collected_by_step?.step6_confirmed === true,
          step6ConfirmedState: nextStep6?.confirmed === true,
          hasDraft: Boolean(nextDraft && Object.keys(nextDraft).length > 0),
        }));
      }
    } catch (err) {
      const errorMessage: ResumeCraftConversationMessage = {
        role: "assistant",
        content: (err as Error).message || "请求失败，请重试。",
        timestamp: nowTimeLabel(),
        backendStep: activeBackendStep,
      };
      const failedMessages = [...nextMessages, errorMessage];
      setConversationMessages(failedMessages);
      setMessagesByStep(messagesByStepFromConversation(failedMessages));
      setResult({ kind: "error", message: errorMessage.content });
    } finally {
      setChatLoading(false);
    }
  };
  
  const onSendChat = async (e: FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    await sendChatMessage(chatInput.trim());
  };
  
  const updateEducationField = (index: number, field: keyof EducationItem, value: string) => {
    setProfile((prev) => {
      const rows = prev.education.length ? [...prev.education] : [{ ...EMPTY_EDUCATION }];
      const current = rows[index] ?? { ...EMPTY_EDUCATION };
      rows[index] = { ...current, [field]: value };
      return { ...prev, education: rows };
    });
  };

  const updateEducationPeriodDate = (index: number, part: "start" | "end", value: string) => {
    setProfile((prev) => {
      const rows = prev.education.length ? [...prev.education] : [{ ...EMPTY_EDUCATION }];
      const current = rows[index] ?? { ...EMPTY_EDUCATION };
      const parsed = splitPeriod(current.period);
      const start = part === "start" ? value : parsed.start;
      const end = part === "end" ? value : parsed.end;
      rows[index] = { ...current, period: `${start || ""}~${end || ""}`.trim() };
      return { ...prev, education: rows };
    });
  };

  const openMonthCalendar = (index: number, part: "start" | "end", currentValue: string) => {
    const parsed = parseMonthValue(currentValue);
    setMonthPickerYear(parsed?.year ?? new Date().getFullYear());
    setOpenMonthPicker({ index, part });
  };

  const selectMonthFromPicker = (index: number, part: "start" | "end", year: number, month: number) => {
    const value = `${year}-${String(month).padStart(2, "0")}`;
    updateEducationPeriodDate(index, part, value);
    setOpenMonthPicker(null);
  };

  const addEducationRow = () => {
    setActiveEducationIndex(educationRows.length);
    setProfile((prev) => ({ ...prev, education: [...(prev.education.length ? prev.education : [{ ...EMPTY_EDUCATION }]), { ...EMPTY_EDUCATION }] }));
  };

  const removeEducationRow = (index: number) => {
    const rows = educationRows;
    const nextLength = Math.max(rows.length - 1, 1);
    setActiveEducationIndex((current) => (current > index ? current - 1 : Math.min(current, nextLength - 1)));
    setProfile((prev) => {
      const currentRows = prev.education.length ? [...prev.education] : [{ ...EMPTY_EDUCATION }];
      const nextRows = currentRows.filter((_, idx) => idx !== index);
      return { ...prev, education: nextRows.length ? nextRows : [{ ...EMPTY_EDUCATION }] };
    });
  };

  const switchEducation = (nextIndex: number) => {
    if (nextIndex < 0 || nextIndex >= educationRows.length || nextIndex === activeEducationIndex) return;
    setOpenMonthPicker(null);
    setActiveEducationIndex(nextIndex);
  };

  useEffect(() => {
    const compact = profile.education
      .map((item) =>
        [item.school, item.major, item.degree, item.period, item.highlights]
          .map((part) => String(part || "").trim())
          .filter(Boolean)
          .join(" | ")
      )
      .filter(Boolean);
    setWizardState((prev) => ({
      ...prev,
      collected_by_step: { ...prev.collected_by_step, education: compact },
      step_states: {
        ...prev.step_states,
        step3: { ...prev.step_states.step3, confirmed: compact.length > 0 },
      },
    }));
  }, [profile.education]);

  const renderResume = async (overrides?: RenderRequest) => {
    const requested = overrides ?? pendingRenderRef.current ?? {};
    const currentWizardState = requested.wizardState ?? wizardState;
    const currentConversationMessages = requested.conversationMessages ?? conversationMessages;
    const currentBackendStep = requested.activeBackendStep ?? activeBackendStep;
    const currentStep6 = currentWizardState.step_states?.step6;
    const currentDraft = currentStep6?.draft_json;
    const hasDraft = Boolean(currentDraft && Object.keys(currentDraft).length > 0);
    const confirmed = currentWizardState.collected_by_step?.step6_confirmed === true && currentStep6?.confirmed === true;

    console.info("[resume-craft] render decision", JSON.stringify({
      accepted,
      bypassConsent: requested.bypassConsent === true,
      currentBackendStep,
      confirmed,
      hasDraft,
      renderLoading,
    }));

    if (!accepted && !requested.bypassConsent) {
      console.info("[resume-craft] render deferred for consent");
      pendingRenderRef.current = requested;
      setResult({ kind: "pending", message: "等待确认后开始生成简历。" });
      setShowConsentPrompt(true);
      return;
    }
    pendingRenderRef.current = null;
    // The explicit confirmation state is the render contract. Do not repeat
    // the page phase check here; the backend validates the same state before
    // allowing the high-cost render request.
    if (!confirmed || !hasDraft || renderLoading) {
      console.warn("[resume-craft] render skipped", {
        currentBackendStep,
        confirmed,
        hasDraft,
        renderLoading,
      });
      setResult({
        kind: "error",
        message: renderLoading
          ? "生成请求正在处理中，请稍候。"
          : !confirmed
            ? "生成未执行：当前简历尚未确认。"
            : "生成未执行：没有可生成的简历草稿。",
      });
      return;
    }
    if (generatedResume) releaseGeneratedHtmlUrl(generatedResume.htmlUrl);
    setGeneratedResume(null);
    setResult({ kind: "pending", message: "生成请求已发送，正在生成简历。" });
    setRenderLoading(true);
    try {
      const history = toAgentHistory(currentConversationMessages);
      const baseProfile = buildProfilePayload();
      const step1Profile = {
        ...baseProfile,
        template_code: normalizeTemplateCodeForUI(requested.template_code || baseProfile.template_code),
        language: normalizeLanguageForUI(requested.language || baseProfile.language),
      };
      const payload: Record<string, unknown> = {
        history,
        step1_profile: step1Profile,
        wizard_state: currentWizardState,
        render_ready: true,
        template_code: step1Profile.template_code,
        language: step1Profile.language,
        photo_pref: step1Profile.photo_pref,
        draft_json: (currentDraft || {}) as Record<string, unknown>,
      };
      if (step1Profile.photo_pref === "with_photo") payload.photo_data_url = photoDataUrl;

      console.info("[resume-craft] render request started", JSON.stringify({
        currentBackendStep,
        historyLength: history.length,
        hasDraft,
      }));
      const resp = (await callCareerforgeSkill(settings, "/careerforge/resume-craft/render", payload)) as Record<string, unknown>;
      const reportHtml = String(resp.report_html || "").trim();
      if (!reportHtml) throw new Error(String(resp.message || "未返回有效简历 HTML"));
      const reportUrl = normalizeAgentText(resp.report_url);
      let htmlUrl = "";
      if (reportUrl) {
        try {
          htmlUrl = new URL(reportUrl, window.location.origin).toString();
        } catch {
          htmlUrl = "";
        }
      }
      if (!htmlUrl) {
        htmlUrl = URL.createObjectURL(new Blob([reportHtml], { type: "text/html;charset=utf-8" }));
        generatedHtmlUrlsRef.current.push(htmlUrl);
      }
      setGeneratedResume({
        html: reportHtml,
        htmlUrl,
        pdfBase64: normalizeAgentText(resp.report_pdf_base64),
        pdfName: normalizeAgentText(resp.report_pdf_name) || "resume.pdf",
      });
      setResult({ kind: "success", message: "简历已生成。" });
      console.info("[resume-craft] render completed", JSON.stringify({
        htmlChars: reportHtml.length,
        htmlLink: true,
      }));
    } catch (err) {
      console.error("[resume-craft] render failed", err);
      pendingRenderRef.current = requested;
      setResult({ kind: "error", message: (err as Error).message || "生成失败" });
    } finally {
      setRenderLoading(false);
    }
  };

  const stepCard = (stepNo: StepNumber, content: ReactNode) => (
    <article className={`surface resume-craft-step-card ${stepNo === 1 ? "resume-craft-step1-card" : stepNo === 2 ? "resume-craft-step2-card" : "resume-craft-chat-step"}`} ref={(el) => (stepRefs.current[stepNo] = el)}>
      {content}
    </article>
  );

  return (
    <>
      {featureGuard.overlay}
    <section className={`resume-craft-page ${step === 3 ? "is-chat-page" : ""} ${step === 1 ? "is-step1-page" : ""} ${step === 2 ? "is-step2-page" : ""}`}>
      <NavLink to="/" className="back-home-btn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        返回
      </NavLink>
      <div className="resume-craft-layout">
        <div className={`resume-craft-wizard-viewport ${step === 3 ? "is-chat-viewport" : ""} ${step === 1 ? "is-step1-viewport" : ""} ${step === 2 ? "is-step2-viewport" : ""}`} style={step === 3 && viewportHeight ? { height: `${viewportHeight}px` } : undefined}>
          <div className="resume-craft-wizard-track" ref={wizardTrackRef} style={{ transform: `translateX(-${(step - 1) * STEP_SHIFT}%)` }}>
            {stepCard(
              1,
              <>
                <header className="resume-craft-step-head resume-craft-step1-head">
                  <div className="resume-craft-step1-head-copy">
                    <h2>{STEP_TITLES[1]}</h2>
                    <p>设置模板、语言、可选照片、目标岗位与 JD 摘要。</p>
                  </div>
                  <button type="button" className="primary-btn resume-craft-next-btn resume-craft-step1-next-btn" disabled={!canStep1Next} onClick={goNext}>下一步</button>
                  <div className="resume-craft-head-divider" />
                </header>
                <div className="resume-craft-step-grid resume-craft-step1-select-section">
                  <label className="resume-craft-control" htmlFor="rc-template">
                    <span className="resume-craft-control-label">模板</span>
                    <div className="resume-craft-select-shell">
                      <span className="resume-craft-select-icon" aria-hidden="true">TM</span>
                      <select id="rc-template" value={profile.template_code} onChange={(e) => setProfile((prev) => ({ ...prev, template_code: e.target.value }))}>
                        {TEMPLATE_OPTIONS.map((item) => (
                          <option key={item.value} value={item.value}>{item.label}</option>
                        ))}
                      </select>
                    </div>
                  </label>

                  <label className="resume-craft-control" htmlFor="rc-language">
                    <span className="resume-craft-control-label">语言</span>
                    <div className="resume-craft-select-shell">
                      <span className="resume-craft-select-icon" aria-hidden="true">LG</span>
                      <select id="rc-language" value={profile.language} onChange={(e) => setProfile((prev) => ({ ...prev, language: e.target.value }))}>
                        {LANGUAGE_OPTIONS.map((item) => (
                          <option key={item.value} value={item.value}>{item.label}</option>
                        ))}
                      </select>
                    </div>
                  </label>
                </div>

                <div className="resume-craft-photo-box">
                  <label className="resume-craft-photo-label" htmlFor="rc-photo">上传照片（可选，仅支持 PNG/JPG）</label>
                  <input
                    id="rc-photo"
                    ref={photoInputRef}
                    type="file"
                    accept=".png,.jpg,.jpeg,image/png,image/jpeg"
                    className="resume-craft-photo-input"
                    onChange={(e) => savePhotoFile(e.target.files?.[0] ?? null)}
                  />
                  <p className="resume-craft-photo-name">{photoLoading ? "读取照片中..." : photoFile ? `已选择：${photoFile.name}` : "未上传（默认按不放照片处理）"}</p>
                  {photoHint ? (
                    <p
                      className={`resume-craft-photo-hint ${
                        /仅支持|失败|重试/.test(photoHint) ? "error" : photoDataUrl ? "ok" : "note"
                      }`}
                    >
                      {photoHint}
                    </p>
                  ) : null}
                  {!photoHint && photoDataUrl ? <p className="resume-craft-photo-hint ok">✓ 照片已就绪，将按“放照片”生成。</p> : null}
                </div>
                <div className="resume-craft-soft-separator" aria-hidden="true" />

                <div className="resume-craft-form-grid resume-craft-step1-form-section">
                  <label className="resume-craft-control" htmlFor="rc-target-role">
                    <span className="resume-craft-control-label">目标岗位 <em>*</em></span>
                    <input id="rc-target-role" value={profile.target_role} placeholder="填写你期望的岗位方向，帮助我们为你定制简历内容" onChange={(e) => setProfile((prev) => ({ ...prev, target_role: e.target.value }))} />
                  </label>
                </div>

                <div className="resume-craft-form-grid resume-craft-step1-form-section">
                  <label className="resume-craft-control" htmlFor="rc-jd-summary">
                    <span className="resume-craft-control-label">目标 JD 摘要</span>
                    <textarea id="rc-jd-summary" value={profile.jd_summary} placeholder="示例：AI 应用开发工程师，要求 3 年 Python/TypeScript 经验，熟悉 LLM/RAG 技术栈，有分布式系统设计经验" onChange={(e) => setProfile((prev) => ({ ...prev, jd_summary: e.target.value }))} />
                  </label>
                </div>

              </>
            )}

            {stepCard(
              2,
              <>
                <header className="resume-craft-chat-head">
                  <div className="resume-craft-chat-head-left">
                    <h2>{STEP_TITLES[2]}</h2>
                    <p>填写姓名、联系方式等个人信息，以及教育背景。</p>
                    <div className="resume-craft-head-divider" />
                  </div>
                  <div className="resume-craft-head-actions">
                    <button type="button" className="ghost-btn resume-craft-back-btn resume-craft-chat-nav-btn" onClick={goPrev}>上一步</button>
                    <button type="button" className="primary-btn resume-craft-next-btn resume-craft-chat-nav-btn" onClick={goNext} disabled={!canStep2Next}>下一步</button>
                  </div>
                </header>

                <div className="resume-craft-param-brief">
                  <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'template'} onClick={() => setExpandedPill(expandedPill === 'template' ? null : 'template')}>{templateLabel(profile.template_code)}</button>
                  <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'language'} onClick={() => setExpandedPill(expandedPill === 'language' ? null : 'language')}>{profile.language === "zh" ? "中文" : profile.language === "en" ? "英文" : "中英文双版"}</button>
                  <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'photo'} onClick={() => setExpandedPill(expandedPill === 'photo' ? null : 'photo')}>{photoDataUrl ? "放照片" : "不放照片"}</button>
                  <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'targetRole'} onClick={() => setExpandedPill(expandedPill === 'targetRole' ? null : 'targetRole')}>{profile.target_role || "未填写"}</button>
                </div>
                {expandedPill === 'template' && (
                  <div className="resume-craft-pill-panel">
                    <select value={profile.template_code} onChange={(e) => setProfile((prev) => ({ ...prev, template_code: e.target.value }))}>
                      {TEMPLATE_OPTIONS.map((item) => (<option key={`pill-t-${item.value}`} value={item.value}>{item.label}</option>))}
                    </select>
                  </div>
                )}
                {expandedPill === 'language' && (
                  <div className="resume-craft-pill-panel">
                    <select value={profile.language} onChange={(e) => setProfile((prev) => ({ ...prev, language: e.target.value }))}>
                      {LANGUAGE_OPTIONS.map((item) => (<option key={`pill-l-${item.value}`} value={item.value}>{item.label}</option>))}
                    </select>
                  </div>
                )}
                {expandedPill === 'photo' && (
                  <div className="resume-craft-pill-panel">
                    <button type="button" className="ghost-btn" onClick={() => photoInputRef.current?.click()}>选择照片</button>
                  </div>
                )}
                {expandedPill === 'targetRole' && (
                  <div className="resume-craft-pill-panel">
                    <input value={profile.target_role} placeholder="目标岗位" onChange={(e) => setProfile((prev) => ({ ...prev, target_role: e.target.value }))} />
                  </div>
                )}

                <div className="resume-craft-form-grid">
                  <label className="resume-craft-control" htmlFor="rc-name">
                    <span className="resume-craft-control-label">姓名 <em>*</em></span>
                    <input id="rc-name" value={profile.personal_info.name} aria-invalid={touchedFields.name && !profile.personal_info.name.trim()} aria-describedby={touchedFields.name && !profile.personal_info.name.trim() ? "rc-name-error" : undefined} onBlur={() => setTouchedFields((prev) => ({ ...prev, name: true }))} onChange={(e) => setProfile((prev) => ({ ...prev, personal_info: { ...prev.personal_info, name: e.target.value } }))} />
                    {touchedFields.name && !profile.personal_info.name.trim() ? <span id="rc-name-error" className="resume-craft-control-error">请填写姓名</span> : null}
                  </label>
                  <label className="resume-craft-control" htmlFor="rc-phone">
                    <span className="resume-craft-control-label">手机 <em>*</em></span>
                    <input id="rc-phone" value={profile.personal_info.phone} aria-invalid={touchedFields.phone && !profile.personal_info.phone.trim()} aria-describedby={touchedFields.phone && !profile.personal_info.phone.trim() ? "rc-phone-error" : undefined} onBlur={() => setTouchedFields((prev) => ({ ...prev, phone: true }))} onChange={(e) => setProfile((prev) => ({ ...prev, personal_info: { ...prev.personal_info, phone: e.target.value } }))} />
                    {touchedFields.phone && !profile.personal_info.phone.trim() ? <span id="rc-phone-error" className="resume-craft-control-error">请填写手机号</span> : null}
                  </label>
                  <label className="resume-craft-control" htmlFor="rc-email">
                    <span className="resume-craft-control-label">邮箱 <em>*</em></span>
                    <input id="rc-email" value={profile.personal_info.email} aria-invalid={touchedFields.email && !profile.personal_info.email.trim()} aria-describedby={touchedFields.email && !profile.personal_info.email.trim() ? "rc-email-error" : undefined} onBlur={() => setTouchedFields((prev) => ({ ...prev, email: true }))} onChange={(e) => setProfile((prev) => ({ ...prev, personal_info: { ...prev.personal_info, email: e.target.value } }))} />
                    {touchedFields.email && !profile.personal_info.email.trim() ? <span id="rc-email-error" className="resume-craft-control-error">请填写邮箱</span> : null}
                  </label>
                  <label className="resume-craft-control" htmlFor="rc-city">
                    <span className="resume-craft-control-label">城市</span>
                    <input id="rc-city" value={profile.personal_info.city} onChange={(e) => setProfile((prev) => ({ ...prev, personal_info: { ...prev.personal_info, city: e.target.value } }))} />
                  </label>
                  <label className="resume-craft-control" htmlFor="rc-links">
                    <span className="resume-craft-control-label">链接（逗号分隔）</span>
                    <input id="rc-links" value={linksInput} placeholder="GitHub, LinkedIn" onChange={(e) => setLinksInput(e.target.value)} />
                  </label>
                </div>

                  <section className="resume-craft-education-wrap">
                    <div className="resume-craft-education-head-row">
                      <h3>
                        <span className="resume-craft-edu-icon" aria-hidden="true">EDU</span>
                        教育背景
                      </h3>
                      <div className="resume-craft-education-nav" aria-label="教育经历切换">
                        <button
                          type="button"
                          className="ghost-btn resume-craft-education-nav-btn"
                          aria-label="上一段教育经历"
                          title="上一段教育经历"
                          onClick={() => switchEducation(activeEducationIndex - 1)}
                          disabled={activeEducationIndex === 0}
                        >
                          ←
                        </button>
                        <span>{activeEducationIndex + 1} / {educationRows.length}</span>
                        <button
                          type="button"
                          className="ghost-btn resume-craft-education-nav-btn"
                          aria-label="下一段教育经历"
                          title="下一段教育经历"
                          onClick={() => switchEducation(activeEducationIndex + 1)}
                          disabled={activeEducationIndex >= educationRows.length - 1}
                        >
                          →
                        </button>
                      </div>
                    </div>
                    <div className="resume-craft-education-carousel" ref={educationCarouselRef}>
                      <div className="resume-craft-edu-item" key={`edu-${activeEducationIndex}`}>
                        <div className="resume-craft-edu-main-row">
                          <input
                            value={edu.school}
                            placeholder="学校 *"
                            onChange={(e) => updateEducationField(index, "school", e.target.value)}
                          />
                          <input
                            value={edu.major}
                            placeholder="专业 *"
                            onChange={(e) => updateEducationField(index, "major", e.target.value)}
                          />
                          <input
                            value={edu.degree}
                            placeholder="学位 *"
                            onChange={(e) => updateEducationField(index, "degree", e.target.value)}
                          />
                          <div className="resume-craft-edu-time-range">
                            <div className="resume-craft-month-picker-field start" ref={openMonthPicker?.index === index && openMonthPicker?.part === "start" ? monthPickerWrapRef : null}>
                              <button
                                type="button"
                                className="resume-craft-month-display"
                                aria-label="开始时间（月）"
                                onClick={() => openMonthCalendar(index, "start", splitPeriod(edu.period).start)}
                              >
                                {formatMonthDisplay(splitPeriod(edu.period).start) || "开始时间"}
                              </button>
                              {openMonthPicker?.index === index && openMonthPicker?.part === "start" ? (
                                <div className="resume-craft-month-popover" role="dialog" aria-label="开始时间选择" onMouseDown={(event) => event.stopPropagation()} onClick={(event) => event.stopPropagation()}>
                                  <div className="resume-craft-month-popover-head">
                                    <span>年份</span>
                                    <select
                                      className="resume-craft-month-year-select"
                                      value={monthPickerYear}
                                      aria-label="选择年份"
                                      onChange={(e) => setMonthPickerYear(Number(e.target.value))}
                                    >
                                      {Array.from({ length: 81 }, (_, i) => monthPickerYear - 40 + i).map((year) => (
                                        <option key={`start-year-${year}`} value={year}>
                                          {year} 年
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                  <div className="resume-craft-month-grid">
                                    {Array.from({ length: 12 }, (_, m) => {
                                      const month = m + 1;
                                      const picked = parseMonthValue(splitPeriod(edu.period).start);
                                      const isActive = picked?.year === monthPickerYear && picked?.month === month;
                                      return (
                                        <button
                                          key={`start-${month}`}
                                          type="button"
                                          className={`resume-craft-month-cell ${isActive ? "active" : ""}`}
                                          onClick={() => selectMonthFromPicker(index, "start", monthPickerYear, month)}
                                        >
                                          {String(month).padStart(2, "0")} 月
                                        </button>
                                      );
                                    })}
                                  </div>
                                </div>
                              ) : null}
                            </div>
                            <span aria-hidden="true">至</span>
                            <div className="resume-craft-month-picker-field end" ref={openMonthPicker?.index === index && openMonthPicker?.part === "end" ? monthPickerWrapRef : null}>
                              <button
                                type="button"
                                className="resume-craft-month-display"
                                aria-label="结束时间（月）"
                                onClick={() => openMonthCalendar(index, "end", splitPeriod(edu.period).end)}
                              >
                                {formatMonthDisplay(splitPeriod(edu.period).end) || "结束时间"}
                              </button>
                              {openMonthPicker?.index === index && openMonthPicker?.part === "end" ? (
                                <div className="resume-craft-month-popover" role="dialog" aria-label="结束时间选择" onMouseDown={(event) => event.stopPropagation()} onClick={(event) => event.stopPropagation()}>
                                  <div className="resume-craft-month-popover-head">
                                    <span>年份</span>
                                    <select
                                      className="resume-craft-month-year-select"
                                      value={monthPickerYear}
                                      aria-label="选择年份"
                                      onChange={(e) => setMonthPickerYear(Number(e.target.value))}
                                    >
                                      {Array.from({ length: 81 }, (_, i) => monthPickerYear - 40 + i).map((year) => (
                                        <option key={`end-year-${year}`} value={year}>
                                          {year} 年
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                  <div className="resume-craft-month-grid">
                                    {Array.from({ length: 12 }, (_, m) => {
                                      const month = m + 1;
                                      const picked = parseMonthValue(splitPeriod(edu.period).end);
                                      const isActive = picked?.year === monthPickerYear && picked?.month === month;
                                      return (
                                        <button
                                          key={`end-${month}`}
                                          type="button"
                                          className={`resume-craft-month-cell ${isActive ? "active" : ""}`}
                                          onClick={() => selectMonthFromPicker(index, "end", monthPickerYear, month)}
                                        >
                                          {String(month).padStart(2, "0")} 月
                                        </button>
                                      );
                                    })}
                                  </div>
                                </div>
                              ) : null}
                            </div>
                          </div>
                        </div>
                        <div className="resume-craft-edu-highlight-row">
                          <textarea
                            value={edu.highlights}
                            placeholder="亮点（可选）：如 GPA、奖学金、核心课程、研究方向、项目成果"
                            onChange={(e) => updateEducationField(index, "highlights", e.target.value)}
                          />
                          <div className="resume-craft-edu-side-actions">
                            {(profile.education.length ? profile.education.length : 1) > 1 ? (
                              <button type="button" className="ghost-btn resume-craft-edu-remove-btn" onClick={() => removeEducationRow(index)}>
                                删除
                              </button>
                            ) : null}
                            <button type="button" className="ghost-btn resume-craft-add-education-btn" onClick={addEducationRow}>+ 新增教育经历</button>
                          </div>
                        </div>
                      </div>
                    </div>
                </section>
              </>
            )}

            {stepCard(
              3,
              <>
                <header className="resume-craft-chat-head resume-craft-combined-head">
                  <div className="resume-craft-chat-head-left">
                    <h2>Step3 工作/项目/技能</h2>
                    <p>{CHAT_STEP_DESCRIPTIONS[activePhase.step]}</p>
                    <div className="resume-craft-head-divider" />
                  </div>
                  <div className="resume-craft-head-actions">
                    <button type="button" className="ghost-btn resume-craft-back-btn resume-craft-chat-nav-btn" onClick={goPrev}>上一步</button>
                    <button type="button" className="ghost-btn resume-craft-restart-btn resume-craft-chat-nav-btn" onClick={onRestartCurrentChat} disabled={chatLoading || renderLoading}>重新开始</button>
                  </div>
                </header>

                <div className="resume-craft-param-brief">
                  <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'template'} onClick={() => setExpandedPill(expandedPill === 'template' ? null : 'template')}>{templateLabel(profile.template_code)}</button>
                  <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'language'} onClick={() => setExpandedPill(expandedPill === 'language' ? null : 'language')}>{profile.language === "zh" ? "中文" : profile.language === "en" ? "英文" : "中英文双版"}</button>
                  <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'photo'} onClick={() => setExpandedPill(expandedPill === 'photo' ? null : 'photo')}>{photoDataUrl ? "放照片" : "不放照片"}</button>
                  <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'targetRole'} onClick={() => setExpandedPill(expandedPill === 'targetRole' ? null : 'targetRole')}>{profile.target_role || "未填写"}</button>
                  {activeBackendStep === 4 ? <span className="resume-craft-pill">经历进度 {wizardState.step_states.step4.finalized_experiences.length}/{profile.expected_experience_count}</span> : null}
                </div>
                {expandedPill === 'template' && (
                  <div className="resume-craft-pill-panel">
                    <select value={profile.template_code} onChange={(e) => setProfile((prev) => ({ ...prev, template_code: e.target.value }))}>
                      {TEMPLATE_OPTIONS.map((item) => (<option key={`pill-ct-${item.value}`} value={item.value}>{item.label}</option>))}
                    </select>
                  </div>
                )}
                {expandedPill === 'language' && (
                  <div className="resume-craft-pill-panel">
                    <select value={profile.language} onChange={(e) => setProfile((prev) => ({ ...prev, language: e.target.value }))}>
                      {LANGUAGE_OPTIONS.map((item) => (<option key={`pill-cl-${item.value}`} value={item.value}>{item.label}</option>))}
                    </select>
                  </div>
                )}
                {expandedPill === 'photo' && (
                  <div className="resume-craft-pill-panel">
                    <button type="button" className="ghost-btn" onClick={() => photoInputRef.current?.click()}>选择照片</button>
                  </div>
                )}
                {expandedPill === 'targetRole' && (
                  <div className="resume-craft-pill-panel">
                    <input value={profile.target_role} placeholder="目标岗位" onChange={(e) => setProfile((prev) => ({ ...prev, target_role: e.target.value }))} />
                  </div>
                )}

                {result.kind !== "idle" ? (
                  <div
                    className={`resume-craft-render-feedback is-${result.kind}`}
                    role={result.kind === "error" ? "alert" : "status"}
                    aria-live="polite"
                  >
                    <span className="resume-craft-render-feedback-label">
                      {result.kind === "pending" ? "生成中" : result.kind === "success" ? "生成完成" : "生成失败"}
                    </span>
                    <p>{result.message}</p>
                    {result.kind === "success" && generatedResume ? (
                      <a href={generatedResume.htmlUrl} target="_blank" rel="noreferrer" className="resume-craft-html-link">
                        查看 HTML 简历
                      </a>
                    ) : null}
                    {result.kind === "error" ? (
                      <button
                        type="button"
                        className="ghost-btn resume-craft-retry-btn"
                        onClick={() => {
                          const pending = pendingRenderRef.current;
                          if (pending) void renderResume({ ...pending, bypassConsent: true });
                        }}
                        disabled={!pendingRenderRef.current || renderLoading}
                      >
                        重试生成
                      </button>
                    ) : null}
                  </div>
                ) : null}

                <div
                  ref={resumeViewRef}
                  className={`resume-craft-view-stack resume-craft-view-${resumeView}`}
                  aria-live="polite"
                >
                  <div
                    ref={chatPanelRef}
                    className="resume-craft-view-panel resume-craft-chat-panel"
                    aria-hidden={resumeView !== "chat"}
                  >
                    <div className="chat-log resume-craft-chat-log">
                      {conversationMessages.map((msg, idx) => (
                        <div key={`${msg.backendStep}-${msg.role}-${idx}`} className={`msg ${msg.role}`}>
                          {msg.role === "assistant" ? <span className="msg-ai-avatar" aria-hidden="true">AI</span> : null}
                          <div className="resume-craft-bubble-wrap">
                            {msg.isPreview && msg.role === "assistant" ? (
                              <div className="resume-craft-message-bubble resume-craft-preview-message">
                                <div dangerouslySetInnerHTML={{ __html: simpleMarkdownToHtml(msg.content) }} />
                                {msg.htmlLink ? (
                                  <a href={msg.htmlLink.href} target="_blank" rel="noreferrer" className="resume-craft-html-link">
                                    {msg.htmlLink.label}
                                  </a>
                                ) : null}
                              </div>
                            ) : (
                              <span className="resume-craft-message-bubble">
                                {msg.content}
                                {msg.htmlLink ? (
                                  <a href={msg.htmlLink.href} target="_blank" rel="noreferrer" className="resume-craft-html-link">
                                    {msg.htmlLink.label}
                                  </a>
                                ) : null}
                              </span>
                            )}
                            <small className="resume-craft-msg-time">{msg.timestamp}</small>
                          </div>
                        </div>
                      ))}
                      {chatLoading ? (
                        <div className="msg assistant">
                          <span className="msg-ai-avatar" aria-hidden="true">AI</span>
                          <div className="resume-craft-bubble-wrap">
                            <span>思考中...</span>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  </div>

                  <div
                    ref={generatingPanelRef}
                    className="resume-craft-view-panel resume-craft-generating-panel"
                    aria-hidden={resumeView !== "generating"}
                  >
                    <div className="resume-craft-generating-state">
                      <span className="resume-craft-generating-spinner" aria-hidden="true" />
                      <strong>正在生成简历</strong>
                      <span>请稍候，生成结果会显示在当前页面。</span>
                    </div>
                  </div>

                  <section
                    ref={resultPanelRef}
                    className="resume-craft-view-panel resume-craft-generated-panel"
                    aria-hidden={resumeView !== "result"}
                  >
                    {generatedResume ? (
                      <>
                        <header className="resume-craft-generated-head">
                          <div>
                            <h3>简历结果</h3>
                            <p>已在当前页面生成，可继续返回对话修改。</p>
                          </div>
                          <div className="resume-craft-generated-actions">
                            <a
                              href={generatedResume.htmlUrl}
                              target="_blank"
                              rel="noreferrer"
                              className="ghost-btn resume-craft-result-action-btn"
                            >
                              查看 HTML
                            </a>
                            {generatedResume.pdfBase64 ? (
                              <a
                                href={`data:application/pdf;base64,${generatedResume.pdfBase64}`}
                                download={generatedResume.pdfName}
                                className="primary-btn resume-craft-result-action-btn"
                              >
                                下载 PDF
                              </a>
                            ) : null}
                            <button type="button" className="ghost-btn resume-craft-result-action-btn" onClick={returnToChat}>
                              返回修改
                            </button>
                          </div>
                        </header>
                        <div className="resume-craft-generated-frame-wrap">
                          <iframe
                            className="resume-craft-generated-frame"
                            title="生成的简历预览"
                            srcDoc={generatedResume.html}
                            sandbox=""
                          />
                        </div>
                      </>
                    ) : null}
                  </section>
                </div>

              </>
            )}
          </div>
        </div>

        {step === 3 && resumeView === "chat" ? (
          <div className="resume-craft-fixed-composer">
            <form className="chat-input resume-craft-chat-input" onSubmit={onSendChat}>
              <textarea
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    void sendChatMessage(chatInput);
                  }
                }}
                placeholder={CHAT_INPUT_PLACEHOLDERS[activeBackendStep]}
                disabled={chatLoading || renderLoading}
                rows={1}
                aria-label="输入当前步骤信息"
              />
              <button className="primary-btn resume-craft-send-btn" disabled={!chatInput.trim() || chatLoading || renderLoading}>发送</button>
            </form>
          </div>
        ) : null}

      </div>
      <ConsentModal
        open={showConsentPrompt}
        onClose={() => setShowConsentPrompt(false)}
        onAccept={() => {
          const pending = pendingRenderRef.current;
          if (pending) void renderResume({ ...pending, bypassConsent: true });
        }}
      />
    </section>
    </>
  );
}
