export function ByokRiskPage() {
  return (
    <section className="surface legal-page">
      <h2>BYOK 风险提示</h2>
      <p>自带 API Key 模式下，请妥善管理你自己的密钥与额度。</p>
      <p>建议使用专用子密钥、额度限制与定期轮换策略。</p>
      <p>密钥仅在当前浏览器本地保存，清理缓存会导致设置丢失。</p>
    </section>
  );
}
