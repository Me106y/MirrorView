import { FormEvent, SyntheticEvent, useEffect, useMemo, useRef, useState } from "react";
import { gsap } from "gsap";
import { callCareerforgeSkill } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";
import { FRONTEND_BUILD_VERSION } from "../buildInfo";

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
  { value: "07", label: "优雅对称" }
];

const LANGUAGE_OPTIONS = [
  { value: "zh", label: "中文" },
  { value: "en", label: "英文" },
  { value: "both", label: "中英文双版" }
];

const PHOTO_OPTIONS = [
  { value: "no_photo", label: "不放照片" },
  { value: "with_photo", label: "放照片" }
];

const INITIAL_MESSAGE = "我们先从第一个字段开始：请告诉我你的目标岗位。";

const MISSING_LABEL_MAP: Record<string, string> = {
  conversation_turns: "至少两轮用户信息",
  target_role: "目标岗位",
  education: "教育背景",
  experience: "项目/工作经历",
  skills: "技能与工具",
  contact: "联系方式",
  photo: "照片",
  template: "模板",
  language: "语言",
  photo_pref: "照片偏好"
};

const FIELD_PROMPT_MAP: Record<string, string> = {
  target_role: "请先补充目标岗位这个字段（例如：AI 应用开发工程师）。",
  education: "请补充教育背景这个字段（学校/专业/学位/时间）。",
  experience: "请补充项目或工作经历这个字段（公司/项目/职责/成果）。",
  skills: "请补充技能与工具这个字段（技术栈/工具/熟练度）。",
  contact: "请补充联系方式这个字段（邮箱/电话/城市/GitHub 等）。",
  photo: "你选择了放照片，请先上传 PNG/JPG 照片。",
  conversation_turns: "请继续补充信息，我们每轮只收集一个字段。",
};

const FIELD_ORDER = ["target_role", "education", "experience", "skills", "contact", "photo", "conversation_turns"];
const CORE_FIELD_ORDER = ["target_role", "education", "experience", "skills", "contact"];

function nextPromptFromMissing(missingFields: string[]) {
  for (const field of FIELD_ORDER) {
    if (missingFields.includes(field) && FIELD_PROMPT_MAP[field]) {
      return FIELD_PROMPT_MAP[field];
    }
  }
  for (const field of missingFields) {
    if (FIELD_PROMPT_MAP[field]) {
      return FIELD_PROMPT_MAP[field];
    }
  }
  return "请继续补充下一项字段信息。";
}

function isTargetRolePromptReply(text: string) {
  const content = String(text || "").trim();
  if (!content) {
    return false;
  }
  const hasTargetRole = ["目标岗位", "求职岗位", "岗位", "职位", "第一个字段"].some((token) =>
    content.includes(token)
  );
  const hasAsk = ["补充", "告诉", "填写", "提供", "先", "请", "需要"].some((token) => content.includes(token));
  return hasTargetRole && hasAsk;
}

function assistantRecentlyAskedTargetRole(history: Msg[]) {
  for (let i = history.length - 1; i >= Math.max(0, history.length - 6); i -= 1) {
    const msg = history[i];
    if (!msg || msg.role !== "assistant") {
      continue;
    }
    if (["目标岗位", "求职岗位", "岗位", "职位", "第一个字段"].some((token) => msg.content.includes(token))) {
      return true;
    }
  }
  return false;
}

