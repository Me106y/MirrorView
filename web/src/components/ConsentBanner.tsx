import { useState } from "react";
import { Link } from "react-router-dom";
import { useConsent } from "../context/ConsentContext";

const BANNER_DISMISSED_KEY = "mirrorview:web:consent:banner:dismissed";

export function ConsentBanner() {
  const { accepted, accept } = useConsent();
  const [dismissed, setDismissed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(BANNER_DISMISSED_KEY) === "true";
    } catch {
      return false;
    }
  });

  if (accepted || dismissed) {
    return null;
  }

  const handleDismiss = () => {
    try {
      localStorage.setItem(BANNER_DISMISSED_KEY, "true");
    } catch {
      // ignore storage errors
    }
    setDismissed(true);
  };

  return (
    <div className="consent-banner">
      <div className="consent-banner-content">
        <span className="consent-banner-icon" aria-hidden="true">!</span>
        <div className="consent-banner-text">
          <p>
            本产品涉及 AI 生成内容与 BYOK（自带密钥）使用。使用前请阅读
            <Link to="/legal/privacy">隐私政策</Link>、<Link to="/legal/terms">服务条款</Link>、
            <Link to="/legal/ai-disclaimer">AI 免责声明</Link>、<Link to="/legal/byok-risk">BYOK 风险提示</Link>。
          </p>
        </div>
      </div>
      <div className="consent-banner-actions">
        <button type="button" className="ghost-btn" onClick={handleDismiss}>
          稍后提醒
        </button>
        <button type="button" className="primary-btn" onClick={accept}>
          我已阅读并同意
        </button>
      </div>
    </div>
  );
}
