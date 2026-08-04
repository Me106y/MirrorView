import { useEffect, useRef } from "react";
import { useConsent } from "../context/ConsentContext";

interface ConsentModalProps {
  open: boolean;
  onClose?: () => void;
  onAccept?: () => void;
}

export function ConsentModal({ open, onClose, onAccept }: ConsentModalProps) {
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
    onAccept?.();
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
          本产品涉及 AI 生成内容与 BYOK（自带密钥）使用。使用前请阅读隐私政策、服务条款、AI 免责声明、BYOK 风险提示。
        </p>
        <button className="primary-btn" onClick={handleAccept}>
          我已阅读并同意
        </button>
      </div>
    </div>
  );
}
