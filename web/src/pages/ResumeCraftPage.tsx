import { FormEvent, ReactNode, SyntheticEvent, useEffect, useMemo, useRef, useState } from "react";
import { callCareerforgeSkill } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";
import { loadResumeCraftDraft, saveResumeCraftDraft } from "../lib/storage";
import type { EducationItem, ResumeCraftWizardState, Step1Profile } from "../types";
import { ConsentModal } from "../components/ConsentModal";
import { useConsent } from "../context/ConsentContext";

type Msg = { role: "user" | "assistant"; content: string; timestamp: string };
type StepNumber = 1 | 2 | 3 | 4 | 5;
type ChatStep = 3 | 4 | 5;

const UI_TO_BACKEND: Record<number, number> = { 1: 1, 2: 3, 3: 4, 4: 5, 5: 6 };
function uiStepToBackendKey(step: number): string { return `step${UI_TO_BACKEND[step]}`; }

type ResultState = {
  kind: "idle" | "report" | "error";
  reportHtml: string;
  message: string;
};

const STEPS: StepNumber[] = [1, 2, 3, 4, 5];
const CHAT_STEPS: ChatStep[] = [3, 4, 5];
const STEP_SHIFT = 100 / 5;

const TEMPLATE_OPTIONS = [
  { value: "01", label: "杂志编辑风" },
  { value: "02", label: "极简主义" },
  { value: "03", label: "深蓝双栏" },
  { value: "04", label: "深灰左栏" },
  { value: "05", label: "深色头部" },
  { value: "06", label: "清新青色" },
  { value: "07", label: "优雅对称" },
];

const LANGUAGE_OPTIONS = [
  { value: "zh", label: "中文" },
  { value: "en", label: "英文" },
  { value: "both", label: "中英文双版" },
];

const STEP_PROMPTS: Record<ChatStep, string> = {
  3: "我们进入 Step3（工作/项目经历）。请描述第一段经历的场景、职责、行动和结果。",
  4: "我们进入 Step4（技能与证书）。请先列出与你目标岗位最相关的技能与证书。",
  5: "我们进入 Step5（确认与偏好）。请确认最想突出项、语气偏好，以及是否可生成简历。",
};

