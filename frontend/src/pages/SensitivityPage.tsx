import { useState } from "react";
import type { ModuleId } from "@/api/types";
import { LoadState } from "@/components/LoadState";
import { useCalibration } from "@/hooks/useCalibration";
import { pl } from "@/i18n/pl";
import { MODULES } from "@/lib/enums";
import { Calibrator } from "@/components/Calibrator";

/** "Czułość wykrywania": pick the alert threshold per module from labelled outcomes. */
export function SensitivityPage() {
  const [module, setModule] = useState<ModuleId>("m2_risk_disclosure");
  const query = useCalibration(module);
  const report = query.data;
  const enough = report ? report.n_labels >= Math.max(1, report.min_labels ?? 1) : false;

  return (
    <div className="page">
      <div>
        <h1 className="title">{pl.sensitivity.title}</h1>
        <p className="lead lead--wide">
          {report && enough ? pl.sensitivity.lead(report.n_labels) : " "}
        </p>
      </div>
      <div role="tablist" className="seg">
        {MODULES.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={module === id}
            className="seg__tab"
            onClick={() => setModule(id)}
          >
            {pl.sensitivityTabs[id]}
          </button>
        ))}
      </div>
      {query.isError ? (
        <LoadState error onRetry={() => void query.refetch()} />
      ) : !report ? (
        <LoadState />
      ) : !enough ? (
        <LoadState empty={pl.sensitivity.noLabels} />
      ) : (
        <Calibrator key={`${module}:${report.current_threshold}`} report={report} />
      )}
    </div>
  );
}
