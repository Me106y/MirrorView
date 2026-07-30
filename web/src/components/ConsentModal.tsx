import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useConsent } from "../context/ConsentContext";

interface ConsentModalProps {
  open: boolean;
  onClose?: () => void;
}

export function ConsentModal({ open, onClose }: ConsentModalProps) {
  const { accepted, accept } = useConsent();
  const modalRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open || accepted) return;
    const modal = modalRef.current;
    if (!modal) return;

    const focusable = modal.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    first?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose?.();
        return;
      }
      if (e.key !== "Tab") return;
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last?.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, accepted, onClose]);

  if (!open || accepted) {
    return null;
  }

  const handleAccept = () => {
    accept();
    onClose?.();
  };

  return (
    <div className="consent-overlay">
      <div
        className="consent-card"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="consent-modal-title"
      >
        <h2 id="consent-modal-title">首次使用确认</h2>
        <p>
          继续使用前，请确认你已阅读并同意下列文件：
          <Link to="/legal/privacy">隐私政策</Link>、<Link to="/legal/terms">服务条款</Link>、
          <Link to="/legal/ai-disclaimer">AI 免责声明</Link>、<Link to="/legal/byok-risk">BYOK 风险提示</Link>。
        </p>
        <p>本产品首版采用匿名即用与本地同意记录策略，不做账号登录。</p>
        <button className="primary-btn" onClick={handleAccept}>
          我已阅读并同意
        </button>
      </div>
    </div>
  );
}
