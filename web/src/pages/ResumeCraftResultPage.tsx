import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  loadResumeCraftResult,
  saveResumeCraftResult,
  type ResumeCraftResultArtifact,
} from "../lib/storage";

const TEMPLATE_LABELS: Record<string, string> = {
  "01": "杂志编辑风",
  "02": "极简主义",
  "03": "深蓝双栏",
  "04": "深灰左栏",
  "05": "深色头部",
  "06": "清新青色",
  "07": "优雅对称",
};

type ResultRouteState = { artifact?: unknown };

function normalizeArtifact(value: unknown): ResumeCraftResultArtifact | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Partial<ResumeCraftResultArtifact>;
  if (typeof candidate.reportHtml !== "string" || !candidate.reportHtml.trim()) return null;
  return {
    reportHtml: candidate.reportHtml,
    reportName: typeof candidate.reportName === "string" && candidate.reportName.trim() ? candidate.reportName : "resume-craft-report.html",
    reportPdfName: typeof candidate.reportPdfName === "string" && candidate.reportPdfName.trim() ? candidate.reportPdfName : "resume-craft-report.pdf",
    reportPdfBase64: typeof candidate.reportPdfBase64 === "string" ? candidate.reportPdfBase64 : "",
    templateCode: typeof candidate.templateCode === "string" ? candidate.templateCode : "02",
    language: typeof candidate.language === "string" ? candidate.language : "zh",
  };
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function ResumeCraftResultPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const previewFrameRef = useRef<HTMLIFrameElement | null>(null);
  const [frameHeight, setFrameHeight] = useState(980);
  const [artifact] = useState<ResumeCraftResultArtifact | null>(() => {
    const routeArtifact = normalizeArtifact((location.state as ResultRouteState | null)?.artifact);
    return routeArtifact ?? loadResumeCraftResult();
  });

  useEffect(() => {
    if (artifact) {
      saveResumeCraftResult(artifact);
      return;
    }
    navigate("/resume-craft", { replace: true });
  }, [artifact, navigate]);

  if (!artifact) return null;

  const exportHtml = () => {
    downloadBlob(new Blob([artifact.reportHtml], { type: "text/html;charset=utf-8" }), artifact.reportName);
  };

  const exportPdf = () => {
    if (artifact.reportPdfBase64) {
      try {
        const binary = window.atob(artifact.reportPdfBase64.replace(/\s+/g, ""));
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) {
          bytes[index] = binary.charCodeAt(index);
        }
        downloadBlob(new Blob([bytes], { type: "application/pdf" }), artifact.reportPdfName);
        return;
      } catch {
        // Fall through to browser printing when the PDF payload is unavailable.
      }
    }

    const previewWindow = previewFrameRef.current?.contentWindow;
    if (!previewWindow) return;
    previewWindow.focus();
    previewWindow.print();
  };

  const onPreviewLoad = () => {
    const document = previewFrameRef.current?.contentDocument;
    if (!document?.body) return;
    const height = Math.max(document.body.scrollHeight, document.documentElement?.scrollHeight || 0, 900);
    setFrameHeight(Math.min(Math.max(height + 16, 900), 3400));
  };

  return (
    <section className="resume-craft-page resume-craft-result-page">
      <NavLink to="/resume-craft" className="back-home-btn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
        返回简历制作
      </NavLink>
      <div className="resume-craft-layout">
        <section className="surface resume-craft-final-page">
          <header className="resume-craft-final-head">
            <div>
              <h2>简历已生成</h2>
              <p>HTML 预览和 PDF 文件已经准备完成。</p>
            </div>
            <div className="resume-craft-final-head-actions">
              <span className="resume-craft-result-meta">模板：{TEMPLATE_LABELS[artifact.templateCode] || "简历模板"}</span>
              <span className="resume-craft-result-meta">语言：{artifact.language === "en" ? "英文" : artifact.language === "both" ? "中英文双版" : "中文"}</span>
              <button type="button" className="ghost-btn" onClick={exportHtml}>导出 HTML</button>
              <button type="button" className="primary-btn resume-craft-regenerate-btn" onClick={exportPdf}>导出 PDF</button>
            </div>
          </header>
          <iframe
            ref={previewFrameRef}
            title="生成的简历预览"
            className="resume-craft-preview-frame resume-craft-final-frame"
            srcDoc={artifact.reportHtml}
            onLoad={onPreviewLoad}
            style={{ height: `${frameHeight}px` }}
          />
        </section>
      </div>
    </section>
  );
}