const STEP_TITLES: Record<StepNumber, string> = {
  1: "Step1 基础信息",
  2: "Step2 个人信息与教育背景",
  3: "Step3 工作/项目经历（Grill）",
  4: "Step4 技能与证书（对话）",
  5: "Step5 确认与偏好（对话）",
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

const EMPTY_EDUCATION: EducationItem = {
  school: "",
  major: "",
  degree: "",
  period: "",
  highlights: "",
};

function simpleMarkdownToHtml(md: string): string {
  return md
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

function stepKey(step: ChatStep) {
  return uiStepToBackendKey(step) as "step3" | "step4" | "step5" | "step6";
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

function getStepReplyGuard(step: ChatStep, text: string) {
  const content = String(text || "");
  if (step === 3) return content.trim().length > 0;
  if (step === 4) return /技能|证书|工具|语言能力|熟练度/.test(content);
  return /确认|偏好|语气|突出|生成/.test(content);
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
  const { accepted } = useConsent();
  const [showConsentPrompt, setShowConsentPrompt] = useState(false);

  const [step, setStep] = useState<StepNumber>(1);
  const [profile, setProfile] = useState<Step1Profile>(() => loadResumeCraftDraft() ?? EMPTY_PROFILE);
  const [linksInput, setLinksInput] = useState(() => profile.personal_info.links.join(", "));

  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoDataUrl, setPhotoDataUrl] = useState("");
  const [photoHint, setPhotoHint] = useState("");
  const [photoLoading, setPhotoLoading] = useState(false);

  const [wizardState, setWizardState] = useState<ResumeCraftWizardState>(EMPTY_WIZARD);
  const [messagesByStep, setMessagesByStep] = useState<Record<ChatStep, Msg[]>>({
    3: [{ role: "assistant", content: STEP_PROMPTS[3], timestamp: nowTimeLabel() }],
    4: [{ role: "assistant", content: STEP_PROMPTS[4], timestamp: nowTimeLabel() }],
    5: [{ role: "assistant", content: STEP_PROMPTS[5], timestamp: nowTimeLabel() }],
  });
  const [missingByStep, setMissingByStep] = useState<Record<ChatStep, string[]>>({
    3: ["experience"],
    4: ["skills"],
    5: ["confirm"],
  });

  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [renderLoading, setRenderLoading] = useState(false);
  const [result, setResult] = useState<ResultState>({ kind: "idle", reportHtml: "", message: "" });
  const [showFinalPreview, setShowFinalPreview] = useState(false);
  const [reportName, setReportName] = useState("resume-craft-report.html");
  const [reportPdfName, setReportPdfName] = useState("resume-craft-report.pdf");
  const [reportPdfBase64, setReportPdfBase64] = useState("");
  const [frameHeight, setFrameHeight] = useState(980);
  const [viewportHeight, setViewportHeight] = useState<number | null>(null);
  const [openMonthPicker, setOpenMonthPicker] = useState<{ index: number; part: "start" | "end" } | null>(null);
  const [monthPickerYear, setMonthPickerYear] = useState<number>(new Date().getFullYear());
  const [expandedPill, setExpandedPill] = useState<string | null>(null);
  const [touchedFields, setTouchedFields] = useState<Record<string, boolean>>({});

  const previewFrameRef = useRef<HTMLIFrameElement | null>(null);
  const photoInputRef = useRef<HTMLInputElement | null>(null);
  const wizardTrackRef = useRef<HTMLDivElement | null>(null);
  const stepRefs = useRef<Record<StepNumber, HTMLElement | null>>({ 1: null, 2: null, 3: null, 4: null, 5: null });
  const monthPickerWrapRef = useRef<HTMLDivElement | null>(null);
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

  const activeChatStep = step >= 3 ? (step as ChatStep) : null;
  const activeMissing = activeChatStep ? missingByStep[activeChatStep] : [];

  const canGenerate = useMemo(() => {
    const hasExperience = wizardState.step_states.step4.finalized_experiences.length > 0;
    return wizardState.collected_by_step.step6_confirmed && hasExperience && !renderLoading;
  }, [wizardState, renderLoading]);

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
    const onPointerDown = (event: MouseEvent) => {
      if (!openMonthPicker) return;
      const target = event.target as Node | null;
      if (monthPickerWrapRef.current && target && monthPickerWrapRef.current.contains(target)) return;
      setOpenMonthPicker(null);
    };
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && openMonthPicker) {
        setOpenMonthPicker(null);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onEscape);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
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
    if (step < 5) {
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
    if (step === 2) {
      setProfile((prev) => ({ ...prev, education: [{ ...EMPTY_EDUCATION }] }));
      setWizardState((prev) => ({
        ...prev,
        collected_by_step: { ...prev.collected_by_step, education: [] },
        step_states: { ...prev.step_states, step3: { turn_count: 0, confirmed: false } },
      }));
      return;
    }
    if (!activeChatStep) return;
    setMessagesByStep((prev) => ({ ...prev, [activeChatStep]: [{ role: "assistant", content: STEP_PROMPTS[activeChatStep], timestamp: nowTimeLabel() }] }));
    setMissingByStep((prev) => ({ ...prev, [activeChatStep]: [activeChatStep === 3 ? "experience" : activeChatStep === 4 ? "skills" : "confirm"] }));
    setWizardState((prev) => {
      const next = JSON.parse(JSON.stringify(prev)) as ResumeCraftWizardState;
      const key = stepKey(activeChatStep);
      next.chat_history_by_step[key] = [];
      if (activeChatStep === 3) {
        next.collected_by_step.experiences = [];
        next.step_states.step4 = {
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
          },
        };
      }
      if (activeChatStep === 4) {
        next.collected_by_step.skills_and_certs = [];
        next.step_states.step5 = { turn_count: 0, confirmed: false };
      }
      if (activeChatStep === 5) {
        next.collected_by_step.final_preferences = "";
        next.collected_by_step.step6_confirmed = false;
        next.step_states.step6 = {
          turn_count: 0,
          confirmed: false,
          preview_ready: false,
          awaiting_confirm: false,
          preview_markdown: "",
          draft_json: {},
          revision_count: 0,
        };
      }
      return next;
    });
    setChatInput("");
  };

  const sendChatMessage = async (messageText: string) => {
    if (!activeChatStep || !messageText.trim() || chatLoading) return;
  
    const userMessage: Msg = { role: "user", content: messageText.trim(), timestamp: nowTimeLabel() };
    const nextMessages = [...messagesByStep[activeChatStep], userMessage];
    setMessagesByStep((prev) => ({ ...prev, [activeChatStep]: nextMessages }));
    setChatInput("");
    setChatLoading(true);
  
    try {
      const step1Profile = buildProfilePayload();
      const resp = (await callCareerforgeSkill(settings, "/careerforge/resume-craft/chat-turn", {
        message: userMessage.content,
        history: nextMessages,
        current_step: UI_TO_BACKEND[activeChatStep],
        step1_profile: step1Profile,
        wizard_state: wizardState,
        step_profile: wizardState.collected_by_step,
        template_code: step1Profile.template_code,
        language: step1Profile.language,
        photo_pref: step1Profile.photo_pref,
        experience_state: wizardState.step_states.step4,
      })) as Record<string, unknown>;
  
      const serverReply = String(resp.reply || "").trim();
      const step6PreviewMarkdown = String(resp.step6_preview_markdown || "").trim();
      const step6AppliedChanges = Array.isArray(resp.step6_applied_changes)
        ? (resp.step6_applied_changes as unknown[])
            .map((item) => String(item || "").trim())
            .filter(Boolean)
        : [];
      let safeReply = serverReply || STEP_PROMPTS[activeChatStep];
      if (activeChatStep === 3) {
        safeReply = serverReply || STEP_PROMPTS[activeChatStep];
      } else if (activeChatStep === 5) {
        if (!safeReply && step6PreviewMarkdown) {
          safeReply = `以下是准备生成的内容，请先确认：\n\n${step6PreviewMarkdown}`;
        }
      } else {
        safeReply = getStepReplyGuard(activeChatStep, serverReply) ? serverReply : STEP_PROMPTS[activeChatStep];
      }
  
      if (activeChatStep === 5 && step6PreviewMarkdown && !safeReply.includes(step6PreviewMarkdown)) {
        const changeText = step6AppliedChanges.length
          ? `已应用修改：\n${step6AppliedChanges.map((item) => `- ${item}`).join("\n")}\n\n`
          : "";
        safeReply = `${changeText}以下是准备生成的内容，请先确认：\n\n${step6PreviewMarkdown}\n\n如无误请回复"确认生成"，或继续提出修改意见。`;
      }
  
      const nextWizard = (resp.wizard_state as ResumeCraftWizardState | undefined) || wizardState;
      const missingFields = Array.isArray(resp.missing_fields) ? (resp.missing_fields as string[]) : [];
      const nextStepSuggestion = String(resp.next_step_suggestion || "stay");
      const action = String(resp.action || "");
  
      setWizardState(nextWizard);
      setMissingByStep((prev) => ({ ...prev, [activeChatStep]: missingFields }));
      setMessagesByStep((prev) => ({
        ...prev,
        [activeChatStep]: [...nextMessages, { role: "assistant", content: safeReply || STEP_PROMPTS[activeChatStep], timestamp: nowTimeLabel() }],
      }));
      if (activeChatStep === 3 && action === "experience_done" && nextStepSuggestion === "next") {
        setStep(4);
      }
      if (activeChatStep === 4 && nextStepSuggestion === "next") {
        setStep(5);
      }
      if (activeChatStep === 5 && action === "step6_confirm") {
        // Keep user in Step5 and enable render button only after explicit confirmation.
        setStep(5);
      }
    } catch (err) {
      setMessagesByStep((prev) => ({
        ...prev,
        [activeChatStep]: [...nextMessages, { role: "assistant", content: (err as Error).message || "请求失败，请重试。", timestamp: nowTimeLabel() }],
      }));
    } finally {
      setChatLoading(false);
    }
  };
  
  const onSendChat = async (e: FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    await sendChatMessage(chatInput.trim());
  };
  
  const generatePreview = async () => {
    await sendChatMessage("请生成简历预览");
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
    setProfile((prev) => ({ ...prev, education: [...(prev.education.length ? prev.education : [{ ...EMPTY_EDUCATION }]), { ...EMPTY_EDUCATION }] }));
  };

  const removeEducationRow = (index: number) => {
    setProfile((prev) => {
      const rows = prev.education.length ? [...prev.education] : [{ ...EMPTY_EDUCATION }];
      const nextRows = rows.filter((_, idx) => idx !== index);
      return { ...prev, education: nextRows.length ? nextRows : [{ ...EMPTY_EDUCATION }] };
    });
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
      step_states: { ...prev.step_states, step3: { turn_count: compact.length, confirmed: compact.length > 0 } },
    }));
  }, [profile.education]);

  const renderResume = async (overrides?: { template_code?: string; language?: string }) => {
    if (!accepted) {
      setShowConsentPrompt(true);
      return;
    }
    if (!canGenerate) return;
    setRenderLoading(true);
    try {
      const history = CHAT_STEPS.flatMap((s) => messagesByStep[s]);
      const baseProfile = buildProfilePayload();
      const step1Profile = {
        ...baseProfile,
        template_code: normalizeTemplateCodeForUI(overrides?.template_code || baseProfile.template_code),
        language: normalizeLanguageForUI(overrides?.language || baseProfile.language),
      };
      const payload: Record<string, unknown> = {
        history,
        step1_profile: step1Profile,
        wizard_state: wizardState,
        finalized_step_data: wizardState.collected_by_step,
        finalized_experiences: wizardState.step_states.step4.finalized_experiences,
        template_code: step1Profile.template_code,
        language: step1Profile.language,
        photo_pref: step1Profile.photo_pref,
        draft_json: (wizardState.step_states.step6?.draft_json || {}) as Record<string, unknown>,
      };
      if (step1Profile.photo_pref === "with_photo") payload.photo_data_url = photoDataUrl;

      const resp = (await callCareerforgeSkill(settings, "/careerforge/resume-craft/render", payload)) as Record<string, unknown>;
      const reportHtml = String(resp.report_html || "").trim();
      if (!reportHtml) throw new Error(String(resp.message || "未返回有效简历 HTML"));
      setResult({ kind: "report", reportHtml, message: "" });
      setReportName(String(resp.report_name || "resume-craft-report.html"));
      const nextPdfName = String(resp.report_pdf_name || "resume-craft-report.pdf").trim();
      const nextPdfBase64 = String(resp.report_pdf_base64 || "").trim();
      setReportPdfName(nextPdfName || "resume-craft-report.pdf");
      setReportPdfBase64(nextPdfBase64);
      setShowFinalPreview(true);
    } catch (err) {
      setResult({ kind: "error", reportHtml: "", message: (err as Error).message || "生成失败" });
      setReportPdfName("resume-craft-report.pdf");
      setReportPdfBase64("");
      setShowFinalPreview(false);
    } finally {
      setRenderLoading(false);
    }
  };

  const onPreviewLoad = (e: SyntheticEvent<HTMLIFrameElement>) => {
    const doc = e.currentTarget.contentDocument;
    if (!doc?.body) return;
    const h = Math.max(doc.body.scrollHeight, doc.documentElement?.scrollHeight || 0, 900);
    setFrameHeight(Math.min(Math.max(h + 16, 900), 3400));
  };

  const exportHtml = () => {
    if (result.kind !== "report") return;
    const blob = new Blob([result.reportHtml], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = reportName;
    link.click();
    URL.revokeObjectURL(url);
  };

  const exportPdf = () => {
    if (result.kind !== "report") return;
    if (reportPdfBase64) {
      try {
        const binary = window.atob(reportPdfBase64.replace(/\s+/g, ""));
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) {
          bytes[i] = binary.charCodeAt(i);
        }
        const blob = new Blob([bytes], { type: "application/pdf" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = reportPdfName || "resume-craft-report.pdf";
        link.click();
        URL.revokeObjectURL(url);
        return;
      } catch {
        // fallback to browser print below
      }
    }
    const frame = previewFrameRef.current;
    const win = frame?.contentWindow;
    if (!win) return;
    win.focus();
    win.print();
  };

  const backToWizardFromPreview = () => {
    setShowFinalPreview(false);
    setPhotoLoading(false);
    setProfile((prev) => ({
      ...prev,
      template_code: normalizeTemplateCodeForUI(prev.template_code),
      language: normalizeLanguageForUI(prev.language),
    }));
    setStep(1);
  };

  const stepCard = (stepNo: StepNumber, content: ReactNode) => (
    <article className={`surface resume-craft-step-card ${stepNo <= 1 ? "resume-craft-step1-card" : "resume-craft-chat-step"}`} ref={(el) => (stepRefs.current[stepNo] = el)}>
      {content}
    </article>
  );

  if (showFinalPreview && result.kind === "report") {
    return (
      <section className="resume-craft-page">
        <div className="resume-craft-layout">
          <section className="surface resume-craft-final-page">
            <header className="resume-craft-final-head">
              <div>
                <h2>简历预览</h2>
                <p>已生成 HTML 简历，你可以直接预览或导出。</p>
              </div>
              <div className="resume-craft-final-head-actions">
                <label className="resume-craft-result-control">
                  <span>模板</span>
                  <select
                    value={normalizeTemplateCodeForUI(profile.template_code)}
                    onChange={(e) =>
                      setProfile((prev) => ({ ...prev, template_code: normalizeTemplateCodeForUI(e.target.value) }))
                    }
                  >
                    {TEMPLATE_OPTIONS.map((item) => (
                      <option key={`result-template-${item.value}`} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="resume-craft-result-control">
                  <span>语言</span>
                  <select
                    value={normalizeLanguageForUI(profile.language)}
                    onChange={(e) =>
                      setProfile((prev) => ({ ...prev, language: normalizeLanguageForUI(e.target.value) }))
                    }
                  >
                    {LANGUAGE_OPTIONS.map((item) => (
                      <option key={`result-language-${item.value}`} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="primary-btn resume-craft-regenerate-btn"
                  onClick={() => renderResume({ template_code: profile.template_code, language: profile.language })}
                  disabled={renderLoading}
                >
                  {renderLoading ? "重新生成中..." : "按当前模板/语言重新生成"}
                </button>
                <button type="button" className="ghost-btn" onClick={backToWizardFromPreview}>返回继续编辑</button>
                <button type="button" className="ghost-btn" onClick={exportHtml}>导出 HTML</button>
                <button type="button" className="ghost-btn" onClick={exportPdf}>导出 PDF</button>
              </div>
            </header>
            <iframe
              ref={previewFrameRef}
              title="Resume Craft HTML Preview Final"
              className="resume-craft-preview-frame resume-craft-final-frame"
              srcDoc={result.reportHtml}
              onLoad={onPreviewLoad}
              style={{ height: `${frameHeight}px` }}
            />
          </section>
        </div>
        <ConsentModal open={showConsentPrompt} onClose={() => { setShowConsentPrompt(false); if (accepted) void renderResume(); }} />
      </section>
    );
  }

  return (
    <section className="resume-craft-page">
      <div className="resume-craft-layout">
        <div className="resume-craft-wizard-viewport" style={viewportHeight ? { height: `${viewportHeight}px` } : undefined}>
          <div className="resume-craft-wizard-track" ref={wizardTrackRef} style={{ transform: `translateX(-${(step - 1) * STEP_SHIFT}%)` }}>
            {stepCard(
              1,
              <>
                <header className="resume-craft-step-head">
                  <div className="resume-craft-step-title-row">
                    <span className="resume-craft-step-tag">Step 1 / 5</span>
                    <span className="resume-craft-step-progress-note">基础信息填写</span>
                  </div>
                  <h2>{STEP_TITLES[1]}</h2>
                  <p>设置模板、语言、可选照片、目标岗位与 JD 摘要。</p>
                  <div className="resume-craft-head-divider" />
                </header>
                <div className="resume-craft-soft-separator" aria-hidden="true" />

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

                <div className="resume-craft-step-actions">
                  <button type="button" className="primary-btn resume-craft-next-btn" disabled={!canStep1Next} onClick={goNext}>下一步</button>
                </div>
              </>
            )}

            {stepCard(
              2,
              <>
                <header className="resume-craft-chat-head">
                  <div className="resume-craft-chat-head-left">
                    <span className="resume-craft-step-tag">Step 2 / 5</span>
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
                  <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'template'} onClick={() => setExpandedPill(expandedPill === 'template' ? null : 'template')}>模板 {profile.template_code}</button>
                  <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'language'} onClick={() => setExpandedPill(expandedPill === 'language' ? null : 'language')}>{profile.language === "zh" ? "中文" : profile.language === "en" ? "英文" : "中英文双版"}</button>
                  <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'photo'} onClick={() => setExpandedPill(expandedPill === 'photo' ? null : 'photo')}>{photoDataUrl ? "放照片" : "不放照片"}</button>
                  <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'targetRole'} onClick={() => setExpandedPill(expandedPill === 'targetRole' ? null : 'targetRole')}>岗位 {profile.target_role || "未填写"}</button>
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
                    <h3>
                      <span className="resume-craft-edu-icon" aria-hidden="true">EDU</span>
                      教育背景
                    </h3>
                    {(profile.education.length ? profile.education : [{ ...EMPTY_EDUCATION }]).map((edu, index) => (
                      <div className="resume-craft-edu-item" key={`edu-${index}`}>
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
                                <div className="resume-craft-month-popover" role="dialog" aria-label="开始时间选择">
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
                                <div className="resume-craft-month-popover" role="dialog" aria-label="结束时间选择">
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
                          {(profile.education.length ? profile.education.length : 1) > 1 ? (
                            <button type="button" className="ghost-btn resume-craft-edu-remove-btn" onClick={() => removeEducationRow(index)}>
                              删除
                            </button>
                          ) : null}
                        </div>
                      </div>
                  ))}
                  <button type="button" className="ghost-btn" onClick={addEducationRow}>+ 新增教育经历</button>
                </section>
              </>
            )}

            {([3, 4, 5] as ChatStep[]).map((chatStep) =>
              stepCard(
                chatStep,
                <>
                  <header className="resume-craft-chat-head">
                    <div className="resume-craft-chat-head-left">
                      <span className="resume-craft-step-tag">Step {chatStep} / 5</span>
                      <h2>{STEP_TITLES[chatStep]}</h2>
                      <p>{chatStep === 3 ? "每段经历最多 Grill 2-3 轮，达上限自动完成该段。" : "当前步骤仅收集本步骤字段，不跨步提问。"}</p>
                      <div className="resume-craft-head-divider" />
                    </div>
                    <div className="resume-craft-head-actions">
                      <button type="button" className="ghost-btn resume-craft-back-btn resume-craft-chat-nav-btn" onClick={goPrev}>上一步</button>
                      <button type="button" className="ghost-btn resume-craft-restart-btn resume-craft-chat-nav-btn" onClick={onRestartCurrentChat} disabled={chatLoading || renderLoading || step !== chatStep}>重新开始</button>
                      {chatStep < 5 ? (
                        <button type="button" className="primary-btn resume-craft-next-btn resume-craft-chat-nav-btn" onClick={goNext} disabled={step !== chatStep || activeMissing.length > 0}>下一步</button>
                      ) : null}
                    </div>
                  </header>

                  <div className="resume-craft-param-brief">
                    <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'template'} onClick={() => setExpandedPill(expandedPill === 'template' ? null : 'template')}>模板 {profile.template_code}</button>
                    <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'language'} onClick={() => setExpandedPill(expandedPill === 'language' ? null : 'language')}>{profile.language === "zh" ? "中文" : profile.language === "en" ? "英文" : "中英文双版"}</button>
                    <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'photo'} onClick={() => setExpandedPill(expandedPill === 'photo' ? null : 'photo')}>{photoDataUrl ? "放照片" : "不放照片"}</button>
                    <button type="button" className="resume-craft-pill-btn" aria-expanded={expandedPill === 'targetRole'} onClick={() => setExpandedPill(expandedPill === 'targetRole' ? null : 'targetRole')}>岗位 {profile.target_role || "未填写"}</button>
                    {chatStep === 3 ? <span className="resume-craft-pill">经历进度 {wizardState.step_states.step4.finalized_experiences.length}/{profile.expected_experience_count}</span> : null}
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

                  <div className="chat-log resume-craft-chat-log">
                    {(messagesByStep[chatStep] || []).map((msg, idx) => (
                      <div key={`${chatStep}-${msg.role}-${idx}`} className={`msg ${msg.role}`}>
                        {msg.role === "assistant" ? <span className="msg-ai-avatar" aria-hidden="true">AI</span> : null}
                        <div className="resume-craft-bubble-wrap">
                          <span>{msg.content}</span>
                          <small className="resume-craft-msg-time">{msg.timestamp}</small>
                        </div>
                      </div>
                    ))}
                    {chatLoading && step === chatStep ? (
                      <div className="msg assistant">
                        <span className="msg-ai-avatar" aria-hidden="true">AI</span>
                        <div className="resume-craft-bubble-wrap">
                          <span>思考中...</span>
                        </div>
                      </div>
                    ) : null}
                  </div>

                  <form className="chat-input resume-craft-chat-input" onSubmit={onSendChat}>
                    <input
                      value={step === chatStep ? chatInput : ""}
                      onChange={(e) => setChatInput(e.target.value)}
                      placeholder="输入当前步骤信息后发送"
                      disabled={step !== chatStep}
                      aria-label="输入当前步骤信息"
                    />
                    <button className="primary-btn resume-craft-send-btn" disabled={step !== chatStep || !chatInput.trim() || chatLoading || renderLoading}>发送</button>
                  </form>

                  <div className="resume-craft-readiness-note">
                    {step === chatStep ? (
                      activeMissing.length ? <p>请继续补充当前步骤信息。</p> : <p>当前步骤信息已满足最小完整度，可进入下一步。</p>
                    ) : (
                      <p>切换到本步骤后可继续对话。</p>
                    )}
                  </div>

                  {chatStep === 5 && wizardState?.step_states?.step6?.preview_markdown ? (
                    <div className="resume-craft-preview-panel">
                      <div className="resume-craft-preview-header">
                        <span className="resume-craft-preview-title">草稿预览</span>
                        <button
                          type="button"
                          className="ghost-btn resume-craft-preview-close"
                          onClick={() => setWizardState(prev => ({
                            ...prev,
                            step_states: {
                              ...prev.step_states,
                              step6: { ...prev.step_states.step6, preview_markdown: "" }
                            }
                          }))}
                        >
                          ✕
                        </button>
                      </div>
                      <div
                        className="resume-craft-preview-content"
                        dangerouslySetInnerHTML={{ __html: simpleMarkdownToHtml(wizardState.step_states.step6.preview_markdown) }}
                      />
                    </div>
                  ) : null}

                  {chatStep === 5 ? (
                    <div className="resume-craft-step-actions">
                      <button type="button" className="ghost-btn" disabled={renderLoading || chatLoading} onClick={generatePreview}>
                        预览草稿
                      </button>
                      <button type="button" className="primary-btn resume-craft-next-btn" disabled={!canGenerate} onClick={() => void renderResume()}>
                        {renderLoading ? "生成中..." : wizardState?.step_states?.step6?.preview_ready ? "确认生成简历" : "生成简历"}
                      </button>
                    </div>
                  ) : null}
                </>
              )
            )}
          </div>
        </div>

        {result.kind === "error" ? (
          <section className="surface resume-craft-output resume-craft-result-error" style={{ marginTop: 14 }}>
            <p className="resume-result-error">{result.message}</p>
            <button type="button" className="ghost-btn" onClick={() => void renderResume()}>重试</button>
          </section>
        ) : null}
      </div>
      <ConsentModal open={showConsentPrompt} onClose={() => { setShowConsentPrompt(false); if (accepted) void renderResume(); }} />
    </section>
  );
}
