import { DragEvent, FormEvent, KeyboardEvent, SyntheticEvent, useMemo, useRef, useState } from "react";
import { callCareerforgeSkillMultipart } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";

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
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const canSubmit = Boolean(targetRole.trim() && jdText.trim() && resumeFile) && !loading;

  const canUseReportActions = useMemo(
    () => result.kind === "report" && Boolean(result.reportHtml.trim()),
    [result]
  );

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
          (typeof payload.message === "string" && payload.message) ||
          "报告 HTML 生成失败，请重试。";
        setResult({ kind: "error", reportHtml: "", message });
      } else {
        setResult({ kind: "report", reportHtml, message: "" });
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
    } catch {
      setFrameHeight(980);
    }
  };

  return (
    <section className="resume-match-page">
      <div className="resume-match-layout">
        <form className="surface resume-match-form" onSubmit={onSubmit}>
          <header className="resume-match-form-head">
            <h2>简历匹配分析</h2>
            <p>上传简历与岗位 JD，AI 自动计算匹配度并给出优化建议。</p>
          </header>

          <label>目标岗位</label>
          <input value={targetRole} onChange={(e) => setTargetRole(e.target.value)} placeholder="例如：AI 产品经理" />

          <label>上传简历（仅支持 PDF）</label>
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

          <label>岗位 JD</label>
          <textarea
            rows={10}
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            placeholder="粘贴岗位描述，建议包含职责、要求与加分项"
          />

          <button className="primary-btn resume-submit-btn" disabled={!canSubmit}>
            <span aria-hidden="true">◍</span>
            {loading ? "分析中..." : "AI 生成匹配分析"}
          </button>
          {!canSubmit && !loading ? <p className="resume-form-tip">请填写完整信息后提交分析。</p> : null}
        </form>

        {result.kind !== "idle" ? (
          <section className="resume-match-result-inline" aria-live="polite">
            {result.kind === "report" ? (
              <>
                <header className="resume-result-head">
                  <h3>结果</h3>
                  <span>AI 匹配分析报告</span>
                </header>

                <div className="resume-result-body has-report">
                  <iframe
                    title="Resume Match HTML Report"
                    className="resume-report-frame"
                    srcDoc={result.reportHtml}
                    onLoad={onReportFrameLoad}
                    style={{ height: `${frameHeight}px` }}
                  />
                </div>

                <div className="resume-result-actions">
                  <button type="button" className="ghost-btn" onClick={exportReport} disabled={!canUseReportActions}>
                    导出 HTML
                  </button>
                </div>
              </>
            ) : (
              <p className="resume-result-error">{result.message}</p>
            )}
          </section>
        ) : null}
      </div>
    </section>
  );
}
