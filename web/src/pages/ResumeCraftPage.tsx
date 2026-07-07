import { FormEvent, SyntheticEvent, useEffect, useMemo, useRef, useState } from "react";
import { gsap } from "gsap";
import { callCareerforgeSkill } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";
import type { ExperienceState, Step1Profile } from "../types";

type Msg = { role: "user" | "assistant"; content: string };

type ResultState = {
  kind: "idle" | "report" | "error";
  reportHtml: string;
  message: string;
};

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

const PHOTO_OPTIONS = [
  { value: "no_photo", label: "不放照片" },
  { value: "with_photo", label: "放照片" },
];

const INITIAL_STEP2_MESSAGE =
  "我们只收集工作/项目经历。请先描述第 1 段最相关经历：场景、职责、你做了什么，以及结果。";

const MISSING_LABEL_MAP: Record<string, string> = {
  experience: "工作/项目经历",
  photo: "照片",
};

const TONE_OPTIONS = ["专业简洁", "结果导向", "技术深度", "业务价值", "国际化"];

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
  education: [{ school: "", major: "", degree: "", period: "", highlights: "" }],
  skills: [],
  certificates: [],
};

const EMPTY_EXPERIENCE_STATE: ExperienceState = {
  current_index: 1,
  followup_count: 0,
  drafts: [],
  finalized_experiences: [],
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

function containsNonExperiencePrompt(text: string) {
  const content = String(text || "");
  return ["目标岗位", "教育", "技能", "联系方式", "证书", "语言", "模板"].some((token) => content.includes(token));
}

export function ResumeCraftPage() {
  const { settings } = useModelSettings();
  const [step, setStep] = useState<1 | 2>(1);
  const [messages, setMessages] = useState<Msg[]>([{ role: "assistant", content: INITIAL_STEP2_MESSAGE }]);
  const [input, setInput] = useState("");
  const [profile, setProfile] = useState<Step1Profile>(EMPTY_PROFILE);
  const [educationDraft, setEducationDraft] = useState(EMPTY_PROFILE.education);
  const [skillsInput, setSkillsInput] = useState("");
  const [certInput, setCertInput] = useState("");
  const [linksInput, setLinksInput] = useState("");

  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoDataUrl, setPhotoDataUrl] = useState("");
  const [photoHint, setPhotoHint] = useState("");
  const [photoLoading, setPhotoLoading] = useState(false);

  const [experienceState, setExperienceState] = useState<ExperienceState>(EMPTY_EXPERIENCE_STATE);
  const [chatLoading, setChatLoading] = useState(false);
  const [renderLoading, setRenderLoading] = useState(false);
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [result, setResult] = useState<ResultState>({ kind: "idle", reportHtml: "", message: "" });
  const [reportName, setReportName] = useState("resume-craft-report.html");
  const [frameHeight, setFrameHeight] = useState(980);
  const [viewportHeight, setViewportHeight] = useState<number | null>(null);

  const previewFrameRef = useRef<HTMLIFrameElement | null>(null);
  const photoInputRef = useRef<HTMLInputElement | null>(null);
  const wizardTrackRef = useRef<HTMLDivElement | null>(null);
  const step1CardRef = useRef<HTMLElement | null>(null);
  const step2CardRef = useRef<HTMLElement | null>(null);

  const hasUserMessages = useMemo(() => messages.some((msg) => msg.role === "user"), [messages]);

  const canGoNext = useMemo(() => {
    const hasTemplate = TEMPLATE_OPTIONS.some((item) => item.value === profile.template_code);
    const hasLanguage = LANGUAGE_OPTIONS.some((item) => item.value === profile.language);
    const hasTargetRole = profile.target_role.trim().length > 0;
    const hasName = profile.personal_info.name.trim().length > 0;
    const hasEmailOrPhone = profile.personal_info.email.trim() || profile.personal_info.phone.trim();
    const hasEducation = educationDraft.some((item) => item.school.trim() || item.major.trim() || item.degree.trim());
    const hasSkills = splitTags(skillsInput).length > 0;
    const needsPhoto = profile.photo_pref === "with_photo";

    if (!hasTemplate || !hasLanguage || !hasTargetRole || !hasName || !hasEmailOrPhone || !hasEducation || !hasSkills) {
      return false;
    }
    if (photoLoading) {
      return false;
    }
    if (needsPhoto) {
      return Boolean(photoDataUrl) && !photoHint;
    }
    return true;
  }, [profile, educationDraft, skillsInput, photoDataUrl, photoHint, photoLoading]);

  useEffect(() => {
    const track = wizardTrackRef.current;
    if (!track) {
      return;
    }
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    gsap.killTweensOf(track);
    gsap.to(track, {
      xPercent: step === 1 ? 0 : -50,
      duration: prefersReducedMotion ? 0 : 0.45,
      ease: "power2.inOut",
    });
    return () => {
      gsap.killTweensOf(track);
    };
  }, [step]);

  useEffect(() => {
    const activeCard = step === 1 ? step1CardRef.current : step2CardRef.current;
    if (!activeCard) {
      return;
    }
    const updateHeight = () => setViewportHeight(activeCard.offsetHeight);
    updateHeight();
    if (typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(() => updateHeight());
    observer.observe(activeCard);
    return () => observer.disconnect();
  }, [step, photoDataUrl, photoHint, photoLoading, messages.length, chatLoading, renderLoading, result.kind, skillsInput, certInput]);

  const savePhotoFile = async (file: File | null) => {
    if (!file) {
      setPhotoFile(null);
      setPhotoDataUrl("");
      setPhotoHint(profile.photo_pref === "with_photo" ? "请选择 PNG/JPG 照片。" : "");
      if (photoInputRef.current) {
        photoInputRef.current.value = "";
      }
      return;
    }

    if (!isSupportedPhotoFile(file)) {
      setPhotoFile(null);
      setPhotoDataUrl("");
      setPhotoHint("仅支持 PNG/JPG/JPEG 图片。");
      if (photoInputRef.current) {
        photoInputRef.current.value = "";
      }
      return;
    }

    setPhotoLoading(true);
    setPhotoHint("");
    setPhotoFile(file);
    try {
      const dataUrl = await fileToDataUrl(file);
      setPhotoDataUrl(dataUrl);
      setPhotoHint("");
    } catch (err) {
      setPhotoFile(null);
      setPhotoDataUrl("");
      setPhotoHint((err as Error).message || "读取图片失败，请重试。");
    } finally {
      setPhotoLoading(false);
    }
  };

  const buildStep1ProfilePayload = (): Step1Profile => ({
    ...profile,
    personal_info: {
      ...profile.personal_info,
      links: splitTags(linksInput),
    },
    education: educationDraft
      .map((item) => ({
        school: item.school.trim(),
        major: item.major.trim(),
        degree: item.degree.trim(),
        period: item.period.trim(),
        highlights: item.highlights.trim(),
      }))
      .filter((item) => item.school || item.major || item.degree || item.period || item.highlights),
    skills: splitTags(skillsInput),
    certificates: splitTags(certInput),
  });

  const renderResume = async (history: Msg[], currentExperienceState: ExperienceState) => {
    if (renderLoading) {
      return;
    }
    setRenderLoading(true);
    try {
      const step1Profile = buildStep1ProfilePayload();
      const payload: Record<string, unknown> = {
        history: history.map((msg) => ({ role: msg.role, content: msg.content })),
        step1_profile: step1Profile,
        finalized_experiences: currentExperienceState.finalized_experiences,
        template_code: step1Profile.template_code,
        language: step1Profile.language,
        photo_pref: step1Profile.photo_pref,
      };
      if (step1Profile.photo_pref === "with_photo") {
        payload.photo_data_url = photoDataUrl;
      }

      const resp = await callCareerforgeSkill(settings, "/careerforge/resume-craft/render", payload);
      const html =
        (typeof (resp as Record<string, unknown>).report_html === "string" &&
          ((resp as Record<string, unknown>).report_html as string)) ||
        "";
      const name =
        (typeof (resp as Record<string, unknown>).report_name === "string" &&
          ((resp as Record<string, unknown>).report_name as string)) ||
        "resume-craft-report.html";

      if (!html.trim()) {
        setResult({ kind: "error", reportHtml: "", message: "未生成有效 HTML，请继续补充信息后重试。" });
      } else {
        setReportName(name);
        setResult({ kind: "report", reportHtml: html, message: "" });
      }
    } catch (err) {
      setResult({ kind: "error", reportHtml: "", message: (err as Error).message });
    } finally {
      setRenderLoading(false);
    }
  };

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || chatLoading || renderLoading) {
      return;
    }

    const history = messages.map((msg) => ({ role: msg.role, content: msg.content }));
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setChatLoading(true);

    try {
      const step1Profile = buildStep1ProfilePayload();
      const resp = await callCareerforgeSkill(settings, "/careerforge/resume-craft/chat-turn", {
        message: text,
        history,
        step1_profile: step1Profile,
        experience_state: experienceState,
        template_code: step1Profile.template_code,
        language: step1Profile.language,
        photo_pref: step1Profile.photo_pref,
        photo_uploaded: Boolean(photoDataUrl),
      });

      const serverState = ((resp as Record<string, unknown>).experience_state || EMPTY_EXPERIENCE_STATE) as ExperienceState;
      const nextState: ExperienceState = {
        current_index: Number(serverState.current_index || 1),
        followup_count: Number(serverState.followup_count || 0),
        drafts: Array.isArray(serverState.drafts) ? serverState.drafts.map((item) => String(item)) : [],
        finalized_experiences: Array.isArray(serverState.finalized_experiences)
          ? serverState.finalized_experiences.map((item) => String(item))
          : [],
      };
      setExperienceState(nextState);

      const renderReady = Boolean((resp as Record<string, unknown>).render_ready);
      const nextMissing = Array.isArray((resp as Record<string, unknown>).missing_fields)
        ? ((resp as Record<string, unknown>).missing_fields as string[]).map((item) => String(item))
        : [];
      setMissingFields(nextMissing);

      const fallbackExperienceAsk =
        renderReady || nextMissing.length === 0
          ? "经历信息已完成收集，我将基于 Step1 与经历内容生成简历预览。"
          : `继续补充第 ${nextState.current_index} 段经历：请重点说明职责、挑战、行动和结果。`;

      let reply =
        (typeof resp.reply === "string" && resp.reply.trim()) ||
        (typeof resp.message === "string" && resp.message.trim()) ||
        fallbackExperienceAsk;

      if (!renderReady && containsNonExperiencePrompt(reply)) {
        reply = fallbackExperienceAsk;
      }

      const replyMsg: Msg = { role: "assistant", content: reply };
      setMessages((prev) => [...prev, replyMsg]);

      if (renderReady) {
        const nextHistory: Msg[] = [...messages, { role: "user", content: text }, replyMsg];
        await renderResume(nextHistory, nextState);
      }
    } catch (err) {
      const reply = `继续补充第 ${experienceState.current_index} 段经历：请重点说明职责、挑战、行动和结果。`;
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      setMissingFields(["experience"]);
      setResult({ kind: "error", reportHtml: "", message: (err as Error).message });
    } finally {
      setChatLoading(false);
    }
  };

  const onPreviewLoad = (e: SyntheticEvent<HTMLIFrameElement>) => {
    try {
      const frame = e.currentTarget;
      const doc = frame.contentDocument;
      if (!doc) {
        return;
      }
      const bodyHeight = doc.body?.scrollHeight ?? 0;
      const htmlHeight = doc.documentElement?.scrollHeight ?? 0;
      const next = Math.max(720, bodyHeight, htmlHeight);
      setFrameHeight(next + 12);
    } catch {
      setFrameHeight(980);
    }
  };

  const exportHtml = () => {
    if (result.kind !== "report" || !result.reportHtml.trim()) {
      return;
    }
    const blob = new Blob([result.reportHtml], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = reportName || "resume-craft-report.html";
    link.click();
    URL.revokeObjectURL(url);
  };

  const exportPdf = () => {
    const frameWindow = previewFrameRef.current?.contentWindow;
    if (!frameWindow) {
      return;
    }
    frameWindow.focus();
    frameWindow.print();
  };

  const onNextStep = () => {
    if (!canGoNext) {
      if (profile.photo_pref === "with_photo" && !photoDataUrl) {
        setPhotoHint("选择“放照片”后，必须上传 PNG/JPG 照片。");
      }
      return;
    }
    const nextProfile = buildStep1ProfilePayload();
    setProfile(nextProfile);
    setMessages([{ role: "assistant", content: `好的，我们开始收集经历。请先描述第 1 段与“${nextProfile.target_role}”最相关的工作/项目经历。` }]);
    setExperienceState({ ...EMPTY_EXPERIENCE_STATE });
    setStep(2);
  };

  const onRestartChat = () => {
    if (chatLoading || renderLoading) {
      return;
    }
    setMessages([{ role: "assistant", content: `好的，我们重新开始经历深挖。请描述第 1 段关键经历。` }]);
    setInput("");
    setMissingFields([]);
    setExperienceState({ ...EMPTY_EXPERIENCE_STATE });
    setResult({ kind: "idle", reportHtml: "", message: "" });
    setReportName("resume-craft-report.html");
    setFrameHeight(980);
  };

  const readableMissingFields = missingFields
    .map((item) => MISSING_LABEL_MAP[item] || item)
    .filter((item, index, arr) => arr.indexOf(item) === index);

  const updateEducation = (index: number, key: keyof Step1Profile["education"][number], value: string) => {
    setEducationDraft((prev) => prev.map((item, idx) => (idx === index ? { ...item, [key]: value } : item)));
  };

  return (
    <section className="resume-craft-page">
      <div className="resume-craft-layout">
        <div className="resume-craft-wizard-viewport" style={viewportHeight ? { height: `${viewportHeight}px` } : undefined}>
          <div className="resume-craft-wizard-track" ref={wizardTrackRef}>
            <article className="surface resume-craft-step-card" ref={step1CardRef}>
              <header className="resume-craft-step-head">
                <span className="resume-craft-step-tag">Step 1 / 2</span>
                <h2>先完成基础信息（前五流程）</h2>
                <p>在这里填写目标岗位、个人信息、教育、技能与偏好。Step2 只做经历深挖。</p>
                <div className="resume-craft-head-divider" />
              </header>

              <div className="resume-craft-step-grid">
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

                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">照片偏好</span>
                  <div className="resume-craft-select-shell">
                    <span className="resume-craft-select-icon" aria-hidden="true">PH</span>
                    <select
                      value={profile.photo_pref}
                      onChange={(e) => {
                        const next = e.target.value;
                        setProfile((prev) => ({ ...prev, photo_pref: next }));
                        if (next === "with_photo" && !photoDataUrl) {
                          setPhotoHint("选择“放照片”后，必须上传 PNG/JPG 照片。");
                        } else if (next === "no_photo") {
                          setPhotoHint("");
                        }
                      }}
                    >
                      {PHOTO_OPTIONS.map((item) => (
                        <option key={item.value} value={item.value}>{item.label}</option>
                      ))}
                    </select>
                  </div>
                </label>
              </div>

              {profile.photo_pref === "with_photo" ? (
                <div className="resume-craft-photo-box">
                  <label className="resume-craft-photo-label">上传照片（仅支持 PNG/JPG）</label>
                  <input
                    ref={photoInputRef}
                    type="file"
                    accept=".png,.jpg,.jpeg,image/png,image/jpeg"
                    className="resume-craft-photo-input"
                    onChange={(e) => savePhotoFile(e.target.files?.[0] ?? null)}
                  />
                  <p className="resume-craft-photo-name">
                    {photoLoading ? "读取照片中..." : photoFile ? `已选择：${photoFile.name}` : "尚未上传照片"}
                  </p>
                  {photoHint ? <p className="resume-craft-photo-hint error">{photoHint}</p> : null}
                  {!photoHint && photoDataUrl ? <p className="resume-craft-photo-hint ok">✓ 照片已就绪</p> : null}
                </div>
              ) : null}

              <div className="resume-craft-form-grid">
                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">目标岗位</span>
                  <input value={profile.target_role} onChange={(e) => setProfile((prev) => ({ ...prev, target_role: e.target.value }))} />
                </label>
                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">目标 JD 摘要</span>
                  <textarea value={profile.jd_summary} onChange={(e) => setProfile((prev) => ({ ...prev, jd_summary: e.target.value }))} />
                </label>

                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">姓名</span>
                  <input
                    value={profile.personal_info.name}
                    onChange={(e) =>
                      setProfile((prev) => ({ ...prev, personal_info: { ...prev.personal_info, name: e.target.value } }))
                    }
                  />
                </label>
                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">手机</span>
                  <input
                    value={profile.personal_info.phone}
                    onChange={(e) =>
                      setProfile((prev) => ({ ...prev, personal_info: { ...prev.personal_info, phone: e.target.value } }))
                    }
                  />
                </label>
                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">邮箱</span>
                  <input
                    value={profile.personal_info.email}
                    onChange={(e) =>
                      setProfile((prev) => ({ ...prev, personal_info: { ...prev.personal_info, email: e.target.value } }))
                    }
                  />
                </label>
                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">城市</span>
                  <input
                    value={profile.personal_info.city}
                    onChange={(e) =>
                      setProfile((prev) => ({ ...prev, personal_info: { ...prev.personal_info, city: e.target.value } }))
                    }
                  />
                </label>
                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">链接（逗号分隔）</span>
                  <input value={linksInput} onChange={(e) => setLinksInput(e.target.value)} placeholder="GitHub, LinkedIn" />
                </label>

                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">技能（逗号分隔）</span>
                  <input value={skillsInput} onChange={(e) => setSkillsInput(e.target.value)} placeholder="Python, LangChain, RAG" />
                </label>
                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">证书（逗号分隔）</span>
                  <input value={certInput} onChange={(e) => setCertInput(e.target.value)} placeholder="PMP, AWS SAA" />
                </label>
                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">希望突出项</span>
                  <input value={profile.focus_points} onChange={(e) => setProfile((prev) => ({ ...prev, focus_points: e.target.value }))} />
                </label>
                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">语气偏好</span>
                  <select value={profile.tone_pref} onChange={(e) => setProfile((prev) => ({ ...prev, tone_pref: e.target.value }))}>
                    {TONE_OPTIONS.map((item) => (
                      <option key={item} value={item}>{item}</option>
                    ))}
                  </select>
                </label>
                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">计划收集几段经历</span>
                  <input
                    type="number"
                    min={1}
                    max={5}
                    value={profile.expected_experience_count}
                    onChange={(e) => setProfile((prev) => ({ ...prev, expected_experience_count: Number(e.target.value || 1) }))}
                  />
                </label>
              </div>

              <div className="resume-craft-education-wrap">
                <h3>教育背景</h3>
                {educationDraft.map((item, idx) => (
                  <div key={`edu-${idx}`} className="resume-craft-edu-row">
                    <input placeholder="学校" value={item.school} onChange={(e) => updateEducation(idx, "school", e.target.value)} />
                    <input placeholder="专业" value={item.major} onChange={(e) => updateEducation(idx, "major", e.target.value)} />
                    <input placeholder="学位" value={item.degree} onChange={(e) => updateEducation(idx, "degree", e.target.value)} />
                    <input placeholder="时间" value={item.period} onChange={(e) => updateEducation(idx, "period", e.target.value)} />
                    <input placeholder="亮点" value={item.highlights} onChange={(e) => updateEducation(idx, "highlights", e.target.value)} />
                  </div>
                ))}
                <button
                  type="button"
                  className="ghost-btn"
                  onClick={() => setEducationDraft((prev) => [...prev, { school: "", major: "", degree: "", period: "", highlights: "" }])}
                >
                  + 新增教育条目
                </button>
              </div>

              <div className="resume-craft-step-actions">
                <button
                  type="button"
                  className={`primary-btn resume-craft-next-btn${photoLoading ? " is-loading" : ""}`}
                  onClick={onNextStep}
                  disabled={!canGoNext}
                >
                  {photoLoading ? "处理中..." : "下一步（进入经历深挖）"}
                </button>
              </div>
            </article>

            <article className="surface resume-craft-step-card resume-craft-chat-step" ref={step2CardRef}>
              <header className="resume-craft-chat-head">
                <div className="resume-craft-chat-head-left">
                  <span className="resume-craft-step-tag">Step 2 / 2</span>
                  <h2>工作/项目经历深挖（Grill）</h2>
                  <p>本阶段仅收集经历，不再询问目标岗位、教育、技能、联系方式。</p>
                  <div className="resume-craft-head-divider" />
                </div>
                <div className="resume-craft-head-actions">
                  <button type="button" className="ghost-btn resume-craft-back-btn" onClick={() => setStep(1)}>
                    上一步
                  </button>
                  <button type="button" className="ghost-btn resume-craft-restart-btn" onClick={onRestartChat} disabled={chatLoading || renderLoading}>
                    重新开始
                  </button>
                </div>
              </header>

              <div className="resume-craft-param-brief">
                <span className="resume-craft-pill template">模板 {profile.template_code}</span>
                <span className="resume-craft-pill language">{profile.language === "zh" ? "中文" : profile.language === "en" ? "英文" : "中英文双版"}</span>
                <span className="resume-craft-pill photo">{profile.photo_pref === "with_photo" ? "放照片" : "不放照片"}</span>
                <span className="resume-craft-pill">岗位 {profile.target_role || "未填写"}</span>
                <span className="resume-craft-pill">经历进度 {experienceState.finalized_experiences.length}/{profile.expected_experience_count}</span>
              </div>

              <div className="chat-log resume-craft-chat-log">
                {messages.map((msg, idx) => (
                  <div key={`${msg.role}-${idx}`} className={`msg ${msg.role}`}>
                    {msg.role === "assistant" ? (
                      <span className="msg-ai-avatar" aria-hidden="true">AI</span>
                    ) : null}
                    <span>{msg.content}</span>
                  </div>
                ))}
                {chatLoading ? (
                  <div className="msg assistant">
                    <span className="msg-ai-avatar" aria-hidden="true">AI</span>
                    <span>正在进行经历深挖...</span>
                  </div>
                ) : null}
              </div>

              <form className="chat-input resume-craft-chat-input" onSubmit={onSend}>
                <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="例如：我负责设计 RAG 检索链路，将响应时延降低 35%" />
                <button className="primary-btn resume-craft-send-btn" disabled={!input.trim() || chatLoading || renderLoading}>
                  {chatLoading ? "发送中..." : "发送"}
                </button>
              </form>

              <div className="resume-craft-readiness-note">
                {readableMissingFields.length ? (
                  <p>继续补充：{readableMissingFields.join("、")}</p>
                ) : hasUserMessages ? (
                  <p>{renderLoading ? "经历完整，正在自动生成..." : "经历已完整，可继续补充以优化内容。"}</p>
                ) : (
                  <p>请先发送一段经历，系统会自动进行 2-3 轮 Grill 深挖。</p>
                )}
              </div>

              <section className="resume-craft-output">
                {result.kind === "idle" ? (
                  <div className="resume-craft-preview-placeholder">
                    <div className="resume-craft-preview-wire" aria-hidden="true">
                      <span className="head" />
                      <span className="line" />
                      <span className="line short" />
                      <span className="line" />
                    </div>
                    <p>经历深挖完成后，这里会展示完整简历预览。</p>
                  </div>
                ) : null}
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
            </article>
          </div>
        </div>
      </div>
    </section>
  );
}
