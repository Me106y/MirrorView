import { FormEvent, ReactNode, SyntheticEvent, useEffect, useMemo, useRef, useState } from "react";
import { gsap } from "gsap";
import { callCareerforgeSkill } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";
import type { ResumeCraftWizardState, Step1Profile } from "../types";

type Msg = { role: "user" | "assistant"; content: string };
type StepNumber = 1 | 2 | 3 | 4 | 5 | 6;
type ChatStep = 3 | 4 | 5 | 6;

type ResultState = {
  kind: "idle" | "report" | "error";
  reportHtml: string;
  message: string;
};

const STEPS: StepNumber[] = [1, 2, 3, 4, 5, 6];
const CHAT_STEPS: ChatStep[] = [3, 4, 5, 6];
const STEP_SHIFT = 100 / 6;

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
  3: "我们进入 Step3（教育背景）。请先提供第一段教育信息：学校、专业、学位、时间。",
  4: "我们进入 Step4（工作/项目经历）。请描述第一段经历的场景、职责、行动和结果。",
  5: "我们进入 Step5（技能与证书）。请先列出与你目标岗位最相关的技能与证书。",
  6: "我们进入 Step6（确认与偏好）。请确认最想突出项、语气偏好，以及是否可生成简历。",
};

const STEP_TITLES: Record<StepNumber, string> = {
  1: "Step1 基础信息",
  2: "Step2 个人信息",
  3: "Step3 教育背景（对话）",
  4: "Step4 工作/项目经历（Grill）",
  5: "Step5 技能与证书（对话）",
  6: "Step6 确认与偏好（对话）",
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
    step4: { current_index: 1, followup_count: 0, drafts: [], finalized_experiences: [] },
    step5: { turn_count: 0, confirmed: false },
    step6: { turn_count: 0, confirmed: false },
  },
};

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
  return `step${step}` as "step3" | "step4" | "step5" | "step6";
}

function getStepReplyGuard(step: ChatStep, text: string) {
  const content = String(text || "");
  if (step === 3) return /教育|学校|专业|学位|在读|毕业/.test(content);
  if (step === 4) return /经历|项目|职责|挑战|行动|结果|量化/.test(content);
  if (step === 5) return /技能|证书|工具|语言能力|熟练度/.test(content);
  return /确认|偏好|语气|突出|生成/.test(content);
}

