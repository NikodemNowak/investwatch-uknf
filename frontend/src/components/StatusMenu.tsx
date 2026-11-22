import { Link } from "react-router-dom";
import type { FindingWithPost, Status } from "@/api/types";
import { Dropdown } from "@/components/Dropdown";
import { Icon } from "@/components/Icon";
import { useSetStatus } from "@/hooks/useFinding";
import { pl } from "@/i18n/pl";
import { STATUSES } from "@/lib/enums";
import { useToasts } from "@/state/toastContext";

/** "⋯" menu of a list row: set the analyst status without opening the finding. */
export function StatusMenu({ finding }: { finding: FindingWithPost }) {
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
  return (
    <Dropdown
      align="right"
      buttonClassName="icon-btn row-menu"
      ariaLabel={pl.review.statusMenu}
      testId="row-status-menu"
      label={<Icon name="more" size={18} />}
    >
      {(close) => (
        <div className="menu" role="menu" aria-label={pl.review.statusMenuTitle}>
          <div className="menu__title">{pl.review.statusMenuTitle}</div>
          {STATUSES.map((status) => (
            <button
              key={status}
              type="button"
              role="menuitemradio"
              aria-checked={finding.status === status}
              className="menu__item"
              disabled={mutation.isPending}
              onClick={() => {
                if (status !== finding.status) set(status);
                close();
              }}
            >
              <span className="menu__check">
                {finding.status === status && <Icon name="check" size={14} />}
              </span>
              <span className="menu__text">{pl.review.statusOptions[status]}</span>
            </button>
          ))}
          <div className="menu__sep" />
          <Link to={`/zgloszenia/${finding.id}`} role="menuitem" className="menu__item">
            <span className="menu__check" />
            <span className="menu__text">{pl.review.openFinding}</span>
          </Link>
        </div>
      )}
    </Dropdown>
  );
}
