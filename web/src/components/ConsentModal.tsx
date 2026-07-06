import { Link } from "react-router-dom";
import { useConsent } from "../context/ConsentContext";

export function ConsentModal() {
  const { accepted, accept } = useConsent();

  if (accepted) {
    return null;
  }

  return (
    <div className="consent-overlay">
      <div className="consent-card">
        <h2>首次使用确认</h2>
        <p>
          继续使用前，请确认你已阅读并同意下列文件：
          <Link to="/legal/privacy">隐私政策</Link>、<Link to="/legal/terms">服务条款</Link>、
          <Link to="/legal/ai-disclaimer">AI 免责声明</Link>、<Link to="/legal/byok-risk">BYOK 风险提示</Link>。
        </p>
        <p>本产品首版采用匿名即用与本地同意记录策略，不做账号登录。</p>
        <button className="primary-btn" onClick={accept}>
          我已阅读并同意
        </button>
      </div>
    </div>
  );
}
