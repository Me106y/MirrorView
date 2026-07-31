import { DragEvent, FormEvent, KeyboardEvent, SyntheticEvent, useEffect, useMemo, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { callCareerforgeSkillMultipart } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";
import { gsap } from "gsap";

type ResultState = {
  kind: "idle" | "report" | "error";
  reportHtml: string;
  message: string;
};

function isPdfFile(file: File) {
  const byName = file.name.toLowerCase().endsWith(".pdf");
  const byType = file.type === "application/pdf";
  return byName || byType;
}

export function ResumeMatchPage() {
  const { settings } = useModelSettings();
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [jdText, setJdText] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [result, setResult] = useState<ResultState>({ kind: "idle", reportHtml: "", message: "" });
  const [reportName, setReportName] = useState("resume-match-report.html");
  const [uploadHint, setUploadHint] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [frameHeight, setFrameHeight] = useState(980);
  const [showReport, setShowReport] = useState(false);
  const [showNoModelWarning, setShowNoModelWarning] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const reportFrameRef = useRef<HTMLIFrameElement>(null);
  const warningRef = useRef<HTMLDivElement>(null);

  const canSubmit = Boolean(targetRole.trim() && jdText.trim() && resumeFile) && !loading;

  const canUseReportActions = useMemo(
    () => result.kind === "report" && Boolean(result.reportHtml.trim()),
    [result]
  );

  useEffect(() => {
    if (showNoModelWarning && warningRef.current) {
      gsap.fromTo(warningRef.current,
        { x: -8 },
        { x: 0, duration: 0.5, ease: 'elastic.out(1, 0.3)', yoyo: true, repeat: 3 }
      );
    }
  }, [showNoModelWarning]);

  const setResume = (file: File | null) => {
    if (!file) {
      setResumeFile(null);
      setUploadHint("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }
    if (!isPdfFile(file)) {
      setResumeFile(null);
      setUploadHint("仅支持 PDF 文件。");
      return;
    }
    setResumeFile(file);
    setUploadHint("");
  };

  const onDropResume = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0] ?? null;
    setResume(file);
  };

  const onDropzoneKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInputRef.current?.click();
    }
  };

  const hasApiKey = settings.apiKey.trim().length > 0;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!resumeFile) {
      setUploadHint("请先上传 PDF 简历文件。");
      return;
    }

    if (!isPdfFile(resumeFile)) {
      setUploadHint("仅支持 PDF 文件。");
      return;
    }

    if (!hasApiKey) {
      setShowNoModelWarning(true);
      return;
    }

    setUploadHint("");
    setLoading(true);
    setResult({ kind: "idle", reportHtml: "", message: "" });
    try {
      const resp = await callCareerforgeSkillMultipart(
        settings,
        "/careerforge/resume-match",
        {
          jd_text: jdText,
          target_role: targetRole
        },
        {
          resume: resumeFile
        }
      );
      const reportHtml =
        (typeof (resp as Record<string, unknown>).report_html === "string" &&
          ((resp as Record<string, unknown>).report_html as string)) ||
        "";
      const nextReportName =
        (typeof (resp as Record<string, unknown>).report_name === "string" &&
          ((resp as Record<string, unknown>).report_name as string)) ||
        "resume-match-report.html";
      setReportName(nextReportName);

      if (!reportHtml.trim()) {
        const payload = (resp.result ?? resp) as Record<string, unknown>;
        const message =
          (typeof payload.error === "string" && payload.error) ||
          (typeof payload.message === "string" && payload.message) ||
          "分析失败，请检查模型配置后重试。";
        setResult({ kind: "error", reportHtml: "", message });
      } else {
        setResult({ kind: "report", reportHtml, message: "" });
        setShowReport(true);
      }
    } catch (err) {
      setResult({ kind: "error", reportHtml: "", message: (err as Error).message });
    } finally {
      setLoading(false);
    }
  };

  const exportReport = () => {
    if (!canUseReportActions) {
      return;
    }
    const blob = new Blob([result.reportHtml], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = reportName || "resume-match-report.html";
    link.click();
    URL.revokeObjectURL(url);
  };

  function exportPdf() {
    const frame = reportFrameRef.current;
    if (!frame?.contentWindow) return;
    frame.contentWindow.focus();
    frame.contentWindow.print();
  }

  const onReportFrameLoad = (e: SyntheticEvent<HTMLIFrameElement>) => {
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

      // Inject styles for internal navigation links
      const style = doc.createElement('style');
      style.textContent = `
        a[href*="resume-craft"], a[href*="cover-letter"], a[href*="mock-interview"], a[href*="resume-match"] {
          color: #4f7ba3;
          text-decoration: underline;
          cursor: pointer;
          transition: color 150ms;
        }
        a[href*="resume-craft"]:hover, a[href*="cover-letter"]:hover, a[href*="mock-interview"]:hover, a[href*="resume-match"]:hover {
          color: #2d5a7b;
        }
      `;
      doc.head.appendChild(style);

      // Inject click handler for internal navigation
      doc.addEventListener('click', (ev: MouseEvent) => {
        const target = ev.target as HTMLElement;
        const link = target.closest('a');
        if (!link) return;
        const href = link.getAttribute('href');
        if (!href) return;

        const internalRoutes: Record<string, string> = {
          'resume-craft': '/resume-craft',
          'cover-letter': '/cover-letter',
          'mock-interview': '/mock-interview',
          'resume-match': '/resume-match',
        };

        for (const [key, path] of Object.entries(internalRoutes)) {
          if (href.includes(key)) {
            ev.preventDefault();
            window.location.href = path;
            return;
          }
        }
      });
    } catch {
      setFrameHeight(980);
    }
  };

  const openSettingsFromWarning = () => {
    setShowNoModelWarning(false);
    window.dispatchEvent(new CustomEvent("open-settings"));
  };

  if (showReport && result.kind === "report") {
    return (
      <section className="resume-match-report-page">
        <NavLink to="/" className="back-home-btn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7"/>
          </svg>
          返回
        </NavLink>
        <div className="resume-match-report-head">
          <h2>匹配分析报告</h2>
          <div className="resume-match-report-actions">
            <button className="report-ghost-btn" onClick={() => setShowReport(false)}>
              ← 返回修改
            </button>
            <button className="report-outline-btn" onClick={exportReport} title="导出 HTML">
              <svg className="export-btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              导出 HTML
            </button>
            <button className="export-btn export-btn--pdf" onClick={exportPdf} title="请在打印对话框中选择'另存为 PDF'">
              <svg className="export-btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              导出 PDF
            </button>
          </div>
        </div>
        <div className="resume-match-report-body">
          <iframe
            ref={reportFrameRef}
            className="resume-report-frame"
            srcDoc={result.reportHtml}
            onLoad={onReportFrameLoad}
            title="匹配分析报告"
            style={{ height: frameHeight + "px" }}
          />
        </div>
      </section>
    );
  }

  return (
    <section className="resume-match-page">
      <NavLink to="/" className="back-home-btn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        返回
      </NavLink>
      <div className="resume-match-layout">
        <form className="surface resume-match-form" onSubmit={onSubmit}>
          <header className="resume-match-form-head">
            <h2>简历匹配分析</h2>
            <p>上传简历与岗位 JD，AI 自动计算匹配度并给出优化建议。</p>
          </header>

          <label htmlFor="rm-role">目标岗位</label>
          <input id="rm-role" value={targetRole} onChange={(e) => setTargetRole(e.target.value)} placeholder={'填写你正在申请的岗位名称，如"AI 产品经理"'} />

          <label htmlFor="rm-resume">上传简历（仅支持 PDF）</label>
          <div
            className={`resume-dropzone${isDragOver ? " is-dragover" : ""}${resumeFile ? " has-file" : ""}`}
            role="button"
            tabIndex={0}
            aria-label="上传 PDF 简历"
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={onDropzoneKeyDown}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragOver(true);
            }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={onDropResume}
          >
            <input
              ref={fileInputRef}
              className="resume-file-input"
              type="file"
              accept=".pdf,application/pdf"
              onChange={(e) => setResume(e.target.files?.[0] ?? null)}
            />
            <span className="resume-dropzone-icon" aria-hidden="true">
              ↑
            </span>
            <p className="resume-dropzone-title">
              {resumeFile ? "PDF 简历已上传" : "点击或拖拽 PDF 简历到此处上传"}
            </p>
            <p className="resume-dropzone-sub">{resumeFile ? resumeFile.name : "仅支持 .pdf 文件"}</p>
            {resumeFile ? (
              <button
                type="button"
                className="resume-file-clear"
                onClick={(e) => {
                  e.stopPropagation();
                  setResume(null);
                }}
              >
                删除文件
              </button>
            ) : null}
          </div>

          {uploadHint ? <p className="resume-form-error">{uploadHint}</p> : null}
          {!uploadHint && resumeFile ? <p className="resume-file-ok">✓ PDF 文件就绪</p> : null}

          <label htmlFor="rm-jd">岗位 JD</label>
          <textarea
            id="rm-jd"
            rows={5}
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            placeholder={"岗位职责：\n- 负责 AI 产品的需求分析与技术落地\n\n任职要求：\n- 3年以上后端开发经验\n- 熟悉 Python/TypeScript\n\n加分项：\n- 有 LLM/RAG 项目经验"}
          />

          <button className="primary-btn resume-submit-btn" disabled={!canSubmit}>
            <span aria-hidden="true">◍</span>
            {loading ? "分析中..." : "AI 生成匹配分析"}
          </button>
          {!canSubmit && !loading ? <p className="resume-form-tip">请填写完整信息后提交分析。</p> : null}
        </form>

        {result.kind === "error" ? (
          <section className="resume-match-result-inline" aria-live="polite">
            <div className="resume-match-result-error">
              <p className="resume-result-error">{result.message}</p>
              <button type="button" className="ghost-btn" onClick={() => void onSubmit({ preventDefault: () => {} } as FormEvent)}>重试</button>
            </div>
          </section>
        ) : null}
      </div>

      {showNoModelWarning && (
        <div className="no-model-warning-overlay" onClick={() => setShowNoModelWarning(false)}>
          <div className="no-model-warning" ref={warningRef} onClick={(e) => e.stopPropagation()}>
            <h3>请先配置模型</h3>
            <p>
              使用 AI 分析功能需要填入你自己的 API 密钥。
              点击右上角「模型设置」按钮进行配置，密钥仅保存在浏览器本地。
            </p>
            <div className="no-model-warning-actions">
              <button className="report-outline-btn" onClick={() => setShowNoModelWarning(false)}>
                知道了
              </button>
              <button className="export-btn export-btn--pdf" onClick={openSettingsFromWarning}>
                打开设置
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
