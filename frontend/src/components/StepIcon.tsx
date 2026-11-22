import { Icon } from "@/components/Icon";
import type { StepState } from "@/lib/checkSteps";

/** 32 px circle for a progress step: check, spinner, empty ring, dash or cross. */
export function StepIcon({ state }: { state: StepState }) {
  return (
    <span className={`circle circle--${state}`}>
      {state === "done" && <Icon name="check" size={16} color="#15803d" />}
      {state === "run" && <Icon name="spinner" size={18} />}
      {state === "skip" && <Icon name="dash" size={16} />}
      {state === "fail" && <Icon name="cross" size={14} color="#b91c1c" />}
    </span>
  );
}
