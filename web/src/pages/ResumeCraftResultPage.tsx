import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  loadResumeCraftResult,
  saveResumeCraftResult,
  type ResumeCraftEditorState,
  type ResumeCraftResultArtifact,
} from "../lib/storage";

type ResultRouteState = { artifact?: unknown };

function normalizeEditorState(value: unknown): ResumeCraftEditorState | undefined {
  if (!value || typeof value !== "object") return undefined;
  const candidate = value as Partial<ResumeCraftEditorState>;
  if (!candidate.wizardState || typeof candidate.wizardState !== "object") return undefined;
  if (!candidate.messagesByStep || typeof candidate.messagesByStep !== "object") return undefined;
  return candidate as ResumeCraftEditorState;
}

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
    editorState: normalizeEditorState(candidate.editorState),
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
  const [frameHeight, setFrameHeight] = useState(900);
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
    const updateFrameHeight = () => {
      const document = previewFrameRef.current?.contentDocument;
      if (!document?.body) return;
      const height = Math.max(document.body.scrollHeight, document.documentElement?.scrollHeight || 0, 0);
      setFrameHeight(Math.max(height + 24, 900));
    };

    requestAnimationFrame(updateFrameHeight);
    window.setTimeout(updateFrameHeight, 80);
  };

  return (
    <section className="resume-craft-page resume-craft-result-page">
      <div className="resume-craft-layout">
        <section className="surface resume-craft-final-page">
          <header className="resume-craft-final-head">
            <div>
              <h2>简历已生成</h2>
              <p>HTML 预览和 PDF 文件已经准备完成。</p>
            </div>
            <div className="resume-craft-final-head-actions">
              <NavLink to="/resume-craft" state={{ resumeCraftStep: 5, editorState: artifact.editorState }} className="ghost-btn resume-craft-result-action-btn resume-craft-result-back-btn">
                上一步
              </NavLink>
              <button type="button" className="primary-btn resume-craft-export-html-btn" onClick={exportHtml}>导出 HTML</button>
              <button type="button" className="ghost-btn resume-craft-result-action-btn" onClick={exportPdf}>导出 PDF</button>
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