function looksLikeTargetRoleAnswer(text: string) {
  const value = String(text || "").trim();
  if (!value) {
    return false;
  }
  if (/(?:目标岗位|求职岗位|岗位|职位)\s*[:：]\s*/i.test(value)) {
    return true;
  }
  const lower = value.toLowerCase();
  const roleHints = [
    "开发",
    "工程师",
    "产品",
    "运营",
    "设计",
    "算法",
    "测试",
    "经理",
    "顾问",
    "分析师",
    "架构师",
    "developer",
    "engineer",
    "manager",
    "analyst",
    "scientist",
  ];
  if (value.length <= 64 && roleHints.some((token) => lower.includes(token))) {
    return true;
  }
  // Hard fallback for Step2 first question: short free-text answer is treated as role.
  if (value.length <= 64) {
    return true;
  }
  return false;
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

export function ResumeCraftPage() {
  const { settings } = useModelSettings();
  const [step, setStep] = useState<1 | 2>(1);
  const [messages, setMessages] = useState<Msg[]>([{ role: "assistant", content: INITIAL_MESSAGE }]);
  const [input, setInput] = useState("");
  const [templateCode, setTemplateCode] = useState("02");
  const [language, setLanguage] = useState("zh");
  const [photoPref, setPhotoPref] = useState("no_photo");
  const [photoFile, setPhotoFile] = useState<File | null>(null);
  const [photoDataUrl, setPhotoDataUrl] = useState("");
  const [photoHint, setPhotoHint] = useState("");
  const [photoLoading, setPhotoLoading] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [renderLoading, setRenderLoading] = useState(false);
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [fieldAnswers, setFieldAnswers] = useState<Record<string, string>>({});
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
    const hasTemplate = TEMPLATE_OPTIONS.some((item) => item.value === templateCode);
    const hasLanguage = LANGUAGE_OPTIONS.some((item) => item.value === language);
    const needsPhoto = photoPref === "with_photo";
    if (!hasTemplate || !hasLanguage || photoLoading) {
      return false;
    }
    if (needsPhoto) {
      return Boolean(photoDataUrl) && !photoHint;
    }
    return true;
  }, [templateCode, language, photoPref, photoDataUrl, photoHint, photoLoading]);

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
    const updateHeight = () => {
      setViewportHeight(activeCard.offsetHeight);
    };
    updateHeight();
    if (typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(() => updateHeight());
    observer.observe(activeCard);
    return () => observer.disconnect();
  }, [step, photoPref, photoDataUrl, photoHint, photoLoading, messages.length, chatLoading, renderLoading, result.kind]);

  const savePhotoFile = async (file: File | null) => {
    if (!file) {
      setPhotoFile(null);
      setPhotoDataUrl("");
      setPhotoHint(photoPref === "with_photo" ? "请选择 PNG/JPG 照片。" : "");
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

  const renderResume = async (history: Msg[]) => {
    if (!history.length || renderLoading) {
      return;
    }
    setRenderLoading(true);
    try {
      const payload: Record<string, unknown> = {
        history: history.map((msg) => ({ role: msg.role, content: msg.content })),
        template_code: templateCode,
        language,
        photo_pref: photoPref,
      };
      if (photoPref === "with_photo") {
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

    const askedRoleRecently = assistantRecentlyAskedTargetRole(messages);
    const roleAnsweredNow = looksLikeTargetRoleAnswer(text);
    const userTurns = messages.filter((msg) => msg.role === "user").length + 1;
    const currentCoreField =
      CORE_FIELD_ORDER.find((field) => !fieldAnswers[field]?.trim()) ??
      CORE_FIELD_ORDER[CORE_FIELD_ORDER.length - 1];

    const localAnswers = {
      ...fieldAnswers,
      [currentCoreField]: text,
    };
    setFieldAnswers(localAnswers);

    let localMissing = CORE_FIELD_ORDER.filter((field) => !localAnswers[field]?.trim());
    if (photoPref === "with_photo" && !photoDataUrl) {
      localMissing = [...localMissing, "photo"];
    }
    if (userTurns < 2) {
      localMissing = [...localMissing, "conversation_turns"];
    }

    const localReply =
      localMissing.length > 0
        ? `我已收到你的信息。${nextPromptFromMissing(localMissing)}`
        : "信息已收集完整，我将为你生成简历预览。";
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setChatLoading(true);
    try {
      // Step2 uses deterministic local progression so it remains stable even
      // when remote chat-turn API is stale/unavailable.
      let nextMissing = localMissing;
      if (askedRoleRecently && roleAnsweredNow) {
        nextMissing = nextMissing.filter((field) => field !== "target_role");
      }
      const reply = `我已收到你的信息。${nextPromptFromMissing(nextMissing)}`;
      const replyMsg: Msg = { role: "assistant", content: reply };
      setMessages((prev) => [...prev, replyMsg]);
      setMissingFields(nextMissing);

      if (nextMissing.length === 0) {
        const nextHistory: Msg[] = [...messages, { role: "user", content: text }, replyMsg];
        await renderResume(nextHistory);
      }
    } catch {
      const replyMsg: Msg = { role: "assistant", content: localReply };
      setMessages((prev) => [...prev, replyMsg]);
      setMissingFields(localMissing);

      if (localMissing.length === 0) {
        const nextHistory: Msg[] = [...messages, { role: "user", content: text }, replyMsg];
        await renderResume(nextHistory);
      }
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
      if (photoPref === "with_photo" && !photoDataUrl) {
        setPhotoHint("选择“放照片”后，必须上传 PNG/JPG 照片。");
      }
      return;
    }
    setStep(2);
  };

  const onRestartChat = () => {
    if (chatLoading || renderLoading) {
      return;
    }
    setMessages([{ role: "assistant", content: INITIAL_MESSAGE }]);
    setInput("");
    setMissingFields([]);
    setFieldAnswers({});
    setResult({ kind: "idle", reportHtml: "", message: "" });
    setReportName("resume-craft-report.html");
    setFrameHeight(980);
  };

  const readableMissingFields = missingFields
    .map((item) => MISSING_LABEL_MAP[item] || item)
    .filter((item, index, arr) => arr.indexOf(item) === index);

  return (
    <section className="resume-craft-page">
      <div className="resume-craft-layout">
        <div
          className="resume-craft-wizard-viewport"
          style={viewportHeight ? { height: `${viewportHeight}px` } : undefined}
        >
          <div className="resume-craft-wizard-track" ref={wizardTrackRef}>
            <article className="surface resume-craft-step-card" ref={step1CardRef}>
              <header className="resume-craft-step-head">
                <span className="resume-craft-step-tag">Step 1 / 2</span>
                <h2>先设置生成参数</h2>
                <p>选择模板、语言和照片偏好，再进入对话收集信息。</p>
                <div className="resume-craft-head-divider" />
              </header>

              <div className="resume-craft-step-grid">
                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">模板</span>
                  <div className="resume-craft-select-shell">
                    <span className="resume-craft-select-icon" aria-hidden="true">
                      TM
                    </span>
                    <select value={templateCode} onChange={(e) => setTemplateCode(e.target.value)}>
                      {TEMPLATE_OPTIONS.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </label>

                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">语言</span>
                  <div className="resume-craft-select-shell">
                    <span className="resume-craft-select-icon" aria-hidden="true">
                      LG
                    </span>
                    <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                      {LANGUAGE_OPTIONS.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </label>

                <label className="resume-craft-control">
                  <span className="resume-craft-control-label">照片偏好</span>
                  <div className="resume-craft-select-shell">
                    <span className="resume-craft-select-icon" aria-hidden="true">
                      PH
                    </span>
                    <select
                      value={photoPref}
                      onChange={(e) => {
                        const next = e.target.value;
                        setPhotoPref(next);
                        if (next === "with_photo" && !photoDataUrl) {
                          setPhotoHint("选择“放照片”后，必须上传 PNG/JPG 照片。");
                        } else if (next === "no_photo") {
                          setPhotoHint("");
                        }
                      }}
                    >
                      {PHOTO_OPTIONS.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </label>
              </div>

              <div className="resume-craft-step-illustration">
                <div className="resume-craft-wireframe" aria-hidden="true">
                  <div className="resume-craft-wireframe-head" />
                  <div className="resume-craft-wireframe-line" />
                  <div className="resume-craft-wireframe-line short" />
                  <div className="resume-craft-wireframe-blocks">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
                <p>完成设置后，将进入 AI 对话收集信息并自动生成预览。</p>
              </div>

              {photoPref === "with_photo" ? (
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

              <div className="resume-craft-step-actions">
                <button
                  type="button"
                  className={`primary-btn resume-craft-next-btn${photoLoading ? " is-loading" : ""}`}
                  onClick={onNextStep}
                  disabled={!canGoNext}
                >
                  {photoLoading ? "处理中..." : "下一步"}
                </button>
              </div>
            </article>

            <article className="surface resume-craft-step-card resume-craft-chat-step" ref={step2CardRef}>
              <header className="resume-craft-chat-head">
                <div className="resume-craft-chat-head-left">
                  <span className="resume-craft-step-tag">Step 2 / 2</span>
                  <h2>Resume Craft Agent</h2>
                  <p>通过多轮对话收集信息，系统达到完整度后会自动生成简历预览。</p>
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
                <span className="resume-craft-pill template">模板 {templateCode}</span>
                <span className="resume-craft-pill language">{language === "zh" ? "中文" : language === "en" ? "英文" : "中英文双版"}</span>
                <span className="resume-craft-pill photo">{photoPref === "with_photo" ? "放照片" : "不放照片"}</span>
              </div>

              <div className="chat-log resume-craft-chat-log">
                {messages.map((msg, idx) => (
                  <div key={`${msg.role}-${idx}`} className={`msg ${msg.role}`}>
                    {msg.role === "assistant" ? (
                      <span className="msg-ai-avatar" aria-hidden="true">
                        AI
                      </span>
                    ) : null}
                    <span>{msg.content}</span>
                  </div>
                ))}
                {chatLoading ? (
                  <div className="msg assistant">
                    <span className="msg-ai-avatar" aria-hidden="true">
                      AI
                    </span>
                    <span>正在思考，请稍候...</span>
                  </div>
                ) : null}
              </div>

              <form className="chat-input resume-craft-chat-input" onSubmit={onSend}>
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="例如：我在上一家公司负责 RAG 服务落地，支持 8 个业务场景"
                />
                <button className="primary-btn resume-craft-send-btn" disabled={!input.trim() || chatLoading || renderLoading}>
                  {chatLoading ? "发送中..." : "发送"}
                </button>
              </form>

              <div className="resume-craft-readiness-note">
                {readableMissingFields.length ? (
                  <p>继续补充：{readableMissingFields.join("、")}</p>
                ) : hasUserMessages ? (
                  <p>{renderLoading ? "信息完整，正在自动生成..." : "信息已进入生成阶段，可继续补充细节优化。"}</p>
                ) : (
                  <p>先发送至少两轮关键信息，系统会自动判定并触发生成。</p>
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
                    <p>达到完整度后，这里会展示完整简历预览。</p>
                  </div>
                ) : null}
                {result.kind === "error" ? <p className="resume-result-error">{result.message}</p> : null}
                <p className="resume-craft-build-mark">build: {FRONTEND_BUILD_VERSION}</p>

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
                      <button type="button" className="ghost-btn" onClick={exportHtml}>
                        导出 HTML
                      </button>
                      <button type="button" className="ghost-btn" onClick={exportPdf}>
                        导出 PDF
                      </button>
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