export function ResumeCraftPage() {
  const { settings } = useModelSettings();

  const [step, setStep] = useState<StepNumber>(1);
  const [profile, setProfile] = useState<Step1Profile>(EMPTY_PROFILE);
  const [linksInput, setLinksInput] = useState("");

  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoDataUrl, setPhotoDataUrl] = useState("");
  const [photoHint, setPhotoHint] = useState("");
  const [photoLoading, setPhotoLoading] = useState(false);

  const [wizardState, setWizardState] = useState<ResumeCraftWizardState>(EMPTY_WIZARD);
  const [messagesByStep, setMessagesByStep] = useState<Record<ChatStep, Msg[]>>({
    3: [{ role: "assistant", content: STEP_PROMPTS[3] }],
    4: [{ role: "assistant", content: STEP_PROMPTS[4] }],
    5: [{ role: "assistant", content: STEP_PROMPTS[5] }],
    6: [{ role: "assistant", content: STEP_PROMPTS[6] }],
  });
  const [missingByStep, setMissingByStep] = useState<Record<ChatStep, string[]>>({
    3: ["education"],
    4: ["experience"],
    5: ["skills"],
    6: ["confirm"],
  });

  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [renderLoading, setRenderLoading] = useState(false);
  const [result, setResult] = useState<ResultState>({ kind: "idle", reportHtml: "", message: "" });
  const [reportName, setReportName] = useState("resume-craft-report.html");
  const [frameHeight, setFrameHeight] = useState(980);
  const [viewportHeight, setViewportHeight] = useState<number | null>(null);

  const previewFrameRef = useRef<HTMLIFrameElement | null>(null);
  const photoInputRef = useRef<HTMLInputElement | null>(null);
  const wizardTrackRef = useRef<HTMLDivElement | null>(null);
  const stepRefs = useRef<Record<StepNumber, HTMLElement | null>>({ 1: null, 2: null, 3: null, 4: null, 5: null, 6: null });

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
    return hasName && hasPhone && hasEmail;
  }, [profile.personal_info]);

  const activeChatStep = step >= 3 ? (step as ChatStep) : null;
  const activeMessages = activeChatStep ? messagesByStep[activeChatStep] : [];
  const activeMissing = activeChatStep ? missingByStep[activeChatStep] : [];

  const canGenerate = useMemo(() => {
    const hasExperience = wizardState.step_states.step4.finalized_experiences.length > 0;
    return wizardState.collected_by_step.step6_confirmed && hasExperience && !renderLoading;
  }, [wizardState, renderLoading]);

  useEffect(() => {
    const track = wizardTrackRef.current;
    if (!track) return;
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    gsap.killTweensOf(track);
    gsap.to(track, {
      xPercent: -((step - 1) * STEP_SHIFT),
      duration: prefersReducedMotion ? 0 : 0.45,
      ease: "power2.inOut",
    });
    return () => gsap.killTweensOf(track);
  }, [step]);

  useEffect(() => {
    const card = stepRefs.current[step];
    if (!card) return;
    const updateHeight = () => setViewportHeight(card.offsetHeight);
    updateHeight();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => updateHeight());
    observer.observe(card);
    return () => observer.disconnect();
  }, [step, profile, photoHint, photoLoading, messagesByStep, wizardState, result.kind, chatLoading, renderLoading]);

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
    education: [],
    skills: wizardState.collected_by_step.skills_and_certs,
    certificates: [],
  });

  const goNext = () => {
    if (step === 1 && !canStep1Next) return;
    if (step === 2 && !canStep2Next) return;
    if (step < 6) setStep((prev) => (prev + 1) as StepNumber);
  };

  const goPrev = () => {
    if (step > 1) setStep((prev) => (prev - 1) as StepNumber);
  };

  const onRestartCurrentChat = () => {
    if (!activeChatStep) return;
    setMessagesByStep((prev) => ({ ...prev, [activeChatStep]: [{ role: "assistant", content: STEP_PROMPTS[activeChatStep] }] }));
    setMissingByStep((prev) => ({ ...prev, [activeChatStep]: [activeChatStep === 3 ? "education" : activeChatStep === 4 ? "experience" : activeChatStep === 5 ? "skills" : "confirm"] }));
    setWizardState((prev) => {
      const next = JSON.parse(JSON.stringify(prev)) as ResumeCraftWizardState;
      const key = stepKey(activeChatStep);
      next.chat_history_by_step[key] = [];
      if (activeChatStep === 3) {
        next.collected_by_step.education = [];
        next.step_states.step3 = { turn_count: 0, confirmed: false };
      }
      if (activeChatStep === 4) {
        next.collected_by_step.experiences = [];
        next.step_states.step4 = { current_index: 1, followup_count: 0, drafts: [], finalized_experiences: [] };
      }
      if (activeChatStep === 5) {
        next.collected_by_step.skills_and_certs = [];
        next.step_states.step5 = { turn_count: 0, confirmed: false };
      }
      if (activeChatStep === 6) {
        next.collected_by_step.final_preferences = "";
        next.collected_by_step.step6_confirmed = false;
        next.step_states.step6 = { turn_count: 0, confirmed: false };
      }
      return next;
    });
    setChatInput("");
  };

  const onSendChat = async (e: FormEvent) => {
    e.preventDefault();
    if (!activeChatStep || !chatInput.trim() || chatLoading) return;

    const userMessage: Msg = { role: "user", content: chatInput.trim() };
    const nextMessages = [...messagesByStep[activeChatStep], userMessage];
    setMessagesByStep((prev) => ({ ...prev, [activeChatStep]: nextMessages }));
    setChatInput("");
    setChatLoading(true);

    try {
      const step1Profile = buildProfilePayload();
      const resp = (await callCareerforgeSkill(settings, "/careerforge/resume-craft/chat-turn", {
        message: userMessage.content,
        history: nextMessages,
        current_step: activeChatStep,
        step1_profile: step1Profile,
        wizard_state: wizardState,
        step_profile: wizardState.collected_by_step,
        template_code: step1Profile.template_code,
        language: step1Profile.language,
        photo_pref: step1Profile.photo_pref,
        experience_state: wizardState.step_states.step4,
      })) as Record<string, unknown>;

      const serverReply = String(resp.reply || "").trim();
      const safeReply = getStepReplyGuard(activeChatStep, serverReply) ? serverReply : STEP_PROMPTS[activeChatStep];
      const nextWizard = (resp.wizard_state as ResumeCraftWizardState | undefined) || wizardState;
      const missingFields = Array.isArray(resp.missing_fields) ? (resp.missing_fields as string[]) : [];

      setWizardState(nextWizard);
      setMissingByStep((prev) => ({ ...prev, [activeChatStep]: missingFields }));
      setMessagesByStep((prev) => ({
        ...prev,
        [activeChatStep]: [...nextMessages, { role: "assistant", content: safeReply || STEP_PROMPTS[activeChatStep] }],
      }));
    } catch (err) {
      setMessagesByStep((prev) => ({
        ...prev,
        [activeChatStep]: [...nextMessages, { role: "assistant", content: (err as Error).message || "请求失败，请重试。" }],
      }));
    } finally {
      setChatLoading(false);
    }
  };

  const renderResume = async () => {
    if (!canGenerate) return;
    setRenderLoading(true);
    try {
      const history = CHAT_STEPS.flatMap((s) => messagesByStep[s]);
      const step1Profile = buildProfilePayload();
      const payload: Record<string, unknown> = {
        history,
        step1_profile: step1Profile,
        wizard_state: wizardState,
        finalized_step_data: wizardState.collected_by_step,
        finalized_experiences: wizardState.step_states.step4.finalized_experiences,
        template_code: step1Profile.template_code,
        language: step1Profile.language,
        photo_pref: step1Profile.photo_pref,
      };
      if (step1Profile.photo_pref === "with_photo") payload.photo_data_url = photoDataUrl;

      const resp = (await callCareerforgeSkill(settings, "/careerforge/resume-craft/render", payload)) as Record<string, unknown>;
      const reportHtml = String(resp.report_html || "").trim();
      if (!reportHtml) throw new Error(String(resp.message || "未返回有效简历 HTML"));
      setResult({ kind: "report", reportHtml, message: "" });
      setReportName(String(resp.report_name || "resume-craft-report.html"));
    } catch (err) {
      setResult({ kind: "error", reportHtml: "", message: (err as Error).message || "生成失败" });
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
    const frame = previewFrameRef.current;
    const win = frame?.contentWindow;
    if (!win) return;
    win.focus();
    win.print();
  };

  const stepCard = (stepNo: StepNumber, content: ReactNode) => (
    <article className={`surface resume-craft-step-card ${stepNo <= 2 ? "resume-craft-step1-card" : "resume-craft-chat-step"}`} ref={(el) => (stepRefs.current[stepNo] = el)}>
      {content}
    </article>
  );

  return (
    <section className="resume-craft-page">
      <div className="resume-craft-layout">
        <div className="resume-craft-wizard-viewport" style={viewportHeight ? { height: `${viewportHeight}px` } : undefined}>
          <div className="resume-craft-wizard-track" ref={wizardTrackRef}>
            {stepCard(
              1,
              <>
                <header className="resume-craft-step-head">
                  <div className="resume-craft-step-title-row">
                    <span className="resume-craft-step-tag">Step 1 / 6</span>
                    <span className="resume-craft-step-progress-note">基础信息填写</span>
                  </div>
                  <h2>{STEP_TITLES[1]}</h2>
                  <p>设置模板、语言、可选照片、目标岗位与 JD 摘要。</p>
                  <div className="resume-craft-head-divider" />
                </header>
                <div className="resume-craft-soft-separator" aria-hidden="true" />

                <div className="resume-craft-step-grid resume-craft-step1-select-section">
                  <label className="resume-craft-control">
                    <span className="resume-craft-control-label">模板</span>
                    <div className="resume-craft-select-shell">
                      <span className="resume-craft-select-icon" aria-hidden="true">TM</span>
                      <select value={profile.template_code} onChange={(e) => setProfile((prev) => ({ ...prev, template_code: e.target.value }))}>
                        {TEMPLATE_OPTIONS.map((item) => (
                          <option key={item.value} value={item.value}>{item.label}</option>
                        ))}
                      </select>
                    </div>
                  </label>

                  <label className="resume-craft-control">
                    <span className="resume-craft-control-label">语言</span>
                    <div className="resume-craft-select-shell">
                      <span className="resume-craft-select-icon" aria-hidden="true">LG</span>
                      <select value={profile.language} onChange={(e) => setProfile((prev) => ({ ...prev, language: e.target.value }))}>
                        {LANGUAGE_OPTIONS.map((item) => (
                          <option key={item.value} value={item.value}>{item.label}</option>
                        ))}
                      </select>
                    </div>
                  </label>
                </div>

                <div className="resume-craft-photo-box">
                  <label className="resume-craft-photo-label">上传照片（可选，仅支持 PNG/JPG）</label>
                  <input
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
                  <label className="resume-craft-control">
                    <span className="resume-craft-control-label">目标岗位 <em>*</em></span>
                    <input value={profile.target_role} placeholder="例如：AI 应用开发工程师" onChange={(e) => setProfile((prev) => ({ ...prev, target_role: e.target.value }))} />
                  </label>
                </div>

                <div className="resume-craft-form-grid resume-craft-step1-form-section">
                  <label className="resume-craft-control">
                    <span className="resume-craft-control-label">目标 JD 摘要</span>
                    <textarea value={profile.jd_summary} placeholder="可粘贴核心职责、技术要求、业务场景关键词" onChange={(e) => setProfile((prev) => ({ ...prev, jd_summary: e.target.value }))} />
                  </label>
                </div>

                <div className="resume-craft-step-actions">
                  <button type="button" className="primary-btn resume-craft-next-btn" disabled={!canStep1Next} onClick={goNext}>下一步  -&gt;</button>
                </div>
              </>
            )}

            {stepCard(
              2,
              <>
                <header className="resume-craft-step-head">
                  <div className="resume-craft-step-title-row">
                    <span className="resume-craft-step-tag">Step 2 / 6</span>
                    <span className="resume-craft-step-progress-note">个人信息填写</span>
                  </div>
                  <h2>{STEP_TITLES[2]}</h2>
                  <p>填写姓名、联系方式、城市和个人链接。</p>
                  <div className="resume-craft-head-divider" />
                </header>

                <div className="resume-craft-form-grid">
                  <label className="resume-craft-control">
                    <span className="resume-craft-control-label">姓名 <em>*</em></span>
                    <input value={profile.personal_info.name} onChange={(e) => setProfile((prev) => ({ ...prev, personal_info: { ...prev.personal_info, name: e.target.value } }))} />
                  </label>
                  <label className="resume-craft-control">
                    <span className="resume-craft-control-label">手机 <em>*</em></span>
                    <input value={profile.personal_info.phone} onChange={(e) => setProfile((prev) => ({ ...prev, personal_info: { ...prev.personal_info, phone: e.target.value } }))} />
                  </label>
                  <label className="resume-craft-control">
                    <span className="resume-craft-control-label">邮箱 <em>*</em></span>
                    <input value={profile.personal_info.email} onChange={(e) => setProfile((prev) => ({ ...prev, personal_info: { ...prev.personal_info, email: e.target.value } }))} />
                  </label>
                  <label className="resume-craft-control">
                    <span className="resume-craft-control-label">城市</span>
                    <input value={profile.personal_info.city} onChange={(e) => setProfile((prev) => ({ ...prev, personal_info: { ...prev.personal_info, city: e.target.value } }))} />
                  </label>
                  <label className="resume-craft-control">
                    <span className="resume-craft-control-label">链接（逗号分隔）</span>
                    <input value={linksInput} placeholder="GitHub, LinkedIn" onChange={(e) => setLinksInput(e.target.value)} />
                  </label>
                </div>

                <div className="resume-craft-step-actions">
                  <button type="button" className="ghost-btn resume-craft-back-btn resume-craft-step2-nav-btn" onClick={goPrev}>上一步</button>
                  <button type="button" className="primary-btn resume-craft-next-btn resume-craft-step2-nav-btn" disabled={!canStep2Next} onClick={goNext}>下一步  -&gt;</button>
                </div>
              </>
            )}

            {([3, 4, 5, 6] as ChatStep[]).map((chatStep) =>
              stepCard(
                chatStep,
                <>
                  <header className="resume-craft-chat-head">
                    <div className="resume-craft-chat-head-left">
                      <span className="resume-craft-step-tag">Step {chatStep} / 6</span>
                      <h2>{STEP_TITLES[chatStep]}</h2>
                      <p>{chatStep === 4 ? "每段经历最多 Grill 2-3 轮，达上限自动完成该段。" : "当前步骤仅收集本步骤字段，不跨步提问。"}</p>
                      <div className="resume-craft-head-divider" />
                    </div>
                    <div className="resume-craft-head-actions">
                      <button type="button" className="ghost-btn resume-craft-back-btn" onClick={goPrev}>上一步</button>
                      <button type="button" className="ghost-btn resume-craft-restart-btn" onClick={onRestartCurrentChat} disabled={chatLoading || renderLoading || step !== chatStep}>重新开始</button>
                      {chatStep < 6 ? (
                        <button type="button" className="primary-btn resume-craft-next-btn" onClick={goNext} disabled={step !== chatStep || activeMissing.length > 0}>下一步  -&gt;</button>
                      ) : null}
                    </div>
                  </header>

                  <div className="resume-craft-param-brief">
                    <span className="resume-craft-pill template">模板 {profile.template_code}</span>
                    <span className="resume-craft-pill language">{profile.language === "zh" ? "中文" : profile.language === "en" ? "英文" : "中英文双版"}</span>
                    <span className="resume-craft-pill photo">{photoDataUrl ? "放照片" : "不放照片"}</span>
                    <span className="resume-craft-pill">岗位 {profile.target_role || "未填写"}</span>
                    {chatStep === 4 ? <span className="resume-craft-pill">经历进度 {wizardState.step_states.step4.finalized_experiences.length}/{profile.expected_experience_count}</span> : null}
                  </div>

                  <div className="chat-log resume-craft-chat-log">
                    {(messagesByStep[chatStep] || []).map((msg, idx) => (
                      <div key={`${chatStep}-${msg.role}-${idx}`} className={`msg ${msg.role}`}>
                        {msg.role === "assistant" ? <span className="msg-ai-avatar" aria-hidden="true">AI</span> : null}
                        <span>{msg.content}</span>
                      </div>
                    ))}
                    {chatLoading && step === chatStep ? (
                      <div className="msg assistant">
                        <span className="msg-ai-avatar" aria-hidden="true">AI</span>
                        <span>思考中...</span>
                      </div>
                    ) : null}
                  </div>

                  <form className="chat-input resume-craft-chat-input" onSubmit={onSendChat}>
                    <input
                      value={step === chatStep ? chatInput : ""}
                      onChange={(e) => setChatInput(e.target.value)}
                      placeholder="输入当前步骤信息后发送"
                      disabled={step !== chatStep}
                    />
                    <button className="primary-btn resume-craft-send-btn" disabled={step !== chatStep || !chatInput.trim() || chatLoading || renderLoading}>发送</button>
                  </form>

                  <div className="resume-craft-readiness-note">
                    {step === chatStep ? (
                      activeMissing.length ? <p>继续补充：{activeMissing.join("、")}</p> : <p>当前步骤信息已满足最小完整度，可进入下一步。</p>
                    ) : (
                      <p>切换到本步骤后可继续对话。</p>
                    )}
                  </div>

                  {chatStep === 6 ? (
                    <div className="resume-craft-step-actions">
                      <button type="button" className="primary-btn resume-craft-next-btn" disabled={!canGenerate} onClick={renderResume}>
                        {renderLoading ? "生成中..." : "生成简历"}
                      </button>
                    </div>
                  ) : null}
                </>
              )
            )}
          </div>
        </div>

        {result.kind !== "idle" ? (
          <section className="surface resume-craft-output" style={{ marginTop: 14 }}>
            {result.kind === "error" ? <p className="resume-result-error">{result.message}</p> : null}
            {result.kind === "report" ? (
            <>
              <header className="resume-craft-preview-head">
                <h3>简历预览</h3>
                <span>已嵌入当前页面</span>
              </header>
              <iframe
                ref={previewFrameRef}
                title="Resume Craft HTML Preview"
                className="resume-craft-preview-frame"
                srcDoc={result.reportHtml}
                onLoad={onPreviewLoad}
                style={{ height: `${frameHeight}px` }}
              />
              <div className="resume-craft-actions">
                <button type="button" className="ghost-btn" onClick={exportHtml}>导出 HTML</button>
                <button type="button" className="ghost-btn" onClick={exportPdf}>导出 PDF</button>
              </div>
            </>
            ) : null}
          </section>
        ) : null}
      </div>
    </section>
  );
}
