import type { FindingWithPost, Status } from "@/api/types";
import { Icon } from "@/components/Icon";
import { useSetStatus } from "@/hooks/useFinding";
import { pl } from "@/i18n/pl";
import { useToasts } from "@/state/toastContext";

/** "To nie naruszenie" / "Potwierdź naruszenie" buttons (toggle the analyst status). */
export function Decision({ finding }: { finding: FindingWithPost }) {
  const mutation = useSetStatus(finding.id);
  const toasts = useToasts();
  const set = (status: Status) =>
    mutation.mutate(status, {
      onSuccess: () =>
        toasts.show({
          key: "status",
          tone: "success",
          title: pl.finding.statusSaved,
          text: pl.statuses[status],
        }),
      onError: () => toasts.show({ key: "status", tone: "danger", title: pl.finding.statusError }),
    });
  const confirmed = finding.status === "confirmed";
  const dismissed = finding.status === "dismissed";
  return (
    <div className="detail-head__actions">
      <button
        type="button"
        className="btn btn--outline btn--pad20"
        aria-pressed={dismissed}
        disabled={mutation.isPending}
        onClick={() => set(dismissed ? "in_review" : "dismissed")}
      >
        {dismissed && <Icon name="check" size={16} color="#15803d" />}
        {dismissed ? pl.finding.dismissed : pl.finding.dismiss}
      </button>
      <button
        type="button"
        className="btn btn--danger btn--pad20"
        aria-pressed={confirmed}
        disabled={mutation.isPending}
        onClick={() => set(confirmed ? "in_review" : "confirmed")}
      >
        {confirmed && <Icon name="check" size={16} color="#ffffff" />}
        {confirmed ? pl.finding.confirmed : pl.finding.confirm}
      </button>
    </div>
  );
}
