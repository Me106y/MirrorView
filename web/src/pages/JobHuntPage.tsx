import { useModelSettings } from "../context/ModelSettingsContext";
import { useCareerFeatureGuard } from "../components/CareerFeatureGuard";

export function JobHuntPage() {
  const { settings } = useModelSettings();
  const featureGuard = useCareerFeatureGuard(settings, "岗位搜索");

  return (
    <>
      {featureGuard.overlay}
      <section className="surface single-panel">
        <h2>Job Hunt (Phase B)</h2>
        <p>本页面已保留独立路由，Week 1 仅提供上线占位。</p>
        <p>下一阶段将接入异步任务提交、轮询结果、实时数据源与授权模式。</p>
      </section>
    </>
  );
}
